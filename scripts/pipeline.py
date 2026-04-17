#!/usr/bin/env python3
"""
私人巴菲特 · 单股分析 Pipeline
兼容入口，实际实现已拆到 fetch / analysis / jobs 模块。
"""
try:
    from scripts._bootstrap import bootstrap_paths
except ImportError:
    from _bootstrap import bootstrap_paths

bootstrap_paths()

import sys

from scripts.pipeline_analysis import _analyze_earnings_quality, _compute_trading_params, _run_analysis, _run_layer2
from scripts.pipeline_fetch import (
    _fetch_1a_quote,
    _fetch_1b_financials,
    _fetch_1c1_news,
    _fetch_1c2_capital,
    _fetch_1c3_technicals,
)
from scripts.pipeline_jobs import (
    run_analysis_only,
    run_daily_all,
    run_letter_only,
    run_news_update,
    run_pipeline,
    run_quant_only,
    start_analysis_only,
    start_letter_only,
    start_news_update,
    start_pipeline,
    start_quant_only,
)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "daily":
        run_daily_all()
    else:
        print("Usage: python3 pipeline.py daily")
