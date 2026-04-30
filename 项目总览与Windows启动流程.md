# 自动化直播间项目总览与 Windows 启动流程

> 当前文档描述的是 **WSL2 虚拟机 + Windows 本地工具** 的实现版本：自动化直播间主链路在 WSL2 Ubuntu 中运行，OBS Studio、微信开发者工具和小程序 UI 自动化在 Windows 本地运行。
> 同一套主链路也可以直接在 Mac 本地运行。后续如果开发“全部原生 Windows 版本”，需要另行补充 PowerShell/Windows venv/原生路径相关流程。

本文档把当前仓库中的两部分能力合在一起说明：

1. **自动化直播间主链路**：抖音直播间弹幕 -> 弹幕结构化 -> aibz 岗位 API 查询 -> 豆包 LLM 解说 -> 豆包 TTS 音频 -> OBS 展示/播放。
2. **automation 小程序 UI 自动化链路**：监听同一份结构化弹幕 JSONL -> 驱动微信开发者工具中的 AIBZ 小程序 -> 搜索岗位、点击详情、滚动浏览、保存日志和截图。

注意：`automation/` 来自独立仓库 `https://github.com/Xuanaaaaaa/automation.git`，不随本仓库提交；需要运行小程序 UI 自动化时再额外 clone 到项目根目录。

合并后的定位不是让小程序 UI 自动化替代后端 API 查询，而是让同一条弹幕查询同时被两个消费者使用：

```text
抖音直播间弹幕
  -> 弹幕抓取与解析
  -> 结构化 JSONL
       ├─ 主链路消费者：岗位 API -> LLM 解说 -> TTS -> OBS 音频/文本
       └─ UI 消费者：微信开发者工具 -> AIBZ 小程序搜索/浏览/截图
```

---

## 1. 项目组成

| 目录 / 文件 | 作用 | 运行位置 |
|---|---|---|
| `弹幕提取/DouyinLiveWebFetcher/` | 连接抖音 Web 直播间 WebSocket，保存原始弹幕，并把有效查岗弹幕写成结构化 JSONL | Mac 本地 / WSL2 Ubuntu |
| `弹幕提取/DouyinLiveWebFetcher/弹幕分析脚本/danmaku_parser.py` | 弹幕解析：噪声过滤、规则命中、可选 LLM 兜底、去重 | Mac 本地 / WSL2 Ubuntu |
| `小程序API提取岗位信息/aibz_job_search.py` | 直连 aibz 后端岗位搜索接口，完成签名、参数清洗、响应整理 | Mac 本地 / WSL2 Ubuntu |
| `语音生成/job_narration_workflow.py` | 根据岗位结果生成直播口播文案，并调用豆包 TTS 生成 mp3 | Mac 本地 / WSL2 Ubuntu |
| `链路监控/orchestrator.py` | 主编排器：tail 弹幕 JSONL，串起 API 查询、LLM、TTS，写 events/traces | Mac 本地 / WSL2 Ubuntu |
| `链路监控/monitor.py` | 只读监控器：读取 events JSONL，展示实时链路状态 | Mac 本地 / WSL2 Ubuntu |
| `Obs_auto/obs_jsonl_text_updater.py` | 从结构化弹幕 JSONL 读取最新字段，更新 OBS 文本源 | Mac 本地控制 Mac OBS / WSL2 控制 Windows OBS |
| `Obs_auto/obs_audio_player.py` | 从 events JSONL 读取 `audio_path`，通过 OBS 媒体源播放 mp3 | Mac 本地控制 Mac OBS / WSL2 控制 Windows OBS |
| `scripts/*.sh` | WSL/Linux/macOS 侧初始化、启动、停止、查看日志脚本 | Mac 本地 / WSL2 Ubuntu |
| `automation/watch-danmu.js` | 外部 clone 后可用；监听结构化弹幕 JSONL，串行驱动小程序 UI 自动化 | Windows |
| `automation/lib/automation-core.js` | 外部 clone 后可用；微信开发者工具连接、自动登录、筛选、点击岗位、详情滚动、截图等核心动作 | Windows |
| `automation/loop-search.js` | 外部 clone 后可用；小程序 UI 自动化的离线批量/单条测试入口 | Windows |

## 2. 运行位置与命令差异

### 2.1 Mac 本地运行

Mac 上可以直接运行 `auto-live-room` 主项目。OBS 如果也在 Mac 上，就用 `OBS_HOST=localhost` 控制本机 OBS。

```bash
cp .env.example .env
./scripts/bootstrap.sh
./scripts/start_all.sh
./scripts/status.sh
./scripts/logs.sh monitor
./scripts/stop_all.sh
```

Mac 上的 OBS 旁路命令也是 Bash 脚本：

```bash
./scripts/run_obs_text.sh
./scripts/run_obs_audio.sh
```

如果只跑主链路，不跑小程序 UI 自动化，不需要 clone `automation`。

### 2.2 Windows 当前推荐运行方式

Windows 当前推荐是 **WSL2 Ubuntu + Windows 本地工具**：

```text
WSL2 Ubuntu:
  auto-live-room 主链路
  scripts/*.sh
  Python venv
  events / traces / audio

Windows 本地:
  OBS Studio
  微信开发者工具
  Node.js
  automation 独立仓库
```

WSL2 中运行主链路，命令和 Mac 基本一致：

```bash
cp .env.example .env
./scripts/bootstrap.sh
./scripts/start_all.sh
./scripts/status.sh
./scripts/logs.sh monitor
./scripts/stop_all.sh
```

区别主要在路径和 GUI 工具：

| 场景 | Mac 本地 | Windows 当前版本 |
|---|---|---|
| 主项目 `auto-live-room` | Mac 终端直接跑 Bash 脚本 | WSL2 Ubuntu 中跑 Bash 脚本 |
| OBS Studio | Mac 本机 OBS | Windows 本机 OBS |
| OBS WebSocket Host | 通常 `localhost` | WSL 里通常填 Windows 宿主机 IP |
| TTS 音频路径 | 普通 macOS 路径即可 | 推荐 `AUDIO_DIR=/mnt/c/...` |
| OBS 音频路径转换 | `OBS_AUDIO_PATH_MODE=auto` 或 `posix` | `OBS_AUDIO_PATH_MODE=wsl-to-windows` |
| 小程序 UI 自动化 | 当前未作为主流程描述 | Windows 本地运行 `automation` |
| 小程序监听路径 | 不适用或需另配 | `\\wsl$\Ubuntu\...\output` |

Windows 本地启动小程序自动化使用 PowerShell/CMD，而不是 Bash：

```powershell
cd D:\workspace\auto-live-room
git clone https://github.com/Xuanaaaaaa/automation.git automation

cd D:\workspace\auto-live-room\automation
npm install miniprogram-automator

$env:DANMU_JSONL_DIR = "\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output"
node watch-danmu.js
```

### 2.3 暂未覆盖的原生 Windows 版本

当前仓库没有提供完整原生 Windows PowerShell 启停脚本。也就是说，不建议直接在 Windows 原生 Python 环境中运行 `auto-live-room` 主链路。

未来如果开发全部原生 Windows 版本，需要单独补齐：

```text
scripts/start_all.ps1
scripts/stop_all.ps1
scripts/status.ps1
scripts/logs.ps1
Windows 原生 venv 路径，如 venv\Scripts\python.exe
Windows 原生音频路径和 OBS 路径处理
```

---

## 3. 总体运行链路

### 3.1 弹幕输入与结构化

`scripts/run_danmu.sh` 会进入 `弹幕提取/DouyinLiveWebFetcher/`，使用该目录下的 `venv/bin/python` 启动 `main.py`。

启动后：

1. `main.py` 读取项目根目录 `.env` 中的 `LIVE_ID`，或使用启动时输入的 `LIVE_ID`。
2. `liveMan.py` 用 `LIVE_ID` 打开抖音直播间，获取 `room_id`、`ttwid`，生成 WebSocket 签名并连接抖音 IM。
3. 每条聊天消息先写入原始弹幕日志：

```text
弹幕提取/DouyinLiveWebFetcher/danmu/{live_id}_{timestamp}.txt
```

4. 后台解析线程调用 `DanmakuParser.parse()`：

```text
原始弹幕
  -> 长度/噪声过滤
  -> 规则解析岗位、城市、学历、薪资、经验、行业
  -> 可选 LLM 兜底
  -> 去重
  -> JobQuery
```

5. 命中的查岗弹幕写入结构化 JSONL：

```text
弹幕提取/DouyinLiveWebFetcher/output/{live_id}_{timestamp}.jsonl
```

典型结构化记录：

```json
{
  "ts": "2026-04-29 10:00:00",
  "live_id": "266454629091",
  "user_id": "1001",
  "user_name": "Alice",
  "keyword": "产品经理",
  "city": "北京",
  "education": "本科",
  "source": "rule",
  "raw_text": "查北京产品经理 本科",
  "query_payload": {
    "education": "本科",
    "intention_job": ["产品经理"],
    "intention_location": ["北京"],
    "job_type": null,
    "company_type": null
  }
}
```

这份 JSONL 是后续所有模块的主输入。

### 3.2 主链路：岗位 API、解说和 TTS

`scripts/run_pipeline.sh` 会启动 `链路监控/orchestrator.py`。

默认情况下，脚本会按 `.env` 中的 `LIVE_ID` 自动找到最新的：

```text
弹幕提取/DouyinLiveWebFetcher/output/${LIVE_ID}_*.jsonl
```

也可以用 `DANMU_JSONL=/完整路径/file.jsonl` 指定固定文件。

主编排器对每条新结构化弹幕执行：

```text
received
  -> search_jobs_from_payload(query_payload, AIBZ_TOKEN)
  -> normalize_job(first_job)
  -> generate_script_with_doubao()
  -> synthesize_with_doubao_tts()
  -> completed
```

每条弹幕生成一个 `trace_id`，并写两类产物：

| 产物 | 路径 | 用途 |
|---|---|---|
| 阶段事件流 | `链路监控/events/events_{timestamp}.jsonl` | 给监控器和 OBS 音频播放旁路实时读取 |
| 终态 trace | `链路监控/traces/traces_{timestamp}.jsonl` | 事后复盘、统计每阶段耗时和失败原因 |
| TTS 音频 | `链路监控/audio/trace_{trace_id}.mp3`，或 `.env` 中 `AUDIO_DIR` 指定目录 | 给 OBS 媒体源播放 |

`events` 中的 `completed` 事件会带上：

```json
{
  "type": "stage",
  "trace_id": "...",
  "stage": "completed",
  "audio_path": "链路监控/audio/trace_....mp3",
  "timing": {
    "search_ms": 420,
    "narration_ms": 1180,
    "tts_ms": 710
  }
}
```

### 3.3 OBS 文本和音频旁路

OBS 相关脚本不在 `scripts/start_all.sh` 中自动启动，需要单独运行。

文本旁路：

```text
结构化弹幕 JSONL
  -> Obs_auto/obs_jsonl_text_updater.py
  -> OBS 文本源，如“当前查询”
```

音频旁路：

```text
链路监控/events/events_*.jsonl
  -> 读取 completed/synthesized 事件中的 audio_path
  -> Obs_auto/obs_audio_player.py
  -> OBS 媒体源，如“岗位语音”
```

在 Windows OBS + WSL2 项目模式下，建议把 `AUDIO_DIR` 放到 Windows 可读目录，例如：

```bash
AUDIO_DIR=/mnt/c/Users/你的Windows用户名/auto-live-room-audio
OBS_AUDIO_PATH_MODE=wsl-to-windows
```

这样 OBS 音频旁路会把 `/mnt/c/...` 转成 `C:\...` 后交给 Windows OBS。

### 3.4 小程序 UI 自动化链路

`automation/watch-danmu.js` 在 Windows 上运行。它通过 Windows 的 `\\wsl$` 路径监听 WSL 中的结构化弹幕输出目录：

```text
\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output
```

运行后：

1. 找到目录中最新的 `.jsonl` 文件，首次启动从文件末尾开始读，避免处理历史弹幕。
2. 如果弹幕端重启生成新文件，自动切换到新文件。
3. 跳过 `automation_*` 状态事件。
4. 将弹幕记录适配为小程序筛选条件：

| 弹幕字段 | 小程序 UI 字段 |
|---|---|
| `keyword` 或 `query_payload.intention_job[0]` | `position` |
| `query_payload.intention_company` | `company` |
| `education` 或 `query_payload.education` | `education`，仅保留 `本科/硕士/博士/大专` |
| `query_payload.company_type` | `companyType` |
| `query_payload.job_type` | `job_type` |
| `city` 或 `query_payload.intention_location[0]` | `city` |

5. 用 30 秒默认窗口对相同 `position/company/education/companyType/job_type/city` 去重。
6. 将任务放入串行队列，确保微信小程序同一时间只执行一个搜索流程。
7. 连接微信开发者工具 auto 模式，自动登录测试账号。
8. 每条查询执行一轮：

```text
打开 /pages/position/search
  -> 点击筛选按钮
  -> 填职位/公司
  -> 选择学历/企业类型/岗位类型/城市区域
  -> 点击开始匹配
  -> 点击第一个岗位
  -> 进入详情页并模拟滚动
  -> 保存日志和截图
  -> 返回搜索页
```

UI 自动化产物默认写入：

```text
automation/test-runs/watch-{timestamp}/
  test.log
  status.jsonl
  screenshots/
```

其中 `status.jsonl` 是远端 `Xuanaaaaaa/automation` 最新实现中的状态事件文件，记录 `automation_started`、`automation_done`、`automation_failed`。它默认写在本次 watcher 运行目录下，也可以通过 `AUTOMATION_STATUS_JSONL` 指定到其他位置；不会再回写到弹幕结构化 JSONL。

当前城市筛选仍有限制：小程序筛选弹窗里只有 `京津冀/江浙沪/川渝` 这类区域按钮，`automation-core.js` 目前会在有 `city` 时选择第一个区域按钮，尚未做精确城市映射。

---

## 4. 数据流向

### 4.1 文件级数据流

```text
抖音 WebSocket
  -> danmu/{live_id}_{timestamp}.txt
  -> output/{live_id}_{timestamp}.jsonl
       ├─ 链路监控/orchestrator.py
       │    ├─ 小程序API提取岗位信息/aibz_job_search.py
       │    ├─ 语音生成/job_narration_workflow.py
       │    ├─ 链路监控/events/events_{timestamp}.jsonl
       │    ├─ 链路监控/traces/traces_{timestamp}.jsonl
       │    └─ 链路监控/audio/trace_{trace_id}.mp3
       ├─ Obs_auto/obs_jsonl_text_updater.py
       │    └─ OBS 文本源
       └─ automation/watch-danmu.js
            ├─ 微信开发者工具 auto 模式
            ├─ AIBZ 小程序 UI 搜索/详情滚动
            ├─ automation/test-runs/.../test.log
            ├─ automation/test-runs/.../status.jsonl
            ├─ automation/test-runs/.../screenshots/*.png
            └─ automation_started/done/failed 状态事件

链路监控/events/events_{timestamp}.jsonl
  -> 链路监控/monitor.py
  -> Obs_auto/obs_audio_player.py
       -> OBS 媒体源播放 mp3
```

### 4.2 环境变量数据流

根目录 `.env` 是 WSL 主链路的配置中心。核心变量：

| 变量 | 作用 |
|---|---|
| `LIVE_ID` | 抖音直播间 ID；弹幕抓取、pipeline 默认 JSONL 选择、OBS 文本默认文件选择都会用到 |
| `AIBZ_TOKEN` | aibz 登录态 token，不带 `Bearer ` 前缀 |
| `DOUBAO_LLM_API_KEY` / `DOUBAO_API_KEY` | 豆包/火山方舟文本模型 key |
| `DOUBAO_TTS_API_KEY` / `DOUBAO_API_KEY` | 豆包 TTS key |
| `AUDIO_DIR` | TTS mp3 输出目录；Windows OBS 联动时建议设到 `/mnt/c/...` |
| `OBS_HOST` / `OBS_PORT` / `OBS_PASSWORD` | OBS WebSocket 连接信息 |
| `OBS_AUDIO_PATH_MODE` | WSL 控制 Windows OBS 时设为 `wsl-to-windows` |

`automation` 使用 Windows 进程环境变量：

| 变量 | 作用 |
|---|---|
| `DANMU_JSONL_DIR` | 必填，结构化弹幕 JSONL 输出目录的 Windows 路径，通常是 `\\wsl$\...` |
| `DANMU_LIVE_ID` | 可选，只监听指定 live_id 前缀的文件 |
| `WECHAT_DEVTOOLS_CLI` | 微信开发者工具 `cli.bat` 路径 |
| `WECHAT_MINIPROGRAM_PROJECT` | 小程序编译产物目录，如 `D:/aibz/dist/dev/mp-weixin` |
| `WECHAT_AUTO_PORT` | DevTools auto WebSocket 端口，默认 `9420` |
| `DEDUP_WINDOW_MS` | UI 自动化去重窗口，默认 `30000` |
| `POLL_INTERVAL_MS` | JSONL 轮询间隔，默认 `2000` |
| `AUTOMATION_STATUS_JSONL` | 可选，自动化状态事件输出文件；默认 `automation/test-runs/watch-{timestamp}/status.jsonl` |

---

## 5. Windows 上的完整启动流程

推荐部署形态：

```text
Windows 宿主机
  ├─ OBS Studio
  ├─ 微信开发者工具
  ├─ Node.js + automation
  └─ WSL2 Ubuntu
       └─ 自动化直播间 Python 主链路
```

### 5.1 Windows 侧准备

1. 安装 **WSL2 Ubuntu**。
2. 安装 **OBS Studio**。
3. 安装 **微信开发者工具**。
4. 安装 **Node.js >= 14**。
5. 确认 Windows 网络可以访问 GitHub、Python/npm 包源、抖音直播、aibz 接口、豆包服务。
6. 如果要 OBS 联动，打开 OBS：
   - 启用 WebSocket。
   - 记录端口，默认 `4455`。
   - 记录密码。
   - 创建文本源，默认可命名为 `当前查询`。
   - 创建媒体源，默认可命名为 `岗位语音`。

### 5.2 WSL2 Ubuntu 初始化项目

在 WSL2 中：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl

git clone https://github.com/Xuanaaaaaa/auto-live-room.git
cd auto-live-room

cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
LIVE_ID=你的抖音直播间ID
AIBZ_TOKEN=你的aibz token，不带Bearer前缀
DOUBAO_LLM_API_KEY=你的豆包LLMKey
DOUBAO_TTS_API_KEY=你的豆包TTSKey
```

如果要让 Windows OBS 自动播放 WSL 生成的音频，建议同时配置：

```bash
AUDIO_DIR=/mnt/c/Users/你的Windows用户名/auto-live-room-audio
OBS_HOST=Windows宿主机IP
OBS_PORT=4455
OBS_PASSWORD=你的OBSWebSocket密码
OBS_AUDIO_INPUT_NAME=岗位语音
OBS_AUDIO_PATH_MODE=wsl-to-windows
```

`OBS_HOST` 可以在 WSL 中查看 Windows 宿主机网关：

```bash
cat /etc/resolv.conf | grep nameserver
```

然后安装 Python 依赖：

```bash
./scripts/bootstrap.sh
```

该脚本会准备三个虚拟环境：

```text
弹幕提取/DouyinLiveWebFetcher/venv
语音生成/.venv
Obs_auto/.venv
```

### 5.3 启动主链路

在 WSL 项目根目录：

```bash
./scripts/start_all.sh
```

脚本会依次启动：

1. `danmu`：弹幕抓取与结构化。
2. `pipeline`：岗位 API、LLM、TTS 编排器。
3. `monitor`：只读事件监控器。

日志位置：

```text
logs/danmu.log
logs/pipeline.log
logs/monitor.log
```

常用命令：

```bash
./scripts/status.sh
./scripts/logs.sh danmu
./scripts/logs.sh pipeline
./scripts/logs.sh monitor
./scripts/stop_all.sh
```

只想验证编排器结构、不消耗真实 API：

```bash
PIPELINE_DRY_RUN=1 PIPELINE_FROM_START=1 PIPELINE_NO_TTS=1 ./scripts/run_pipeline.sh
```

### 5.4 启动 OBS 文本和音频旁路

OBS 旁路需要单独终端启动。

先 dry-run 验证文本读取：

```bash
OBS_DRY_RUN=1 OBS_ONCE=1 ./scripts/run_obs_text.sh
```

正式更新 OBS 文本源：

```bash
./scripts/run_obs_text.sh
```

先 dry-run 验证音频事件：

```bash
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

正式让 OBS 媒体源播放 TTS mp3：

```bash
./scripts/run_obs_audio.sh
```

### 5.5 Windows 上准备小程序 UI 自动化

以下步骤在 Windows PowerShell 或 CMD 中执行。

先额外 clone 小程序自动化仓库到主项目根目录：

```powershell
cd D:\workspace\auto-live-room
git clone https://github.com/Xuanaaaaaa/automation.git automation
```

进入 `automation` 目录，安装依赖：

```powershell
cd D:\workspace\auto-live-room\automation
npm install miniprogram-automator
```

确认 AIBZ 小程序已经编译到微信开发者工具可打开的目录，例如：

```text
D:/aibz/dist/dev/mp-weixin
```

微信开发者工具中需要打开：

```text
设置 -> 安全 -> 服务端口
设置 -> 安全 -> 多端插件服务端口
```

`automation-core.js` 会在端口未监听时调用：

```text
cli.bat auto --project <小程序项目路径> --auto-port 9420
```

所以通常不需要手动提前执行 `cli.bat auto`。如果默认路径不一致，请用环境变量覆盖。

### 5.6 启动小程序弹幕 watcher

PowerShell 示例：

```powershell
cd D:\workspace\auto-live-room\automation

$env:DANMU_JSONL_DIR = "\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output"
$env:WECHAT_DEVTOOLS_CLI = "D:/software/微信web开发者工具/cli.bat"
$env:WECHAT_MINIPROGRAM_PROJECT = "D:/aibz/dist/dev/mp-weixin"
$env:WECHAT_AUTO_PORT = "9420"

node watch-danmu.js
```

CMD 示例：

```cmd
cd /d D:\workspace\auto-live-room\automation

set DANMU_JSONL_DIR=\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output
set WECHAT_DEVTOOLS_CLI=D:/software/微信web开发者工具/cli.bat
set WECHAT_MINIPROGRAM_PROJECT=D:/aibz/dist/dev/mp-weixin
set WECHAT_AUTO_PORT=9420

node watch-danmu.js
```

启动成功后，它会：

```text
连接 DevTools
  -> 自动登录
  -> 从 JSONL 文件末尾开始监听
  -> 新弹幕进入串行队列
  -> 执行小程序搜索/浏览详情
  -> 写 test-runs 日志、状态事件和截图
```

也可以脱离直播链路单独测试：

```powershell
node loop-search.js --input '{"position":"产品经理","education":"本科"}'
node loop-search.js --file test-queries.json
```

---

## 6. 推荐启动顺序

正式直播时建议按这个顺序：

1. Windows 打开 OBS Studio，确认 WebSocket 可用，文本源和媒体源已创建。
2. Windows 确认微信开发者工具安装正常，小程序项目已编译。
3. WSL 启动主链路：

```bash
./scripts/start_all.sh
```

4. WSL 查看三进程状态：

```bash
./scripts/status.sh
./scripts/logs.sh monitor
```

5. WSL 单独启动 OBS 文本旁路：

```bash
./scripts/run_obs_text.sh
```

6. WSL 单独启动 OBS 音频旁路：

```bash
./scripts/run_obs_audio.sh
```

7. Windows 启动小程序 UI watcher：

```powershell
cd D:\workspace\auto-live-room\automation
$env:DANMU_JSONL_DIR = "\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output"
node watch-danmu.js
```

8. 在直播间发送测试弹幕：

```text
查北京产品经理 本科
```

9. 观察以下成功标志：

| 阶段 | 成功标志 |
|---|---|
| 弹幕抓取 | `logs/danmu.log` 出现 `【聊天msg】` |
| 结构化 | `output/{live_id}_*.jsonl` 新增一行，包含 `keyword=产品经理` |
| 主编排器 | `logs/pipeline.log` 出现 `received/searched/narrated/synthesized/completed` |
| 监控器 | `logs/monitor.log` 出现对应 trace 进度 |
| OBS 文本 | OBS 文本源显示最新查询 |
| OBS 音频 | OBS 媒体源播放 `trace_*.mp3` |
| 小程序 UI 自动化 | 微信开发者工具中自动筛选、搜索、点击岗位、滚动详情 |
| UI 日志截图 | `automation/test-runs/watch-*/test.log`、`status.jsonl` 和 `screenshots/*.png` 生成 |

---

## 7. 关停流程

Windows 小程序 watcher：

```text
Ctrl+C
```

脚本会停止监听，并等待当前队列任务结束。

WSL OBS 旁路：

```text
Ctrl+C
```

WSL 主链路：

```bash
./scripts/stop_all.sh
```

该脚本会按顺序停止：

```text
monitor -> pipeline -> danmu
```

---

## 8. 当前边界与需要确认的点

### 8.1 automation 状态事件已独立落盘

远端 `Xuanaaaaaa/automation` 最新提交 `dfea725` 已将状态事件改为独立落盘。`automation/watch-danmu.js` 不再把状态事件追加回结构化弹幕 JSONL，而是写入：

```text
automation/test-runs/watch-{timestamp}/status.jsonl
```

也可以通过环境变量覆盖：

```powershell
$env:AUTOMATION_STATUS_JSONL = "D:\workspace\auto-live-room\automation\test-runs\status.jsonl"
```

状态事件格式仍然是：

```json
{"type":"automation_started","trace_id":"...","criteria":{...}}
{"type":"automation_done","trace_id":"...","status":"ok"}
{"type":"automation_failed","trace_id":"...","status":"failed","error":"..."}
```

因此主编排器 `链路监控/orchestrator.py` 只会继续消费弹幕解析输出，不会被 UI 自动化状态事件误触发。

### 8.2 城市筛选尚未精确映射

弹幕解析可以提取 `北京/上海/杭州` 等城市；aibz API 主链路会把城市放进 `query_payload.intention_location`。

小程序 UI 自动化当前只能在筛选弹窗中选择区域按钮，尚未完成：

```text
北京 -> 京津冀
上海/杭州/苏州 -> 江浙沪
成都/重庆 -> 川渝
```

以及更精确的城市选择页操作。

### 8.3 小程序路径和 DevTools 路径需要按机器配置

默认值来自 `automation/lib/automation-core.js`：

```text
WECHAT_DEVTOOLS_CLI 默认 D:/software/微信web开发者工具/cli.bat
WECHAT_MINIPROGRAM_PROJECT 默认 D:/aibz/dist/dev/mp-weixin
WECHAT_AUTO_PORT 默认 9420
```

新 Windows 电脑如果目录不同，不要改代码，优先用环境变量覆盖。

### 8.4 token 和 key 都是本机配置

`.env` 不应提交到 Git。换电脑后需要重新配置：

```text
LIVE_ID
AIBZ_TOKEN
DOUBAO_LLM_API_KEY
DOUBAO_TTS_API_KEY
OBS_PASSWORD
```

`AIBZ_TOKEN` 过期时，`pipeline.log` 常见报错为：

```text
JobSearchError code=301
```

此时需要重新从小程序/开发者工具 Network 面板获取登录态 token。

---

## 9. 快速命令索引

WSL 主链路：

```bash
./scripts/bootstrap.sh
./scripts/start_all.sh
./scripts/status.sh
./scripts/logs.sh monitor
./scripts/logs.sh pipeline
./scripts/logs.sh danmu
./scripts/stop_all.sh
```

WSL 单独启动：

```bash
./scripts/run_danmu.sh
./scripts/run_pipeline.sh
./scripts/run_monitor.sh
```

WSL OBS：

```bash
./scripts/run_obs_text.sh
./scripts/run_obs_audio.sh
```

WSL 离线验证：

```bash
PIPELINE_DRY_RUN=1 PIPELINE_FROM_START=1 PIPELINE_NO_TTS=1 ./scripts/run_pipeline.sh
OBS_DRY_RUN=1 OBS_ONCE=1 ./scripts/run_obs_text.sh
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

Windows 小程序自动化：

```powershell
cd D:\workspace\auto-live-room\automation
npm install miniprogram-automator

$env:DANMU_JSONL_DIR = "\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output"
node watch-danmu.js
```

Windows 小程序离线测试：

```powershell
node loop-search.js --input '{"position":"产品经理","education":"本科"}'
node loop-search.js --file test-queries.json
```
