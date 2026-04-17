"""Stock actions that are not page-presentation related."""

import threading
import time

import db
from radar_app.legacy.pipeline import run_pipeline_job, start_pipeline_job

VALID_EVENT_TYPES = {
    "st_trigger", "st_lifted", "restructuring_announced", "restructuring_vote",
    "restructuring_approved", "rights_issue", "bonus_share", "name_change",
    "delist_warning", "delist_final", "major_shareholder_change", "scheme_risk",
}


def start_stock_job(user_id, code, starter):
    stock = db.get_stock(code)
    if not stock:
        return None
    return {"job_id": starter(user_id, code, stock["market"])}


def cancel_job(job_id):
    job = db.get_job(job_id)
    if not job:
        return None
    if job["status"] in ("running", "pending"):
        db.update_job(job_id, status="done", log=(job.get("log") or "") + "\n⚠️ 用户手动取消")
    return {"status": "cancelled"}


def start_batch_analysis(user_id, codes):
    if not codes:
        return None
    job_ids = []
    for code in codes[:20]:
        stock = db.get_stock(code)
        if not stock:
            continue
        job_id = start_pipeline_job(user_id, code, stock["market"])
        job_ids.append({"code": code, "job_id": job_id})
    return {"job_ids": job_ids}


def start_rerun_all():
    def _run():
        codes = db.all_watched_codes()
        for code in codes:
            stock = db.get_stock(code)
            if not stock:
                continue
            job_id = db.create_job(user_id=None, code=code, job_type="rerun_all")
            run_pipeline_job(job_id, code, stock.get("market", "cn"), force=False)
            time.sleep(5)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    count = len(db.all_watched_codes())
    return {
        "ok": True,
        "message": f"已启动，共 {count} 只股票，顺利约 {count * 35 // 60} 分钟，限流时最多 {count * 100 // 60} 分钟",
    }


def add_stock_event_record(code, data):
    event_type = data.get("event_type", "")
    if event_type not in VALID_EVENT_TYPES:
        return {"error": f"invalid event_type: {event_type}"}, 400
    summary = (data.get("summary") or "").strip()
    if not summary:
        return {"error": "summary required"}, 400
    db.add_stock_event(
        code=code.upper(),
        event_type=event_type,
        event_date=data.get("event_date") or "",
        summary=summary,
        detail=data.get("detail"),
    )
    return {"ok": True}, 200
