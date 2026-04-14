#!/usr/bin/env python3
"""
quantitative_rating.py 回归测试

运行：python3 tests/test_quantitative_rating.py
"""
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from quantitative_rating import QuantitativeRater, _pct

rater = QuantitativeRater()

# ── 固定测试数据 ──────────────────────────────────────────

MAOTAI = [   # 茅台：护城河极宽，连续盈利，利润率顶级
    {"year": "2024", "roe": "34.5%", "net_margin": "47.2%", "debt_ratio": "22.0%", "net_profit": "857.0"},
    {"year": "2023", "roe": "35.1%", "net_margin": "46.8%", "debt_ratio": "21.5%", "net_profit": "747.0"},
    {"year": "2022", "roe": "33.8%", "net_margin": "46.0%", "debt_ratio": "22.0%", "net_profit": "627.0"},
    {"year": "2021", "roe": "32.9%", "net_margin": "45.5%", "debt_ratio": "21.0%", "net_profit": "524.0"},
    {"year": "2020", "roe": "31.5%", "net_margin": "44.9%", "debt_ratio": "20.0%", "net_profit": "467.0"},
]

DISTRESSED = [  # 持续亏损：负ROE，负利润，高债务
    {"year": "2024", "roe": "-18.5%", "net_margin": "-25.0%", "debt_ratio": "91.0%", "net_profit": "-12.5"},
    {"year": "2023", "roe": "-22.0%", "net_margin": "-30.0%", "debt_ratio": "88.0%", "net_profit": "-15.0"},
    {"year": "2022", "roe": "-10.0%", "net_margin": "-12.0%", "debt_ratio": "82.0%", "net_profit": "-8.0"},
]

AVERAGE = [   # 一般公司：ROE 中等，有债务，利润适度
    {"year": "2024", "roe": "14.0%", "net_margin": "8.5%", "debt_ratio": "55.0%", "net_profit": "30.0"},
    {"year": "2023", "roe": "13.5%", "net_margin": "8.2%", "debt_ratio": "56.0%", "net_profit": "28.0"},
    {"year": "2022", "roe": "12.8%", "net_margin": "7.9%", "debt_ratio": "57.0%", "net_profit": "25.0"},
]

EMPTY_NEWS = {}


# ─────────────────────────────────────────────────────────
# _pct() helper
# ─────────────────────────────────────────────────────────

class TestPctHelper(unittest.TestCase):
    def test_string_with_percent(self):
        self.assertAlmostEqual(_pct("15.3%"), 15.3)

    def test_plain_float(self):
        self.assertAlmostEqual(_pct(20.5), 20.5)

    def test_negative_string(self):
        self.assertAlmostEqual(_pct("-8.2%"), -8.2)

    def test_none_returns_default(self):
        self.assertAlmostEqual(_pct(None, 0.0), 0.0)
        self.assertAlmostEqual(_pct(None, 5.0), 5.0)

    def test_invalid_string_returns_default(self):
        self.assertAlmostEqual(_pct("N/A", 0.0), 0.0)

    def test_zero_string(self):
        self.assertAlmostEqual(_pct("0%"), 0.0)


# ─────────────────────────────────────────────────────────
# 单维度评分
# ─────────────────────────────────────────────────────────

class TestScoreROE(unittest.TestCase):
    def test_excellent(self):
        score, _ = rater.score_roe(30.0)
        self.assertEqual(score, 15)

    def test_good(self):
        score, _ = rater.score_roe(22.0)
        self.assertEqual(score, 13)

    def test_mediocre(self):
        score, _ = rater.score_roe(7.0)
        self.assertEqual(score, 3)

    def test_nearly_zero(self):
        score, _ = rater.score_roe(2.0)
        self.assertEqual(score, 0)

    def test_loss(self):
        score, _ = rater.score_roe(-5.0)
        self.assertEqual(score, -5)


class TestScoreNetMargin(unittest.TestCase):
    def test_high(self):
        score, _ = rater.score_net_margin(40.0)
        self.assertEqual(score, 10)

    def test_negative(self):
        score, _ = rater.score_net_margin(-3.0)
        self.assertEqual(score, -5)

    def test_borderline_zero(self):
        score, _ = rater.score_net_margin(0.0)
        self.assertEqual(score, 2)   # 0 < margin < 5 → 2 分


class TestScoreROEStability(unittest.TestCase):
    def test_very_stable(self):
        roe_list = [20.0, 20.5, 19.8, 20.2, 19.9]
        score, _ = rater.score_roe_stability(roe_list)
        self.assertEqual(score, 10)

    def test_volatile(self):
        roe_list = [5.0, 20.0, -10.0, 25.0, 2.0]
        score, _ = rater.score_roe_stability(roe_list)
        self.assertLessEqual(score, 3)

    def test_insufficient_data(self):
        score, desc = rater.score_roe_stability([20.0])
        self.assertEqual(score, 5)  # 数据不足返回中间值


class TestScoreSafety(unittest.TestCase):
    def test_low_debt(self):
        score, _ = rater.score_debt(0.1)
        self.assertEqual(score, 10)

    def test_high_debt(self):
        score, _ = rater.score_debt(3.0)
        self.assertEqual(score, -5)

    def test_consecutive_profit(self):
        score, _ = rater.score_profitability_sustainability([10.0, 8.0, 7.0])
        self.assertEqual(score, 10)

    def test_consecutive_loss(self):
        score, _ = rater.score_profitability_sustainability([-5.0, -3.0, -2.0])
        self.assertEqual(score, -5)


class TestScoreValuation(unittest.TestCase):
    def test_cheap_pe(self):
        score, _ = rater.score_pe_valuation(10)
        self.assertEqual(score, 7)

    def test_expensive_pe(self):
        score, _ = rater.score_pe_valuation(90)
        self.assertEqual(score, -2)

    def test_none_pe(self):
        score, desc = rater.score_pe_valuation(None)
        self.assertEqual(score, 3)   # 缺失给中间分

    def test_near_52w_low(self):
        score, _ = rater.score_price_position(5.0)
        self.assertEqual(score, 3)

    def test_near_52w_high(self):
        score, _ = rater.score_price_position(95.0)
        self.assertEqual(score, -3)

    def test_none_position(self):
        score, _ = rater.score_price_position(None)
        self.assertEqual(score, 0)


# ─────────────────────────────────────────────────────────
# rate_stock() 端对端
# ─────────────────────────────────────────────────────────

class TestRateStockEndToEnd(unittest.TestCase):

    def test_maotai_gets_high_grade(self):
        """茅台级别的公司应该得 A 或 B+"""
        result = rater.rate_stock(
            code="600519", name="贵州茅台",
            annual_data=MAOTAI,
            pe_percentile=30,    # PE 历史偏低
            pb_percentile=35,
            price_52week_pct=25,
            news_signals=EMPTY_NEWS,
        )
        self.assertGreaterEqual(result["score"], 75)
        self.assertIn(result["grade"], ("A", "B+"))
        self.assertEqual(result["conclusion"], "买入")

    def test_distressed_gets_low_grade(self):
        """持续亏损公司应该得 C 或 D"""
        result = rater.rate_stock(
            code="000999", name="烂公司",
            annual_data=DISTRESSED,
            pe_percentile=None,
            pb_percentile=None,
            price_52week_pct=80,
            news_signals=EMPTY_NEWS,
        )
        self.assertLessEqual(result["score"], 45)
        self.assertIn(result["grade"], ("C", "C+", "D"))

    def test_distressed_has_red_flags(self):
        """亏损公司必须有红旗"""
        result = rater.rate_stock(
            code="000999", name="烂公司",
            annual_data=DISTRESSED,
            pe_percentile=None,
            pb_percentile=None,
            price_52week_pct=None,
            news_signals=EMPTY_NEWS,
        )
        self.assertGreater(len(result["red_flags"]), 0)
        self.assertTrue(any("亏损" in f or "ROE" in f for f in result["red_flags"]))

    def test_average_company_middle_grade(self):
        """中等公司应在 B- 到 C+ 区间"""
        result = rater.rate_stock(
            code="001001", name="中等公司",
            annual_data=AVERAGE,
            pe_percentile=50,
            pb_percentile=50,
            price_52week_pct=50,
            news_signals=EMPTY_NEWS,
        )
        self.assertIn(result["grade"], ("B", "B-", "C+", "C"))

    def test_empty_annual_data_no_crash(self):
        """空数据不应崩溃"""
        result = rater.rate_stock(
            code="TEST", name="无数据公司",
            annual_data=[],
            pe_percentile=None,
            pb_percentile=None,
            price_52week_pct=None,
            news_signals=EMPTY_NEWS,
        )
        self.assertIn("grade", result)
        self.assertIn("score", result)
        self.assertIsInstance(result["score"], int)

    def test_return_dict_has_required_keys(self):
        """返回值必须包含所有关键字段"""
        result = rater.rate_stock(
            code="600519", name="茅台",
            annual_data=MAOTAI,
            pe_percentile=40,
            pb_percentile=40,
            price_52week_pct=50,
            news_signals=EMPTY_NEWS,
        )
        required = ("code", "name", "score", "grade", "conclusion",
                    "components", "red_flags", "reasoning")
        for key in required:
            self.assertIn(key, result, f"缺少字段: {key}")

    def test_components_structure(self):
        """components 必须是四维度元组"""
        result = rater.rate_stock(
            code="600519", name="茅台",
            annual_data=MAOTAI,
            pe_percentile=40, pb_percentile=40, price_52week_pct=50,
            news_signals=EMPTY_NEWS,
        )
        for key in ("moat", "growth_management", "safety", "valuation"):
            self.assertIn(key, result["components"])
            score, details = result["components"][key]
            self.assertIsInstance(score, int)
            self.assertIsInstance(details, list)


# ─────────────────────────────────────────────────────────
# 评级边界（grade thresholds）
# ─────────────────────────────────────────────────────────

class TestGradeBoundaries(unittest.TestCase):
    def test_grade_A_at_85(self):
        r = rater.get_grade_and_conclusion(85)
        self.assertEqual(r["grade"], "A")

    def test_grade_Bplus_at_75(self):
        r = rater.get_grade_and_conclusion(75)
        self.assertEqual(r["grade"], "B+")

    def test_grade_B_at_65(self):
        r = rater.get_grade_and_conclusion(65)
        self.assertEqual(r["grade"], "B")

    def test_grade_Bminus_at_55(self):
        r = rater.get_grade_and_conclusion(55)
        self.assertEqual(r["grade"], "B-")

    def test_grade_Cplus_at_45(self):
        r = rater.get_grade_and_conclusion(45)
        self.assertEqual(r["grade"], "C+")

    def test_grade_C_at_35(self):
        r = rater.get_grade_and_conclusion(35)
        self.assertEqual(r["grade"], "C")

    def test_grade_D_below_35(self):
        r = rater.get_grade_and_conclusion(20)
        self.assertEqual(r["grade"], "D")

    def test_below_84_not_A(self):
        r = rater.get_grade_and_conclusion(84)
        self.assertNotEqual(r["grade"], "A")

    def test_buyback_boosts_management(self):
        """回购信号应提升管理层评分"""
        score_with, _ = rater.score_management({"high_pos_buyback": 1})
        score_without, _ = rater.score_management({})
        self.assertGreater(score_with, score_without)

    def test_resignation_penalizes_management(self):
        """CFO离职应降低管理层评分"""
        score_bad, _ = rater.score_management({"high_neg_resignation": 1})
        score_ok, _  = rater.score_management({})
        self.assertLess(score_bad, score_ok)


# ─────────────────────────────────────────────────────────
# 防回归：已知 bug 场景
# ─────────────────────────────────────────────────────────

class TestRegressions(unittest.TestCase):

    def test_float_roe_no_crash(self):
        """US 股票的 ROE 是 float 不是字符串，不能 strip() 崩溃 (2026-04-13 bug)"""
        data = [{"year": "2024", "roe": 0.25, "net_margin": 0.18,
                 "debt_ratio": 30.0, "net_profit": 5.0}]
        result = rater.rate_stock(
            code="AAPL", name="Apple",
            annual_data=data,
            pe_percentile=40, pb_percentile=40, price_52week_pct=50,
            news_signals={},
        )
        self.assertIn("grade", result)

    def test_all_none_signals_no_crash(self):
        """全部 None 的数据不应崩溃"""
        data = [{"year": "2024", "roe": None, "net_margin": None,
                 "debt_ratio": None, "net_profit": None}]
        result = rater.rate_stock(
            code="TEST", name="空数据",
            annual_data=data,
            pe_percentile=None, pb_percentile=None, price_52week_pct=None,
            news_signals={},
        )
        self.assertIn("grade", result)

    def test_score_is_always_int(self):
        """score 必须是整数，模板渲染依赖这个"""
        for annual in [MAOTAI, DISTRESSED, AVERAGE, []]:
            result = rater.rate_stock(
                code="X", name="X", annual_data=annual,
                pe_percentile=50, pb_percentile=50, price_52week_pct=50,
                news_signals={},
            )
            self.assertIsInstance(result["score"], int,
                                  f"score 不是 int: {type(result['score'])}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
