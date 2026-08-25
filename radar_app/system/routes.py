"""Settings, reports, and utility routes extracted from the legacy app module."""

import os
import sqlite3
import threading

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for

from radar_app.data.jobs import create_job, get_job, update_job
from radar_app.shared.auth import login_required
from radar_app.shared.i18n import clear_i18n_cache
from radar_app.system.service import (
    build_accuracy_context,
    build_report_context,
    get_settings_context,
    run_script,
    save_general_settings,
    save_push_settings,
    send_push_test,
    update_locale_preference,
)


def register_system_routes(app):
    @app.route("/report")
    @app.route("/report/<date>")
    @login_required
    def report(date=None):
        context = build_report_context(date, request.args.get("period", "daily"))
        if not context:
            flash("No report available yet.", "info")
            return redirect(url_for("index"))
        return render_template("report.html", **context)

    @app.route("/report/accuracy")
    @login_required
    def accuracy():
        return render_template("accuracy.html", **build_accuracy_context())

    @app.route("/fetch", methods=["POST"])
    @login_required
    def fetch():
        try:
            return jsonify(run_script(current_app.root_path, "stock_pipeline.py", timeout=180))
        except TimeoutError:
            return jsonify({"ok": False, "stdout": "", "stderr": "Timed out (180s)"})

    @app.route("/run-digest", methods=["POST"])
    @login_required
    def run_digest():
        mode = request.form.get("mode", "weekly")
        if mode not in ("weekly", "monthly", "quarterly"):
            flash("Invalid mode.", "warning")
            return redirect(url_for("index"))
        try:
            result = run_script(current_app.root_path, "periodic_digest.py", mode, timeout=300)
            if result["ok"]:
                flash(f"{mode.capitalize()} digest generated.", "success")
            else:
                flash(f"Error: {result['stderr'][-200:]}", "danger")
        except TimeoutError:
            flash("Timed out (5 min).", "danger")
        return redirect(url_for("index"))

    def _check_scan_token():
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        expected = os.environ.get("SCAN_TOKEN", "")
        return expected and token == expected

    @app.route("/api/trigger-pipeline", methods=["POST"])
    def trigger_pipeline():
        """GitHub Actions cron: run full daily pipeline for all watched stocks + push notifications."""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        job_id = create_job(None, "daily_pipeline", "cron_pipeline")
        app_ctx = current_app._get_current_object()

        def _run():
            update_job(job_id, "running")
            try:
                from scripts.stock_pipeline import main as run_pipeline
                run_pipeline()
                app_ctx.logger.info("[trigger-pipeline] job %s done", job_id)
            except Exception as e:
                update_job(job_id, "failed", error=str(e))
                app_ctx.logger.warning("[trigger-pipeline] job %s failed: %s", job_id, e)
                return
            try:
                from scripts.backfill_returns import backfill_predictions
                backfill_predictions()
                app_ctx.logger.info("[trigger-pipeline] backfill_predictions done")
            except Exception as e:
                app_ctx.logger.warning("[trigger-pipeline] backfill_predictions failed: %s", e)
            update_job(job_id, "done")

        threading.Thread(target=_run, daemon=False, name="gh-pipeline-trigger").start()
        return jsonify({"status": "started", "job_id": job_id}), 202

    @app.route("/api/trigger-digest", methods=["POST"])
    def trigger_digest():
        """GitHub Actions cron step 2: commit daily snapshot + ingest predictions.
        Runs in its own thread, completely independent of precursor scan."""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        app_ctx = current_app._get_current_object()

        def _run():
            try:
                from scripts.daily_digest import run_daily_digest
                run_daily_digest()
                app_ctx.logger.info("[trigger-digest] daily digest done")
            except Exception as e:
                app_ctx.logger.warning("[trigger-digest] daily digest failed: %s", e)

        threading.Thread(target=_run, daemon=False, name="gh-digest-trigger").start()
        return jsonify({"status": "started"}), 202

    @app.route("/api/trigger-scan", methods=["POST"])
    def trigger_scan():
        """GitHub Actions cron 调用此端点触发每日前兆扫描（仅扫描，不提交快照）。"""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        job_id = create_job(None, "precursor_scan", "cron_scan")
        app_ctx = current_app._get_current_object()

        def _run():
            update_job(job_id, "running")
            errors = []
            steps = []

            def _note(msg):
                """把进度写进 job.log —— US-174。

                原来三件事的 print 全打到 stdout（Fly 日志），job.log 里只有
                开头那一行「▶ 开始扫描前兆信号…」。2026-08-25 查扫描为什么
                连续超时，翻到的日志**总共 26 个字符**，什么也说明不了。
                没有可见性就没有诊断。
                """
                steps.append(msg)
                try:
                    update_job(job_id, "running", log="\n".join(steps)[-4000:])
                except Exception:
                    pass
                app_ctx.logger.info("[trigger-scan] %s", msg)

            # ── 次序按「谁最容易被饿死」排，不按重要性排（US-174）──
            #
            # 原来是 前兆扫描 → 内部人 → 行业映射。前兆扫描要跑 75+ 分钟
            # （209 只 A股，每只融券/参与度各 30s 上限），而 job 在 120 分钟
            # 被 expire_stale_jobs 判死。于是 2026-08-22 之后连续三次超时，
            # **排在第三的行业映射一次都没轮到** —— 东财映射从 08-22 起
            # 死死停在 263 只，自选股行业覆盖率卡在 60%。
            #
            # 我一开始把这归因于 US-169 的断链。断链是真的，但只是一半：
            # 链修好之后映射依然没恢复，因为它在这里被饿死。
            # 两个独立的原因，各自都足以让它停摆。
            #
            # 所以便宜的活排前面，让最贵的那件去承担超时风险。
            try:
                from scripts.industry_signals import capture_daily_em, refresh_map_em
                cap = capture_daily_em()
                _note(f"行业日线: {cap}")
                mp = refresh_map_em()
                _note(f"行业映射: {mp}")

                # 全军覆没才算错（否则限流导致的零星失败会天天报警）。
                # refresh_map_em 返回 failed 字典而不是抛异常，不这样 surface
                # 的话外面完全看不见 —— 08-22 我据此误判过一次「三段全成功」。
                if not mp.get("boards"):
                    errors.append(f"industry_em: 板块列表拉取失败 "
                                  f"（{'; '.join(mp.get('failed', [])[:2])}）")
                elif mp.get("attempted") and not mp.get("mapped"):
                    errors.append(
                        f"industry_em: {mp['attempted']} 个板块全部失败 "
                        f"（{'; '.join(mp.get('failed', [])[:3])}）")
            except Exception as e:
                errors.append(f"industry_em: {e}")
                _note(f"行业映射失败: {e}")

            # US-142 内部人增减持：同为东财源，只能在 Fly 悉尼跑，搭这趟车。
            try:
                import db
                from scripts.insider_moves import run_insider_refresh
                codes = [c for c, _ in db.get_all_cn_watchlist_stocks()]
                res = run_insider_refresh(codes)
                _note(f"内部人: {res}")
            except Exception as e:
                errors.append(f"insider: {e}")
                _note(f"内部人失败: {e}")

            # 最贵的放最后 —— 它超时的话，前面两件已经落库了
            try:
                from scripts.precursor_scan import run_precursor_scan
                _note("前兆扫描: 开始（约 209 只 A股，按小时计）")
                result = run_precursor_scan()
                _note(f"前兆扫描: {result}")
            except Exception as e:
                errors.append(f"precursor: {e}")
                _note(f"前兆扫描失败: {e}")

            if errors:
                update_job(job_id, "failed", error="; ".join(errors)[:500])
            else:
                update_job(job_id, "done")

        threading.Thread(target=_run, daemon=False, name="gh-scan-trigger").start()
        return jsonify({"status": "started", "job_id": job_id}), 202

    @app.route("/api/scan-status/<int:job_id>")
    def scan_status(job_id):
        """US-150：让 GHA 能等扫描真正跑完再往下走。

        /api/job/<id> 是 @login_required 的（给浏览器用），GHA 只有 SCAN_TOKEN，
        所以单开这个 token 鉴权的只读端点。

        为什么需要它：trigger-scan 立刻返回 202，扫描在 Fly 后台跑 75+ 分钟。
        digest-svc 原来靠 cron 时间「猜」扫描跑完了没有 —— 实测 08-14 的快照里
        precursor 的 cache_age_hours 从 1.3h 一路到 0.0h，说明取快照时扫描还在写，
        妈妈那封信的「机构层」读到的是扫了一半的数据。
        """
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        job = get_job(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        return jsonify(
            {
                "job_id": job_id,
                "status": job.get("status"),
                "started_at": str(job.get("started_at") or ""),
                "finished_at": str(job.get("finished_at") or ""),
                "error": job.get("error"),
            }
        )

    @app.route("/api/trigger-backup", methods=["POST"])
    def trigger_backup():
        """Create a point-in-time SQLite backup at /data/radar.db.bak (called by GHA weekly)."""
        if not _check_scan_token():
            return jsonify({"error": "unauthorized"}), 401

        db_path = os.environ.get("DATABASE_URL", "").replace("sqlite:////", "/")
        if not db_path:
            db_path = "/data/radar.db"
        bak_path = db_path + ".bak"
        try:
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(bak_path)
            src.backup(dst)
            dst.close()
            src.close()
            size_kb = os.path.getsize(bak_path) // 1024
            current_app.logger.info("[backup] wrote %s (%d KB)", bak_path, size_kb)
            return jsonify({"ok": True, "path": bak_path, "size_kb": size_kb})
        except Exception as e:
            current_app.logger.error("[backup] failed: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/set-locale", methods=["POST"])
    def set_locale():
        locale = request.form.get("locale", "en")
        if locale not in ("en", "zh"):
            locale = "en"
        session["locale"] = locale
        # Auto-set home market to CN when switching to Chinese (if still on NZ default)
        current_region = session.get("region", "nz")
        if locale == "zh" and current_region == "nz":
            session["region"] = "cn"
            current_region = "cn"
        update_locale_preference(session.get("user_id"), current_region, locale)
        clear_i18n_cache()
        return redirect(request.referrer or url_for("index"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        user_id = session["user_id"]
        if request.method == "POST":
            action = request.form.get("action", "general")

            if action == "general":
                region = request.form.get("region", "nz")
                locale = request.form.get("locale", "en")
                save_general_settings(user_id, region, locale)
                session["region"] = region
                session["locale"] = locale
                clear_i18n_cache()
                flash("Settings saved.", "success")

            elif action == "push":
                notify_daily = 1 if request.form.get("notify_daily") else 0
                webhook = request.form.get("wecom_webhook", "").strip()
                save_push_settings(user_id, notify_daily, webhook)
                flash("推送设置已保存。", "success")

            elif action == "test_push":
                category, message = send_push_test(user_id)
                flash(message, category)

            return redirect(url_for("settings"))

        return render_template("settings.html", **get_settings_context(user_id))

    # ── Session status (for Next.js navbar) ──────────────────────────────────

    @app.route("/api/me")
    def api_me():
        return jsonify({
            "user_id": session.get("user_id"),
            "display_name": session.get("display_name"),
            "role": session.get("role"),
        })

    # ── Public API (no auth required) ────────────────────────────────────────

    @app.route("/api/public/feed")
    def api_public_feed():
        """Return publicly published analyses for the homepage."""
        from radar_app.data.core import get_conn
        with get_conn() as c:
            rows = c.execute("""
                SELECT ar.id, ar.code, ar.grade, ar.conclusion, ar.reasoning,
                       ar.analysis_date, ar.framework_used,
                       s.name AS stock_name, s.market
                FROM analysis_results ar
                JOIN stocks s ON s.code = ar.code
                WHERE ar.is_public = 1
                ORDER BY ar.analysis_date DESC, ar.id DESC
                LIMIT 20
            """).mappings().all()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/public/article/<code>")
    def api_public_article(code):
        """Return a single public article (full letter_html)."""
        from radar_app.data.core import get_conn
        with get_conn() as c:
            row = c.execute("""
                SELECT ar.*, s.name AS stock_name, s.market, s.industry
                FROM analysis_results ar
                JOIN stocks s ON s.code = ar.code
                WHERE ar.code = :code AND ar.is_public = 1
                ORDER BY ar.id DESC LIMIT 1
            """, {"code": code}).mappings().fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        return jsonify(dict(row))

    @app.route("/api/public/poll/today")
    def api_poll_today():
        """Return today's market poll (creates one if none exists)."""
        import datetime
        from radar_app.data.core import get_conn
        today = datetime.date.today().isoformat()
        with get_conn() as c:
            row = c.execute(
                "SELECT * FROM market_polls WHERE poll_date = :d",
                {"d": today}
            ).mappings().fetchone()
            if not row:
                c.execute(
                    "INSERT INTO market_polls (poll_date, question) VALUES (:d, :q)",
                    {"d": today, "q": "大盘今天涨还是跌？"}
                )
                row = c.execute(
                    "SELECT * FROM market_polls WHERE poll_date = :d",
                    {"d": today}
                ).mappings().fetchone()
        return jsonify(dict(row))

    @app.route("/api/public/poll/vote", methods=["POST"])
    def api_poll_vote():
        """Submit a vote. Body: {direction: 'up'|'down'}. Cookie-based dedup."""
        import datetime
        from radar_app.data.core import get_conn
        today = datetime.date.today().isoformat()
        cookie_key = f"voted_{today}"
        if request.cookies.get(cookie_key):
            return jsonify({"error": "already_voted"}), 400
        data = request.get_json(silent=True) or {}
        direction = data.get("direction")
        if direction not in ("up", "down"):
            return jsonify({"error": "invalid direction"}), 400
        col = "up_votes" if direction == "up" else "down_votes"
        with get_conn() as c:
            # Ensure today's poll exists
            exists = c.execute(
                "SELECT id FROM market_polls WHERE poll_date = :d", {"d": today}
            ).fetchone()
            if not exists:
                c.execute(
                    "INSERT INTO market_polls (poll_date, question) VALUES (:d, :q)",
                    {"d": today, "q": "大盘今天涨还是跌？"}
                )
            c.execute(
                f"UPDATE market_polls SET {col} = {col} + 1 WHERE poll_date = :d",
                {"d": today}
            )
            row = c.execute(
                "SELECT up_votes, down_votes FROM market_polls WHERE poll_date = :d",
                {"d": today}
            ).mappings().fetchone()
        resp = jsonify({"up_votes": row["up_votes"], "down_votes": row["down_votes"]})
        resp.set_cookie(cookie_key, "1", max_age=86400, samesite="Lax")
        return resp

    @app.route("/api/public/city-data")
    def api_city_data():
        """Return city living cost data grouped by category (major / lifestyle).
        30-day TTL for Numbeo cities; lifestyle cities always use latest manual seed.
        """
        import threading
        from scripts.fetch_city_costs import _ensure_table, get_all_cities, is_stale, refresh_all

        _ensure_table()
        cities = get_all_cities()

        major_stale = [c for c in cities if c.get("city_category") == "major"
                       and is_stale(c.get("fetched_at", ""), days=30)]
        needs_refresh = len(cities) == 0 or len(major_stale) > 0

        if len(cities) == 0:
            cities = refresh_all()
        elif needs_refresh:
            threading.Thread(target=refresh_all, daemon=True).start()

        # Determine display year (most recent report_year in DB)
        years = [c["report_year"] for c in cities if c.get("report_year")]
        report_year = max(years) if years else 2025

        return jsonify({
            "cities": cities,
            "report_year": report_year,
        })

    # ── US-116 价值发现·第一页「这是什么生意」（步0 分类，脚手架 + 众包）──
    @app.route("/api/public/company/<code>")
    def api_public_company(code):
        """返回建议类型 + 人话解释 + 可改选候选（无建议时让用户帮判断）。"""
        from radar_app.data.core import get_conn
        from radar_app.data.company_types import TYPE_INFO, SELECTABLE_TYPES, type_card
        with get_conn() as c:
            row = c.execute(
                "SELECT s.name, s.market, sm.company_type "
                "FROM stocks s LEFT JOIN stock_meta sm ON sm.code = s.code "
                "WHERE s.code = :code", {"code": code}
            ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        ctype = row["company_type"]
        suggested = type_card(ctype) if ctype and ctype in TYPE_INFO else None
        return jsonify({
            "code": code,
            "name": row["name"],
            "market": row["market"],
            "suggested_type": ctype,
            "suggested": suggested,
            "options": [type_card(k) for k in SELECTABLE_TYPES],
        })

    @app.route("/api/public/company/<code>/classify", methods=["POST"])
    def api_public_company_classify(code):
        """记录用户对公司类型的判断（众包标签；过验证门再回填分类）。"""
        from radar_app.data.core import get_conn
        from radar_app.data.company_types import TYPE_INFO
        data = request.get_json(silent=True) or {}
        picked = data.get("type")
        if picked not in TYPE_INFO:
            return jsonify({"error": "invalid type"}), 400
        with get_conn() as c:
            c.execute(
                "INSERT INTO stock_type_votes (code, company_type, created_at) "
                "VALUES (:code, :t, CURRENT_TIMESTAMP)",
                {"code": code, "t": picked},
            )
            rows = c.execute(
                "SELECT company_type, COUNT(*) n FROM stock_type_votes "
                "WHERE code = :code GROUP BY company_type ORDER BY n DESC",
                {"code": code},
            ).all()
        return jsonify({"ok": True, "votes": [dict(r) for r in rows]})
