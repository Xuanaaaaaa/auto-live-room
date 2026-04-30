# 自动化直播间 × 小程序 UI 自动化控制 合并说明

本文档用于在新电脑上把两个项目放到同一目录后，指导 Claude Code 进行合并。

目标不是把两个项目简单拼在一起，而是让“小程序 UI 自动化控制模块”消费“自动化直播间弹幕解析模块”的结构化输出，通过共享文件驱动小程序搜索、点击岗位、浏览详情。

## 1. 两个模块的定位

### 1.1 自动化直播间项目

自动化直播间当前主链路是：

```text
抖音直播间弹幕
  -> 弹幕提取与解析
  -> 输出结构化 JSONL
  -> 岗位查询/语音生成/TTS 等下游模块
```

其中，本次合并最关心的是弹幕解析输出文件。

典型路径：

```text
弹幕提取/DouyinLiveWebFetcher/output/{live_id}_{timestamp}.jsonl
```

该文件是 JSON Lines 格式，一行一条结构化弹幕命中结果。每行通常包含：

```json
{
  "ts": "2026-04-27 10:39:12",
  "live_id": "59475730286",
  "user_id": "1001",
  "user_name": "Alice",
  "keyword": "产品经理",
  "city": "北京",
  "industry": null,
  "salary": "15k-25k",
  "experience": null,
  "education": "本科",
  "source": "rule",
  "raw_text": "查北京产品经理 15k-25k",
  "query_payload": {
    "major": null,
    "education": "本科",
    "intention_job": ["产品经理"],
    "intention_company": null,
    "intention_location": ["北京"],
    "job_type": null,
    "graduate_time": null,
    "company_type": null,
    "is_unlimited_major": null,
    "order_by": null,
    "jobCategory": null,
    "timeType": null
  }
}
```

注意：这里的 `query_payload` 是后端 API 查询语义；小程序 UI 自动化不一定直接使用这些字段名，需要做适配。

### 1.2 小程序 UI 自动化控制模块

同事项目是“小程序 UI 自动化控制模块”，核心脚本通常是：

```text
automation/loop-search.js
```

它的作用是：

```text
连接微信开发者工具 auto 模式
  -> 自动登录 AIBZ 小程序
  -> 打开岗位搜索页
  -> 打开筛选弹窗
  -> 填入筛选条件
  -> 点击开始匹配
  -> 点击岗位卡片
  -> 进入岗位详情
  -> 模拟滑动浏览
  -> 保存日志和截图
```

它目前的输入更接近批处理测试数据，例如：

```json
[
  { "position": "Java开发", "education": "本科", "companyType": "央国企" },
  { "position": "产品经理", "education": "硕士", "job_type": "全职" }
]
```

或单条：

```bash
node automation/loop-search.js --input '{"position":"产品经理","education":"本科"}'
```

本次合并后，它应该从弹幕解析输出文件里持续读取新记录，而不是只读静态测试 JSON。

## 2. 合并后的目标架构

推荐合并成如下关系：

```text
自动化直播间/弹幕解析模块
  append JSONL 查询事件
        |
        v
共享 JSONL 文件
        |
        v
小程序 UI 自动化控制模块
  tail/轮询新行
  过滤有效弹幕查询
  字段适配
  排队执行小程序 UI 操作
  写日志/截图/状态事件
```

核心原则：

1. 弹幕解析模块负责“识别用户想查什么”。
2. 小程序 UI 自动化模块负责“把识别结果变成小程序上的可视化操作”。
3. 两者通过共享文件通信。
4. 共享文件应优先按 append-only JSONL 事件流设计。
5. 不要让两个进程同时修改同一个 JSON 数组文件。

## 3. 共享文件协议

### 3.1 推荐文件格式

使用 JSONL，一行一个 JSON 对象。

弹幕解析模块持续追加查询记录：

```json
{"type":"danmu_query","trace_id":"...","ts":"...","raw_text":"查北京产品经理","keyword":"产品经理","city":"北京","education":"本科","query_payload":{"intention_job":["产品经理"],"intention_location":["北京"],"education":"本科"}}
```

如果当前弹幕端还没有 `type` 和 `trace_id` 字段，也可以先兼容旧格式：

```json
{"ts":"...","raw_text":"查北京产品经理","keyword":"产品经理","query_payload":{...}}
```

UI 自动化消费者应支持两种记录：

1. `type` 缺失但含有 `query_payload` 或 `keyword`：视为查询事件。
2. `type == "danmu_query"`：视为查询事件。

如果 UI 自动化模块也要把执行状态写回同一个文件，必须追加新行，不要回写旧行：

```json
{"type":"automation_started","trace_id":"...","ts":"...","criteria":{"position":"产品经理","education":"本科"}}
{"type":"automation_done","trace_id":"...","ts":"...","status":"ok","screenshots":[".../1-result.png",".../1-detail-scrolled.png"]}
{"type":"automation_failed","trace_id":"...","ts":"...","status":"failed","error":"筛选按钮未找到"}
```

消费者读文件时必须跳过 `automation_started`、`automation_done`、`automation_failed` 等状态事件，避免读到自己写的状态后重复触发小程序搜索。

### 3.2 是否允许读写同一个文件

可以，但必须遵守：

1. 只追加，不修改。
2. 每条记录单行 JSON。
3. 写入后立即 flush，保证另一进程能及时读到。
4. UI 自动化模块需要记录已消费 offset 或已消费 `trace_id`，避免重启后重复执行。
5. 如果要降低互相干扰，状态事件也可以写到单独文件，例如：

```text
链路监控/events/*.jsonl
小程序自动化/events/*.jsonl
```

但本次需求是“通过读写同一个文件”，所以同文件 append-only 方案优先。

## 4. 字段适配规则

弹幕解析结果与小程序筛选表单字段不同，需要适配层。

推荐适配函数语义：

```text
danmu record -> automation criteria
```

字段映射：

| 弹幕解析字段 | 小程序 UI 自动化字段 | 说明 |
|---|---|---|
| `record.keyword` | `position` | 优先使用顶层 keyword |
| `record.query_payload.intention_job[0]` | `position` | keyword 缺失时兜底 |
| `record.query_payload.intention_company` | `company` | 如果小程序筛选支持公司名 |
| `record.education` | `education` | 顶层学历优先 |
| `record.query_payload.education` | `education` | 顶层缺失时兜底 |
| `record.query_payload.company_type` | `companyType` | 注意小程序脚本当前字段名是 camelCase |
| `record.query_payload.job_type` | `job_type` | 保持同事脚本现有字段 |
| `record.city` | 待确认 | 如果小程序筛选页有城市控件，需要新增 UI 操作 |
| `record.query_payload.intention_location[0]` | 待确认 | 同上 |

建议适配逻辑：

```js
function toAutomationCriteria(record) {
  const payload = record.query_payload || {}
  const first = (value) => Array.isArray(value) ? value[0] : value

  return compact({
    position: record.keyword || first(payload.intention_job),
    company: payload.intention_company,
    education: record.education || payload.education,
    companyType: payload.company_type,
    job_type: payload.job_type
  })
}
```

其中 `compact` 表示删除 `null`、`undefined`、空字符串、空数组。

注意：

1. 不要为了适配 UI 自动化而修改弹幕解析模块的原始 schema。
2. `query_payload` 继续作为通用下游语义。
3. UI 自动化模块单独派生 `criteria` 即可。

## 5. 对小程序 UI 自动化模块的改造要求

### 5.1 从批处理改为流式/队列消费

当前 `loop-search.js` 主要支持：

```bash
--file automation/test-queries.json
--input '{"position":"Java开发"}'
```

合并后建议新增共享文件消费模式：

```bash
node automation/loop-search.js --watch-jsonl <shared-jsonl-path>
```

或新增单独入口，避免破坏原测试脚本：

```bash
node automation/watch-danmu.js --file <shared-jsonl-path>
```

推荐做法是保留 `loop-search.js` 的核心动作函数，然后新增 watcher 入口：

```text
watch shared jsonl
  -> read new complete lines
  -> JSON.parse
  -> isQueryEvent(record)
  -> toAutomationCriteria(record)
  -> enqueue(criteria)
  -> sequentially runOneCycle(mp, criteria, index)
```

### 5.2 必须串行执行

微信小程序 UI 自动化不能并发点击。即使直播间弹幕很多，也必须排队。

要求：

1. 同一时间只执行一个小程序搜索流程。
2. 新弹幕查询进入队列。
3. 可设置最大队列长度，防止弹幕高峰积压。
4. 可做去重，例如同一 `position + city + education` 在 30 秒内只执行一次。

### 5.3 连接和登录只做一次

UI 自动化模块应常驻：

```text
启动
  -> connect DevTools
  -> ensureLoggedIn
  -> 开始 watch JSONL
  -> 每条查询 runOneCycle
```

不要每条弹幕都重新启动微信开发者工具或重新登录。

### 5.4 保留原来的测试入口

请尽量保留同事脚本现有能力：

```bash
node automation/loop-search.js --file automation/test-queries.json
node automation/loop-search.js --input '{"position":"产品经理"}'
```

这样合并后仍然可以脱离弹幕链路单独验证小程序自动化。

## 6. 运行环境要求

小程序 UI 自动化模块依赖：

1. Node.js >= 14。
2. `miniprogram-automator`。
3. 微信开发者工具。
4. 微信开发者工具安全设置里开启服务端口。
5. 小程序已编译到微信开发者工具可打开的 `mp-weixin` 目录。

同事脚本里可能硬编码了 Windows 路径，例如：

```js
const CLI_PATH = 'D:/software/微信web开发者工具/cli.bat'
const PROJECT_PATH = 'D:/aibz/dist/dev/mp-weixin'
```

合并时应改成可配置项，优先从环境变量读取：

```text
WECHAT_DEVTOOLS_CLI
WECHAT_MINIPROGRAM_PROJECT
WECHAT_AUTO_PORT
```

不要把新电脑的绝对路径写死在代码里。

## 7. 日志、截图与状态

UI 自动化模块原本会输出：

```text
automation/test-runs/{timestamp}/test.log
automation/test-runs/{timestamp}/screenshots/*.png
```

合并后建议继续保留，并在状态事件里记录关键路径：

```json
{
  "type": "automation_done",
  "trace_id": "...",
  "status": "ok",
  "run_dir": "automation/test-runs/2026-04-29T10-00-00",
  "screenshots": [
    "screenshots/1-result.png",
    "screenshots/1-detail-scrolled.png"
  ]
}
```

失败时追加：

```json
{
  "type": "automation_failed",
  "trace_id": "...",
  "status": "failed",
  "error": "筛选按钮未找到 (.filter-icon)",
  "run_dir": "..."
}
```

## 8. 与现有语音链路的关系

自动化直播间项目里已经有“后端 API 查询 -> 语音生成 -> TTS”的链路。

本次小程序 UI 自动化合并不应默认破坏该链路。

推荐关系：

```text
同一条弹幕解析结果
  -> API 查询/TTS 链路：负责生成语音内容
  -> 小程序 UI 自动化链路：负责可视化展示小程序操作
```

也就是说，小程序 UI 自动化是并行消费者，不是必须替代 API 查询模块。

如果后续决定让 UI 自动化替代 API 查询作为岗位数据来源，需要额外实现“从小程序页面提取结构化岗位数据”的能力；当前同事脚本主要产出日志和截图，不建议直接承担 TTS 数据来源。

## 9. 验收标准

合并完成后至少满足：

1. 弹幕解析模块可以继续正常写 JSONL。
2. UI 自动化模块可以监听同一个 JSONL 文件。
3. 文件追加一条查询记录后，UI 自动化模块能自动执行一次小程序搜索。
4. 字段映射正确，例如“查北京产品经理 本科”能转成 `position=产品经理`、`education=本科`。
5. UI 自动化模块不会消费自己写入的 `automation_*` 状态事件。
6. 多条查询连续写入时，自动化模块串行执行，不并发点击。
7. 微信开发者工具连接和登录只初始化一次。
8. 每次执行有日志和截图。
9. 失败不会导致 watcher 进程直接退出，除非是 DevTools 连接等致命错误。
10. 原有 `--file` / `--input` 测试入口尽量仍可运行。

## 10. 建议的合并步骤

1. 先把两个项目放在同一工作目录下，确认目录结构。
2. 找到弹幕解析模块实际输出的 JSONL 文件。
3. 找到小程序 UI 自动化模块的主入口和动作函数。
4. 抽出或复用 `runOneCycle(mp, criteria, index)` 一类单次执行函数。
5. 新增 JSONL watcher，支持从文件尾部开始读新行。
6. 新增 `isQueryEvent(record)` 和 `toAutomationCriteria(record)`。
7. 加入串行队列，确保同一时间只跑一个 UI 自动化任务。
8. 加入状态事件写入，注意跳过自身状态事件。
9. 把硬编码路径改为环境变量或命令行参数。
10. 用手工追加 JSONL 的方式做离线验证。
11. 再接入真实弹幕解析输出验证。

## 11. 手工测试样例

可以先不用真实直播，手工追加一条 JSONL：

```json
{"type":"danmu_query","trace_id":"test-001","ts":"2026-04-29 10:00:00","raw_text":"查北京产品经理 本科","keyword":"产品经理","city":"北京","education":"本科","query_payload":{"education":"本科","intention_job":["产品经理"],"intention_location":["北京"],"job_type":null,"company_type":null,"intention_company":null}}
```

期望：

1. watcher 读到该行。
2. 适配出：

```json
{"position":"产品经理","education":"本科"}
```

3. 小程序自动打开筛选页并搜索。
4. 生成本轮日志和截图。
5. 共享文件追加 `automation_started` 和 `automation_done` 或失败事件。

## 12. 需要避免的做法

1. 不要把共享文件改成 JSON 数组后反复整体读写。
2. 不要让两个进程同时覆盖写同一个文件。
3. 不要让 UI 自动化模块并发执行多个查询。
4. 不要每条弹幕都重新启动微信开发者工具。
5. 不要把 Windows/Mac 本机绝对路径硬编码进合并后的通用代码。
6. 不要为了 UI 自动化修改弹幕解析输出的既有字段语义。
7. 不要让 UI 自动化消费 `automation_done` 之类的状态事件。

## 13. 待确认事项

合并时如果遇到以下问题，需要根据小程序页面实际情况决定：

1. 小程序筛选页是否支持城市筛选？如果支持，需要补充 `city/intention_location` 的 UI 操作。
2. 公司类型字段在小程序 UI 里的文本是否和 `company_type` 完全一致？例如“央国企”“知名外企”“私企大厂”。
3. 学历字段是否只接受“本科/硕士/博士/大专”？如果弹幕解析出“985/211”“一本”，需要在 UI 适配层丢弃或转义。
4. 状态事件是否必须写回同一个共享文件？如果不是强要求，单独状态文件会更干净。
5. watcher 重启后是从文件末尾开始，还是从上次 offset 继续？直播场景通常建议从末尾开始，测试场景可支持 `--from-start`。

