# OBS 直播文字自动刷新设置说明

这份说明从安装 OBS 开始，到设置竖屏直播画面，再到运行本项目脚本，把 JSONL 文件最后一条 `raw_text` 实时显示到 OBS 直播页面中。

## 1. 安装 OBS Studio

1. 打开 OBS 官网：https://obsproject.com/
2. 下载 macOS 版本。
3. 安装并打开 OBS Studio。

新版 OBS 一般已经内置 WebSocket 服务，不需要额外安装插件。

## 2. 设置手机直播竖屏画布

在 OBS 中打开：

```text
设置 -> 视频
```

推荐配置：

```text
基础画布分辨率：1080x1920
输出缩放分辨率：1080x1920
常用 FPS 值：30
```

如果电脑性能一般，可以改成：

```text
基础画布分辨率：720x1280
输出缩放分辨率：720x1280
常用 FPS 值：30
```

建议先用 `1080x1920`，如果画面卡顿再降到 `720x1280`。

## 3. 添加直播画面来源

在 OBS 主界面的“来源”区域点击 `+`，根据实际需要添加：

```text
显示器采集
窗口采集
浏览器
文本
```

如果使用“显示器采集”，它会采集整块屏幕，但可以在 OBS 预览画布中裁剪和缩放：

- 拖动红框：移动位置。
- 拖动红框四角：缩放大小。
- 按住 `Option` 再拖动红框边缘：裁剪画面。
- 右键来源，选择 `变换 -> 编辑变换`：精确设置位置、大小和裁剪。

调好后可以点击“来源”列表中的小锁，避免误拖。

## 4. 创建要被脚本控制的文字源

在 OBS 的“来源”区域点击 `+`：

```text
文本
```

创建时建议这样设置：

```text
来源名称：当前查询
文本输入模式：手动输入
初始内容：当前查询：
字体：PingFang SC / 苹方-简
```

注意：文本输入模式要选“手动输入”，不要选“从文件读取”。本项目脚本会通过 OBS WebSocket 直接更新这个文本源。

推荐文字样式：

```text
字体：PingFang SC / 苹方-简
字号：42-56，1080x1920 画布下可先试 48
颜色：白色
描边：开启，黑色，2-4px
```

手机直播平台右侧和底部会有按钮、评论区、输入区等遮挡，重要文字不要贴边。1080x1920 画布可以先把文字放在：

```text
x：80
y：1500
宽度：900 左右
```

## 5. 启用 OBS WebSocket

在 OBS 中打开：

```text
工具 -> WebSocket 服务器设置
```

确认：

```text
启用 WebSocket 服务器：勾选
服务器端口：4455
启用身份验证：勾选
密码：使用你自己的 OBS WebSocket 密码
```

记住密码，后面运行脚本时需要通过 `OBS_PASSWORD` 传入。

## 6. 准备项目虚拟环境

进入项目目录：

```bash
cd <项目目录>/Obs_auto
```

如果还没有虚拟环境，创建：

```bash
python3 -m venv .venv
```

安装依赖：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

也可以先激活虚拟环境：

```bash
source .venv/bin/activate
```

激活后命令里的 `.venv/bin/python` 可以简写成 `python`。

## 7. 先验证 JSONL 文件读取

先用项目自带示例验证：

```bash
cd <项目目录>/Obs_auto

.venv/bin/python obs_jsonl_text_updater.py \
  --file examples/upstream.jsonl \
  --dry-run \
  --once
```

正常会输出：

```text
当前查询：26的，电子商务
```

再用真实上游文件验证：

```bash
cd <项目目录>/Obs_auto

.venv/bin/python obs_jsonl_text_updater.py \
  --file "你的上游文件地址" \
  --dry-run
```

此时脚本不会连接 OBS，只会在终端打印将要显示的文字。上游 JSONL 文件追加新记录后，终端应该自动输出新的：

```text
当前查询：...
```

弹幕抓取端每次启动都会生成新的 `output/{live_id}_{时间戳}.jsonl`。如果不想每次手动替换路径，可以用最新文件匹配：

```bash
cd <项目目录>/Obs_auto

.venv/bin/python obs_jsonl_text_updater.py \
  --latest-glob "<项目目录>/弹幕提取/DouyinLiveWebFetcher/output/459180008319_*.jsonl" \
  --field raw_text \
  --dry-run
```

确认 dry-run 正常后，再进入下一步连接 OBS。

## 8. 正式连接 OBS 运行

确保：

- OBS 已打开。
- OBS WebSocket 已启用。
- 端口是 `4455`。
- OBS 中已经有一个文本源，名称是 `当前查询`。

运行：

```bash
cd <项目目录>/Obs_auto

OBS_PASSWORD="你的OBS WebSocket密码" \
.venv/bin/python obs_jsonl_text_updater.py \
  --port 4455 \
  --latest-glob "<项目目录>/弹幕提取/DouyinLiveWebFetcher/output/459180008319_*.jsonl" \
  --input-name 当前查询 \
  --field raw_text \
  --wrap-width 36 \
  --max-lines 3
```

说明：

- `OBS_PASSWORD`：换成你的 OBS WebSocket 密码。
- `--input-name 当前查询`：必须和 OBS 里的文字源名称完全一致。
- `--latest-glob`：自动选择最新的弹幕结构化 JSONL 文件。也可以换成固定 `--file`。
- `--field raw_text`：显示弹幕命中记录里的原始弹幕文本。
- `--wrap-width 36`：自动换行宽度，中文字符按 2 个宽度计算。
- `--max-lines 3`：最多显示 3 行，避免文字占满屏幕。

如果你要从链路监控 trace 文件读取弹幕原文，字段要换成嵌套路径：

```bash
OBS_PASSWORD="你的OBS WebSocket密码" \
.venv/bin/python obs_jsonl_text_updater.py \
  --port 4455 \
  --latest-glob "<项目目录>/链路监控/traces/traces_*.jsonl" \
  --input-name 当前查询 \
  --field danmu.raw_text \
  --wrap-width 36 \
  --max-lines 3
```

如果想显示更多行，可以改成：

```bash
--max-lines 4
```

如果文字区域更宽，可以改成：

```bash
--wrap-width 44
```

如果文字区域更窄，可以改成：

```bash
--wrap-width 28
```

## 9. 常见问题

### 连接 OBS 超时

检查：

```text
OBS 是否已经打开
OBS WebSocket 是否已经启用
端口是否是 4455
密码是否正确
命令里是否使用了 --host 127.0.0.1
```

可以测试端口：

```bash
nc -vz 127.0.0.1 4455
```

如果显示 `succeeded`，说明端口可连接。

### OBS 文字没有变化

检查：

```text
OBS 文字源名称是否是 当前查询
命令里的 --input-name 是否也是 当前查询
文本源是否被隐藏
JSONL 文件最后一条是否有 raw_text 字段
```

### 中文显示异常

在 OBS 文本源里选择中文字体：

```text
PingFang SC / 苹方-简
Heiti SC / 黑体-简
Songti SC / 宋体-简
```

优先推荐 `PingFang SC / 苹方-简`。

### 文字太长溢出屏幕

正式运行命令中加：

```bash
--wrap-width 36 --max-lines 3
```

根据 OBS 里文字框的宽度调节：

```text
28：更窄，换行更多
36：推荐先试
44：更宽，换行更少
```

## 10. 停止脚本

在运行脚本的终端中按：

```text
Control + C
```

即可停止。
