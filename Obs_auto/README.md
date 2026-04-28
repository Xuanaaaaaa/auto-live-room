# OBS JSONL Text Updater

把上游 JSONL 文件中最后一条记录的 `raw_text` 显示到 OBS 文字源里，显示格式为：

```text
当前查询：raw_text
```

## 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

## 先不连接 OBS，验证 JSONL 读取

```bash
python3 obs_jsonl_text_updater.py --file examples/upstream.jsonl --dry-run --once
```

预期输出：

```text
当前查询：26的，电子商务
```

## 连接 OBS 后运行

1. 安装 OBS Studio。
2. 在 OBS 中创建一个文本源，名称建议设为 `当前查询`。
3. 打开 OBS WebSocket 服务，默认端口通常是 `4455`，并记下密码。
4. 运行脚本：

```bash
OBS_PASSWORD="你的OBS WebSocket密码" python3 obs_jsonl_text_updater.py --file /path/to/upstream.jsonl --input-name 当前查询
```

脚本会优先监听文件变化，发现新记录后把 OBS 文本源更新为 `当前查询：...`。如果没有安装 `watchdog`，会自动退回到每 0.3 秒检查一次。

弹幕端每次启动都会生成新的 `output/{live_id}_{时间戳}.jsonl` 文件。为了避免每次手动改路径，推荐用 `--latest-glob` 自动选择最新文件：

```bash
OBS_PASSWORD="你的OBS WebSocket密码" \
python3 obs_jsonl_text_updater.py \
  --latest-glob "<项目目录>/弹幕提取/DouyinLiveWebFetcher/output/459180008319_*.jsonl" \
  --input-name 当前查询 \
  --field raw_text \
  --wrap-width 36 \
  --max-lines 3
```

如果消费的是链路监控 trace 文件，弹幕原文在嵌套字段里，可以这样读取：

```bash
OBS_PASSWORD="你的OBS WebSocket密码" \
python3 obs_jsonl_text_updater.py \
  --latest-glob "<项目目录>/链路监控/traces/traces_*.jsonl" \
  --input-name 当前查询 \
  --field danmu.raw_text \
  --wrap-width 36 \
  --max-lines 3
```

## 常用参数

```bash
python3 obs_jsonl_text_updater.py \
  --file /path/to/upstream.jsonl \
  --input-name 当前查询 \
  --host localhost \
  --port 4455 \
  --password "你的OBS WebSocket密码" \
  --interval 0.3 \
  --wrap-width 36
```

- `--file`：上游 JSONL 文件路径，与 `--latest-glob` 二选一。
- `--latest-glob`：自动选择匹配到的最新 JSONL 文件，并在运行中切换到更新的文件。
- `--input-name`：OBS 里的文本源名称。
- `--prefix`：显示前缀，默认 `当前查询：`。
- `--field`：读取字段，默认 `raw_text`；支持 `danmu.raw_text` 这类点路径。
- `--wrap-width`：自动换行宽度，中文字符按 2 个宽度计算；默认不换行。
- `--max-lines`：最多显示几行，默认不限制。
- `--dry-run`：只打印结果，不连接 OBS。
- `--once`：只更新一次后退出。
- `--watch-mode`：监听模式，默认 `auto`；可选 `watchdog` 或 `poll`。
