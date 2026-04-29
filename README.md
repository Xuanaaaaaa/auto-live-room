# 自动化直播间

这是一个把直播间弹幕转换成岗位解说音频的自动化链路项目。

当前主链路：

```text
抖音直播间弹幕
  -> 弹幕命中与结构化
  -> 小程序 API 查询岗位
  -> 豆包 LLM 生成解说文案
  -> 豆包 TTS 生成 mp3
  -> events / traces / logs 记录链路状态
```

## 项目结构

```text
弹幕提取/DouyinLiveWebFetcher/   抓取直播间弹幕并输出结构化 JSONL
小程序API提取岗位信息/            调用 aibz 岗位搜索接口
语音生成/                         生成解说文案和 TTS 音频
链路监控/                         编排器、事件监控、trace 统计
Obs_auto/                         OBS 文本源更新相关工具
scripts/                          初始化、启动、停止、日志脚本
```

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

查看状态：

```bash
./scripts/status.sh
```

查看实时监控：

```bash
./scripts/logs.sh monitor
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

同样会提示输入 `LIVE_ID`。

单独启动编排器：

```bash
./scripts/run_pipeline.sh
```

单独启动只读监控器：

```bash
./scripts/run_monitor.sh
```

单独启动 OBS 文本更新：

```bash
./scripts/run_obs_text.sh
```

离线验证编排器，不消耗 aibz / LLM / TTS：

```bash
PIPELINE_DRY_RUN=1 PIPELINE_FROM_START=1 PIPELINE_NO_TTS=1 ./scripts/run_pipeline.sh
```

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
```

`events` 用来看实时阶段，`traces` 用来做事后复盘。

## 迁移注意事项

### Mac / Linux

推荐直接使用现有 bash 脚本：

```bash
cp .env.example .env
./scripts/bootstrap.sh
./scripts/start_all.sh
```

`.env` 不会提交到 GitHub，新电脑必须重新填写直播间 ID、token 和 API key。

### Windows

当前推荐使用 **WSL2 Ubuntu** 运行项目，OBS Studio 仍然安装在 Windows 宿主机。

```text
Windows OBS Studio
  + WSL2 Ubuntu 运行本项目
```

这样可以继续使用现有 `scripts/*.sh`。原生 Windows PowerShell 脚本尚未适配。

详见 [Windows迁移教程.md](Windows迁移教程.md)。

## 重要文档

- [全链路运行手册.md](全链路运行手册.md)
- [部署脚本说明.md](部署脚本说明.md)
- [Windows迁移教程.md](Windows迁移教程.md)

## 安全提醒

- 不要提交 `.env`
- 不要把 `AIBZ_TOKEN`、豆包 API Key、OBS 密码写进代码
- token 过期后更新 `.env` 并重启链路
