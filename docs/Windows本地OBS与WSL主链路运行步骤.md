# Windows 本地 OBS 与 WSL 主链路运行步骤

## 1. 打开 OBS

在 Windows 本地打开 OBS。

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

## 3. 启动 WSL 主链路

```powershell
wsl -d Ubuntu --cd /home/hermes/auto-live-room bash -lc "LIVE_ID=1231231231313 ./scripts/start_all.sh"
```

## 4. 无直播测试时写入模拟弹幕

向当前最新文件追加模拟弹幕：

```text
\\wsl.localhost\Ubuntu\home\hermes\auto-live-room\弹幕提取\DouyinLiveWebFetcher\output\1231231231313_*.jsonl
```

## 5. 观察 OBS

观察 OBS 中的 `岗位语音` 媒体源是否播放音频。

## 6. 停止 WSL 主链路

```powershell
wsl -d Ubuntu --cd /home/hermes/auto-live-room ./scripts/stop_all.sh
```

## 7. 停止 OBS 音频脚本

```powershell
Get-Process | Where-Object { $_.Path -like "D:\workspace\auto-live-room\Obs_auto\*" } | Stop-Process
```
