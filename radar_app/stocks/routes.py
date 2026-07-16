"""Stock detail and analysis-related routes extracted from the legacy app module."""

import json as _json
from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import db
from radar_app.shared.auth import admin_required, login_required
from radar_app.legacy.pipeline import (
    start_letter_job,
    start_news_update_job,
    start_pipeline_job,
    start_quant_job,
)
from radar_app.stocks.action_service import (
    add_stock_event_record,
    cancel_job,
    start_batch_analysis,
    start_rerun_all,
    start_stock_job,
)
from radar_app.stocks.service import (
    build_stock_page_context,
    get_job_payload,
    get_letter_payload,
)
from scripts.config import CN_TZ
from scripts.institutional_radar import compute_intention_score, _classify_inst_sellers, _build_observations
from scripts.precursor_signals import fetch_precursor_signals


def _demo_block():
    """Return 403 JSON when a demo user tries to trigger AI analysis."""
    if session.get("is_demo"):
        return jsonify({"error": "demo_readonly", "message": "Sign up to run your own analysis."}), 403
    return None


def register_stock_routes(app):
    def _stock_context(code):
        context = build_stock_page_context(code, session['user_id'])
        return context

    @app.route('/stock/<path:code>')
    @login_required
    def stock_page(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found. Add it to your watchlist first.', 'warning')
            return redirect(url_for('index'))
        return render_template('stock/letter.html', **context)

    @app.route('/stock/<path:code>/signals')
    @login_required
    def stock_signals(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found.', 'warning')
            return redirect(url_for('index'))
        return render_template('stock/signals.html', **context)

    @app.route('/stock/<path:code>/lifecycle')
    @admin_required   # 新功能先管理员内测，数据验准前不给妈妈看（US-129）
    def stock_lifecycle(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found.', 'warning')
            return redirect(url_for('index'))
        from radar_app.stocks.lifecycle import build_lifecycle
        try:
            context['lc'] = build_lifecycle(code.upper())
        except Exception:
            context['lc'] = None
        context['active_tab'] = 'lifecycle'
        return render_template('stock/lifecycle.html', **context)

    @app.route('/stock/<path:code>/archive')
    @login_required
    def stock_archive(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found.', 'warning')
            return redirect(url_for('index'))
        return render_template('stock/archive.html', **context)

    @app.route('/stock/<path:code>/supply-chain')
    @login_required
    def stock_supply_chain_page(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found.', 'warning')
            return redirect(url_for('index'))
        if context.get('market') not in ('us', 'cn'):
            return redirect(url_for('stock_page', code=code.upper()))
        return render_template('stock/supply_chain.html', **context)

    @app.route('/stock/<path:code>/events')
    @login_required
    def stock_events_page(code):
        context = _stock_context(code.upper())
        if not context:
            flash('Stock not found.', 'warning')
            return redirect(url_for('index'))
        return render_template('stock/events.html', **context)

    # Legacy redirects
    @app.route('/stock/<path:code>/letter')
    @login_required
    def stock_letter(code):
        return redirect(url_for('stock_page', code=code.upper()), 301)

    @app.route('/stock/<path:code>/fundamentals')
    @login_required
    def stock_fundamentals_page(code):
        return redirect(url_for('stock_archive', code=code.upper()), 301)

    @app.route('/stock/<path:code>/radar')
    @login_required
    def stock_radar_page(code):
        return redirect(url_for('stock_signals', code=code.upper()), 301)

    @app.route('/api/news/<code>')
    @login_required
    def api_news(code):
        return jsonify(db.get_news(code, days=7))

    @app.route('/api/analyst/<code>')
    @login_required
    def api_analyst(code):
        data = db.get_analyst_consensus(code.upper())
        return jsonify(data or {})

    @app.route('/api/letter/<code>')
    @login_required
    def api_letter(code):
        return jsonify(get_letter_payload(code))

    @app.route('/api/analyze/<code>', methods=['POST'])
    @login_required
    def api_analyze(code):
        if (blocked := _demo_block()): return blocked
        payload = start_stock_job(session['user_id'], code, start_pipeline_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/analyze-only/<code>', methods=['POST'])
    @login_required
    def api_analyze_only(code):
        if (blocked := _demo_block()): return blocked
        payload = start_stock_job(session['user_id'], code, start_quant_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/generate-letter/<code>', methods=['POST'])
    @login_required
    def api_generate_letter(code):
        if (blocked := _demo_block()): return blocked
        payload = start_stock_job(session['user_id'], code, start_letter_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/refresh-news/<code>', methods=['POST'])
    @login_required
    def api_refresh_news(code):
        payload = start_stock_job(session['user_id'], code, start_news_update_job)
        if not payload:
            return jsonify({'error': 'stock not found'}), 404
        return jsonify(payload)

    @app.route('/api/job/<int:job_id>')
    @login_required
    def api_job(job_id):
        payload = get_job_payload(job_id)
        if not payload:
            return jsonify({'error': 'not found'}), 404
        return jsonify(payload)

    @app.route('/api/job/<int:job_id>/cancel', methods=['POST'])
    @login_required
    def api_job_cancel(job_id):
        payload = cancel_job(job_id)
        if not payload:
            return jsonify({'error': 'not found'}), 404
        return jsonify(payload)

    @app.route('/api/analyze-batch', methods=['POST'])
    @login_required
    def api_analyze_batch():
        if (blocked := _demo_block()): return blocked
        payload = start_batch_analysis(session['user_id'], (request.get_json() or {}).get('codes', []))
        if not payload:
            return jsonify({'error': 'no codes'}), 400
        return jsonify(payload)

    @app.route('/api/rerun-all', methods=['POST'])
    @admin_required
    def api_rerun_all():
        return jsonify(start_rerun_all())

    @app.route('/api/stock/<path:code>/events', methods=['POST'])
    @admin_required
    def add_stock_event(code):
        payload, status = add_stock_event_record(code, request.get_json() or {})
        return jsonify(payload), status

    @app.route('/api/intention/<path:code>')
    @login_required
    def api_intention(code):
        """
        机构意向综合评分 — 实时计算（A股专用）。
        前兆信号现场拉取，行为信号从 DB 读取缓存。
        """
        code = code.upper().split(".")[0].zfill(6)
        if not (code.isdigit() and len(code) == 6):
            return jsonify({"error": "A股代码只支持6位数字"}), 400

        # ── 从 DB 读取已有信号 ────────────────────────────────────────
        funds = db.get_fundamentals(code) or {}
        signals = funds.get("signals", {}) or {}

        # 北向趋势（从 market_data / signals 中读，格式兼容）
        northbound = signals.get("northbound", {}) or {}
        # 不是 northbound dict 直接是 market-level，需适配
        if isinstance(northbound, str):
            try:
                northbound = _json.loads(northbound)
            except Exception:
                northbound = {}

        # 股东人数（inst_quarterly 表）
        sh_row = db.get_inst_quarterly(code)
        shareholder = {}
        inst_top = signals.get("inst_top") or []
        if sh_row and sh_row.get("quarter"):
            pct = sh_row.get("sh_pct_change", 0) or 0
            shareholder = {
                code: {
                    "cnt": sh_row.get("shareholder_cnt", 0),
                    "pct_change": pct,
                    "quarter": sh_row.get("quarter", ""),
                    "signal": "",
                    # 把 inst_top 带进去，供 _classify_inst_sellers 使用
                    "inst_top": inst_top,
                    "inc": int(signals.get("inst_increased") or 0),
                    "dec": int(signals.get("inst_decreased") or 0),
                }
            }

        # 资金流（从 fund_flow 表）
        fund_flow_row = db.get_fund_flow(code)
        fund_flow = {code: fund_flow_row} if fund_flow_row else {}

        # 报价（从 price 表，只需 change）
        price_row = db.get_latest_price(code)
        stock_row = db.get_stock(code)
        stock_name = (stock_row or {}).get("name", code)
        quotes = {code: {"change": price_row.get("change_pct", 0) or 0,
                         "name": stock_name}} if price_row else {code: {"change": 0, "name": stock_name}}

        # ── 前兆信号：优先读缓存，force=1 时强制重拉 ────────────────
        force_refresh = request.args.get("force") == "1"
        from radar_app.data.market import get_precursor_cache, save_precursor_cache
        cached = get_precursor_cache(code) if not force_refresh else {}
        cache_age_h = cached.get("age_hours", 999)

        if cached and cache_age_h < 48:
            # 48 小时内的缓存直接用；首页加载已负责每日刷新
            stock_precursor = {
                "survey":        cached.get("survey", {}),
                "short_selling": cached.get("short_selling", {}),
                "participation": cached.get("participation", {}),
            }
            precursor = {code: stock_precursor}
            fetched_at_str = cached.get("fetched_at", "")[:16]
            from_cache = True
        else:
            # 完全没有缓存时才现场拉（加 30 秒超时保护）
            try:
                import signal as _sig

                def _timeout_handler(signum, frame):
                    raise TimeoutError("precursor fetch timeout")

                _sig.signal(_sig.SIGALRM, _timeout_handler)
                _sig.alarm(30)
                try:
                    precursor = fetch_precursor_signals([code])
                finally:
                    _sig.alarm(0)
            except Exception:
                precursor = {}
            stock_precursor = precursor.get(code, {})
            try:
                sv = stock_precursor.get("survey", {})
                sh = stock_precursor.get("short_selling", {})
                pa = stock_precursor.get("participation", {})
                score_val = float(sv.get("score", 0) or 0)
                save_precursor_cache(code, sv, sh, pa, score_val, is_active=True)
            except Exception:
                pass
            fetched_at_str = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")
            from_cache = False

        # ── 计算综合评分 ─────────────────────────────────────────────
        score_data = compute_intention_score(
            code,
            lhb={},
            northbound=northbound,
            insider_all={},
            block_trades={},
            shareholder=shareholder,
            repurchase={},
            fund_flow=fund_flow,
            quotes=quotes,
            precursor=precursor,
        )

        # ── 数据新鲜度 + 原始前兆数据（供 UI 显示详情）────────────────
        score_data["precursor_fetched_at"] = fetched_at_str
        score_data["precursor_from_cache"] = from_cache
        score_data["behavioral_note"] = (
            "行为信号（高管/龙虎榜/大宗）来自每日 pipeline；"
            "本次只拉取了前兆信号（调研热度/融券/机构参与度）。"
        )
        # 原始前兆数据传给前端，用于 survey events / participation 数值展示
        score_data["precursor_raw"] = {
            "survey":        stock_precursor.get("survey", {}),
            "short_selling": stock_precursor.get("short_selling", {}),
            "participation": stock_precursor.get("participation", {}),
        }

        # 信号快照：inst_top + 资金流数据，供前端叙事渲染
        fund_flow_row = fund_flow.get(code) or {}
        score_data["signals_snapshot"] = {
            "inst_increased":   int(signals.get("inst_increased") or 0),
            "inst_decreased":   int(signals.get("inst_decreased") or 0),
            "inst_top":         inst_top,
            "main_net":         fund_flow_row.get("main_net"),
            "main_ratio":       fund_flow_row.get("main_ratio"),
            "margin_balance":   signals.get("margin_balance"),
            "margin_change_pct": signals.get("margin_change_pct"),
            "margin_direction": signals.get("margin_direction"),
        }

        # inst_classification 用真实 inst_top 重算（compute 里没有 inst_top 时为空）
        score_data["inst_classification"] = _classify_inst_sellers(inst_top)

        # observations 重建（带完整 signals_snapshot）
        score_data["observations"] = _build_observations(
            score_data.get("components", {}),
            score_data["precursor_raw"],
            score_data["inst_classification"],
            score_data["signals_snapshot"],
        )

        return jsonify(score_data)

    @app.route('/api/stock/<path:code>/bundle')
    @login_required
    def api_export_bundle(code):
        from scripts.export_bundle import build_export_bundle
        result = build_export_bundle(code.upper(), user_id=session.get('user_id'))
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result)

    @app.route('/api/predict/<path:code>', methods=['POST'])
    @login_required
    def api_submit_prediction(code):
        """Record a user's directional prediction for a stock signal."""
        import json as _json
        from datetime import datetime
        from radar_app.data.core import get_conn, CN_TZ

        data = request.get_json() or {}
        direction = data.get('direction')
        if direction not in ('up', 'down', 'unsure'):
            return jsonify({'error': 'invalid direction'}), 400
        note = (data.get('note') or '')[:80]

        _VALID_SIGNAL_TYPES = {'margin', 'survey', 'participation', 'fund_flow',
                               'insider', 'northbound', 'block_trade', 'inst_hold', 'general'}
        signal_type = data.get('signal_type') or 'general'
        if signal_type not in _VALID_SIGNAL_TYPES:
            signal_type = 'general'

        predicted_outcome = data.get('predicted_outcome') or None
        if predicted_outcome not in ('confirms', 'fails', None):
            predicted_outcome = None

        # snapshot the current precursor cache for this code (best effort)
        pure = code.upper().split('.')[0].zfill(6)
        snap_json = None
        try:
            with get_conn() as c:
                row = c.execute(
                    "SELECT survey_json, short_json, partic_json FROM stock_precursor_cache "
                    "WHERE code=:code ORDER BY fetched_at DESC LIMIT 1", {"code": pure}
                ).fetchone()
                if row:
                    snap_json = _json.dumps({
                        'survey':   _json.loads(row['survey_json'] or 'null'),
                        'short':    _json.loads(row['short_json']  or 'null'),
                        'partic':   _json.loads(row['partic_json'] or 'null'),
                    })
        except Exception:
            pass

        now = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
        user_id = session.get('user_id')
        with get_conn() as c:
            c.execute(
                "INSERT INTO signal_predictions "
                "(user_id, code, created_at, direction, note, signal_snapshot, signal_type, predicted_outcome) "
                "VALUES (:uid,:code,:now,:dir,:note,:snap,:stype,:outcome)",
                {"uid": user_id, "code": pure, "now": now, "dir": direction, "note": note,
                 "snap": snap_json, "stype": signal_type, "outcome": predicted_outcome},
            )
        return jsonify({'ok': True})

    @app.route('/api/predict/<path:code>', methods=['GET'])
    @login_required
    def api_get_predictions(code):
        """Return the last 5 predictions the current user made for this stock."""
        from radar_app.data.core import get_conn
        pure = code.upper().split('.')[0].zfill(6)
        user_id = session.get('user_id')
        with get_conn() as c:
            rows = c.execute(
                "SELECT id, direction, note, created_at, correct, actual_return_5d, "
                "signal_type, predicted_outcome "
                "FROM signal_predictions "
                "WHERE user_id=:uid AND code=:code "
                "ORDER BY created_at DESC LIMIT 10",
                {"uid": user_id, "code": pure},
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    # ── US-97 供应链溯源 ──────────────────────────────────────────────────────

    @app.route('/api/supply-chain/scan/<path:code>', methods=['POST'])
    @login_required
    def api_supply_chain_scan(code):
        """触发多跳 BOM 供应链扫描（美股 Hop-1+2，A股 Hop-1）。"""
        if (blocked := _demo_block()): return blocked
        import threading as _threading
        ticker = code.upper().split('.')[0]
        stock_row = db.get_stock(ticker) or {}
        company_name = stock_row.get('name', ticker)
        market = stock_row.get("market", "us")

        def _run():
            try:
                from scripts.supply_chain_mapper import run_multihop_scan
                run_multihop_scan(ticker, market, company_name)
                # For US stocks, also scan three cross-border sources (A-share suppliers)
                if market == "us":
                    try:
                        from scripts.supply_chain_sources import scan_all_sources
                        scan_all_sources(ticker, company_name)
                    except Exception as e2:
                        print(f"[supply_chain] three-source scan error: {e2}")
            except Exception as e:
                print(f"[supply_chain] scan thread error: {e}")

        _threading.Thread(target=_run, daemon=True).start()
        return jsonify({'ok': True, 'status': 'scanning', 'code': ticker})

    @app.route('/api/supply-chain/<path:code>', methods=['GET'])
    @login_required
    def api_supply_chain_get(code):
        """返回缓存的供应链链接（含多跳树结构）以及跨境A股供应商。"""
        ticker = code.upper().split('.')[0]
        stock_row = db.get_stock(ticker) or {}
        market = stock_row.get("market", "us")
        user_region = session.get("region", "nz")
        try:
            from scripts.supply_chain_mapper import (
                get_supply_chain_links, get_supply_chain_tree,
                is_cache_fresh, was_scan_attempted,
            )
            links           = get_supply_chain_links(ticker)
            tree            = get_supply_chain_tree(ticker)
            fresh           = is_cache_fresh(ticker)
            scan_attempted  = was_scan_attempted(ticker)
        except Exception as e:
            return jsonify({'error': str(e), 'links': [], 'tree': {}, 'fresh': False})

        a_share_suppliers = []
        if market == "us":
            try:
                from scripts.supply_chain_sources import get_us_suppliers_for_ticker
                a_share_suppliers = get_us_suppliers_for_ticker(ticker)
            except Exception:
                pass

        return jsonify({
            'links': links, 'tree': tree, 'fresh': fresh, 'count': len(links),
            'a_share_suppliers': a_share_suppliers,
            'scan_attempted': scan_attempted,
            'user_region': user_region,
        })

    @app.route('/api/supply-chain/global', methods=['GET'])
    @login_required
    def api_supply_chain_global():
        """返回当前用户所有美股的供应链数据，找出共享供应商节点（跨组合系统性风险）。"""
        uid = session['user_id']
        try:
            from radar_app.data.core import get_conn
            with get_conn() as c:
                # 用户所有美股自选股（含持有+观察）
                stocks = c.execute("""
                    SELECT uw.stock_code, s.name, uw.status
                    FROM user_watchlist uw
                    JOIN stocks s ON s.code = uw.stock_code
                    WHERE uw.user_id = :uid
                      AND s.market = 'us'
                      AND uw.status IN ('holding','watching')
                      AND uw.removed_at IS NULL
                """, {"uid": uid}).fetchall()

                if not stocks:
                    return jsonify({"nodes": [], "edges": [], "shared": []})

                codes = [r["stock_code"] for r in stocks]
                placeholders = ",".join(f"'{c}'" for c in codes)

                links = c.execute(f"""
                    SELECT downstream_code, supplier_name, supplier_ticker,
                           dependency_type, chokepoint_score, supplier_market,
                           source, hop_depth
                    FROM supply_chain_links
                    WHERE downstream_code IN ({placeholders})
                      AND (hop_depth IS NULL OR hop_depth = 1)
                    ORDER BY chokepoint_score DESC
                """).fetchall()

            # Build graph nodes + edges
            stock_meta = {r["stock_code"]: {"name": r["name"], "status": r["status"]} for r in stocks}
            nodes = {}
            edges = []

            # Stock nodes
            for code in codes:
                nodes[code] = {
                    "id": code, "type": "stock",
                    "name": stock_meta[code]["name"],
                    "status": stock_meta[code]["status"],
                    "market": "us",
                }

            # Supplier nodes + edges
            supplier_stocks: dict[str, list[str]] = {}  # supplier_id → [stock codes]
            for lnk in links:
                sup_id = lnk["supplier_ticker"] or lnk["supplier_name"]
                if sup_id not in nodes:
                    nodes[sup_id] = {
                        "id": sup_id, "type": "supplier",
                        "name": lnk["supplier_name"],
                        "market": lnk["supplier_market"] or "unknown",
                        "max_score": lnk["chokepoint_score"],
                    }
                else:
                    nodes[sup_id]["max_score"] = max(
                        nodes[sup_id].get("max_score", 0), lnk["chokepoint_score"]
                    )
                edges.append({
                    "from": lnk["downstream_code"],
                    "to": sup_id,
                    "dep_type": lnk["dependency_type"],
                    "score": lnk["chokepoint_score"],
                    "source": lnk["source"],
                })
                supplier_stocks.setdefault(sup_id, [])
                if lnk["downstream_code"] not in supplier_stocks[sup_id]:
                    supplier_stocks[sup_id].append(lnk["downstream_code"])

            # Shared suppliers (appear in 2+ stocks)
            shared = [
                {
                    "supplier_id": sid,
                    "supplier_name": nodes[sid]["name"],
                    "market": nodes[sid]["market"],
                    "stocks": slist,
                    "max_score": nodes[sid].get("max_score", 0),
                }
                for sid, slist in supplier_stocks.items()
                if len(slist) >= 2
            ]
            shared.sort(key=lambda x: (-x["max_score"], -len(x["stocks"])))

            return jsonify({
                "nodes": list(nodes.values()),
                "edges": edges,
                "shared": shared,
                "stock_codes": codes,
            })
        except Exception as e:
            return jsonify({"error": str(e), "nodes": [], "edges": [], "shared": []})

    # ── US-112 未定价信号 ──────────────────────────────────────────────────

    @app.route('/api/unpriced-signals/<path:code>', methods=['GET'])
    @login_required
    def api_unpriced_signals_get(code):
        """返回自动信号缓存 + 用户最新记录。"""
        uid = session['user_id']
        try:
            from radar_app.data.core import get_conn
            with get_conn() as c:
                row = c.execute("""
                    SELECT * FROM unpriced_signals
                    WHERE stock_code=:code AND user_id=:uid
                    ORDER BY created_at DESC LIMIT 1
                """, {"code": code, "uid": uid}).fetchone()
            if row:
                d = dict(row)
                for key in ("trends_json", "reddit_json", "news_freq_json", "physical_signals"):
                    if d.get(key):
                        try:
                            d[key] = json.loads(d[key])
                        except Exception:
                            pass
                return jsonify({"ok": True, "record": d})
            return jsonify({"ok": True, "record": None})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route('/api/unpriced-signals/<path:code>/scan', methods=['POST'])
    @login_required
    def api_unpriced_signals_scan(code):
        """触发自动信号扫描（A 层），后台线程，结果写库。"""
        uid = session['user_id']
        try:
            from radar_app.data.core import get_conn
            with get_conn() as c:
                stock = c.execute(
                    "SELECT name FROM stocks WHERE code=:code", {"code": code}
                ).fetchone()
            query = stock["name"] if stock else code

            def _run():
                from scripts.social_signals import compute_auto_score
                from radar_app.data.core import get_conn as gc
                result = compute_auto_score(code, query)
                with gc() as conn:
                    conn.execute("""
                        INSERT INTO unpriced_signals
                            (stock_code, user_id, auto_score,
                             trends_json, reddit_json, news_freq_json,
                             total_score, digest_label)
                        VALUES (:code,:uid,:auto,
                                :tr,:rd,:nw,
                                :auto,:lbl)
                        ON CONFLICT DO NOTHING
                    """, {
                        "code": code, "uid": uid,
                        "auto": result["total"],
                        "tr": json.dumps(result["raw"]["trends"]),
                        "rd": json.dumps(result["raw"]["reddit"]),
                        "nw": json.dumps(result["raw"]["news"]),
                        "lbl": _digest_label(result["total"]),
                    })

            import threading
            threading.Thread(target=_run, daemon=True).start()
            return jsonify({"ok": True, "status": "scanning"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route('/api/unpriced-signals/<path:code>', methods=['POST'])
    @login_required
    def api_unpriced_signals_post(code):
        """保存 B+C 层用户输入，计算总分，返回结果。"""
        uid  = session['user_id']
        body = request.get_json() or {}
        try:
            from scripts.social_signals import (
                compute_user_score, judge_insight,
                compute_total, digest_label as _dl, digest_emoji
            )
            from radar_app.data.core import get_conn

            discovery = body.get("discovery", "")
            awareness = body.get("awareness", "")
            physical  = body.get("physical", [])
            insight   = body.get("insight", "").strip()

            user_b = compute_user_score(discovery, awareness, physical)

            # 取最新 A 层分数
            with get_conn() as c:
                stock = c.execute(
                    "SELECT name FROM stocks WHERE code=:code", {"code": code}
                ).fetchone()
                prev = c.execute("""
                    SELECT id, auto_score, trends_json, reddit_json, news_freq_json
                    FROM unpriced_signals
                    WHERE stock_code=:code AND user_id=:uid
                    ORDER BY created_at DESC LIMIT 1
                """, {"code": code, "uid": uid}).fetchone()

            auto_score = prev["auto_score"] if prev else 0
            stock_name = stock["name"] if stock else code

            insight_result = judge_insight(insight, stock_name) if insight else \
                             {"signal_type": "none", "adjustment": 0, "reasoning": ""}

            total = compute_total(auto_score, user_b, insight_result["adjustment"])
            label = _dl(total)
            emoji = digest_emoji(total)

            with get_conn() as c:
                if prev:
                    c.execute("""
                        UPDATE unpriced_signals SET
                            user_score=:ub, discovery_method=:disc,
                            awareness_level=:aw, physical_signals=:ph,
                            insight_text=:ins, insight_type=:itype,
                            insight_adj=:iadj, insight_reason=:irs,
                            total_score=:tot, digest_label=:lbl,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id
                    """, {
                        "ub": user_b, "disc": discovery, "aw": awareness,
                        "ph": json.dumps(physical), "ins": insight,
                        "itype": insight_result["signal_type"],
                        "iadj": insight_result["adjustment"],
                        "irs": insight_result["reasoning"],
                        "tot": total, "lbl": label, "id": prev["id"],
                    })
                else:
                    c.execute("""
                        INSERT INTO unpriced_signals
                            (stock_code, user_id, auto_score, user_score,
                             discovery_method, awareness_level, physical_signals,
                             insight_text, insight_type, insight_adj, insight_reason,
                             total_score, digest_label)
                        VALUES
                            (:code,:uid,0,:ub,
                             :disc,:aw,:ph,
                             :ins,:itype,:iadj,:irs,
                             :tot,:lbl)
                    """, {
                        "code": code, "uid": uid, "ub": user_b,
                        "disc": discovery, "aw": awareness,
                        "ph": json.dumps(physical), "ins": insight,
                        "itype": insight_result["signal_type"],
                        "iadj": insight_result["adjustment"],
                        "irs": insight_result["reasoning"],
                        "tot": total, "lbl": label,
                    })

            return jsonify({
                "ok": True,
                "total": total, "label": label, "emoji": emoji,
                "auto": auto_score, "user_b": user_b,
                "insight": insight_result,
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            return jsonify({"ok": False, "error": str(e)})


def _digest_label(score: int) -> str:
    if score >= 85: return "极早期"
    if score >= 65: return "早期"
    if score >= 45: return "扩散中"
    if score >= 25: return "进主流"
    return "已公开"


# ── US-114 · 价值发现工作流 ────────────────────────────────────────────────

def _fetch_earnings_data(code: str) -> dict:
    """拉取近3年每股盈利。A股用AKShare，港美股用yfinance。"""
    import re
    stock  = db.get_stock(code) or {}
    market = stock.get("market") or (
        "cn" if re.match(r'^\d{6}$', re.sub(r'\.(SS|SZ|SH|BJ)$', '', code, flags=re.IGNORECASE)) else "us"
    )
    rows = []

    quarterly = []  # 近4季度，格式 [{quarter, eps}]

    if market == "cn":
        try:
            import akshare as ak
            pure = re.sub(r'\.(SS|SZ|SH|BJ)$', '', code, flags=re.IGNORECASE)
            # 年度（旧→新排列，前端显示时从上到下是历史→最新）
            df = ak.stock_financial_abstract_ths(symbol=pure, indicator="按年度")
            df = df[df["基本每股收益"].notna() & (df["基本每股收益"] != False)]
            for _, r in df.tail(4).iterrows():   # tail = 最近4年，已按旧→新
                try:
                    eps = float(str(r["基本每股收益"]).replace(",", ""))
                    rows.append({"year": str(r["报告期"]), "eps": round(eps, 4)})
                except Exception:
                    pass
            # 季度
            try:
                dfq = ak.stock_financial_abstract_ths(symbol=pure, indicator="按单季度")
                dfq = dfq[dfq["基本每股收益"].notna() & (dfq["基本每股收益"] != False)]
                for _, r in dfq.tail(4).iterrows():
                    try:
                        eps = float(str(r["基本每股收益"]).replace(",", ""))
                        quarterly.append({"quarter": str(r["报告期"]), "eps": round(eps, 4)})
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            print(f"[value/earnings cn] {e}")
    else:
        try:
            import yfinance as yf
            t = yf.Ticker(code)
            # 优先拿年度 income statement 里的 EPS（最准确）
            annual_eps = []
            try:
                stmt = t.income_stmt  # columns = 年度日期
                if stmt is not None and not stmt.empty:
                    eps_row = None
                    for label in ["Diluted EPS", "Basic EPS", "EPS"]:
                        if label in stmt.index:
                            eps_row = stmt.loc[label]
                            break
                    if eps_row is not None:
                        for col in eps_row.index[:4]:  # 最近4年
                            val = eps_row[col]
                            if val is not None and str(val) not in ("nan", "None"):
                                annual_eps.append({
                                    "year": str(col)[:4],
                                    "eps": round(float(val), 4)
                                })
            except Exception:
                pass

            if annual_eps:
                rows = list(reversed(annual_eps))  # 旧→新
            else:
                info = t.info or {}
                eps = info.get("trailingEps") or info.get("epsTrailingTwelveMonths")
                if eps:
                    rows.append({"year": "TTM", "eps": round(float(eps), 4)})

            # 季度（旧→新）
            try:
                qstmt = t.quarterly_income_stmt
                if qstmt is not None and not qstmt.empty:
                    eps_row = None
                    for label in ["Diluted EPS", "Basic EPS", "EPS"]:
                        if label in qstmt.index:
                            eps_row = qstmt.loc[label]
                            break
                    if eps_row is not None:
                        # 扫全部列，跳过 NaN，取最近 4 个有值的季度（旧→新）
                        valid_cols = [
                            col for col in eps_row.index
                            if eps_row[col] is not None
                            and str(eps_row[col]) not in ("nan", "None", "NaN")
                        ]
                        for col in list(valid_cols[:4])[::-1]:
                            quarterly.append({
                                "quarter": str(col)[:7],
                                "eps": round(float(eps_row[col]), 4)
                            })
            except Exception:
                pass
        except Exception as e:
            print(f"[value/earnings us] {e}")

    if not rows:
        return {"rows": [], "avg": None, "trend": "unknown", "currency": "", "price": None}

    rows = rows[-3:]   # 旧→新排列，取最近3年（避免[:3]截掉最新年）
    values = [r["eps"] for r in rows if r["eps"] is not None]
    avg = round(sum(values) / len(values), 4) if values else None

    trend = "stable"
    if len(values) >= 2:
        if values[-1] > values[0] * 1.05:   # 最新 vs 最旧
            trend = "up"
        elif values[-1] < values[0] * 0.95:
            trend = "down"

    currency_map = {"cn": "¥", "hk": "HK$", "us": "$", "au": "A$", "nz": "NZ$", "kr": "₩"}
    currency = currency_map.get(market, "")

    # ── 当前股价 ──────────────────────────────────────────────────
    price = None
    try:
        from radar_app.data.stocks import get_latest_price
        price_row = get_latest_price(code)
        if price_row:
            price = price_row.get("price")
    except Exception:
        pass

    # ── 衍生指标 ─────────────────────────────────────────────────
    latest_eps = values[-1] if values else None
    pe_current = round(price / latest_eps, 1) if price and latest_eps and latest_eps > 0 else None

    # 52周 PE 区间：从本地 stock_prices 表算（快，无网络依赖）
    pe_52w_low = pe_52w_high = None
    if latest_eps and latest_eps > 0:
        try:
            from radar_app.data.core import get_conn
            with get_conn() as _c:
                from datetime import datetime as _dt, timedelta as _td
                _cut365 = (_dt.utcnow() - _td(days=365)).strftime("%Y-%m-%d")
                _rows = _c.execute(
                    "SELECT price FROM stock_prices WHERE code=:code "
                    "AND fetched_at >= :cut AND price > 0",
                    {"code": code, "cut": _cut365}
                ).fetchall()
            if len(_rows) >= 2:
                _prices = [r["price"] for r in _rows]
                pe_52w_low  = round(min(_prices) / latest_eps, 1)
                pe_52w_high = round(max(_prices) / latest_eps, 1)
            elif market != "cn":
                # 非A股：从 yfinance fast_info 拿52周高低
                import yfinance as yf
                fi = yf.Ticker(code).fast_info
                hi = getattr(fi, 'year_high', None)
                lo = getattr(fi, 'year_low',  None)
                if hi: pe_52w_high = round(float(hi) / latest_eps, 1)
                if lo: pe_52w_low  = round(float(lo) / latest_eps, 1)
        except Exception as e:
            print(f"[value/pe52w] {e}")

    # EPS 3年 CAGR
    eps_cagr = None
    if len(values) >= 2 and values[0] > 0 and values[-1] > 0:
        n = len(values) - 1
        eps_cagr = round((values[-1] / values[0]) ** (1 / n) - 1, 3)

    # 隐含增长率（后端计算，前端直接用）
    implied_growth = None
    if pe_current and pe_current > 0:
        raw = (pe_current / 15 * (1.10 ** 10)) ** (1 / 10) - 1
        implied_growth = round(max(raw, 0), 3)

    # 行业名称 + 行业增速基准
    industry_name = industry_growth_est = None
    _IG = {
        "信息技术": .15, "计算机": .15, "电子": .18, "半导体": .20, "IT": .15,
        "医疗": .12, "医药": .12, "生物": .15, "healthcare": .12,
        "消费": .08, "食品饮料": .08, "consumer": .08,
        "金融": .07, "银行": .06, "financial": .07,
        "能源": .05, "煤炭": .04, "energy": .05,
        "制造": .08, "机械": .08, "industrials": .08,
        "通信": .10, "传媒": .08, "technology": .15,
        "房地产": .02, "real estate": .02,
    }
    try:
        # A股：sector 字段在 DB 里，或跳过（东财接口本地不可用）
        if market == "cn":
            industry_name = stock.get("sector") or None
        else:
            import yfinance as yf
            _info = yf.Ticker(code).info
            industry_name = _info.get("sector") or _info.get("industry")
        if industry_name:
            for kw, g in _IG.items():
                if kw.lower() in industry_name.lower():
                    industry_growth_est = g
                    break
            if industry_growth_est is None:
                industry_growth_est = 0.10
    except Exception:
        pass

    # ── P/S 数据（亏损/成长公司分支，EPS≤0 时前端用）─────────
    ps_current = ps_history = revenue_growth = gross_margin = None
    revenue_abs = shares = None
    if latest_eps is None or latest_eps <= 0:
        try:
            if market != "cn":
                import yfinance as yf
                _t    = yf.Ticker(code)
                _info = _t.info or {}
                _mc   = _info.get("marketCap")
                _rev  = _info.get("totalRevenue")
                shares = _info.get("sharesOutstanding")
                if _mc and _rev and _rev > 0:
                    ps_current  = round(_mc / _rev, 2)
                    revenue_abs = _rev
                # 营收增速（年度 income_stmt）
                try:
                    _stmt = _t.income_stmt
                    if _stmt is not None and not _stmt.empty:
                        for _lbl in ("Total Revenue", "Revenue"):
                            if _lbl in _stmt.index:
                                _revs = [float(v) for v in _stmt.loc[_lbl].values[:3]
                                         if v is not None and str(v) not in ("nan","None")]
                                if len(_revs) >= 2:
                                    _revs.reverse()   # 旧→新
                                    n = len(_revs) - 1
                                    revenue_growth = round((_revs[-1]/_revs[0])**(1/n) - 1, 3)
                                break
                        # 毛利率
                        for _lbl in ("Gross Profit",):
                            if _lbl in _stmt.index and "Total Revenue" in _stmt.index:
                                _gp  = float(_stmt.loc[_lbl].values[0])
                                _rv  = float(_stmt.loc["Total Revenue"].values[0])
                                if _rv > 0:
                                    gross_margin = round(_gp / _rv, 3)
                                break
                except Exception:
                    pass
                # P/S 历史区间（用本地 stock_prices + 当前 shares + annual revenue）
                if shares and revenue_abs:
                    try:
                        from radar_app.data.core import get_conn
                        from datetime import datetime as _dt, timedelta as _td
                        _cut1825 = (_dt.utcnow() - _td(days=1825)).strftime("%Y-%m-%d")
                        with get_conn() as _c:
                            _hrows = _c.execute(
                                "SELECT price, fetched_at FROM stock_prices WHERE code=:code "
                                "AND fetched_at >= :cut AND price > 0",
                                {"code": code, "cut": _cut1825}
                            ).fetchall()
                        if len(_hrows) >= 5:
                            _ps_vals = [r["price"] * shares / revenue_abs for r in _hrows]
                            _ps_vals.sort()
                            ps_history = {
                                "low":    round(_ps_vals[0], 1),
                                "high":   round(_ps_vals[-1], 1),
                                "median": round(_ps_vals[len(_ps_vals)//2], 1),
                            }
                    except Exception:
                        pass
        except Exception as e:
            print(f"[value/ps] {e}")

    return {
        "rows": rows, "quarterly": quarterly,
        "avg": avg, "trend": trend,
        "currency": currency, "market": market, "price": price,
        "pe_current": pe_current,
        "pe_52w_low": pe_52w_low, "pe_52w_high": pe_52w_high,
        "eps_cagr": eps_cagr,
        "implied_growth": implied_growth,
        "industry_name": industry_name,
        "industry_growth_est": industry_growth_est,
        "ps_current": ps_current,
        "ps_history": ps_history,
        "revenue_growth": revenue_growth,
        "gross_margin": gross_margin,
    }


def register_value_routes(app):

    @app.route('/stock/<path:code>/value')
    @login_required
    def stock_value_page(code):
        code = code.upper()
        stock = db.get_stock(code)
        stock_name = (stock or {}).get("name", code)
        locale = session.get("locale", "zh")
        return render_template(
            'stock/value.html',
            code=code,
            stock_name=stock_name,
            locale=locale,
            page=1,
        )

    @app.route('/stock/<path:code>/value/2')
    @login_required
    def stock_value_page2(code):
        code = code.upper()
        stock = db.get_stock(code)
        stock_name = (stock or {}).get("name", code)
        locale = session.get("locale", "zh")
        return render_template(
            'stock/value2.html',
            code=code,
            stock_name=stock_name,
            locale=locale,
            page=2,
        )

    @app.route('/api/value/<path:code>/market-timing')
    @login_required
    def api_value_market_timing(code):
        data = _fetch_market_timing(code.upper())
        return jsonify({"ok": True, **data})

    @app.route('/stock/<path:code>/value/3')
    @login_required
    def stock_value_page3(code):
        code = code.upper()
        stock = db.get_stock(code)
        stock_name = (stock or {}).get("name", code)
        return render_template('stock/value3.html', code=code,
                               stock_name=stock_name, locale=session.get("locale","zh"), page=3)

    @app.route('/stock/<path:code>/value/4')
    @login_required
    def stock_value_page4(code):
        code = code.upper()
        stock = db.get_stock(code)
        stock_name = (stock or {}).get("name", code)
        return render_template('stock/value4.html', code=code,
                               stock_name=stock_name, locale=session.get("locale","zh"), page=4)

    @app.route('/api/value/<path:code>/classify-observation', methods=['POST'])
    @login_required
    def api_value_classify_obs(code):
        body = request.get_json() or {}
        text = (body.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False})
        stock = db.get_stock(code) or {}
        name  = stock.get("name") or code
        result = _judge_insight(text, name)
        return jsonify({"ok": True, **result})

    @app.route('/api/value/<path:code>/signal-guide', methods=['POST'])
    @login_required
    def api_value_signal_guide(code):
        """AI 信号猎手指南：教用户去哪找这家公司的社交信号（24h 缓存）。"""
        data = _generate_signal_guide(code.upper())
        return jsonify({"ok": True, **data})

    @app.route('/api/value/<path:code>/moat-summary')
    @login_required
    def api_value_moat_summary(code):
        data = _fetch_moat_summary(code.upper())
        return jsonify({"ok": True, **data})

    @app.route('/api/value/<path:code>/earnings')
    @login_required
    def api_value_earnings(code):
        data = _fetch_earnings_data(code.upper())
        return jsonify({"ok": True, **data})

    @app.route('/api/value/<path:code>/save', methods=['POST'])
    @login_required
    def api_value_save(code):
        uid  = session['user_id']
        body = request.get_json() or {}
        from radar_app.data.core import get_conn
        with get_conn() as c:
            c.execute("""
                INSERT INTO value_theses
                    (user_id, code, earnings_ps, market_trend, market_obs,
                     years_choice, pe_low, pe_high,
                     fair_value_low, fair_value_high, price_at_save,
                     buy_thesis, review_date, valuation_method, ps_current)
                VALUES
                    (:uid, :code, :eps, :trend, :obs,
                     :years, :pel, :peh,
                     :fvl, :fvh, :price,
                     :thesis, :review, :vm, :ps)
            """, {
                "uid":    uid,
                "code":   code.upper(),
                "eps":    body.get("earnings_ps"),
                "trend":  body.get("demand_trend") or body.get("market_trend"),
                "obs":    body.get("market_obs"),
                "years":  body.get("years_choice"),
                "pel":    body.get("pe_low"),
                "peh":    body.get("pe_high"),
                "fvl":    body.get("fair_value_low"),
                "fvh":    body.get("fair_value_high"),
                "price":  body.get("price_at_save"),
                "thesis": body.get("buy_thesis"),
                "review": body.get("review_date"),
                "vm":     body.get("valuation_method", "eps_pe"),
                "ps":     body.get("ps_current"),
            })
        return jsonify({"ok": True})


def _fetch_moat_summary(code: str) -> dict:
    """Pull moat description + historical PE range for Step 3."""
    import sqlite3 as _sq, re as _re
    from radar_app.data.core import DB_PATH

    result: dict = {"moat_text": None, "pe_history": None, "grade": None, "market": None}

    stock = db.get_stock(code) or {}
    market = stock.get("market", "us")
    result["market"] = market

    try:
        con = _sq.connect(DB_PATH)
        con.row_factory = _sq.Row
        cur = con.cursor()

        # Latest analysis for moat description
        row = cur.execute(
            "SELECT moat, reasoning, grade, raw_output FROM analysis_results "
            "WHERE code=? ORDER BY id DESC LIMIT 1", (code,)
        ).fetchone()
        if row:
            result["grade"] = row["grade"]
            # Try to extract moat narrative from raw_output
            raw = row["raw_output"] or ""
            moat_snippet = None
            for pat in [r'护城河[：:].{10,300}', r'moat[：:].{10,300}',
                        r'竞争优势[：:].{10,300}']:
                m = _re.search(pat, raw, _re.IGNORECASE | _re.DOTALL)
                if m:
                    moat_snippet = m.group(0)[:200].strip()
                    break
            # Fall back to moat score field
            if not moat_snippet and row["moat"]:
                moat_snippet = row["moat"][:200]
            result["moat_text"] = moat_snippet
            result["reasoning"] = (row["reasoning"] or "")[:300]

        # Historical PE from stock_prices (rough: price / latest_eps)
        prices = cur.execute(
            "SELECT price, pe_ratio, fetched_at FROM stock_prices WHERE code=? "
            "ORDER BY fetched_at DESC LIMIT 260", (code,)
        ).fetchall()
        pe_vals = [r["pe_ratio"] for r in prices
                   if r["pe_ratio"] and 3 < r["pe_ratio"] < 200]
        if len(pe_vals) >= 10:
            result["pe_history"] = {
                "low":    round(min(pe_vals), 1),
                "high":   round(max(pe_vals), 1),
                "median": round(sorted(pe_vals)[len(pe_vals)//2], 1),
                "count":  len(pe_vals),
            }

        con.close()
    except Exception as e:
        print(f"[moat-summary] {e}")

    return result


def _fetch_market_timing(code: str) -> dict:
    """Step 2: 社交套利工作流 — 业务构成 + 可量化消费信号（A层）。
    信号按公司类型路由，最终计算数据汇聚度（3+同向=高置信度）。
    不含技术均线/机构信号。
    """
    import re as _re
    stock = db.get_stock(code) or {}
    market = stock.get("market")
    if not market:
        pure_c = _re.sub(r'\.(SS|SZ|SH|BJ|HK|AX|KS|KQ|NZ)$', '', code, flags=_re.I)
        market = ("cn" if _re.match(r'^\d{6}$', pure_c) else
                  "hk" if code.upper().endswith(".HK") else "us")

    result: dict = {"market": market, "biz": None, "signals": [], "convergence": {}}
    result["biz"] = _fetch_biz_description(code, market, stock)

    biz     = result["biz"] or {}
    signals = []
    # 去掉法律后缀（"Duolingo, Inc." → "Duolingo"），避免 Wikipedia/autocomplete 搜到注册页
    raw_name = (stock or {}).get("name") or code.split(".")[0]
    kw  = _re.sub(
        r',?\s*(Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|Group|Holdings?|PLC|SE|AG|NV|SA)\.?$',
        '', raw_name, flags=_re.I).strip().rstrip(',').strip()
    pure    = code.split(".")[0].upper()

    # ── 通用信号（所有市场）──────────────────────────────────
    gt = _fetch_gtrends(code, market, stock)
    if gt:
        signals.append({"type": "gtrends", **gt})

    ac = _fetch_autocomplete(kw, market)
    if ac:
        signals.append({"type": "autocomplete", **ac})

    wp = _fetch_wikipedia(kw, market)
    if wp:
        signals.append({"type": "wikipedia", **wp})

    # ── 消费 App（有 app_store_id 的公司）────────────────────
    app_id = biz.get("app_store_id")
    if app_id:
        ast = _fetch_appstore(app_id)
        if ast:
            signals.append({"type": "appstore", **ast})

    subreddit = biz.get("subreddit")
    if subreddit:
        rd = _fetch_reddit(subreddit)
        if rd:
            signals.append({"type": "reddit", **rd})

    # ── 科技/SaaS（Technology sector，非 App 公司）───────────
    sector  = (biz.get("sector") or stock.get("sector") or "").lower()
    is_tech = any(k in sector for k in ("technolog", "software", "semiconductor", "internet"))
    is_app  = bool(app_id)
    if is_tech and not is_app:
        gh = _fetch_github(kw)
        if gh:
            signals.append({"type": "github", **gh})
        hn = _fetch_hackernews(kw)
        if hn:
            signals.append({"type": "hackernews", **hn})

    # ── 游戏公司（Steam appid 映射）──────────────────────────
    _STEAM = {
        "RBLX":  {"appid": "1526456",  "name": "Roblox"},
        "EA":    {"appid": "1237950",  "name": "EA Sports FC"},
        "TTWO":  {"appid": "1237453",  "name": "GTA V"},
    }
    if pure in _STEAM and _STEAM[pure].get("appid"):
        st = _fetch_steam(_STEAM[pure]["appid"], _STEAM[pure]["name"])
        if st:
            signals.append({"type": "steam", **st})

    # ── A股专属：东财热度排名 ──────────────────────────────────
    if market == "cn":
        em = _fetch_em_hot_rank(code)
        if em:
            signals.append({"type": "em_hot_rank", **em})

    # ── 信息稀缺度（通用反向指标）────────────────────────────
    try:
        from scripts.social_signals import (
            fetch_news_frequency, _news_freq_score,
            fetch_analyst_coverage, _analyst_score,
        )
        news_d     = fetch_news_frequency(code)
        anl_d      = fetch_analyst_coverage(code)
        news_score = _news_freq_score(news_d)
        anl_score  = _analyst_score(anl_d)
        total_a    = news_score + anl_score
        stage = ("极早期" if total_a >= 26 else "早期" if total_a >= 20 else
                 "扩散中" if total_a >= 13 else "进主流" if total_a >= 6 else "已公开")
        signals.append({
            "type":          "undiscovered",
            "news_7d":       news_d.get("count_7d"),
            "news_score":    news_score,
            "analyst_cnt":   anl_d.get("count"),
            "analyst_score": anl_score,
            "total_a":       total_a,
            "stage":         stage,
            "dir":           ("bull" if total_a >= 20 else
                              "bear" if total_a <= 6  else "neut"),
        })
    except Exception as e:
        print(f"[undiscovered] {e}")

    result["signals"]     = signals
    result["convergence"] = _compute_convergence(signals)
    return result


def _fetch_em_keywords(code: str) -> dict | None:
    """东方财富：个股所属概念的热度（反映行业/消费方向市场温度）。"""
    try:
        import akshare as ak
        # 转换为东财格式 600519 → SH600519
        pure = code.split(".")[0]
        suffix = "SH" if pure.startswith(("6", "9")) else "SZ"
        sym = f"{suffix}{pure}"
        df = ak.stock_hot_keyword_em(symbol=sym)
        if df.empty:
            return None
        # 取热度最高的3个概念
        df = df.sort_values("热度", ascending=False).head(3)
        top = [{"concept": r["概念名称"], "heat": int(r["热度"])}
               for _, r in df.iterrows()]
        top_heat   = top[0]["heat"] if top else 0
        top_concept = top[0]["concept"] if top else ""
        # 简单解读：取最高热度绝对值作参考
        level = ("热度极高" if top_heat > 5000 else
                 "热度较高" if top_heat > 1000 else
                 "热度一般" if top_heat > 200  else "热度偏低")
        return {
            "top_concepts": top,
            "top_heat":     top_heat,
            "level":        level,
            "interp":       f"市场最关注的概念是「{top_concept}」，{level}（{top_heat:,}）。"
        }
    except Exception as e:
        print(f"[em_keywords] {e}")
        return None


def _fetch_biz_description(code: str, market: str, stock: dict) -> dict:
    """业务描述 + 收入构成（研究地图）+ app_store_id / subreddit 检测。"""
    out: dict = {
        "sector": stock.get("sector"), "summary": None,
        "app_store_id": None, "subreddit": None,
        "revenue_breakdown": [],   # [{name, pct, amount}]
        "driver": None,            # 核心需求驱动因子一句话
    }

    # ── 非A股：yfinance ──────────────────────────────────────
    if market != "cn":
        try:
            import yfinance as yf
            info = yf.Ticker(code).info
            out["sector"]  = out["sector"] or info.get("sector")
            summary = info.get("longBusinessSummary") or ""
            out["summary"] = summary[:280] if summary else None
            # 商业模式简短标签
            out["biz_model"] = info.get("industry")
        except Exception:
            pass

    # ── A股：AKShare 主营构成 ────────────────────────────────
    if market == "cn":
        try:
            import akshare as ak
            pure = code.split(".")[0]
            prefix = "sh" if pure.startswith(("6", "9")) else "sz"
            sym = f"{prefix}{pure}"
            df = ak.stock_zygc_em(symbol=sym)
            if not df.empty:
                # 取最新报告期，按产品分类
                latest = df["报告日期"].max()
                sub = df[(df["报告日期"] == latest) & (df["分类类型"] == "按产品分类")]
                if sub.empty:
                    sub = df[df["报告日期"] == latest]
                rows = []
                for _, r in sub.head(5).iterrows():
                    name = r.get("主营构成")
                    pct  = r.get("收入比例")   # 小数 0~1
                    amt  = r.get("主营收入")
                    if name and pct is not None:
                        rows.append({
                            "name":   str(name)[:12],
                            "pct":    round(float(pct) * 100, 1),
                            "amount": amt,
                        })
                if rows:
                    out["revenue_breakdown"] = sorted(rows, key=lambda x: -x["pct"])
                    out["biz_model"] = f"主营 {rows[0]['name']}"
        except Exception as e:
            print(f"[zygc] {e}")

        # A股业务描述 fallback：从 analysis_results 提取
        try:
            import sqlite3 as _sql, json as _j
            from radar_app.data.core import DB_PATH
            con = _sql.connect(DB_PATH)
            con.row_factory = _sql.Row
            row = con.execute(
                "SELECT moat_direction FROM analysis_results "
                "WHERE code=? ORDER BY id DESC LIMIT 1", (code,)
            ).fetchone()
            con.close()
            if row and row["moat_direction"]:
                out["summary"] = row["moat_direction"][:200]
        except Exception:
            pass

    # ── App 公司映射 ─────────────────────────────────────────
    _APPS = {
        "DUOL":  {"id": "570060128",  "sub": "duolingo"},
        "RBLX":  {"id": "431946152",  "sub": "roblox"},
        "SNAP":  {"id": "447188370",  "sub": "snapchat"},
        "SPOT":  {"id": "324684580",  "sub": "spotify"},
        "UBER":  {"id": "368677368",  "sub": "uber"},
        "ABNB":  {"id": "1075906324", "sub": "airbnb"},
        "NFLX":  {"id": "363590051",  "sub": "netflix"},
        "META":  {"id": "454638411",  "sub": "facebook"},
    }
    pure = code.split(".")[0].upper()
    if pure in _APPS:
        out["app_store_id"] = _APPS[pure]["id"]
        out["subreddit"]    = _APPS[pure]["sub"]
    return out


def _fetch_gtrends(code: str, market: str, stock: dict) -> dict | None:
    try:
        from pytrends.request import TrendReq
        kw  = (stock or {}).get("name") or code.split(".")[0]
        geo = "CN" if market == "cn" else ""
        hl  = "zh-CN" if market == "cn" else "en-US"
        pt  = TrendReq(hl=hl, tz=480 if market == "cn" else 360)
        pt.build_payload([kw], timeframe="today 3-m", geo=geo)
        df  = pt.interest_over_time()
        if df.empty or kw not in df.columns:
            return None
        vals   = [v for v in df[kw].tolist() if v is not None]
        avg    = round(sum(vals) / len(vals), 1) if vals else None
        recent = round(sum(vals[-4:]) / 4, 1)   if len(vals) >= 4 else avg
        if not avg or avg == 0:
            return None
        # 变化率（速度）比绝对值更有预测力
        change_pct = round((recent - avg) / avg * 100) if avg > 0 else 0
        direction  = ("up"   if change_pct >= 10 else
                      "down" if change_pct <= -10 else "stable")
        dir_       = ("bull" if change_pct >= 15 else
                      "bear" if change_pct <= -15 else "neut")
        arrow = f"↑ +{change_pct}%" if change_pct > 0 else f"↓ {change_pct}%"
        interp = f"搜索热度 {arrow}（过去3个月）"
        return {"avg": avg, "recent": recent, "direction": direction,
                "change_pct": change_pct, "dir": dir_,
                "keyword": kw, "interp": interp, "geo": geo or "全球"}
    except Exception as e:
        print(f"[gtrends] {e}")
        return None


def _fetch_appstore(app_id: str) -> dict | None:
    """iTunes lookup + Apple Top Free Charts rank."""
    import urllib.request as _ur, json as _j
    try:
        # 评分信息
        url = f"https://itunes.apple.com/lookup?id={app_id}&country=US"
        with _ur.urlopen(url, timeout=6) as r:
            info = _j.loads(r.read())["results"][0]
        rating = info.get("averageUserRating")
        cnt    = info.get("userRatingCount")
        name   = info.get("trackName", "")

        # 全榜排名（Top 100 Free）
        rank = None
        try:
            charts_url = "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/100/apps.json"
            with _ur.urlopen(charts_url, timeout=6) as r2:
                charts = _j.loads(r2.read())["feed"]["results"]
            for i, a in enumerate(charts):
                if a["id"] == app_id:
                    rank = i + 1
                    break
        except Exception:
            pass

        dir_ = ("bull" if rank and rank <= 20 else
                "neut" if rank and rank <= 100 else
                "bear")
        rank_str = f"Top Free #{rank}" if rank else "榜外"
        interp   = f"App Store {rank_str}，评分 {rating:.1f}/5（{cnt//10000}万条评价）"
        return {"name": name, "rating": rating, "rating_count": cnt,
                "top100_rank": rank, "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[appstore] {e}")
        return None


def _fetch_reddit(subreddit: str) -> dict | None:
    """Reddit product community activity via public JSON API."""
    import urllib.request as _ur, json as _j
    from datetime import datetime, timezone
    try:
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=50"
        req = _ur.Request(url, headers={"User-Agent": "StockResearch/1.0"})
        with _ur.urlopen(req, timeout=8) as r:
            data = _j.loads(r.read())
        posts = data["data"]["children"]
        now   = datetime.now(timezone.utc).timestamp()
        week  = [p["data"] for p in posts
                 if now - p["data"]["created_utc"] < 7 * 86400]
        if not week:
            return None
        neg_kw = ["bug", "broken", "crash", "problem", "issue", "hate",
                  "terrible", "awful", "worst", "disappointed"]
        neg = sum(1 for p in week
                  if any(w in p["title"].lower() for w in neg_kw))
        pos_pct = round((len(week) - neg) / len(week) * 100)
        sentiment = "正面" if pos_pct >= 70 else "负面" if pos_pct < 40 else "中性"
        dir_ = ("bull" if pos_pct >= 70 else "bear" if pos_pct < 40 else "neut")
        return {"subreddit": subreddit, "posts_7d": len(week),
                "positive_pct": pos_pct, "sentiment": sentiment,
                "dir": dir_,
                "interp": f"r/{subreddit} 近7天 {len(week)} 帖，{pos_pct}% 正面情绪"}
    except Exception as e:
        print(f"[reddit/{subreddit}] {e}")
        return None


def _fetch_autocomplete(keyword: str, market: str) -> dict | None:
    """Google Autocomplete: 检测品牌负向联想词，直接展示词条供用户判断。"""
    import urllib.request as _ur, urllib.parse as _up, re as _re
    try:
        # 中文用品牌名直接搜；英文用 "brand is" 探负向联想
        if market == "cn":
            q_main = _up.quote(keyword)
        else:
            q_main = _up.quote(f"{keyword} is")
        hl  = "zh-CN" if market == "cn" else "en-US"
        url = (f"http://suggestqueries.google.com/complete/search"
               f"?output=toolbar&hl={hl}&q={q_main}")
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=5) as r:
            xml = r.read().decode("utf-8", errors="ignore")
        suggestions = _re.findall(r'data="([^"]+)"', xml)
        if not suggestions:
            return None

        # 完整短语匹配（保守：只标记明确负面，避免 "issues"/"bad" 误报）
        NEG_PHRASES = [
            "dead", "dying", "bankrupt", "shutting down", "going bankrupt",
            "terrible", "scam", "fraud", "going out of business",
            "倒闭", "亏损", "骗局", "欺骗", "退市", "暴雷", "假冒", "维权",
        ]

        def _has_neg(s):
            sl = s.lower()
            return any(p in sl for p in NEG_PHRASES)

        neg_count = sum(1 for s in suggestions if _has_neg(s))
        dir_ = "bear" if neg_count >= 2 else "neut"

        # 展示词：去掉品牌名+查询词前缀，保留尾部有意义部分
        kw_lower = keyword.lower()
        # 去掉 "brand is " / "brand " 前缀后取剩余部分
        strip_prefix = (kw_lower + " is ") if market != "cn" else (kw_lower + " ")
        display = []
        for s in suggestions[:6]:
            sl = s.lower()
            tail = sl[len(strip_prefix):] if sl.startswith(strip_prefix) \
                   else sl[len(kw_lower):].lstrip() if sl.startswith(kw_lower) \
                   else sl
            tail = tail.strip()
            min_len = 1 if market == "cn" else 3   # CJK chars are denser
            if tail and len(tail) >= min_len and tail != kw_lower:
                display.append(tail)
        display = display[:3]

        shown = display or [s[:25] for s in suggestions[:3]]
        interp = f"联想词：「{'」「'.join(shown)}」"
        if neg_count >= 2:
            interp += f"（{neg_count} 个负面词）"

        return {"suggestions": suggestions[:5], "display_words": shown,
                "neg_count": neg_count, "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[autocomplete] {e}")
        return None


def _fetch_wikipedia(keyword: str, market: str) -> dict | None:
    """Wikipedia 月度页面浏览量 30日变化率（学术验证：pageviews↑ → 更高股票回报）。"""
    import urllib.request as _ur, urllib.parse as _up, json as _j, re as _re
    from datetime import datetime, timedelta
    try:
        # 去掉公司法律后缀（避免搜到企业注册页而非品牌主页）
        keyword = _re.sub(
            r',?\s*(Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|Group|Holdings?|PLC|SE|AG|NV|SA)\.?$',
            '', keyword, flags=_re.I).strip().rstrip(',').strip()
        # 先用 OpenSearch 找正确文章标题
        lang = "zh" if market == "cn" else "en"
        for try_lang in ([lang, "en"] if lang == "zh" else [lang]):
            search_url = (f"https://{try_lang}.wikipedia.org/w/api.php"
                          f"?action=opensearch&search={_up.quote(keyword)}"
                          f"&limit=1&format=json")
            req = _ur.Request(search_url,
                              headers={"User-Agent": "PersonalBuffett/1.0"})
            with _ur.urlopen(req, timeout=6) as r:
                res = _j.loads(r.read())
            titles = res[1] if len(res) > 1 else []
            if titles:
                lang = try_lang
                break
        if not titles:
            return None
        title = _up.quote(titles[0].replace(" ", "_"))

        now         = datetime.utcnow()
        this_start  = now.replace(day=1).strftime("%Y%m%d")
        this_end    = now.strftime("%Y%m%d")
        last_end_dt = now.replace(day=1) - timedelta(days=1)
        last_start  = last_end_dt.replace(day=1).strftime("%Y%m%d")
        last_end    = last_end_dt.strftime("%Y%m%d")

        def _views(start, end):
            url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews"
                   f"/per-article/{lang}.wikipedia/all-access/all-agents"
                   f"/{title}/daily/{start}/{end}")
            rq = _ur.Request(url, headers={"User-Agent": "PersonalBuffett/1.0",
                                           "Accept": "application/json"})
            with _ur.urlopen(rq, timeout=8) as r:
                d = _j.loads(r.read())
            return sum(i["views"] for i in d.get("items", []))

        this_raw   = _views(this_start, this_end)
        last_total = _views(last_start, last_end)
        if last_total == 0 or this_raw == 0:
            return None
        # 折算本月完整月估算
        day_of_month = now.day
        this_est     = round(this_raw * 30 / day_of_month)
        change_pct   = round((this_est - last_total) / last_total * 100)
        dir_  = "bull" if change_pct >= 20 else "bear" if change_pct <= -20 else "neut"
        arrow = f"↑ +{change_pct}%" if change_pct > 0 else f"↓ {change_pct}%"
        count_str = f"{this_est//1000}k" if this_est >= 1000 else str(this_est)
        interp = f"Wikipedia关注度 {arrow}（本月 vs 上月，约 {count_str} 次浏览）"
        return {"title": titles[0], "lang": lang, "this_month": this_est,
                "last_month": last_total, "change_pct": change_pct,
                "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[wikipedia] {e}")
        return None


def _fetch_github(keyword: str) -> dict | None:
    """GitHub 相关仓库数（开发者生态活跃度代理，科技/SaaS 专属）。"""
    import urllib.request as _ur, urllib.parse as _up, json as _j
    try:
        url = (f"https://api.github.com/search/repositories"
               f"?q={_up.quote(keyword)}&sort=stars&per_page=1")
        req = _ur.Request(url, headers={
            "User-Agent": "PersonalBuffett/1.0",
            "Accept":     "application/vnd.github.v3+json",
        })
        with _ur.urlopen(req, timeout=6) as r:
            d = _j.loads(r.read())
        total     = d.get("total_count", 0)
        top_stars = d["items"][0].get("stargazers_count", 0) if d.get("items") else 0
        dir_      = "bull" if total >= 1000 else "neut" if total >= 100 else "bear"
        interp    = f"GitHub {total:,} 个相关项目，最热 {top_stars:,} ⭐"
        return {"total": total, "top_stars": top_stars, "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[github] {e}")
        return None


def _fetch_hackernews(keyword: str) -> dict | None:
    """HackerNews 历史讨论量（Algolia API，科技圈早期趋势信号）。"""
    import urllib.request as _ur, urllib.parse as _up, json as _j
    try:
        url = (f"https://hn.algolia.com/api/v1/search"
               f"?query={_up.quote(keyword)}&tags=story&hitsPerPage=1")
        req = _ur.Request(url, headers={"User-Agent": "PersonalBuffett/1.0"})
        with _ur.urlopen(req, timeout=6) as r:
            d = _j.loads(r.read())
        total  = d.get("nbHits", 0)
        dir_   = "bull" if total >= 500 else "neut" if total >= 50 else "bear"
        interp = f"HackerNews {total:,} 条讨论（科技圈关注度）"
        return {"total": total, "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[hackernews] {e}")
        return None


def _fetch_steam(appid: str, game_name: str) -> dict | None:
    """Steam 当前在线人数（游戏公司需求代理）。"""
    import urllib.request as _ur, json as _j
    try:
        url = (f"https://api.steampowered.com/ISteamUserStats"
               f"/GetNumberOfCurrentPlayers/v1/?appid={appid}")
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=6) as r:
            d = _j.loads(r.read())
        ccu = d.get("response", {}).get("player_count", 0)
        if ccu == 0:
            return None
        dir_   = "bull" if ccu >= 10000 else "neut" if ccu >= 1000 else "bear"
        interp = f"Steam {ccu:,} 人在线（{game_name}）"
        return {"appid": appid, "ccu": ccu, "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[steam/{appid}] {e}")
        return None


def _fetch_em_hot_rank(code: str) -> dict | None:
    """A股东财人气排名 + 新晋/铁杆粉丝比（信息扩散阶段判断）。"""
    import re as _re
    try:
        import akshare as ak
        pure = _re.sub(r'\.(SS|SZ|SH|BJ)$', '', code, flags=_re.I).split(".")[0]
        df   = ak.stock_hot_rank_em()
        match = df[df["代码"].str.endswith(pure)]
        if match.empty:
            # 不在热度榜 = 极冷门 = 对社交套利最早期
            return {"rank": None, "off_chart": True, "dir": "bull",
                    "interp": "未上东财热度榜（1000名以外），市场关注极少，信息最早"}
        rank    = int(match.iloc[0]["当前排名"])
        new_pct = None
        try:
            import math as _math
            sym = ("SH" if pure.startswith(("6", "9")) else "SZ") + pure
            df2 = ak.stock_hot_rank_detail_em(symbol=sym)
            if not df2.empty:
                latest = df2.sort_values("时间").iloc[-1]
                val    = float(latest["新晋粉丝"])
                if not _math.isnan(val):
                    new_pct = round(val * 100, 1)
        except Exception:
            pass
        # 排名越靠后=越冷门=信息越早（反向）
        dir_  = "bull" if rank >= 300 else "neut" if rank >= 100 else "bear"
        phase = ""
        if new_pct is not None:
            phase = f"，新晋粉丝 {new_pct}%（{'认知扩散中' if new_pct >= 30 else '老粉主导，已定价' if new_pct < 20 else '扩散初期'}）"
        interp = f"东财热度 #{rank}{phase}"
        return {"rank": rank, "new_pct": new_pct, "dir": dir_, "interp": interp}
    except Exception as e:
        print(f"[em_hot_rank] {e}")
        return None


def _compute_convergence(signals: list) -> dict:
    """数据汇聚度：3+同向信号=高置信度（TickerTrends 核心方法论）。"""
    dirs  = [s.get("dir") for s in signals if s.get("dir") in ("bull", "bear", "neut")]
    if not dirs:
        return {"level": "none", "label": "暂无信号", "color": "gray",
                "bull": 0, "bear": 0, "neut": 0, "total": 0, "dominant": "neut"}
    bull  = dirs.count("bull")
    bear  = dirs.count("bear")
    neut  = dirs.count("neut")
    total = len(dirs)
    same  = max(bull, bear)
    dom   = "bull" if bull >= bear else "bear"

    if same >= 3:
        label = f"多信号汇聚（{same}/{total} 同向{'看多' if dom == 'bull' else '看空'}）"
        color = "green" if dom == "bull" else "red"
        level = "high"
    elif same == 2:
        label = f"信号初现（{same}/{total} 同向）"
        color = "yellow"
        level = "emerging"
    else:
        label = "信号分散，暂无明确方向"
        color = "gray"
        level = "scattered"

    return {"level": level, "label": label, "color": color,
            "bull": bull, "bear": bear, "neut": neut,
            "total": total, "dominant": dom}


def _judge_insight(text: str, stock_name: str) -> dict:
    """US-112 C层：Groq 判断独家洞察信号质量（-15~+15）。"""
    try:
        from scripts.social_signals import judge_insight
        return judge_insight(text, stock_name)
    except Exception as e:
        print(f"[judge_insight] {e}")
        return {"signal_type": "neutral", "adjustment": 0, "reasoning": "判断失败"}


# ── AI 信号猎手指南缓存（内存，24h）──────────────────────────────
_SIGNAL_GUIDE_CACHE: dict = {}   # code → {guides, ts}

_GUIDE_SYSTEM = """你是 Chris Camillo 式的社交套利研究员。
你的任务：根据公司的业务特征，生成一份**具体可执行**的信号猎手清单，
帮助普通投资者**在机构之前**发现消费需求的真实变化。

规则：
- 每条信号说明：去哪 + 找什么 + 什么变化意味着买入信号
- 只写对这家公司真正有价值的渠道，不要通用废话
- 5~7 条，每条 channel 字段不超过 10 字，what 不超过 25 字，signal 不超过 20 字
- 中文输出，平台/产品名称可保留英文
- 只输出 JSON 数组，不加其他文字：
  [{"channel":"渠道","what":"去找什么","signal":"什么变化=信号"}]"""


def _generate_signal_guide(code: str) -> dict:
    """Groq 生成公司专属社交信号猎手指南，24h 内存缓存。"""
    import time, json as _j
    from radar_app.data.core import DB_PATH
    import sqlite3 as _sql

    # 24h 缓存
    cached = _SIGNAL_GUIDE_CACHE.get(code)
    if cached and time.time() - cached["ts"] < 86400:
        return {"guides": cached["guides"], "cached": True}

    stock = db.get_stock(code) or {}
    name  = stock.get("name") or code
    sector = stock.get("sector") or "—"

    # 拿业务描述（已有的 biz summary）
    biz = _fetch_biz_description(code, stock.get("market","us"), stock)
    summary = biz.get("summary") or ""
    biz_model = biz.get("biz_model") or ""

    user_msg = (
        f"公司：{name}（{code}）\n"
        f"行业：{sector}  商业模式：{biz_model}\n"
        f"业务简介：{summary[:200]}\n\n"
        "请生成针对这家公司的社交套利信号猎手清单。"
    )

    try:
        from scripts.buffett_groq import _call_groq
        raw = _call_groq(_GUIDE_SYSTEM, user_msg, max_tokens=400)
        import re
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        guides = _j.loads(m.group()) if m else []
    except Exception as e:
        print(f"[signal_guide] {e}")
        guides = []

    if guides:
        _SIGNAL_GUIDE_CACHE[code] = {"guides": guides, "ts": time.time()}

    return {"guides": guides, "cached": False}

