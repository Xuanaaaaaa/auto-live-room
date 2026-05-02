"""
弹幕解析模块：规则前置 + LLM 兜底
直播间查询样例格式：查北京产品经理岗位

架构：
  弹幕输入 → 噪声过滤 → 规则解析 → (命中则直接输出 / 未命中则 LLM 兜底) → 结构化结果
"""

import re
import json
import time
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional
from openai import OpenAI  # 兼容大多数国产大模型的 OpenAI 兼容接口


# ============================================================
#  数据结构
# ============================================================

@dataclass
class JobQuery:
    """结构化查岗结果"""
    keyword: str                        # 岗位关键词，如 "产品经理"
    city: Optional[str] = None          # 城市，如 "北京"
    industry: Optional[str] = None      # 行业，如 "互联网"
    salary: Optional[str] = None        # 薪资要求，如 "15k-25k"
    experience: Optional[str] = None    # 经验要求，如 "3年"
    education: Optional[str] = None     # 学历要求，如 "本科"
    graduate_time: Optional[str] = None # 毕业时间，如 "2026" 或 "往届"
    raw_text: str = ""                  # 原始弹幕
    source: str = ""                    # 解析来源: "rule" | "llm"


# ============================================================
#  配置
# ============================================================

# ---------- 噪声过滤 ----------
NOISE_PATTERNS = [
    r'^[哈嘿嗯啊噢哦嘻呵]{2,}$',           # 纯语气词
    r'^[0-9]{1,6}$',                        # 纯数字刷屏 (666, 888)
    r'^[!！?？.。,，~～]+$',                 # 纯标点
    r'^[\U0001F600-\U0001FAFF\u2600-\u27BF]+$',  # 纯 emoji
]
NOISE_KEYWORDS = {
    "哈哈", "666", "牛", "厉害", "加油", "谢谢",
    "主播", "来了", "dd", "打卡", "签到", "1",
    "关注", "点赞", "转发", "好看", "收到",
}
MIN_LENGTH = 2   # 弹幕最短有效长度
MAX_LENGTH = 100  # 弹幕最长有效长度

# ---------- 规则解析 ----------
# 查询意图触发词
INTENT_TRIGGERS = [
    r'查',  r'找',  r'搜',  r'看看',  r'有没有',  r'有无',
    r'帮我',  r'我想',  r'想找',  r'求',  r'招不招',
    r'还招',  r'岗位',  r'职位',  r'工作',  r'招聘',
]

# 城市词库（可按需扩充）
CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆",
    "武汉", "南京", "苏州", "西安", "长沙", "郑州", "东莞",
    "天津", "青岛", "宁波", "厦门", "大连", "珠海", "佛山",
    "合肥", "福州", "济南", "昆明", "贵阳", "海口", "无锡",
    "常州", "温州", "石家庄", "哈尔滨", "沈阳", "太原",
]

# 岗位关键词库（高频岗位，用于规则层直接命中）
JOB_KEYWORDS = [
    "产品经理", "前端", "后端", "Java", "Python", "C++", "Go",
    "算法", "数据分析", "测试", "运维", "UI", "UX", "设计",
    "运营", "市场", "销售", "HR", "人事", "财务", "法务",
    "行政", "客服", "安卓", "Android", "iOS", "嵌入式",
    "大数据", "机器学习", "深度学习", "NLP", "全栈",
    "架构师", "项目经理", "技术总监", "CTO", "实习",
    "新媒体", "内容运营", "商务", "采购", "供应链",
    "电商", "直播运营", "视觉设计", "平面设计", "文案",
]

# 行业词库
INDUSTRIES = [
    "互联网", "金融", "教育", "医疗", "电商", "游戏", "社交",
    "物流", "房地产", "汽车", "新能源", "制造业", "零售",
    "传媒", "广告", "文娱", "旅游", "餐饮", "农业",
    "人工智能", "AI", "区块链", "芯片", "半导体", "通信",
    "生物科技", "医药", "保险", "证券", "银行", "咨询",
    "法律", "会计", "外贸", "跨境", "SaaS", "云计算",
    "网络安全", "物联网", "智能硬件",
]

# 学历词库（映射到标准值）
EDUCATIONS = {
    "博士": "博士", "硕士": "硕士", "研究生": "硕士",
    "本科": "本科", "大专": "专科", "专科": "专科",
    "大本": "本科", "985": "985/211", "211": "985/211",
    "一本": "一本", "二本": "二本", "中专": "专科",
    "高中": "高中", "不限学历": "不限",
}

# 薪资正则模式（按优先级排列）
SALARY_PATTERNS = [
    # 15k-25k / 15K-25K
    (r'(\d+)\s*[kK]\s*[-~到至]\s*(\d+)\s*[kK]', lambda m: f"{m.group(1)}k-{m.group(2)}k"),
    # 1万-2万 / 1w-2w
    (r'(\d+)\s*[万wW]\s*[-~到至]\s*(\d+)\s*[万wW]', lambda m: f"{m.group(1)}万-{m.group(2)}万"),
    # 8000-12000（纯数字区间，至少4位才算薪资）
    (r'(\d{4,})\s*[-~到至]\s*(\d{4,})', lambda m: f"{m.group(1)}-{m.group(2)}"),
    # 单个：15k / 2万
    (r'(\d+)\s*[kK]', lambda m: f"{m.group(1)}k"),
    (r'(\d+)\s*[万wW]', lambda m: f"{m.group(1)}万"),
    # 面议
    (r'面议|薪资面议|工资面议', lambda m: "面议"),
]

# 工作年限正则模式（按优先级排列）
EXPERIENCE_PATTERNS = [
    # 1-3年 / 1~3年
    (r'(\d+)\s*[-~到至]\s*(\d+)\s*年', lambda m: f"{m.group(1)}-{m.group(2)}年"),
    # 3年以上 / 3年+
    (r'(\d+)\s*年以上', lambda m: f"{m.group(1)}年以上"),
    (r'(\d+)\s*年\+', lambda m: f"{m.group(1)}年以上"),
    # 3年经验 / 3年
    (r'(\d+)\s*年(?:经验|工作经验)?', lambda m: f"{m.group(1)}年"),
    # 应届 / 应届生
    (r'应届(?:生|毕业生)?', lambda m: "应届"),
    # 无经验
    (r'无经验|没经验|不限经验|经验不限', lambda m: "不限"),
]

# 毕业年份正则模式（保守匹配明确年份/届别表达）
GRADUATE_TIME_PATTERNS = [
    (r'(20[0-3]\d)\s*(?:届|年\s*(?:毕业|毕业生))', lambda m: _normalize_graduate_time(m.group(1))),
    (r'(?:毕业时间|毕业年份|毕业|应届)\s*[:：]?\s*(20[0-3]\d)', lambda m: _normalize_graduate_time(m.group(1))),
    (r'(?<!\d)([0-3]\d)\s*(?:届|年\s*毕业)', lambda m: _normalize_graduate_time(m.group(1))),
]

# ---------- LLM 配置 ----------
LLM_CONFIG = {
    "base_url": "https://api.deepseek.com",   # 替换为实际 API 地址
    "api_key": "sk-4e12e161d5ed407c9fe1338d2044b417",                # 替换为实际 Key
    "model": "deepseek-v4-flash",                      # 推荐用轻量模型控制延迟
    "timeout": 3,                                # 超时秒数
}

# 元词黑名单：LLM 不可把这些泛指词作为 keyword 返回，否则视为非查岗
META_KEYWORDS = {
    "岗位", "职位", "工作", "职业", "工种", "活儿", "活",
    "岗", "事", "事情", "机会", "机遇", "饭碗", "差事",
}

LLM_SYSTEM_PROMPT = """你是一个直播间弹幕解析助手。任务：判断弹幕是否包含「查询某个具体岗位」的意图，并提取结构化信息。

## 关键规则

1. keyword 必须是具体的职业名称（例：产品经理、Java、前端、UI 设计、新媒体运营、销售）。绝不能是下列泛指元词：
   - 岗位、职位、工作、职业、工种、活儿、活、岗、事、事情、机会、机遇、饭碗、差事

2. 如果弹幕只有城市 / 行业 / 薪资 / 学历 / 年限，但没有具体的职业名称，必须判 intent=none。系统无法用泛指词去搜索。

3. 如果弹幕是闲聊、问公司、问主播、抱怨情绪、请求帮助但未指明具体职业，返回 intent=none。

4. 只有当用户明确想搜索某个具体职业（即便表达口语化），才返回 intent=search 并给出该具体职业作为 keyword。

## 字段
- intent: "search" 或 "none"
- keyword: 具体职业名（intent=search 时必填）
- city: 城市（可选）
- industry: 行业（可选）
- salary: 薪资（可选）
- experience: 经验（可选）
- education: 学历（可选）

## 输出格式
仅输出 JSON 一行，不要任何额外文本，不要 markdown 代码块包裹。

## 正例（应返回 intent=search）

弹幕: "查北京产品经理岗位"
输出: {"intent": "search", "keyword": "产品经理", "city": "北京"}

弹幕: "深圳有没有前端的活 3年经验"
输出: {"intent": "search", "keyword": "前端", "city": "深圳", "experience": "3年"}

弹幕: "Java"
输出: {"intent": "search", "keyword": "Java"}

弹幕: "刚毕业能干啥"
输出: {"intent": "search", "keyword": "实习"}

弹幕: "想做点跟运营沾边的"
输出: {"intent": "search", "keyword": "运营"}

## 反例（必须返回 intent=none）

弹幕: "北京岗位"
输出: {"intent": "none"}

弹幕: "上海有什么工作"
输出: {"intent": "none"}

弹幕: "杭州找工作"
输出: {"intent": "none"}

弹幕: "有没有好机会"
输出: {"intent": "none"}

弹幕: "杭州有没有啥好的互联网公司"
输出: {"intent": "none"}

弹幕: "主播今天气色不错"
输出: {"intent": "none"}

弹幕: "本科 3年经验 能干啥"
输出: {"intent": "none"}
"""


# ============================================================
#  第一层：噪声过滤
# ============================================================

def is_noise(text: str) -> bool:
    """判断弹幕是否为噪声，应被直接丢弃"""
    text = text.strip()

    # 长度检查
    if len(text) < MIN_LENGTH or len(text) > MAX_LENGTH:
        return True

    # 关键词命中
    if text in NOISE_KEYWORDS:
        return True

    # 正则匹配
    for pattern in NOISE_PATTERNS:
        if re.fullmatch(pattern, text):
            return True

    return False


# ============================================================
#  第二层：规则解析
# ============================================================

def rule_parse(text: str) -> Optional[JobQuery]:
    """
    基于规则的快速解析。
    能命中则返回 JobQuery，否则返回 None 交给 LLM。
    只有 keyword（岗位）是必须提取到的，其余字段均为可选。
    """
    # 预提取所有可选字段（不依赖触发词，全局扫描）
    city       = _extract_city(text)
    salary     = _extract_salary(text)
    experience = _extract_experience(text)
    education  = _extract_education(text)
    industry   = _extract_industry(text)
    graduate_time = _extract_graduate_time(text)

    # --- 路径 A: 触发词 + 岗位关键词 ---
    for trigger in INTENT_TRIGGERS:
        pattern = rf'{trigger}\s*'
        if re.search(pattern, text):
            remaining = re.sub(pattern, '', text, count=1).strip()
            remaining = re.sub(r'[的岗位职位工作招聘]', '', remaining).strip()

            keyword = _extract_job_keyword(remaining, city)

            if keyword:
                return JobQuery(
                    keyword=keyword,
                    city=city,
                    salary=salary,
                    experience=experience,
                    education=education,
                    graduate_time=graduate_time,
                    industry=industry,
                    raw_text=text,
                    source="rule",
                )

    # --- 路径 B: 纯岗位关键词（"产品经理"、"Java"）---
    keyword = _extract_job_keyword(text, city)
    if keyword:
        # 放宽长度限制：原始文本去掉已识别实体后剩余不超过 10 字符即可
        stripped = text
        for entity in [city, salary, experience, education, industry, graduate_time]:
            if entity:
                stripped = stripped.replace(entity, '', 1)
        stripped = re.sub(r'[的岗位职位工作招聘\s]', '', stripped)
        stripped = stripped.replace(keyword, '', 1)

        if len(stripped) <= 10:
            return JobQuery(
                keyword=keyword,
                city=city,
                salary=salary,
                experience=experience,
                education=education,
                graduate_time=graduate_time,
                industry=industry,
                raw_text=text,
                source="rule",
            )

    return None


def _extract_city(text: str) -> Optional[str]:
    """从文本中提取城市"""
    for city in CITIES:
        if city in text:
            return city
    return None


def _extract_job_keyword(text: str, exclude_city: str = None) -> Optional[str]:
    """从文本中提取岗位关键词"""
    if exclude_city:
        text = text.replace(exclude_city, '').strip()
    for kw in sorted(JOB_KEYWORDS, key=len, reverse=True):
        if kw.lower() in text.lower():
            return kw
    return None


def _extract_salary(text: str) -> Optional[str]:
    """从文本中提取薪资信息"""
    for pattern, formatter in SALARY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return formatter(m)
    return None


def _extract_experience(text: str) -> Optional[str]:
    """从文本中提取工作年限"""
    for pattern, formatter in EXPERIENCE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return formatter(m)
    return None


def _extract_education(text: str) -> Optional[str]:
    """从文本中提取学历要求"""
    # 按词长降序匹配，避免"不限学历"被"学历"截断等问题
    for keyword in sorted(EDUCATIONS.keys(), key=len, reverse=True):
        if keyword in text:
            return EDUCATIONS[keyword]
    return None


def _normalize_graduate_time(year_text: str) -> Optional[str]:
    """归一化毕业时间：25-28 届保留年份，更早统一为往届"""
    year = int(year_text)
    if year < 100:
        year += 2000
    if year < 2025:
        return "往届"
    if year <= 2028:
        return str(year)
    return None


def _extract_graduate_time(text: str) -> Optional[str]:
    """从文本中提取毕业年份"""
    for pattern, formatter in GRADUATE_TIME_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return formatter(m)
    return None


def _extract_industry(text: str) -> Optional[str]:
    """从文本中提取行业"""
    for ind in sorted(INDUSTRIES, key=len, reverse=True):
        if ind.lower() in text.lower():
            return ind
    return None


# ============================================================
#  第三层：LLM 兜底解析
# ============================================================

def llm_parse(text: str) -> Optional[JobQuery]:
    """调用 LLM 解析弹幕意图和实体"""
    try:
        client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"],
        )
        response = client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            temperature=0,
            max_tokens=200,
            timeout=LLM_CONFIG["timeout"],
        )

        raw = response.choices[0].message.content.strip()
        # 清理可能的 markdown 代码块包裹
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)

        if data.get("intent") != "search":
            return None

        keyword = data.get("keyword")
        if not isinstance(keyword, str):
            return None
        keyword = keyword.strip()
        # 黑名单防御：长度过短 / 命中元词 → 视为非查岗
        if len(keyword) < 2 or keyword in META_KEYWORDS:
            print(f"[LLM 关键词被黑名单拦截] raw='{text}' keyword='{keyword}'")
            return None

        return JobQuery(
            keyword=keyword,
            city=data.get("city"),
            industry=data.get("industry"),
            salary=data.get("salary"),
            experience=data.get("experience"),
            education=data.get("education"),
            raw_text=text,
            source="llm",
        )

    except Exception as e:
        print(f"[LLM 解析异常] {e}")
        return None


# ============================================================
#  去重缓存
# ============================================================

class DedupeCache:
    """基于滑动窗口的查询去重"""

    def __init__(self, ttl: int = 60):
        """ttl: 相同查询的去重窗口（秒）"""
        self.ttl = ttl
        self._cache: dict[str, float] = {}

    def _make_key(self, query: JobQuery) -> str:
        parts = [
            query.keyword,
            query.city or '',
            query.salary or '',
            query.experience or '',
            query.education or '',
            query.graduate_time or '',
            query.industry or '',
        ]
        raw = "|".join(parts).lower()
        return hashlib.md5(raw.encode()).hexdigest()

    def is_duplicate(self, query: JobQuery) -> bool:
        self._cleanup()
        key = self._make_key(query)
        if key in self._cache:
            return True
        self._cache[key] = time.time()
        return False

    def _cleanup(self):
        now = time.time()
        expired = [k for k, t in self._cache.items() if now - t > self.ttl]
        for k in expired:
            del self._cache[k]


# ============================================================
#  主解析入口
# ============================================================

class DanmakuParser:
    """
    弹幕解析器

    用法:
        parser = DanmakuParser(enable_llm=True, dedup_ttl=60)
        result = parser.parse("查北京产品经理岗位")
        if result:
            print(result.keyword, result.city)
    """

    def __init__(self, enable_llm: bool = True, dedup_ttl: int = 60):
        self.enable_llm = enable_llm
        self.cache = DedupeCache(ttl=dedup_ttl)
        self.stats = {"total": 0, "noise": 0, "rule_hit": 0, "llm_hit": 0, "dedup": 0}

    def parse(self, text: str) -> Optional[JobQuery]:
        """
        解析单条弹幕，返回 JobQuery 或 None
        """
        self.stats["total"] += 1
        text = text.strip()

        # 第一层：噪声过滤
        if is_noise(text):
            self.stats["noise"] += 1
            return None

        # 第二层：规则解析
        result = rule_parse(text)
        if result:
            if self.cache.is_duplicate(result):
                self.stats["dedup"] += 1
                return None
            self.stats["rule_hit"] += 1
            return result

        # 第三层：LLM 兜底
        if self.enable_llm:
            result = llm_parse(text)
            if result:
                if self.cache.is_duplicate(result):
                    self.stats["dedup"] += 1
                    return None
                self.stats["llm_hit"] += 1
                return result

        return None

    def parse_batch(self, texts: list[str]) -> list[JobQuery]:
        """批量解析，返回有效查询列表"""
        results = []
        for t in texts:
            r = self.parse(t)
            if r:
                results.append(r)
        return results

    def print_stats(self):
        s = self.stats
        processed = s["rule_hit"] + s["llm_hit"]
        print("\n===== 解析统计 =====")
        print(f"  总弹幕数:   {s['total']}")
        print(f"  噪声过滤:   {s['noise']}")
        print(f"  规则命中:   {s['rule_hit']}")
        print(f"  LLM 命中:   {s['llm_hit']}")
        print(f"  去重丢弃:   {s['dedup']}")
        print(f"  有效查询:   {processed}")
        print(f"  规则命中率: {s['rule_hit']/max(processed,1)*100:.1f}%")
        print("====================\n")


# ============================================================
#  测试 & 演示
# ============================================================

if __name__ == "__main__":

    # 关闭 LLM 进行纯规则测试（开启需配置真实 API）
    parser = DanmakuParser(enable_llm=False, dedup_ttl=30)

    test_danmaku = [
        # ---- 标准查询 ----
        "查北京产品经理岗位",                  # 标准格式
        "找深圳前端",                          # 简短格式
        "搜一下杭州Java",                      # 带触发词
        "有没有上海数据分析的岗位",             # 口语化
        "产品经理",                            # 纯岗位
        "Python",                              # 纯岗位

        # ---- 带薪资 ----
        "查北京产品经理 15k-25k",              # 标准 + 薪资区间
        "找深圳前端 20K-30K",                  # 大写K
        "上海Java 1万-2万",                    # 中文万
        "成都运营 面议",                        # 面议

        # ---- 带经验 ----
        "找深圳前端 3年经验",                   # 年限
        "查北京算法 1-3年",                     # 年限区间
        "上海产品经理 5年以上",                  # 年限+以上
        "找杭州Java 应届",                      # 应届生

        # ---- 带学历 ----
        "查北京产品经理 本科",                   # 学历
        "找深圳算法 硕士",                       # 硕士
        "上海前端 大专",                         # 专科
        "查北京产品经理 26届",                   # 毕业年份
        "查上海前端 24届",                       # 往届

        # ---- 带行业 ----
        "查北京互联网产品经理",                  # 行业+岗位
        "找深圳金融数据分析",                    # 行业+岗位
        "游戏行业UI设计",                        # 行业+岗位

        # ---- 多字段组合 ----
        "查北京互联网产品经理 15k-25k 3年经验 本科",  # 全字段
        "找深圳前端 20k 应届 大专",                    # 多字段组合
        "杭州Java 1-3年 985",                          # 城市+岗位+年限+学历

        # ---- 噪声 ----
        "哈哈哈哈",
        "666",
        "签到",

        # ---- LLM 兜底 ----
        "有啥坑给推荐推荐",
        "刚毕业能干啥",
    ]

    print("=" * 70)
    print("  弹幕解析测试（规则模式 · 多字段提取）")
    print("=" * 70)

    for dm in test_danmaku:
        result = parser.parse(dm)
        if result:
            fields = [f"岗位={result.keyword}"]
            if result.city:       fields.append(f"城市={result.city}")
            if result.industry:   fields.append(f"行业={result.industry}")
            if result.salary:     fields.append(f"薪资={result.salary}")
            if result.experience: fields.append(f"经验={result.experience}")
            if result.education:  fields.append(f"学历={result.education}")
            if result.graduate_time: fields.append(f"毕业年份={result.graduate_time}")
            print(f"  ✅  \"{dm}\"")
            print(f"      → {', '.join(fields)}  [{result.source}]")
        else:
            print(f"  ❌  \"{dm}\"  → 过滤/未命中")

    # 去重测试
    print("\n--- 去重测试 ---")
    r1 = parser.parse("查北京产品经理岗位")
    print(f"  重复发送 → {'去重丢弃' if r1 is None else '通过'}")

    parser.print_stats()
