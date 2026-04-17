"""Thin adapters for legacy pipeline and classifier modules."""


def start_pipeline_job(user_id, code, market):
    from pipeline import start_pipeline
    return start_pipeline(user_id, code, market)


def start_quant_job(user_id, code, market):
    from scripts.pipeline import start_quant_only
    return start_quant_only(user_id, code, market)


def start_letter_job(user_id, code, market):
    from scripts.pipeline import start_letter_only
    return start_letter_only(user_id, code, market)


def start_news_update_job(user_id, code, market):
    from scripts.pipeline import start_news_update
    return start_news_update(user_id, code, market)


def run_pipeline_job(job_id, code, market, force=False):
    from scripts.pipeline import run_pipeline
    return run_pipeline(job_id, code, market, force=force)


def compute_trading_params(price, signals, market):
    from scripts.pipeline import _compute_trading_params
    return _compute_trading_params(price, signals, market=market)


def classify_stock_code(code):
    from scripts.classifier import classify_stock
    return classify_stock(code)
