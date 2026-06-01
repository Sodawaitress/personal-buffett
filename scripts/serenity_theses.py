"""
US-96 · Serenity 供应链瓶颈知识库（静态）

来源：@aleabitoreddit 2025-07 ~ 2026-05 语料库整理
方法论：多跳BOM映射，上游瓶颈狩猎，融资质量谱系评估
S级 = 最高信念，A级 = 高信念，B级 = 中等信念

conviction 等级：S / A / B
supply_chain_role：chokepoint（垄断瓶颈） / tier1（一级供应商） / integrator（整合商）
atm_risk：high / medium / low / none（ATM 配股稀释风险）
"""

SERENITY_THESES: dict[str, dict] = {

    # ── S 级：最高信念 ─────────────────────────────────────────────

    "SIVE": {
        "conviction": "S",
        "full_name": "Sivers Semiconductors",
        "supply_chain_role": "chokepoint",
        "thesis": (
            "CPO（共封装光学）超级周期中唯一商用DFB/CW激光供应商。"
            "AMD、MRVL Celestial、Jabil 1.6T LRO、Apple SiPh已锁定设计赢。"
            "2026年MSCI小型股纳入带来约6450万美元被动资金流入。"
            "瑞典小型股，前成量斜坡风险，但无替代供应商。"
        ),
        "key_customers": ["AMD", "MRVL", "Apple", "Jabil"],
        "catalysts": ["MSCI小型股纳入", "纳斯达克斯德哥尔摩双重上市", "CPO量产爬坡"],
        "fail_conditions": [
            "新竞争者进入DFB/CW激光市场",
            "AMD或MRVL取消设计赢订单",
            "产能爬坡严重延误（>12个月）",
        ],
        "atm_risk": "low",
        "track_record_note": "Serenity声明：不计划出售持股（截至2026-04-28）",
        "last_updated": "2026-05-28",
    },

    "AXTI": {
        "conviction": "S",
        "full_name": "AXT Inc.",
        "supply_chain_role": "chokepoint",
        "thesis": (
            "控制全球约40%磷化铟（InP）供应链，双重瓶颈：上游7N铟/镓/锗提炼（Vital/JinMei合资）+ "
            "下游InP衬底晶圆制造。2026年1月6日中国宣布对日双用出口禁令，"
            "事实上形成AXTI的地缘政治护城河。"
        ),
        "key_customers": ["Intel", "Coherent", "II-VI", "CPO激光制造商"],
        "catalysts": [
            "中国InP出口禁令扩大范围",
            "西方超大规模云厂商直接采购InP衬底",
            "CPO超级周期拉动磷化铟需求",
        ],
        "fail_conditions": [
            "中美贸易协定解除出口管制",
            "非中国InP产能大规模建立（需3-5年，短期不现实）",
            "CPO技术路线放弃InP基激光",
        ],
        "atm_risk": "low",
        "track_record_note": "验证：+1057%收益（截至2026-04-24，独立复核确认）",
        "last_updated": "2026-05-28",
    },

    "MU": {
        "conviction": "S",
        "full_name": "Micron Technology",
        "supply_chain_role": "tier1",
        "thesis": (
            "HBM内存超级周期最安全受益者，HBM产能爬坡在三家中最稳健。"
            "预测毛利率73-75%，实际Q2 FY2026毛利率74.9%（Serenity预测精确验证）。"
            "前瞻PE约10x，若NAND价格回升则降至约7x。"
            "运营收入预测：$10.8B(2025)→$46.5B(2026)→~$63.5B(2027)。"
        ),
        "key_customers": ["NVDA", "AMD", "超大规模云厂商"],
        "catalysts": [
            "HBM4量产（2026H2）",
            "NAND价格周期上行",
            "AI推理爆发拉动HBM需求",
        ],
        "fail_conditions": [
            "三星HBM良率提升快于预期抢占份额",
            "AI资本支出周期提前结束",
            "NAND价格持续下行压缩利润",
        ],
        "atm_risk": "none",
        "track_record_note": "毛利率预测73-75%，实际74.9%，精确验证",
        "last_updated": "2026-05-28",
    },

    "NBIS": {
        "conviction": "S",
        "full_name": "Nebius Group",
        "supply_chain_role": "integrator",
        "thesis": (
            "唯一全栈GPU云厂商，GAAP毛利率71.2%为同类最高。"
            "融资质量最高等级：NVDA战略投资$20亿 + 可转债，无ATM稀释。"
            "订单积压：META $270亿 + MSFT约$190亿 = 合计约$460亿。"
            "业务组合：云计算 + ClickHouse + Avride自动驾驶 + Toloka + TripleTen。"
        ),
        "key_customers": ["META", "MSFT", "企业AI客户"],
        "catalysts": [
            "Avride机器人出租车商业化",
            "ClickHouse独立IPO或战略融资",
            "AI云需求继续超出容量",
        ],
        "fail_conditions": [
            "NVDA战略关系恶化",
            "超大规模云厂商大幅削减外部GPU云支出",
            "GAAP毛利率出现持续压缩",
        ],
        "atm_risk": "none",
        "track_record_note": "S级持有整个语料库周期，>$2M头寸，$140→$79下跌中坚守",
        "last_updated": "2026-05-28",
    },

    # ── A 级：高信念 ──────────────────────────────────────────────

    "LITE": {
        "conviction": "A",
        "full_name": "Lumentum Holdings",
        "supply_chain_role": "chokepoint",
        "thesis": (
            "光学电路交换（OCS）垄断地位，Google TPU BOM占比8-12%。"
            "CW/DFB激光是CPO的主要瓶颈，产能据称2028年前已售罄。"
            "SIVE是更纯粹的激光瓶颈玩法，LITE作为整合商位列第二优先级。"
        ),
        "key_customers": ["Google", "MSFT", "Meta"],
        "catalysts": [
            "Google下一代TPU芯片设计赢确认",
            "OCS市场从数据中心实验室扩展至量产",
        ],
        "fail_conditions": [
            "Google将OCS采购转向内部或其他供应商",
            "新OCS技术路线绕过Lumentum IP",
        ],
        "atm_risk": "low",
        "track_record_note": "2026-01降级至$385后恢复结构性做多框架",
        "last_updated": "2026-05-28",
    },

    "COHR": {
        "conviction": "A",
        "full_name": "Coherent Corp.",
        "supply_chain_role": "tier1",
        "thesis": (
            "多元化光子学，垂直整合策略提供更稳健的复合增长。"
            "NVDA $20亿战略投资背书（2026-03-31）。"
            "CEO确认CPO 2026年量产（非2027）。"
            "Serenity评级：光子学板块第三优先（SIVE>LITE>COHR）。"
        ),
        "key_customers": ["NVDA", "超大规模云厂商", "电信运营商"],
        "catalysts": [
            "CPO 2026年量产确认",
            "NVDA战略合作深化",
            "垂直整合效率释放利润率",
        ],
        "fail_conditions": [
            "CPO时间线再次延迟至2027+",
            "垂直整合整合成本超预期",
        ],
        "atm_risk": "low",
        "track_record_note": "Serenity持续持有，光子学三号位",
        "last_updated": "2026-05-28",
    },

    "AAOI": {
        "conviction": "A",
        "full_name": "Applied Optoelectronics",
        "supply_chain_role": "tier1",
        "thesis": (
            "唯一在美国本土垂直整合的收发器制造商（德克萨斯Sugar Land工厂）。"
            "全部产能由AMZN/MSFT/ORCL三家超大规模云厂商包购。"
            "FY2025 Q2业绩超预期爆炸：$378M月收入目标，增速900%+，毛利率约40%。"
        ),
        "key_customers": ["AMZN", "MSFT", "ORCL"],
        "catalysts": [
            "美国本土制造在关税环境下的溢价",
            "超大规模云厂商追加产能订单",
            "毛利率从~40%进一步提升",
        ],
        "fail_conditions": [
            "超大规模云厂商转向海外低成本收发器",
            "Sugar Land工厂产能无法跟上需求增速",
        ],
        "atm_risk": "medium",
        "track_record_note": "2026-05-27 Serenity重新校准了AMZN/MSFT特定光学论文精度",
        "last_updated": "2026-05-28",
    },

    "LPTH": {
        "conviction": "A",
        "full_name": "LightPath Technologies",
        "supply_chain_role": "chokepoint",
        "thesis": (
            "Black Diamond玻璃和锗透镜的美国国防垄断地位。"
            "美国国防部唯一来源供应商认证，2026年Serenity最爱标的。"
            "热成像系统关键材料，$100亿市值潜力预测。"
        ),
        "key_customers": ["US DoD", "雷神", "洛克希德·马丁"],
        "catalysts": [
            "美国国防预算增加热成像采购",
            "DoD唯一来源合同续签或扩大范围",
            "出口许可放开允许盟国销售",
        ],
        "fail_conditions": [
            "DoD找到替代热成像材料（短期不现实）",
            "锗供应链受到中国出口限制（反而可能是正面催化剂）",
        ],
        "atm_risk": "medium",
        "track_record_note": "Serenity 2026年最高信念国防标的",
        "last_updated": "2026-05-28",
    },
}

# ── A股供应链瓶颈知识库（CN Serenity 等价物）────────────────────────────────
# 方法论与US版相同：多跳BOM映射，上游瓶颈猎杀，IDM护城河评估
# conviction 等级：S / A / B
# supply_chain_role：chokepoint / tier1 / integrator

CN_SERENITY_THESES: dict[str, dict] = {

    "688498": {
        "conviction": "A",
        "full_name": "源杰科技",
        "supply_chain_role": "chokepoint",
        "thesis": (
            "国内IDM激光芯片龙头，DFB/EML/CW激光芯片自主从MOCVD外延→芯片→测试全链路。"
            "CW激光（100mW@1310nm）是CPO/硅光子核心输入，与美股SIVE角色直接对应。"
            "数据中心收入+670% YoY，主要客户集中度53.35%（设计赢结构）。"
            "IDM认证周期长（年报明确描述），形成竞争护城河；"
            "IPO后股权扩张导致ROE阶段性摊薄，非护城河退化。"
        ),
        "key_customers": ["天孚通信", "中际旭创", "华为光产品线"],
        "catalysts": [
            "CPO量产带动CW激光片需求爆发",
            "数据中心客户追加设计赢订单",
            "国产替代：SIVE产能不足时国内替代窗口",
            "25H2产能爬坡完成进入规模效应",
        ],
        "fail_conditions": [
            "SIVE等海外激光芯片厂产能大幅扩张并维持价格优势",
            "主要客户（>50%集中度）技术路线切换或自研激光芯片",
            "MOCVD产线扩产延迟超过12个月",
        ],
        "atm_risk": "none",
        "track_record_note": "年报扫描2026-06-01：IDM护城河确认，供应链链路NVDA←Fabrinet←天孚通信←源杰科技独立核实",
        "last_updated": "2026-06-01",
    },

}

# 快速查找：code → thesis
def get_thesis(code: str) -> dict | None:
    """返回 code 对应的 Serenity 论文（US或CN），大小写不敏感。找不到返回 None。"""
    key = code.upper().split(".")[0]
    return SERENITY_THESES.get(key) or CN_SERENITY_THESES.get(key)


# 所有覆盖代码集合，用于分类器快速判断
SERENITY_CODES: frozenset = frozenset(SERENITY_THESES.keys())
CN_SERENITY_CODES: frozenset = frozenset(CN_SERENITY_THESES.keys())
