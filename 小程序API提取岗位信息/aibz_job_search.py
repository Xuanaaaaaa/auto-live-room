"""
aibz 岗位搜索接口直连脚本

绕过小程序前端，直接调用后端 /search/job/match/conditions 接口。
负责签名生成、参数清洗、响应整理、结果落盘。

依赖: pip install requests
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


# ============= 常量 =============

# 签名盐值，与小程序 src/utils/sign.js 中 getSign 一致
SIGN_SALT = "52088869D768AA76"

# 搜索接口路径，与 src/utils/config.js 的 POSITION_REQUEST_URL 一致
SEARCH_PATH = "/search/job/match/conditions"

# 默认生产环境，与 src/global/global.json 当前注释里的生产 URL 一致
DEFAULT_BASE_URL = "https://z5.100dp.com/api"


# ============= 异常 =============

class JobSearchError(Exception):
    """业务异常 (code 非 200/0)"""

    def __init__(self, code, msg, raw=None):
        super().__init__(f"[code={code}] {msg}")
        self.code = code
        self.msg = msg
        self.raw = raw


# ============= 签名 =============

def _sort_for_sign(value):
    """
    递归排序对象 key，数组顺序保留。
    对齐 src/utils/sign.js 中 sortJsonObject + sortJsonArray 的行为。
    """
    if isinstance(value, dict):
        return {k: _sort_for_sign(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_sort_for_sign(item) for item in value]
    return value


def _serialize_for_sign(body):
    """
    与 JS JSON.stringify 字节级对齐:
    - separators=(',',':') 去掉默认的多余空格
    - ensure_ascii=False 保留中文 UTF-8 (JS 默认行为)
    """
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _utc_timestamp_minute():
    """与 dayjs.utc().format('YYYYMMDDHHmm') 等价"""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


def _build_signature(body):
    """
    返回 (sign, timestamp, body_str)
    body_str 必须复用做请求体, 否则 hash 对不上
    """
    ts = _utc_timestamp_minute()
    sorted_body = _sort_for_sign(body)
    body_str = _serialize_for_sign(sorted_body)
    prefix = f"{body_str}-" if body_str else ""
    sign_input = f"{prefix}{SIGN_SALT}-{ts}"
    sign = hashlib.md5(sign_input.encode("utf-8")).hexdigest()
    return sign, ts, body_str


# ============= 入参清洗 =============

def _clean_params(filters):
    """
    对齐 src/utils/index.js 中 getPositionRequestParams 的清洗逻辑:
    - 值为 "不限" -> 删除字段
    - 值为空字符串 / None -> 删除字段
    - 空数组 -> 删除字段
    """
    cleaned = {}
    for k, v in filters.items():
        if v == "不限":
            continue
        if v is None or v == "":
            continue
        if isinstance(v, list) and len(v) == 0:
            continue
        cleaned[k] = v
    return cleaned


# ============= 响应整理 =============

def _flatten_jobs(item):
    """
    展平 item.jobs 子对象。
    与 src/components/XtxJobItem.vue 中 itemData computed 行为一致:
        if (item.jobs) return { ...item, ...item.jobs }
    """
    if isinstance(item, dict) and isinstance(item.get("jobs"), dict):
        merged = {**item, **item["jobs"]}
        merged.pop("jobs", None)
        return merged
    return item


def _normalize_response(raw):
    """
    整理响应保留下面字段:
        code, msg, count, data (经 jobs 展平), query_params (可选), recommendedMessage (可选)
    其它后端返回的字段都在 data[i] 内原样保留, 不做白名单过滤
    """
    data = raw.get("data") or []
    if not isinstance(data, list):
        data = []

    out = {
        "code": raw.get("code"),
        "msg": raw.get("msg") or raw.get("message"),
        "count": raw.get("count", 0),
        "data": [_flatten_jobs(item) for item in data],
    }
    if raw.get("query_params") is not None:
        out["query_params"] = raw["query_params"]
    if raw.get("recommendedMessage") is not None:
        out["recommendedMessage"] = raw["recommendedMessage"]
    return out


# ============= 主函数 =============

def search_jobs(
    filters,
    access_token,
    page=1,
    page_size=20,
    base_url=DEFAULT_BASE_URL,
    version="1.0.0",
    timeout=30,
    save_to=None,
    verbose=False,
):
    """
    调用 /search/job/match/conditions 接口

    Args:
        filters: 入参 dict (见 README)
        access_token: 登录 token, 不带 'Bearer ' 前缀
        page: 页码 (query string)
        page_size: 每页条数 (query string)
        base_url: 接口域名前缀, 默认生产
        version: 小程序版本号请求头, 任意非空字符串即可
        timeout: 请求超时秒数
        save_to: 保存响应 JSON 的文件路径, None 表示不保存
        verbose: True 时打印请求体和签名信息, 便于排查

    Returns:
        dict: 整理后的响应

    Raises:
        ValueError: access_token 为空
        JobSearchError: 业务码非 200/0
        requests.RequestException: 网络/HTTP 异常
    """
    if not access_token:
        raise ValueError("access_token 不能为空, 请填入登录态 token")

    body = _clean_params(filters)
    sign, ts, body_str = _build_signature(body)

    headers = {
        "Content-Type": "application/json;charset=utf-8",
        "sign": sign,
        "timeStamp": ts,
        "Authorization": f"Bearer {access_token}",
        "version": version,
    }

    url = f"{base_url}{SEARCH_PATH}?pageNum={page}&pageSize={page_size}"

    if verbose:
        print(f"[url]  {url}")
        print(f"[ts]   {ts}")
        print(f"[sign] {sign}")
        print(f"[body] {body_str}")

    resp = requests.post(
        url,
        data=body_str.encode("utf-8"),
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json()

    code = raw.get("code")
    if code not in (200, 0):
        raise JobSearchError(
            code,
            raw.get("msg") or raw.get("message") or "未知错误",
            raw,
        )

    result = _normalize_response(raw)

    if save_to:
        path = Path(save_to)
        if path.parent and str(path.parent) != ".":
            path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[saved] {path.resolve()}")

    return result


# ============= payload 适配 =============

_SEARCH_FILTER_KEYS = {
    "major", "education", "intention_job", "intention_company",
    "intention_location", "job_type", "graduate_time", "company_type",
    "is_unlimited_major", "query_str", "order_by", "jobCategory", "timeType",
}

_EDUCATION_NORMALIZE = {
    "博士": "博士",
    "硕士": "硕士",
    "本科": "本科",
    "大专": "专科",
    "中专": "专科",
    "专科": "专科",
}

_EDUCATION_PASSTHROUGH = set(_EDUCATION_NORMALIZE.values())


def _adapt_payload_to_filters(payload):
    """
    把弹幕端 query_payload 转成 search_jobs 能消费的 filters。

    - 只保留接口认识的字段 (_SEARCH_FILTER_KEYS)
    - education 非白名单值丢弃 (如 '985/211'、'一本')
    """
    filters = {k: v for k, v in payload.items() if k in _SEARCH_FILTER_KEYS}
    education = filters.get("education")
    if education is not None:
        normalized_education = _EDUCATION_NORMALIZE.get(education)
        if normalized_education in _EDUCATION_PASSTHROUGH:
            filters["education"] = normalized_education
        else:
            filters.pop("education", None)
    return filters


def search_jobs_from_payload(payload, access_token, **kwargs):
    """
    便捷入口: 直接传弹幕 JSONL 行里的 query_payload 子对象, 内部完成字段适配后调 search_jobs.
    其它参数 (page/page_size/save_to/verbose 等) 与 search_jobs 完全一致.
    """
    return search_jobs(_adapt_payload_to_filters(payload), access_token, **kwargs)


# ============= 示例入口 =============

if __name__ == "__main__":
    # ⚠️ 填入你的 access_token (从小程序开发者工具 Network 面板抓 Authorization 头, 去掉 'Bearer ' 前缀)
    ACCESS_TOKEN = ""

    # 入参示例 - 按你的字段表组合
    filters = {
        "major": "计算机",
        "education": "本科",
        "intention_job": ["后端开发", "算法工程师"],
        "intention_location": ["北京", "上海"],
        "job_type": "全职",
        "is_unlimited_major": 0,
        "order_by": "strat_time",  # 注意拼写: strat 不是 start
        # "intention_company": "字节跳动",
        # "graduate_time": "2025",
        # "company_type": "互联网",
        # "jobCategory": "技术",
        # "timeType": "今日最新",
        # "query_str": "Python",
    }

    out_file = f"job_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    result = search_jobs(
        filters,
        access_token=ACCESS_TOKEN,
        page=1,
        page_size=20,
        save_to=out_file,
        verbose=True,
    )

    print(f"count={result['count']}, returned={len(result['data'])}")
    if result["data"]:
        first = result["data"][0]
        print(
            f"first: id={first.get('id')}, "
            f"name={first.get('name')}, "
            f"company={first.get('company_name')}"
        )
