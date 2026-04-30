# 自动化直播间

这是一个把抖音直播间弹幕转成岗位查询、直播口播和 OBS 音频播放的自动化链路项目。

主链路：

```text
抖音直播间弹幕
  -> 弹幕命中与结构化 JSONL
  -> aibz 岗位 API 查询
  -> 豆包 LLM 生成解说文案
  -> 豆包 TTS 生成 mp3
  -> events / traces / logs 记录链路状态
  -> 可选 OBS 文本展示和音频播放
```

小程序 UI 自动化不随本仓库提交；需要运行时请额外 clone：

```bash
git clone https://github.com/Xuanaaaaaa/automation.git automation
```

完整架构、数据流和 Windows 启动流程见 [项目总览与Windows启动流程.md](项目总览与Windows启动流程.md)。

## 项目结构

```text
弹幕提取/DouyinLiveWebFetcher/   抓取直播间弹幕并输出结构化 JSONL
小程序API提取岗位信息/            调用 aibz 岗位搜索接口
语音生成/                         生成解说文案和 TTS 音频
链路监控/                         编排器、事件监控、trace 统计
Obs_auto/                         OBS 文本源更新、TTS 音频播放工具
scripts/                          初始化、启动、停止、日志脚本
docs/                             迁移、部署、OBS、小程序合并等补充文档
```

根目录仅保留主要入口文档：`README.md` 和 `项目总览与Windows启动流程.md`。其他说明文档集中放在 `docs/`。

## 快速开始

```bash
git clone https://github.com/Xuanaaaaaa/auto-live-room.git
cd auto-live-room

cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
LIVE_ID=你的直播间ID
AIBZ_TOKEN=你的token不要带Bearer前缀
DOUBAO_LLM_API_KEY=你的豆包LLMKey
DOUBAO_TTS_API_KEY=你的豆包TTSKey
```

初始化依赖：

```bash
./scripts/bootstrap.sh
```

后台启动主链路：

```bash
./scripts/start_all.sh
```

脚本会提示输入 `LIVE_ID`；如果 `.env` 里已有默认值，直接回车沿用，输入新值则仅本次启动覆盖。

查看状态和日志：

```bash
./scripts/status.sh
./scripts/logs.sh monitor
./scripts/logs.sh pipeline
./scripts/logs.sh danmu
```

停止：

```bash
./scripts/stop_all.sh
```

## 常用命令

单独启动弹幕抓取：

```bash
./scripts/run_danmu.sh
```

单独启动编排器：

```bash
./scripts/run_pipeline.sh
```

单独启动只读监控器：

```bash
./scripts/run_monitor.sh
```

离线验证编排器，不消耗 aibz / LLM / TTS：

```bash
PIPELINE_DRY_RUN=1 PIPELINE_FROM_START=1 PIPELINE_NO_TTS=1 ./scripts/run_pipeline.sh
```

OBS 文本更新和音频播放旁路需要单独启动：

```bash
./scripts/run_obs_text.sh
./scripts/run_obs_audio.sh
```

`run_obs_audio.sh` 会监听 `链路监控/events/events_*.jsonl` 中的 `audio_path`，把最新 TTS mp3 推给 OBS 媒体源播放。OBS 中需要提前创建媒体源，默认名称为 `岗位语音`。

## 小程序 UI 自动化

小程序自动化代码来自独立仓库，不纳入本仓库提交：

```bash
git clone https://github.com/Xuanaaaaaa/automation.git automation
```

Windows 上运行时，进入额外 clone 出来的 `automation/` 目录：

```powershell
cd D:\workspace\auto-live-room\automation
npm install miniprogram-automator

$env:DANMU_JSONL_DIR = "\\wsl$\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output"
node watch-danmu.js
```

该 watcher 会监听主链路生成的结构化弹幕 JSONL，串行驱动微信开发者工具中的 AIBZ 小程序执行搜索、点击岗位详情、滚动浏览，并把日志、截图和 `status.jsonl` 写入 `automation/test-runs/`。

## 运行产物

运行时会生成以下本地文件，这些文件不会提交到 Git：

```text
logs/                                      后台脚本日志
.run/                                     后台脚本 pid 文件
弹幕提取/DouyinLiveWebFetcher/danmu/       原始弹幕日志
弹幕提取/DouyinLiveWebFetcher/output/      结构化弹幕 JSONL
链路监控/events/                           实时阶段事件流
链路监控/traces/                           端到端 trace
链路监控/audio/                            TTS 音频 mp3
automation/                               外部 clone 的小程序自动化项目
```

`events` 用来看实时阶段，`traces` 用来做事后复盘。

## Windows 运行

当前推荐使用 **WSL2 Ubuntu 运行本项目，Windows 宿主机运行 OBS Studio 和微信开发者工具**：

```text
Windows
  ├─ OBS Studio
  ├─ 微信开发者工具
  ├─ automation 独立仓库
  └─ WSL2 Ubuntu 运行 auto-live-room
```

如果要让 WSL 中生成的 TTS 音频自动进入 Windows OBS，建议把 `AUDIO_DIR` 设置到 `/mnt/c/...` 这类 Windows 可读目录，并设置 `OBS_AUDIO_PATH_MODE=wsl-to-windows`。

详细步骤见 [项目总览与Windows启动流程.md](项目总览与Windows启动流程.md) 和 [docs/Windows迁移教程.md](docs/Windows迁移教程.md)。

## 补充文档

- [项目总览与Windows启动流程.md](项目总览与Windows启动流程.md)
- [docs/全链路运行手册.md](docs/全链路运行手册.md)
- [docs/部署脚本说明.md](docs/部署脚本说明.md)
- [docs/Windows迁移教程.md](docs/Windows迁移教程.md)
- [docs/Windows OBS音频播放对接手册.md](docs/Windows%20OBS音频播放对接手册.md)
- [docs/小程序UI自动化合并说明.md](docs/小程序UI自动化合并说明.md)

## 安全提醒

- 不要提交 `.env`
- 不要把 `AIBZ_TOKEN`、豆包 API Key、OBS 密码写进代码
- token 过期后更新 `.env` 并重启链路
