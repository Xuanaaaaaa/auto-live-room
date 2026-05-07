# Windows 本地 OBS、WSL 主链路与 automation 运行步骤

本流程需要三个部分一起运行：

- Windows 本地 OBS 和 `Obs_auto` 音频脚本。
- WSL 中的 `auto-live-room` 主链路。
- Windows 本地 `D:\workspace\automation` 小程序自动化 watcher。

## 1. 打开 OBS

在 Windows 本地打开 OBS，并确认已启用 OBS WebSocket，端口为 `4455`。

## 2. 启动 OBS 音频脚本

```powershell
cd D:\workspace\auto-live-room\Obs_auto

$env:OBS_PASSWORD="你的 OBS WebSocket 密码"

.\.venv\Scripts\python.exe obs_audio_player.py `
  --latest-glob "\\wsl.localhost\Ubuntu\home\hermes\auto-live-room\链路监控\events\events_*.jsonl" `
  --input-name "岗位语音" `
  --host "192.168.0.224" `
  --port 4455 `
  --path-mode wsl-to-windows
```

## 3. 首次确认 automation 配置

`automation` 项目位于：

```powershell
D:\workspace\automation
```

首次运行或换机器后，先确认 Node.js、依赖、微信开发者工具和本机配置。

```powershell
cd D:\workspace\automation

node -v
npm install miniprogram-automator
node scripts\init-local-config.js
```

当前这台机器的 `config\local.jsonl` 应至少包含以下关键信息：

```json
{"wechatDevtoolsCli":"D:/software/微信web开发者工具/cli.bat","wechatMiniprogramProject":"D:/aibz/dist/build/mp-weixin","wechatAutoPort":9420,"danmuJsonlDir":"\\\\wsl.localhost\\Ubuntu\\home\\hermes\\auto-live-room\\弹幕提取\\DouyinLiveWebFetcher\\output","noProxy":"127.0.0.1,localhost"}
```

同时确认微信开发者工具中已开启：

- 设置 > 安全 > 服务端口
- 设置 > 安全 > 多端插件服务端口

`watch-danmu.js` 启动时会检查 `9420` 端口；如果端口未监听，会自动调用 `cli.bat auto --project ... --auto-port 9420 --trust-project` 启动自动化模式。`cli.bat auto` 会打开一个新的微信开发者工具实例，登录状态不一定与手动打开的实例共享。

## 4. 启动 WSL 主链路

```powershell
wsl -d Ubuntu --cd /home/hermes/auto-live-room bash -lc "LIVE_ID=1231231231313 ./scripts/start_all.sh"
```

启动后，弹幕提取模块会向下面的目录写入 JSONL：

```text
\\wsl.localhost\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output
```

## 5. 启动 automation 弹幕 watcher

另开一个 PowerShell 窗口：

```powershell
cd D:\workspace\automation

$env:DANMU_LIVE_ID="1231231231313"
node watch-danmu.js
```

启动后 watcher 会自动：

- 连接微信开发者工具 `ws://127.0.0.1:9420`。
- 自动登录小程序测试账号。
- 监听主链路输出的最新 JSONL 文件。
- 将新弹幕中的岗位、城市、学历等字段转成小程序筛选条件。
- 串行执行小程序搜索、浏览详情，并在 `D:\workspace\automation\test-runs\watch-*` 写入日志和截图。

如果不想按直播间 ID 过滤，可以不设置 `DANMU_LIVE_ID`：

```powershell
cd D:\workspace\automation
node watch-danmu.js
```

## 6. 无直播测试时写入模拟弹幕

向当前最新文件追加模拟弹幕：

```text
\\wsl.localhost\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output\1231231231313_*.jsonl
```

automation watcher 启动时会从已有文件末尾开始读，不处理历史行。测试时请在 watcher 启动后再追加新的 JSONL 行。

## 7. 观察运行状态

OBS 侧：

- 观察 OBS 中的 `岗位语音` 媒体源是否播放音频。

automation 侧：

- 观察 PowerShell 窗口中的 `[watcher]`、`[enqueue]`、`[connect]`、`[login]` 日志。
- 查看 `D:\workspace\automation\test-runs\watch-*` 下的 `test.log` 和 `screenshots`。
- 若连接失败，优先检查微信开发者工具服务端口、`9420` 是否被占用、`config\local.jsonl` 中的 `wechatDevtoolsCli` 和 `wechatMiniprogramProject` 是否存在。

## 8. 停止 automation watcher

在 automation watcher 的 PowerShell 窗口按 `Ctrl+C`。

脚本会停止监听，并等待当前队列中的小程序自动化任务执行完后退出。

## 9. 停止 WSL 主链路

```powershell
wsl -d Ubuntu --cd /home/hermes/auto-live-room ./scripts/stop_all.sh
```

## 10. 停止 OBS 音频脚本

```powershell
Get-Process | Where-Object { $_.Path -like "D:\workspace\auto-live-room\Obs_auto\*" } | Stop-Process
```
