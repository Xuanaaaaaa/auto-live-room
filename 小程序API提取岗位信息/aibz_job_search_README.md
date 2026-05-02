# aibz 岗位搜索接口直连脚本

直接调用 aibz 后端 `/search/job/match/conditions` 接口，绕开小程序前端。脚本完成签名、参数清洗、响应整理和结果保存。

## 文件

- `aibz_job_search.py` — 脚本主体
- `aibz_job_search_README.md` — 本说明文档

两个文件均放在 `/Users/zhoukexuanmac/workspace/自动化直播间/小程序API提取岗位信息/` 下，独立于 `aibz` 项目运行。

---

## 1. 环境准备

需要 Python 3.7+。仅依赖一个第三方库：

```bash
pip install requests
```

---

## 2. 准备 access_token

后端要求登录态。token 来源：

1. 用微信开发者工具打开 aibz 小程序，登录账号
2. 打开 Network 面板，触发任意接口请求
3. 找到请求头 `Authorization: Bearer xxxxxxxx`，复制 `Bearer` **后面**的字符串
4. 填到 `aibz_job_search.py` 文件底部 `ACCESS_TOKEN = ""` 里，或按下面“手工测试”里的命令临时输入

> token 有有效期，过期会收到 `code: 301` 异常，需要重新抓。

---

## 3. 运行

填好 token 后：

```bash
cd /Users/zhoukexuanmac/workspace/自动化直播间/小程序API提取岗位信息
python aibz_job_search.py
```

脚本会：

1. 用示例入参调用一次接口
2. 控制台打印 `count` 和首条岗位摘要
3. 在当前目录生成 `job_search_YYYYMMDD_HHMMSS.json`，含完整响应

---

## 4. 手工测试

下面的命令都在脚本目录执行：

```bash
cd /Users/zhoukexuanmac/workspace/自动化直播间/小程序API提取岗位信息
```

### 4.1 检查 Python 与依赖

```bash
python3 --version
python3 -c 'import requests; print(requests.__version__)'
```

期望：Python 版本为 3.7+，并能正常打印 `requests` 版本。

### 4.2 语法检查

如果本机 Python 没有缓存目录权限，可以把字节码缓存放到 `/tmp`：

```bash
PYTHONPYCACHEPREFIX=/tmp/aibz_job_search_pycache python3 -m py_compile aibz_job_search.py
```

期望：命令无输出且退出码为 0。

### 4.3 离线 smoke test

这个测试不访问网络，只验证参数清洗、签名、响应展平等核心逻辑：

```bash
PYTHONPYCACHEPREFIX=/tmp/aibz_job_search_pycache python3 - <<'PY'
import aibz_job_search as m

cleaned = m._clean_params({
    "major": "不限",
    "education": "本科",
    "intention_job": [],
    "intention_location": ["上海"],
    "is_unlimited_major": 0,
})
assert cleaned == {
    "education": "本科",
    "intention_location": ["上海"],
    "is_unlimited_major": 0,
}

sign, ts, body = m._build_signature({"b": 2, "a": "计算机"})
assert body == '{"a":"计算机","b":2}'
assert sign and len(sign) == 32
assert len(ts) == 12

item = m._flatten_jobs({"id": 1, "company_name": "X", "jobs": {"name": "后端", "city": "北京"}})
assert item["name"] == "后端"
assert item["city"] == "北京"
assert "jobs" not in item

print("offline smoke test ok")
PY
```

期望：打印 `offline smoke test ok`。

### 4.4 真实接口测试

真实接口测试需要有效 `access_token`。下面命令会隐藏输入 token，不需要把 token 写进源码；回车后粘贴 `Bearer` 后面的 token 字符串即可。

```bash
PYTHONPYCACHEPREFIX=/tmp/aibz_job_search_pycache python3 -c 'import getpass; from datetime import datetime; import aibz_job_search as m; token=getpass.getpass("access_token: "); filters={"major":"计算机","education":"本科","intention_job":["后端开发","算法工程师"],"intention_location":["北京","上海"],"job_type":"全职","is_unlimited_major":0,"order_by":"strat_time"}; out_file="job_search_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".json"; result=m.search_jobs(filters, access_token=token, page=1, page_size=20, save_to=out_file, verbose=True); print("count=%s, returned=%s" % (result["count"], len(result["data"]))); first=result["data"][0] if result["data"] else {}; print("first: id=%s, name=%s, company=%s" % (first.get("id"), first.get("name"), first.get("company_name")))'
```

期望：

1. 控制台打印 `[url]`、`[ts]`、`[sign]`、`[body]`
2. 控制台打印 `[saved] .../job_search_YYYYMMDD_HHMMSS.json`
3. `count` 为数字，`returned` 大于等于 0
4. 如果有结果，会打印首条岗位的 `id`、`name`、`company`

### 4.5 关键词搜索测试

用于验证 `query_str` 场景和 `query_params` 返回：

```bash
PYTHONPYCACHEPREFIX=/tmp/aibz_job_search_pycache python3 -c 'import getpass; from datetime import datetime; import aibz_job_search as m; token=getpass.getpass("access_token: "); filters={"query_str":"Python","major":"不限","intention_job":[],"intention_location":["杭州"]}; out_file="job_search_keyword_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".json"; result=m.search_jobs(filters, access_token=token, page=1, page_size=5, save_to=out_file, verbose=True); print("count=%s, returned=%s, has_query_params=%s" % (result["count"], len(result["data"]), "query_params" in result)); first=result["data"][0] if result["data"] else {}; print("first: id=%s, name=%s, company=%s" % (first.get("id"), first.get("name"), first.get("company_name")))'
```

期望：接口成功时 `has_query_params=True`，并生成 `job_search_keyword_YYYYMMDD_HHMMSS.json`。

如果真实接口测试失败：

- `code: 301`：token 过期或复制错了，重新抓 token
- `401` 或签名异常：确认系统时间准确，重新跑一次
- `requests.exceptions.ProxyError` / `Operation not permitted`：当前终端或执行环境网络被代理/权限拦截，换普通终端运行，或允许该进程访问网络

---

## 5. 入参字段表

调用 `search_jobs(filters, access_token, ...)` 时 `filters` 是一个 dict。下面是所有支持字段（与小程序前端拼装的字段对齐）：

| 字段 | 类型 | 含义 | 备注 |
|---|---|---|---|
| `major` | str | 专业 | |
| `education` | str | 学历 | 例：`"本科"` `"硕士"` |
| `intention_job` | list[str] | 意向岗位 | **必须数组**，空数组会被丢弃 |
| `intention_company` | str | 意向公司 | |
| `intention_location` | list[str] | 意向城市 | **必须数组**，例 `["北京","上海"]` |
| `job_type` | str | 工作性质 | 例：`"全职"` `"实习"` |
| `graduate_time` | str | 毕业时间 | |
| `company_type` | str | 就业方向 | |
| `is_unlimited_major` | int | 是否不限专业 | **数字 0 或 1**，不要传字符串 |
| `query_str` | str | 关键词搜索 | 后端会基于此返回 `query_params` |
| `jobCategory` | str | 岗位类别 | 驼峰命名，与其它字段下划线不一致是后端约定 |
| `timeType` | str | 时间类型 | 例：`"今日最新"` `"即将到期"` |
| `order_by` | str | 排序方式 | `"strat_time"` `"company_attraction"` `"deadline"`，注意 **`strat`** 不是 `start` |

### 不要传的字段

- `position` — 这是表单层字段，前端会拆成 `intention_job` 数组，**直接传 `intention_job` 即可**
- `query_date` — 项目源码里**完全没出现**，无效
- `strategy` — 仅推荐接口 `/v4/ai/jobrecommend/strategy-result-list` 使用，搜索接口不识别

### 表达"不限"

省略对应字段即可，**不要传 `"不限"` 字符串**。脚本会自动把 `"不限"` / 空字符串 / 空数组清掉。

### 分页参数

`page` 和 `page_size` 是 `search_jobs()` 的独立参数（拼到 query string 里），**不要**放进 `filters`。

---

## 6. 输出格式

脚本会把响应整理成这种结构：

```jsonc
{
  "code": 200,
  "msg": "ok",
  "count": 1234,                      // 总条数, 用于分页判断
  "data": [
    {
      "id": 12345,
      "name": "Java开发工程师",        // 岗位标题
      "company_name": "...",
      "city": "...",
      "company_type_key": "...",       // 公司类型标签
      "company_title_key": "...,...",  // 逗号分隔标签
      "start_time": "2025-03-01 10:00:00",
      "end_time": "2025-04-30 23:59:59",
      "job_state": 0,                  // 岗位状态码
      "is_viewed": 0,
      "is_collected": 0,
      "job_url": "...",
      "recommendedMessage": "...",     // AI 圈岗解读, 可能没有
      // 其它后端附带返回的字段都原样保留
    }
  ],
  "query_params": { ... },             // 仅 query_str 搜索时存在
  "recommendedMessage": "..."          // 顶层圈岗解读, 可能没有
}
```

### 关于 `jobs` 嵌套

后端**有些场景**会把核心字段塞在 `jobs` 子对象里：

```jsonc
{ "id": 1, "company_name": "X", "jobs": { "name": "...", "city": "..." } }
```

脚本会自动把 `jobs` 子对象展平合并到外层，使用方拿到的就是扁平结构。

---

## 7. 编程式调用

把脚本当模块用：

```python
from aibz_job_search import search_jobs, JobSearchError

filters = {
    "major": "软件工程",
    "intention_location": ["杭州"],
    "education": "本科",
    "is_unlimited_major": 0,
    "order_by": "strat_time",
}

try:
    result = search_jobs(
        filters,
        access_token="<你的 token>",
        page=1,
        page_size=50,
        save_to="output/page1.json",  # None 则不落盘
        verbose=False,                # True 时打印 url/sign/body 便于排查
    )
    for job in result["data"]:
        print(job["id"], job.get("name"), job.get("company_name"))
except JobSearchError as e:
    print(f"业务异常 code={e.code}, msg={e.msg}")
    # e.raw 是后端原始响应, 可进一步排查
```

### 翻页

```python
all_jobs = []
page = 1
while True:
    res = search_jobs(filters, access_token=TOKEN, page=page, page_size=100)
    all_jobs.extend(res["data"])
    if len(all_jobs) >= res["count"]:
        break
    page += 1
```

> ⚠️ 由于签名时间戳精度到分钟，**不要**在毫秒级密集发请求；连续翻页中间可以加 `time.sleep(0.2)` 之类的间隔。如果跨分钟边界请求失败，脚本会通过 `JobSearchError` 报出，自行重试即可。

### 7.1 从弹幕 JSONL 直接调用

`弹幕提取` 项目每行 JSONL 里的 `query_payload` 就是为这个接口设计的。脚本提供了 `search_jobs_from_payload`，自动做以下两件事：

- 过滤掉接口不认的字段（`position`、`query_date`、`strategy` 等历史残留）
- 把 `education` 归一化为接口识别值（`大专`、`中专`、`专科` 均转为 `专科`），并丢弃非白名单值（`985/211`、`一本`、`二本`、`高中`、`不限`）

```python
import json
from aibz_job_search import search_jobs_from_payload

with open("output/59475730286_xxx.jsonl") as f:
    for line in f:
        record = json.loads(line)
        result = search_jobs_from_payload(
            record["query_payload"],
            access_token=TOKEN,
            page=1, page_size=20,
        )
        print(record["keyword"], "→", result["count"])
```

如果想看适配后的实际 filters，可以直接调内部函数：

```python
from aibz_job_search import _adapt_payload_to_filters
print(_adapt_payload_to_filters(record["query_payload"]))
```

---

## 8. 签名机制说明

签名算法与小程序前端 `src/utils/sign.js` 完全一致：

```
sign = md5(JSON.stringify(sortedBody) + "-" + SALT + "-" + UTC_YYYYMMDDHHmm)
```

要点：

1. **盐值**：`52088869D768AA76`（写死在脚本常量里）
2. **时间戳**：UTC 时间，精度到分钟，与请求头 `timeStamp` 字段保持一致
3. **body 序列化**：递归 key 排序后 `JSON.stringify`
   - `dict` 按 key 字典序升序
   - `list` 顺序保留，但里面的 dict 元素仍递归排序
   - 输出无空格 (`{"a":1,"b":2}` 而不是 `{"a": 1, "b": 2}`)
   - 中文不转 unicode 转义 (`"计算机"` 而不是 `"计算机"`)
4. **请求体复用**：脚本里把签名时序列化的字符串**直接当请求体**发出去，避免 requests 自己再 stringify 引入差异

请求头：

| Header | 值 |
|---|---|
| `Content-Type` | `application/json;charset=utf-8` |
| `sign` | 上面算出的 md5 |
| `timeStamp` | UTC `YYYYMMDDHHmm` |
| `Authorization` | `Bearer <access_token>` |
| `version` | 任意小程序版本号字符串，默认 `1.0.0` |

---

## 9. 错误码处理

脚本对响应 `code` 字段的处理：

| code | 含义 | 脚本行为 |
|---|---|---|
| `200` / `0` | 成功 | 正常返回 |
| `301` | 未登录 / token 失效 | 抛 `JobSearchError`，请重新抓 token |
| `302` | 需要 VIP | 抛 `JobSearchError` |
| `305` | 缺资料 | 抛 `JobSearchError` |
| 其它 | 业务异常 | 抛 `JobSearchError` |

网络异常（连不上、超时、HTTP 非 2xx）会抛 `requests.RequestException`，自行处理。

---

## 10. 常见问题排查

### 签名失败 / 401 / 自定义码

1. 用 `verbose=True` 把 `url`、`ts`、`sign`、`body` 打印出来对照
2. 检查机器时区设置：脚本用 UTC，无关本地时区，但要确保**系统时间正确**（与真实 UTC 偏差超过 1 分钟会失败）
3. 确认 `body_str` 里没有多余空格、中文未被 unicode 转义
4. 用最简 body（如 `{"major":"计算机"}`）排查，能跑通再加字段

### 401 / code 301

token 过期或没填对。重新从小程序抓一遍。

### 跨分钟失败

罕见，只在分钟切换那几百毫秒发生。重试即可。

### 拿到的 data 字段不全

脚本不做字段白名单过滤，后端返回什么就保留什么。如果某条记录字段少，可能是后端针对该 item 的数据本身就缺；或者是 `jobs` 嵌套场景，脚本已经处理过展平。

### 只想看响应不想落盘

调用时 `save_to=None`（默认）即可。

---

## 11. 字段来源对照（给二次维护用）

| 脚本中的位置 | 对应小程序源码 |
|---|---|
| `SIGN_SALT` | `src/utils/sign.js:68` |
| `SEARCH_PATH` | `src/utils/config.js:5` `POSITION_REQUEST_URL` |
| `DEFAULT_BASE_URL` | `src/global/global.json` |
| `_sort_for_sign` | `src/utils/sign.js:12` `sortJsonObject` |
| `_clean_params` | `src/utils/index.js:153` `getPositionRequestParams` |
| `_flatten_jobs` | `src/components/XtxJobItem.vue:168` `itemData` computed |
| 签名算法 | `src/utils/sign.js:59` `getSign` |
| 请求头注入 | `src/utils/http.js:9` `httpInterceptor` |
| 业务码处理 | `src/utils/http.js:45` |
