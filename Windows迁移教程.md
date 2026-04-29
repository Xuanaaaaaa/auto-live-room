# Windows 迁移教程

本文说明如何把自动化直播间项目迁移到 Windows 电脑运行。

当前推荐方案是：**Windows 安装 OBS Studio，项目运行在 WSL2 Ubuntu 中**。这样可以继续使用现有的 bash 脚本、Python venv、日志和后台进程管理方式，迁移成本最低。

## 1. 当前适配结论

### 推荐：WSL2 Ubuntu

适合目标：

- 尽量复用现有 `scripts/*.sh`
- 不重写 PowerShell 脚本
- 保持和 Mac/Linux 一致的目录、venv、pid、日志逻辑

项目主体在 WSL2 里运行：

```text
Windows
  ├─ OBS Studio：安装并运行在 Windows 宿主机
  └─ WSL2 Ubuntu：运行自动化直播间项目
```

### 暂不推荐：原生 Windows 直接运行

当前仓库还没有提供原生 Windows 的 `.ps1` 管理脚本。直接在 PowerShell 里跑会遇到这些差异：

- `venv/bin/python` 在 Windows 原生环境应改为 `venv\Scripts\python.exe`
- `bash` 脚本、`pid` 文件、`kill` 停进程都不是 PowerShell 原生方式
- 中文路径、依赖编译、OBS WebSocket 地址都需要单独验证

如果后续必须原生 Windows 运行，建议另做一套：

- `scripts/start_all.ps1`
- `scripts/stop_all.ps1`
- `scripts/status.ps1`
- `scripts/logs.ps1`

## 2. Windows 侧准备

1. 安装 WSL2 和 Ubuntu。
2. 安装 OBS Studio。
3. 如果要用 OBS 文本联动，开启 OBS WebSocket，并记录端口和密码。
4. 确认 Windows 网络可以访问：
   - GitHub
   - Python 包源
   - 抖音直播间 WebSocket
   - aibz 接口
   - 豆包 LLM/TTS 服务

## 3. WSL2 Ubuntu 准备

在 WSL2 Ubuntu 里安装基础工具：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

拉取项目：

```bash
git clone https://github.com/Xuanaaaaaa/auto-live-room.git
cd auto-live-room
```

准备本机配置：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
LIVE_ID=你的直播间ID
AIBZ_TOKEN=你的token不要带Bearer前缀
DOUBAO_LLM_API_KEY=你的豆包LLMKey
DOUBAO_TTS_API_KEY=你的豆包TTSKey
```

如果暂时不接 OBS，可以先让 OBS 相关配置保持默认。

## 4. 初始化依赖

在 WSL2 项目根目录执行：

```bash
./scripts/bootstrap.sh
```

它会分别创建并安装：

- `弹幕提取/DouyinLiveWebFetcher/venv`
- `语音生成/.venv`
- `Obs_auto/.venv`

如果依赖安装失败，优先检查网络和 Python 版本；必要时换 pip 源。

## 5. 启动全链路

后台启动弹幕抓取、编排器、只读监控器：

```bash
./scripts/start_all.sh
```

查看状态：

```bash
./scripts/status.sh
```

看实时监控摘要：

```bash
./scripts/logs.sh monitor
```

看底层弹幕抓取：

```bash
./scripts/logs.sh danmu
```

看编排器：

```bash
./scripts/logs.sh pipeline
```

停止：

```bash
./scripts/stop_all.sh
```

## 6. OBS 联动注意事项

OBS 如果运行在 Windows，项目如果运行在 WSL2，`OBS_HOST=localhost` 不一定能连到 Windows 宿主机。

可以在 WSL2 里先查看 Windows 宿主机网关地址：

```bash
cat /etc/resolv.conf | grep nameserver
```

把输出里的 IP 填到 `.env`：

```bash
OBS_HOST=上一步看到的IP
OBS_PORT=4455
OBS_PASSWORD=你的OBSWebSocket密码
```

然后单独测试 OBS 文本更新：

```bash
OBS_DRY_RUN=1 OBS_ONCE=1 ./scripts/run_obs_text.sh
```

如果 dry-run 正常，再关闭 `OBS_DRY_RUN` 后测试真实 OBS 连接：

```bash
./scripts/run_obs_text.sh
```

注意：当前 `start_all.sh` 默认只启动弹幕抓取、编排器、监控器，不自动启动 OBS 文本更新器。OBS 文本联动仍然用：

```bash
./scripts/run_obs_text.sh
```

## 7. 音频播放注意事项

当前链路会生成 mp3 到：

```text
链路监控/audio/trace_<trace_id>.mp3
```

如果只是验证生成结果，可以直接在 WSL 文件系统或 Windows 文件管理器里找到该文件播放。

如果要让生成后的 mp3 自动播放进 Windows OBS，使用独立旁路脚本：

```bash
./scripts/run_obs_audio.sh
```

OBS 中先创建一个媒体源，名称默认：

```text
岗位语音
```

WSL 里的 Linux 路径和 Windows OBS 可读路径不同。推荐把音频输出放到 Windows 可读目录，并开启路径转换：

```bash
AUDIO_DIR=/mnt/c/Users/你的Windows用户名/auto-live-room-audio
OBS_AUDIO_PATH_MODE=wsl-to-windows
OBS_AUDIO_INPUT_NAME=岗位语音
```

同时 `.env` 里的 `OBS_HOST` 要指向 Windows 宿主机 IP，`OBS_PORT` 和 `OBS_PASSWORD` 要与 OBS WebSocket 设置一致。

先 dry-run：

```bash
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

确认能找到最新 `audio_path` 后，再关闭 `OBS_AUDIO_DRY_RUN` 正式连接 OBS：

```bash
./scripts/run_obs_audio.sh
```

## 8. 常见问题

### 启动后没有下游反应

先看三份日志：

```bash
./scripts/logs.sh danmu
./scripts/logs.sh pipeline
./scripts/logs.sh monitor
```

重点确认：

- `danmu.log` 是否出现 `WebSocket连接成功`
- `danmu.log` 是否看到 `【聊天msg】`
- `弹幕提取/DouyinLiveWebFetcher/output/${LIVE_ID}_*.jsonl` 是否出现新行
- `pipeline.log` 是否打印 `received`
- `monitor.log` 是否打印 `completed`

### token 失效

如果 `pipeline.log` 出现 `JobSearchError code=301`，说明 `AIBZ_TOKEN` 过期或无效。重新抓 token，更新 `.env`，再重启：

```bash
./scripts/stop_all.sh
./scripts/start_all.sh
```

### OBS 连不上

优先检查：

- Windows OBS 是否已启动
- OBS WebSocket 是否开启
- `.env` 的 `OBS_HOST` 是否是 Windows 宿主机 IP
- `OBS_PORT` 和 `OBS_PASSWORD` 是否正确
- Windows 防火墙是否拦截

## 9. 迁移检查清单

- 已在 WSL2 Ubuntu 中 clone 项目
- 已复制 `.env.example` 为 `.env`
- 已填写 `LIVE_ID`
- 已填写 `AIBZ_TOKEN`
- 已填写豆包 LLM/TTS Key
- 已执行 `./scripts/bootstrap.sh`
- 已执行 `./scripts/start_all.sh`
- `./scripts/status.sh` 显示三个进程 running
- `./scripts/logs.sh monitor` 能看到事件流
- 如需 OBS，已单独测试 `./scripts/run_obs_text.sh`
- 如需 OBS 自动播放 TTS，已单独测试 `./scripts/run_obs_audio.sh`
