# Windows + WSL2 + OBS 音频播放对接手册

本文用于把自动化直播间项目迁移到 Windows 电脑后，让 **WSL2 Ubuntu 中生成的 TTS mp3** 自动通过 **Windows 本机 OBS** 播放到直播中。

这套方案是旁路方案，不改主链路：

```text
WSL2 Ubuntu 主链路
  -> 生成 TTS mp3
  -> 写入 链路监控/events/events_*.jsonl，包含 audio_path
  -> scripts/run_obs_audio.sh 监听 audio_path
  -> 通过 OBS WebSocket 控制 Windows OBS 媒体源播放
```

## 1. 前置条件

### 1.1 Windows 侧

必须准备：

1. Windows 已安装 OBS Studio。
2. OBS 中已启用 WebSocket 服务。
3. OBS 中已创建一个媒体源，名称建议为：

```text
岗位语音
```

媒体源设置建议：

- 类型：媒体源
- 本地文件：先任选一个 mp3 占位
- 循环：关闭
- 源激活时重新开始播放：开启

OBS WebSocket 信息需要记录：

```text
OBS_HOST=Windows 宿主机 IP
OBS_PORT=4455
OBS_PASSWORD=你的 OBS WebSocket 密码
```

端口默认通常是 `4455`。

### 1.2 WSL2 Ubuntu 侧

必须准备：

1. 已安装 WSL2 Ubuntu。
2. Ubuntu 中能访问 GitHub。
3. Ubuntu 中已安装基础工具：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

4. 自动化直播间项目已经 clone 或已经存在。
5. 项目已经执行过：

```bash
./scripts/bootstrap.sh
```

这样会创建：

```text
弹幕提取/DouyinLiveWebFetcher/venv
语音生成/.venv
Obs_auto/.venv
```

OBS 音频播放脚本依赖 `Obs_auto/.venv`。

## 2. 同步最新代码

在 WSL2 Ubuntu 项目目录中执行：

```bash
cd /path/to/auto-live-room
git pull
```

确认已经有这两个文件：

```bash
ls Obs_auto/obs_audio_player.py
ls scripts/run_obs_audio.sh
```

如果文件不存在，说明代码还不是最新，先确认当前分支和远端：

```bash
git branch --show-current
git remote -v
```

## 3. 配置 .env

复制配置模板：

```bash
cp .env.example .env
```

如果 `.env` 已存在，不要覆盖，直接编辑：

```bash
nano .env
```

主链路至少需要：

```bash
LIVE_ID=你的直播间ID
AIBZ_TOKEN=你的token不要带Bearer前缀
DOUBAO_LLM_API_KEY=你的豆包LLMKey
DOUBAO_TTS_API_KEY=你的豆包TTSKey
```

OBS 音频播放需要：

```bash
OBS_HOST=Windows宿主机IP
OBS_PORT=4455
OBS_PASSWORD=你的OBSWebSocket密码
OBS_AUDIO_INPUT_NAME=岗位语音
OBS_AUDIO_PATH_MODE=wsl-to-windows
```

最重要的是音频输出目录。为了让 Windows OBS 能读到 mp3，建议把 TTS 音频写到 Windows C 盘目录：

```bash
AUDIO_DIR=/mnt/c/Users/你的Windows用户名/auto-live-room-audio
```

例如：

```bash
AUDIO_DIR=/mnt/c/Users/zhou/auto-live-room-audio
```

创建目录：

```bash
mkdir -p "$AUDIO_DIR"
```

注意：不要把 `AUDIO_DIR` 放在纯 WSL 路径，比如 `/home/xxx/...`，否则 Windows OBS 可能读不到。

## 4. 获取 Windows 宿主机 IP

在 WSL2 Ubuntu 中执行：

```bash
cat /etc/resolv.conf | grep nameserver
```

输出类似：

```text
nameserver 172.22.96.1
```

把这个 IP 填进 `.env`：

```bash
OBS_HOST=172.22.96.1
```

如果 `OBS_HOST=localhost` 能连通，也可以用 `localhost`；但 WSL2 下更推荐使用上面的宿主机 IP。

## 5. 测试 OBS WebSocket 连通性

先确认 Windows OBS 已打开，WebSocket 已启用。

在 WSL2 中测试端口：

```bash
nc -vz "$OBS_HOST" "$OBS_PORT"
```

如果没有 `nc`：

```bash
sudo apt install -y netcat-openbsd
```

成功时通常能看到：

```text
succeeded
```

如果失败，优先检查：

- Windows OBS 是否已经打开
- OBS WebSocket 是否启用
- 端口是否是 `4455`
- Windows 防火墙是否拦截
- `.env` 中 `OBS_HOST` 是否正确

## 6. 先跑主链路生成一条音频

启动主链路：

```bash
./scripts/start_all.sh
```

启动时脚本会提示输入 `LIVE_ID`。如果 `.env` 里已经填了默认值，直接回车即可。

观察链路状态：

```bash
./scripts/status.sh
./scripts/logs.sh monitor
```

当有弹幕命中并完成 TTS 后，应出现类似：

```text
completed audio=.../trace_xxx.mp3
```

也可以检查音频目录：

```bash
ls -lt "$AUDIO_DIR" | head
```

确认有 `trace_*.mp3`。

## 7. dry-run 测试音频播放器

先不连接 OBS，只验证脚本能从 events 文件里找到最新 `audio_path`，并能把 `/mnt/c/...` 转成 Windows 路径。

```bash
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

期望输出类似：

```text
Starting OBS audio player...
[audio] trace=xxx stage=completed path=C:\Users\你的Windows用户名\auto-live-room-audio\trace_xxx.mp3
[dry-run] play C:\Users\你的Windows用户名\auto-live-room-audio\trace_xxx.mp3
```

如果提示找不到 playable audio event，说明当前最新 events 文件里还没有成功 TTS。可以：

1. 先让直播间触发一条查询弹幕。
2. 或指定一个已知有音频的 events 文件：

```bash
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 \
OBS_AUDIO_EVENTS_FILE=链路监控/events/events_YYYYMMDD_HHMMSS.jsonl \
./scripts/run_obs_audio.sh
```

## 8. 真实连接 OBS 播放一条

dry-run 正常后，测试真实播放：

```bash
OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

如果 `.env` 中没有写 `OBS_PASSWORD`，也可以临时传：

```bash
OBS_PASSWORD="你的OBSWebSocket密码" OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

OBS 中应该播放最新一条 TTS mp3。

如果脚本没有报错但听不到声音，检查：

- OBS 中媒体源名称是否与 `OBS_AUDIO_INPUT_NAME` 完全一致
- OBS 音频混音器中该媒体源是否静音
- OBS 是否把该媒体源加入当前场景
- Windows 系统音量和 OBS 输出音轨是否正常
- mp3 文件在 Windows 文件管理器里是否能打开播放

## 9. 直播时常驻运行

本地测试通过后，直播时建议开两个终端。

终端 A：主链路

```bash
./scripts/start_all.sh
```

终端 B：OBS 音频播放旁路

```bash
./scripts/run_obs_audio.sh
```

`run_obs_audio.sh` 默认只处理新追加事件，不会把旧音频全部重播一遍。

如果还需要 OBS 文字源同步，可以再开终端 C：

```bash
./scripts/run_obs_text.sh
```

注意：`start_all.sh` 默认只启动弹幕抓取、编排器、监控器，不会自动启动 OBS 音频播放和 OBS 文字更新。

## 10. 推荐 .env 示例

下面是 Windows + WSL2 + OBS 自动播放的关键配置示例：

```bash
LIVE_ID=你的直播间ID
AIBZ_TOKEN=你的token不要带Bearer前缀

DOUBAO_LLM_API_KEY=你的豆包LLMKey
DOUBAO_TTS_API_KEY=你的豆包TTSKey

AUDIO_DIR=/mnt/c/Users/你的Windows用户名/auto-live-room-audio

OBS_HOST=172.xx.xx.1
OBS_PORT=4455
OBS_PASSWORD=你的OBSWebSocket密码

OBS_AUDIO_INPUT_NAME=岗位语音
OBS_AUDIO_PATH_MODE=wsl-to-windows
OBS_AUDIO_DRY_RUN=0
OBS_AUDIO_ONCE=0
```

如果要测试一次后退出：

```bash
OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

如果只想看脚本会播放什么，不连接 OBS：

```bash
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

## 11. 常见问题

### 11.1 OBS 连不上

现象：

```text
ConnectionRefusedError
TimeoutError
```

排查：

1. Windows OBS 是否打开。
2. WebSocket 是否启用。
3. `OBS_HOST` 是否是 Windows 宿主机 IP。
4. `OBS_PORT` 是否是 `4455`。
5. Windows 防火墙是否允许 OBS 接收连接。

### 11.2 密码错误

现象通常是认证失败。

处理：

1. 打开 OBS WebSocket 设置。
2. 重新复制密码。
3. 更新 `.env` 中的 `OBS_PASSWORD`。

### 11.3 媒体源不存在

现象通常是 OBS 返回 input not found。

处理：

1. 确认 OBS 来源里有媒体源。
2. 名称与 `OBS_AUDIO_INPUT_NAME` 完全一致。
3. 默认名称是 `岗位语音`。

### 11.4 路径传给 OBS 后不播放

优先检查脚本输出的路径是否是 Windows 路径：

```text
C:\Users\...\trace_xxx.mp3
```

如果仍是：

```text
/mnt/c/...
```

说明没有开启路径转换，设置：

```bash
OBS_AUDIO_PATH_MODE=wsl-to-windows
```

如果路径是：

```text
/home/...
```

说明音频生成在 WSL 私有目录里，Windows OBS 可能读不到。改用：

```bash
AUDIO_DIR=/mnt/c/Users/你的Windows用户名/auto-live-room-audio
```

然后重启主链路重新生成音频。

### 11.5 dry-run 找不到音频事件

说明最新 events 文件里没有成功 TTS 的 `audio_path`。

检查：

```bash
ls -lt 链路监控/events | head
tail -n 20 链路监控/events/events_*.jsonl
```

确认里面有：

```json
{"stage":"completed","audio_path":"...trace_xxx.mp3"}
```

如果没有，先排查主链路 TTS 是否成功。

## 12. 最小测试流程

只想快速验证时，按这个顺序：

```bash
git pull
./scripts/bootstrap.sh
nano .env
mkdir -p "$AUDIO_DIR"
./scripts/start_all.sh
```

等主链路生成一条音频后：

```bash
OBS_AUDIO_DRY_RUN=1 OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
OBS_AUDIO_ONCE=1 ./scripts/run_obs_audio.sh
```

确认 OBS 播放后，直播时常驻：

```bash
./scripts/run_obs_audio.sh
```

