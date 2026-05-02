# 直播间弹幕查岗系统 — 项目说明文档

把抖音直播间的实时弹幕抓下来，识别出"查询岗位"意图的弹幕并结构化，最终以 JSONL 行流的形式写到磁盘，供下游消费。

---

## 1. 整体架构

```
                     +---------------------------+
                     |  抖音直播间 WebSocket 服务  |
                     +-------------+-------------+
                                   | (wss + protobuf + gzip)
                                   v
+---------------------------------------------------+
|  liveMan.py / DouyinLiveWebFetcher                |
|  - 拿 ttwid / room_id                             |
|  - 用 sign.js 计算 signature                       |
|  - 建 WebSocket 长连接 + 心跳                      |
|  - 收消息 → 解 protobuf → 分发到各 _parseXxxMsg     |
+--------------------+------------------------------+
                     |
              聊天消息(_parseChatMsg)
                     |
        +------------+--------------+
        |                           |
        v                           v
  danmu/{ts}.txt               queue.Queue
  (人类可读原始日志)                 |
                                    v
                  +-----------------+----------------+
                  |  _parserWorker (后台 daemon 线程)  |
                  +-----------------+----------------+
                                    |
                                    v
              +---------------------+----------------------+
              |  DanmakuParser.parse()                     |
              |    第 1 层：噪声过滤                          |
              |    第 2 层：规则解析（关键词 + 正则）           |
              |    第 3 层：LLM 兜底（可选）                  |
              |    末层：去重缓存（滑动窗口）                   |
              +---------------------+----------------------+
                                    |
                          命中(JobQuery) | 未命中(None)
                                    |
                                    v
                          output/{live_id}_{ts}.jsonl
                                    |
                                    v
                          下游程序 (tail -f)
```

---

## 2. 弹幕提取（liveMan.py）

弹幕提取部分基于上游开源项目 [saermart/DouyinLiveWebFetcher](https://github.com/saermart/DouyinLiveWebFetcher)，本质是**模拟抖音网页版客户端**绕过签名校验，连上抖音的直播消息推送服务。

### 2.1 抓取流程

| 步骤 | 操作 |
|---|---|
| 1. 拿访客身份 | 访问 `https://live.douyin.com/`，从响应 Cookie 取出 `ttwid` |
| 2. 拿真实 room_id | 访问 `https://live.douyin.com/{live_id}`，从 HTML 正则匹配出内部 `room_id` |
| 3. 构造 wss URL | 拼接几十个查询参数（room_id、设备、cursor 等） |
| 4. 计算 signature | 取 13 个关键参数 → MD5 → 用 `mini_racer` 跑 `sign.js` 中的 `get_sign()` 得到签名 |
| 5. 建立 WebSocket | 用 `websocket-client` 连接，请求头带 ttwid Cookie |
| 6. 心跳保活 | 守护线程每 5 秒发一次 PING（protobuf 序列化的 `PushFrame(payload_type='hb')`） |
| 7. 收消息 + 回 ack | 每条消息按 `PushFrame → gzip 解压 → Response` 三层解码；如果服务端要求 `need_ack`，把 `internal_ext` 包回 ack 帧发回去 |
| 8. 分发处理 | `Response.messages_list` 中的每条消息按 `method` 字段（如 `WebcastChatMessage`）查表分发到对应 `_parseXxxMsg` 方法 |

### 2.2 支持的消息类型

`_wsOnMessage` 共注册了 13 种消息分发：

| method | 处理函数 | 中文 |
|---|---|---|
| `WebcastChatMessage` | `_parseChatMsg` | 聊天弹幕 |
| `WebcastGiftMessage` | `_parseGiftMsg` | 礼物 |
| `WebcastLikeMessage` | `_parseLikeMsg` | 点赞 |
| `WebcastMemberMessage` | `_parseMemberMsg` | 进场 |
| `WebcastSocialMessage` | `_parseSocialMsg` | 关注 |
| `WebcastRoomUserSeqMessage` | `_parseRoomUserSeqMsg` | 在线人数统计 |
| `WebcastFansclubMessage` | `_parseFansclubMsg` | 粉丝团 |
| `WebcastEmojiChatMessage` | `_parseEmojiChatMsg` | 表情包弹幕 |
| `WebcastRoomStatsMessage` | `_parseRoomStatsMsg` | 直播间统计 |
| `WebcastRoomRankMessage` | `_parseRankMsg` | 排行榜 |
| `WebcastRoomMessage` | `_parseRoomMsg` | 直播间信息 |
| `WebcastControlMessage` | `_parseControlMsg` | 直播间状态（结束等） |
| `WebcastRoomStreamAdaptationMessage` | `_parseRoomStreamAdaptationMsg` | 流配置 |

> **注**：本项目下游解析**只针对聊天弹幕**（`_parseChatMsg`）——其余消息保留原始打印输出，但不进入解析队列。礼物/点赞/进场等消息要么没文本，要么文本不是用户输入查询，进解析层会被噪声过滤丢弃，没必要消耗算力。

### 2.3 关键技术点

- **Protobuf**：`protobuf/douyin.proto` 是逆向出的 schema，已用 `betterproto` 编译为 `protobuf/douyin.py`，无需重装 protoc
- **mini_racer**：在 Python 进程内跑 V8 执行 `sign.js`，比起 PyExecJS 起 Node 子进程快几十倍
- **gzip + WebSocket 二进制**：直播这种高吞吐场景的标配
- **整个项目最脆弱的环节是签名脚本**：`sign.js` 是抖音前端逆向出的混淆代码，一旦抖音改前端签名算法，就要重新逆向更新此文件

---

## 3. 解析策略概览（DanmakuParser）

弹幕从 `_parseChatMsg` 投递到队列，后台 worker 调用 `DanmakuParser.parse()`，走三层漏斗。

### 3.1 三层架构

```
弹幕文本
   |
   v
[第 1 层] 噪声过滤  ----> 丢弃
   |
   v
[第 2 层] 规则解析  ----> 命中 JobQuery
   |
   v
[第 3 层] LLM 兜底  ----> 命中 JobQuery / 仍 None
   |
   v
[末层] 去重缓存  ----> 通过 / 丢弃
```

### 3.2 第 1 层：噪声过滤

直接丢弃明显与查岗无关的弹幕。约能过滤掉 **70-80%** 的直播间弹幕。

| 规则 | 示例 |
|---|---|
| 长度 < 2 或 > 100 字符 | "1"、超长刷屏 |
| 噪声关键词精确匹配 | 哈哈、666、牛、签到、打卡、关注、点赞… |
| 纯语气词（`^[哈嘿嗯啊噢哦嘻呵]{2,}$`） | "哈哈哈哈" |
| 纯数字（`^[0-9]{1,6}$`） | "888" |
| 纯标点 / 纯 emoji | "！！！" / "😂🔥" |

### 3.3 第 2 层：规则解析

对单条弹幕做**全局多字段扫描**。每个字段独立提取，互不依赖。

#### 字段提取方式

| 字段 | 必填 | 提取方式 | 示例 |
|---|---|---|---|
| **岗位关键词** | ✅ | 词库匹配（按词长降序，避免子串截断） | 产品经理、Java、前端 |
| 城市 | ❌ | 35 个主要城市词库 | 北京、深圳 |
| 行业 | ❌ | 40+ 行业词库 | 互联网、金融 |
| 薪资 | ❌ | 6 套正则（`数字k-数字k` / `数字万` / `面议` 等） | 15k-25k、1万-2万、面议 |
| 工作年限 | ❌ | 6 套正则（`数字-数字年` / `数字年以上` / `应届`等） | 1-3年、5年以上、应届 |
| 学历 | ❌ | 关键词 + 归一化映射 | 985 → 985/211 |

#### 命中两条路径

**路径 A — 触发词 + 岗位关键词**

弹幕里包含 `查/找/搜/有没有/招不招/岗位/职位` 等触发词时，从剩余文本提取岗位关键词。

**路径 B — 无触发词的纯实体组合**

去掉所有已识别实体（城市、薪资、经验、学历、行业、岗位）和修饰词后剩余 ≤ 10 字符即视为查询。这样 `杭州Java 1-3年 985` 这类无触发词但意图明确的弹幕也能命中。

### 3.4 第 3 层：LLM 兜底（可选）

只有规则层 miss 才会调用 LLM，用于处理口语化、模糊表达。

- 推荐用轻量模型（`gpt-4o-mini`、`deepseek-chat` 等）
- `temperature=0` 保证输出稳定
- 默认超时 3 秒，超时直接放弃该条
- 严格要求只输出 JSON

#### 配置位置

`弹幕分析脚本/danmaku_parser.py:134`

```python
LLM_CONFIG = {
    "base_url": "https://api.example.com/v1",   # ← 你的 API 地址
    "api_key":  "sk-your-api-key",               # ← 你的真实 key
    "model":    "gpt-4o-mini",                   # ← 模型名
    "timeout":  3,
}
```

#### 启用方式

```python
# main.py
room = DouyinLiveWebFetcher(live_id, enable_llm=True)
```

---

## 4. 去重机制

**目的**：多人同时刷"查北京产品经理"时，下游不应该重复执行同一个搜索。

### 4.1 算法

- 滑动窗口 TTL 默认 **60 秒**（构造时 `dedup_ttl` 参数可改）
- 去重键 = **全部已提取字段** 拼接后做 MD5：

```
key = md5( keyword | city | salary | experience | education | graduate_time | industry )
```

- 窗口内键重复 → 丢弃，不输出到 JSONL
- 后台清理过期条目

### 4.2 全字段去重的意义

```
弹幕 A: "查北京产品经理"           → key1（keyword=产品经理, city=北京）
弹幕 B: "查北京产品经理 15k-25k"   → key2（keyword=产品经理, city=北京, salary=15k-25k）
```

A 与 B 不会被相互去重——因为薪资字段不同，**视为两个不同查询**，下游会分别执行。这避免了"查询条件越细的反而被先达者覆盖"的问题。

### 4.3 配置

```python
# main.py
room = DouyinLiveWebFetcher(live_id, dedup_ttl=120)  # 改成 2 分钟窗口
```

---

## 5. 下游接口

### 5.1 输出文件

| 项 | 值 |
|---|---|
| 路径 | `output/{live_id}_{时间戳}.jsonl` |
| 格式 | JSON Lines（每行一个 JSON 对象） |
| 编码 | UTF-8 |
| 写入策略 | 行缓冲（`buffering=1`），命中即立刻可见 |
| 轮转策略 | **每次启动新文件**，不复用旧文件 |

### 5.2 JSONL 字段定义

每行一个 JSON 对象，字段顺序固定：

| 字段 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `ts` | string | ✅ | 写入时间，格式 `YYYY-MM-DD HH:MM:SS` | "2026-04-27 10:39:12" |
| `live_id` | string | ✅ | 直播间 ID（URL 中的短号） | "59475730286" |
| `user_id` | string | ✅ | 抖音用户 ID | "1843748321" |
| `user_name` | string | ✅ | 用户昵称 | "张三" |
| `keyword` | string | ✅ | 岗位关键词 | "产品经理" |
| `city` | string 或 null | ❌ | 城市 | "北京" |
| `industry` | string 或 null | ❌ | 行业 | "互联网" |
| `salary` | string 或 null | ❌ | 薪资 | "15k-25k" |
| `experience` | string 或 null | ❌ | 工作年限 | "3年" |
| `education` | string 或 null | ❌ | 学历（已归一化） | "985/211" |
| `graduate_time` | string 或 null | ❌ | 毕业时间，`25`-`28` 届归一为 `2025`-`2028`，更早归一为 `往届` | "2026" |
| `source` | string | ✅ | 解析来源：`"rule"` 或 `"llm"` | "rule" |
| `raw_text` | string | ✅ | 原始弹幕文本 | "查北京产品经理 15k-25k" |
| `query_payload` | object | ✅ | 派生的下游搜索请求对象，结构见 5.3 | 见下例 |

#### 示例行

```json
{"ts":"2026-04-27 10:39:12","live_id":"59475730286","user_id":"1001","user_name":"Alice","keyword":"产品经理","city":"北京","industry":null,"salary":"15k-25k","experience":null,"education":null,"graduate_time":null,"source":"rule","raw_text":"查北京产品经理 15k-25k","query_payload":{"major":null,"education":null,"intention_job":["产品经理"],"intention_company":null,"intention_location":["北京"],"job_type":null,"graduate_time":null,"company_type":null,"is_unlimited_major":null,"order_by":null,"jobCategory":null,"timeType":null}}
```

### 5.3 `query_payload` 子字段定义

`query_payload` 是基于顶层抽取结果派生出来的"求职搜索请求"对象，字段集与
`小程序API提取岗位信息/aibz_job_search.search_jobs(filters, ...)` 的入参约定对齐，
可直接整体送入下游搜索接口；下游对未知/为空字段自行兜默认值。

| 字段 | 类型 | 来源映射 | 说明 |
|---|---|---|---|
| `intention_job` | [string] 或 null | `keyword` | 有值 → 单元素数组 `[keyword]`；空 → `null` |
| `intention_location` | [string] 或 null | `city` | 有值 → 单元素数组 `[city]`；空 → `null`（不补省份） |
| `education` | string 或 null | `education` | 直接复用顶层 `education`；`大专`、`专科`、`中专` 会归一为 `专科`；下游适配层会丢弃接口不识别的归一化值（如 `985/211`、`一本`） |
| `major` | null | — | 暂不抽取，恒为 `null` |
| `intention_company` | null | — | 暂不抽取 |
| `job_type` | null | — | 暂不抽取（如"全职"） |
| `graduate_time` | string 或 null | `graduate_time` | 直接复用顶层毕业时间，如 `"2026"` 或 `"往届"` |
| `company_type` | null | — | 暂不抽取 |
| `is_unlimited_major` | null | — | 暂不抽取 |
| `order_by` | null | — | 排序方式（`start_time`/`company_attraction`/`deadline`），由下游决定 |
| `jobCategory` | null | — | 岗位类型分类，由下游决定（注意：与顶层 `industry` 行业语义不等同，未做映射） |
| `timeType` | null | — | 今日最新/即将到期，由下游决定 |

> **设计说明**：顶层 13 字段是"弹幕事件 + 抽取结果"语义，含完整溯源信息（user_id、raw_text、source）；`query_payload` 是派生出的下游入参对象。两层分离的好处：调试和复测看顶层，对接下游搜索接口直接 `record["query_payload"]` 整体 POST 即可，schema 演进互不影响。
>
> **不输出的字段及原因**：
> - `position`：与 `intention_job` 语义重复，aibz 后端只识别 `intention_job`
> - `query_date`：aibz 后端源码无引用，不识别
> - `strategy`：仅推荐接口使用，搜索接口不识别
> - `query_str`：与 `intention_job` 同传时会让后端做"模糊+精确"双过滤，把结果集收窄甚至变空，从而让下游 `pick_first_job` 抛错；此场景下命中 JobQuery 时 keyword 必填，单走精确字段足够

### 5.4 下游消费方式

#### 方式 A：实时流式消费（推荐）

```bash
tail -F output/59475730286_*.jsonl | your-downstream-program
```

启动时一次给定文件名（用 `-F` 而非 `-f`，文件不存在时也会等待）。

#### 方式 B：Python 轮询

```python
import json, time
with open('output/59475730286_xxx.jsonl', 'r') as f:
    f.seek(0, 2)  # 跳到文件末尾
    while True:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue
        record = json.loads(line)
        handle(record)
```

#### 方式 C：定期批量读全量

适合非实时场景，每 N 秒读一次新增行。

### 5.5 消费时的契约

下游应当**只关心 JSONL 行**，不要对其他文件作假设：

| 文件 / 目录 | 用途 | 下游是否应该消费 |
|---|---|---|
| `output/{live_id}_{ts}.jsonl` | 结构化查岗结果 | ✅ 是 |
| `output/test_{ts}.jsonl` | `test_parser.py` 产生的测试输出 | ❌ 否（测试用） |
| `danmu/{live_id}_{ts}.txt` | 原始弹幕日志（人类可读） | ❌ 否（仅审计/调试） |

### 5.6 异常情况

| 情况 | 行为 |
|---|---|
| LLM 调用超时/网络错 | 该条弹幕跳过，不写入 JSONL；终端打印 `[LLM 解析异常]` |
| 解析中抛异常 | 该条跳过，终端打印 `[解析异常]`；不影响后续弹幕 |
| 写文件 IO 异常 | 该条跳过，终端打印 `[结构化输出写入异常]` |
| WebSocket 断连 | fetcher 主线程退出；后台 worker 通过 sentinel 优雅停止；文件 close |

---

## 6. 快速开始

### 6.1 启动正式抓取

```bash
cd /path/to/DouyinLiveWebFetcher
source venv/bin/activate

# 编辑 main.py 改 live_id
python main.py
```

`live_id` 是直播间 URL 路径上 `live.douyin.com/` 后面、`?` 之前那串数字。

### 6.2 启动交互式测试（不连真实直播间）

```bash
python test_parser.py              # 默认纯规则
python test_parser.py --llm        # 启用 LLM
python test_parser.py --no-output  # 仅终端展示，不写文件
```

进入 `弹幕> ` 提示符后手动输入文本即可。详见同目录 `test_parser.py` 文件头注释。

### 6.3 启用 LLM

1. 在 `弹幕分析脚本/danmaku_parser.py:134-139` 填入真实 API 配置
2. `main.py` 中 `DouyinLiveWebFetcher(live_id, enable_llm=True)`

---

## 7. 目录结构

```
DouyinLiveWebFetcher/
├── main.py                       # 程序入口
├── liveMan.py                    # 直播间抓取 + 队列调度 + worker（已集成解析）
├── ac_signature.py               # __ac_signature 反爬签名计算
├── a_bogus.js / sign.js / ...    # 抖音前端逆向出的签名 JS（mini_racer 执行）
├── protobuf/
│   ├── douyin.proto              # 直播消息 protobuf schema（逆向得到）
│   └── douyin.py                 # 已编译的 protobuf Python 类
├── 弹幕分析脚本/
│   ├── danmaku_parser.py         # 三层漏斗解析器（噪声 → 规则 → LLM）
│   └── 弹幕解析系统-筛选流程与规则说明.md
├── test_parser.py                # 交互式测试脚本
├── danmu/                        # 原始弹幕日志（人类可读 txt）
├── output/                       # JSONL 结构化输出（给下游用）
├── venv/                         # Python 虚拟环境
├── requirements.txt              # Python 依赖
├── PROJECT_OVERVIEW.md           # 本文件
├── MIGRATION.md                  # Mac → Mac 迁移指南
└── README.MD                     # 上游原始 README
```

---

## 8. 维护提醒

- **签名脚本失效**：抖音改前端签名算法时，WebSocket 连不上，需要从抖音 Web 重新逆向更新 `sign.js`
- **词库扩充**：如果发现规则层漏掉某些常见岗位/城市/行业，往 `danmaku_parser.py` 顶部的词库列表里加即可
- **LLM 命中模式沉淀为规则**：定期 review LLM 命中的弹幕，把高频模式提炼成规则，逐步降低 LLM 调用量
- **去重窗口调整**：直播间互动密度不同时，`dedup_ttl` 可按需要从 60 秒调整到 30~300 秒
