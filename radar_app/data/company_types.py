"""
US-116 · 公司类型的"说人话"教学内容（第一页「这是什么生意」用）。
每类：label 标签 / biz 什么生意 / how 怎么看它（对应哪把尺子）。
是分类页脚手架 + 众包标签的内容源；与 quantitative_rating 的 company_type 一一对应。
"""

TYPE_INFO = {
    "mature_value": {
        "label": "成熟价值股", "en": "Mature value",
        "biz": "稳定盈利、增长温和的成熟公司",
        "how": "看 ROE、护城河、以及价格便不便宜",
    },
    "growth_tech": {
        "label": "成长科技股", "en": "Growth / tech",
        "biz": "营收还在快速增长的公司",
        "how": "看增速和烧钱效率（Rule of 40），别拿当期利润卡它",
    },
    "pre_profit": {
        "label": "未盈利成长股", "en": "Pre-profit growth",
        "biz": "还没盈利、但在快速长大的公司",
        "how": "看营收增速，不看赚不赚钱（没盈利是阶段不是罪）",
    },
    "cyclical": {
        "label": "周期股", "en": "Cyclical",
        "biz": "随经济起落的生意（钢铁/煤炭/化工等）",
        "how": "看它在周期哪一段——利润高点 PE 看着便宜其实最危险",
    },
    "turnaround": {
        "label": "困境反转股", "en": "Turnaround",
        "biz": "曾经赚钱、现在暂时掉队的公司",
        "how": "看它在不在恢复（利润率触底回升没），不是看当期",
    },
    "distressed": {
        "label": "困境/重整股", "en": "Distressed",
        "biz": "濒临困境的公司",
        "how": "先看它能不能活下去（现金、债务）",
    },
    "bank": {
        "label": "银行", "en": "Bank",
        "biz": "放贷赚息差的银行",
        "how": "看坏账（不良率）和每块资产赚多少（ROA），不看增长",
    },
    "securities": {
        "label": "券商 / 投行", "en": "Securities",
        "biz": "证券公司，随股市牛熊大起大落",
        "how": "看它穿越一个牛熊周期的平均盈利，别用某一年判断",
    },
    "insurance": {
        "label": "保险", "en": "Insurance",
        "biz": "卖保单、赚长期的钱",
        "how": "看未来保单值多少钱（内含价值），不看市盈率",
    },
    "biotech": {
        "label": "生物药 / 创新药", "en": "Biotech",
        "biz": "研发新药、临床期还没盈利",
        "how": "看它手里的钱还能烧几年，撑不撑得到新药获批",
    },
    "property": {
        "label": "房地产", "en": "Real estate",
        "biz": "卖房，靠借钱周转的生意",
        "how": "先看负债安不安全（三道红线），地产是债务游戏",
    },
    "utility": {
        "label": "公用事业", "en": "Utility",
        "biz": "水电燃气，稳定、靠分红",
        "how": "看分红稳不稳、现金流够不够",
    },
    "supply_chain": {
        "label": "供应链卡位股", "en": "Supply-chain",
        "biz": "卡在产业链咽喉的公司",
        "how": "看它能不能被替代——越难替代越值钱",
    },
    "speculative": {
        "label": "高风险题材股", "en": "Speculative",
        "biz": "炒概念、题材驱动",
        "how": "风险很高，先问自己看不看得懂",
    },
    "etf": {
        "label": "基金 / ETF", "en": "Fund / ETF",
        "biz": "一篮子股票，不是单一公司",
        "how": "不适用个股分析，看它跟踪什么、费率多少",
    },
}

# 用户能选的候选（脚手架里让用户改选的列表，去掉太边缘的）
SELECTABLE_TYPES = [
    "mature_value", "growth_tech", "pre_profit", "cyclical", "turnaround",
    "distressed", "bank", "securities", "insurance", "biotech", "property",
    "utility", "supply_chain",
]


def type_card(key: str) -> dict:
    """返回单个类型的展示卡（含 key）。"""
    info = TYPE_INFO.get(key)
    if not info:
        return {"key": key, "label": key, "biz": "", "how": ""}
    return {"key": key, **info}
