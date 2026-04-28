# 项目迁移指南（Mac → Mac）

把本项目从一台 Mac 迁移到另一台 Mac 的完整步骤。

## 不能直接整个复制的原因

| 原因 | 说明 |
|---|---|
| **venv 不可移植** | `venv/bin/python` 是写死的旧 Mac 绝对路径，激活脚本里的 shebang 也指向原机器 |
| **mini_racer 是 native 包** | 当前装的是 `macosx_11_0_arm64`（Apple Silicon）轮子，跨架构无法运行（Intel ↔ M 芯片必须重装） |
| **Python 版本依赖** | site-packages 与解释器版本绑定，两台机器 Python 版本不一致时大概率不兼容 |

结论：**源码可以直接拷贝，依赖（venv）必须在新 Mac 上重建。**

---

## 哪些能复制，哪些不能

| 路径 | 是否复制 | 说明 |
|---|---|---|
| `*.py` `*.js` `*.proto` `requirements.txt` `README.MD` | ✅ | 纯文本源码，跨平台无影响 |
| `protobuf/douyin.py` | ✅ | 已编译好的 protobuf Python 代码 |
| `danmu/` | ✅ | 已抓到的弹幕文本，跨平台无影响 |
| `MIGRATION.md`（本文件） | ✅ | 文档 |
| `venv/` | ❌ | **必须重建** |
| `__pycache__/` | ❌ | 不必复制，运行时自动生成 |
| `.git/` | ⚠️ | 可复制但更建议重新 clone（更干净） |

---

## 方式 A：重新 clone（推荐，最干净）

适用于：未对源码做任何修改，或修改已 commit/push 到自己的仓库。

```bash
# 1. 在新 Mac 上 clone
git clone https://github.com/saermart/DouyinLiveWebFetcher.git
cd DouyinLiveWebFetcher

# 2. 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 4. （可选）从旧 Mac 复制已抓到的弹幕
#    在旧 Mac 上：scp -r danmu/ user@新Mac:/path/to/DouyinLiveWebFetcher/

# 5. 运行
python main.py
```

> 注意：本项目已对 `liveMan.py` 做过改动（弹幕落盘到 `danmu/`），重新 clone 后会丢失这些改动。如果改动还没推到自己的仓库，请用方式 B。

---

## 方式 B：打包源码迁移（保留本地改动）

适用于：本地对代码做了修改（比如已加上的弹幕落盘逻辑），还没推到远程。

### 第 1 步：在旧 Mac 打包

```bash
cd /Users/zhoukexuanmac/workspace/弹幕提取

tar -czf douyin.tgz \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  DouyinLiveWebFetcher
```

> 排除 `venv` 和 `__pycache__` 是必须的；`.git` 可视情况保留。

### 第 2 步：传到新 Mac

任选一种：

```bash
# 方法 1：scp（如果两台机器在同网段或可直连）
scp douyin.tgz user@新Mac的IP:/期望路径/

# 方法 2：AirDrop / U 盘 / 网盘 直接拷过去
```

### 第 3 步：在新 Mac 上解压并配置

```bash
cd /期望路径
tar -xzf douyin.tgz
cd DouyinLiveWebFetcher

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 运行
python main.py
```

---

## 新 Mac 的环境要求

迁移前先确认新 Mac 上具备：

| 依赖 | 版本要求 | 检查命令 |
|---|---|---|
| Python | 3.7+（推荐 3.9） | `python3 --version` |
| Node.js | v18+ | `node --version` |
| pip | 任意 | `python3 -m pip --version` |

> `protoc` 不需要安装（项目里 `protobuf/douyin.py` 已经预编译好）。

如果新 Mac 没有 Node.js，建议用 Homebrew 装：

```bash
brew install node
```

---

## 验证迁移成功

进入项目目录，激活 venv 后执行：

```bash
python -c "
import warnings; warnings.filterwarnings('ignore')
from py_mini_racer import MiniRacer
from liveMan import DouyinLiveWebFetcher
ctx = MiniRacer()
print('mini_racer JS 测试:', ctx.eval('1+2'))
print('OK')
"
```

输出 `mini_racer JS 测试: 3` 和 `OK` 即配置成功。

---

## 常见问题

### Q1：新 Mac 是 Intel 芯片，旧 Mac 是 Apple Silicon（或反之），有影响吗？
有。`mini_racer` 是 native 二进制，架构必须匹配。但只要按上面步骤在新 Mac 上重新 `pip install`，pip 会自动下载对应架构的 wheel，无需手动处理。

### Q2：两台 Mac 的 Python 版本不一样怎么办？
只要都是 3.7+ 一般都能装上，但建议保持一致（如都用 3.9）以避免极少数兼容问题。多版本可用 `pyenv` 管理。

### Q3：pip install 时报 SSL/OpenSSL 警告？
是 macOS 自带 LibreSSL 触发的 `urllib3` 警告，不影响运行，可忽略。如果介意可换用 Homebrew 安装的 Python。

### Q4：能不能直接复制 `venv/`？
不行。venv 里有大量绝对路径与 native 二进制，复制过去基本不可用。**永远在目标机器上重建虚拟环境。**

### Q5：抖音签名失效（连不上 wss）怎么办？
那是项目本身的问题，不是迁移问题。需要更新 `sign.js` —— 关注上游仓库 `https://github.com/saermart/DouyinLiveWebFetcher` 的更新。
