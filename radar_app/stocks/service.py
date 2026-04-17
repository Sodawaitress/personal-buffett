"""Stock detail and analysis service helpers."""

from radar_app.stocks.presenter import present_job_payload, present_letter_payload, present_stock_page
from radar_app.stocks.query import get_job, get_job_analysis, get_latest_daily_analysis, get_stock_page_bundle


def build_stock_page_context(code, user_id):
    bundle = get_stock_page_bundle(code, user_id)
    if not bundle:
        return None
    return present_stock_page(bundle)


def get_letter_payload(code):
    return present_letter_payload(get_latest_daily_analysis(code))


def get_job_payload(job_id):
    job = get_job(job_id)
    if not job:
        return None
    result = get_job_analysis(job["code"]) if job["status"] == "done" and job.get("code") else None
    return present_job_payload(job, result)
