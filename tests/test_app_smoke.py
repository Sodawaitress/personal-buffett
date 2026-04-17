#!/usr/bin/env python3
"""
Stock Radar 应用烟测

锁住重构后的主入口、模板目录和关键权限链。

运行方式:
    python3 tests/test_app_smoke.py
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask

from radar_app import create_app


def test_factory_renders_login_template():
    """create_app() 必须能找到根目录模板并渲染登录页"""
    app = create_app()

    with app.test_client() as client:
        health = client.get("/healthz")
        resp = client.get("/login")
        assert health.status_code == 200, "/healthz 应该返回 200"
        assert health.get_json() == {"ok": True}, "/healthz 应该返回稳定 JSON"
        assert resp.status_code == 200, "/login 应该返回 200"
        assert b"<html" in resp.data.lower(), "登录页模板应该被正常渲染"

    print("✓ create_app() 可正常渲染 login.html，健康检查正常")


def test_core_auth_guards():
    """关键页面和 API 仍然保持原来的登录门禁"""
    app = create_app()

    checks = [
        ("/register", 200, None),
        ("/", 302, "/login"),
        ("/watchlist", 302, "/login"),
        ("/api/search?q=AAPL", 302, "/login"),
    ]

    with app.test_client() as client:
        for path, expected_status, expected_location in checks:
            resp = client.get(path)
            assert resp.status_code == expected_status, f"{path} 应返回 {expected_status}"
            if expected_location:
                assert expected_location in resp.headers.get("Location", ""), f"{path} 应跳转到 {expected_location}"

    print("✓ 核心权限链保持正常")


def test_legacy_shims_still_export_app():
    """兼容壳 app.py 和 run.py 仍然导出 Flask app"""
    legacy_app = importlib.import_module("app")
    run_entry = importlib.import_module("run")

    assert isinstance(legacy_app.app, Flask), "app.py 应导出 Flask app"
    assert isinstance(run_entry.app, Flask), "run.py 应导出 Flask app"
    assert legacy_app.app.name == "radar_app", "legacy app 名称应保持稳定"
    assert run_entry.app.name == "radar_app", "run app 名称应保持稳定"

    print("✓ 兼容壳入口正常")


if __name__ == "__main__":
    print("=" * 60)
    print("Stock Radar 应用烟测")
    print("=" * 60)
    print()

    try:
        test_factory_renders_login_template()
        print()

        test_core_auth_guards()
        print()

        test_legacy_shims_still_export_app()
        print()

        print("=" * 60)
        print("✅ 应用烟测通过")
        print("=" * 60)
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ 测试失败: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ 测试出错: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        sys.exit(1)
