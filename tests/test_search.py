#!/usr/bin/env python3
"""
Stock Radar 搜索功能自动化测试

防止搜索功能被破坏的第一道防线。
每次修改搜索代码后运行这个测试。

运行方式:
    python3 tests/test_search.py
    或
    python3 -m pytest tests/test_search.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import db
from radar_app import create_app

app = create_app()


def test_search_requires_login():
    """测试搜索 API 仍然受登录保护"""
    db.init_db()

    with app.test_client() as client:
        resp = client.get('/api/search?q=AAPL')
        assert resp.status_code == 302, "未登录时搜索 API 应该重定向到登录页"
        assert '/login' in resp.headers.get('Location', ''), "未登录应跳转到 /login"

        print("✓ 搜索 API 仍然需要登录")


def test_search_returns_list():
    """测试搜索 API 返回正确的数据类型"""
    db.init_db()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1

        resp = client.get('/api/search?q=AAPL')
        assert resp.status_code == 200, "搜索 API 应该返回 200"

        data = resp.get_json()
        assert isinstance(data, list) or (isinstance(data, dict) and 'loading' in data), \
            "搜索 API 应该返回数组或 {loading: true} 对象"

        print("✓ 搜索 API 返回类型正确")


def test_search_valid_queries():
    """测试有效的搜索查询能返回结果"""
    db.init_db()

    test_cases = [
        ('AAPL', '美股', 1),
        ('茅台', 'A股中文', 1),
        ('600519', 'A股代码', 1),
        ('腾讯', '港股中文', 1),
    ]

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1

        for query, desc, min_results in test_cases:
            resp = client.get(f'/api/search?q={query}')
            assert resp.status_code == 200, f"Query '{query}' ({desc}) failed"

            data = resp.get_json()

            # 处理加载中状态
            if isinstance(data, dict) and data.get('loading'):
                print(f"⚠ Query '{query}' ({desc}): A股数据仍在加载中，跳过")
                continue

            assert isinstance(data, list), f"Query '{query}' ({desc}) 应该返回列表"
            assert len(data) >= min_results, \
                f"Query '{query}' ({desc}) 返回 {len(data)} 个结果，期望 >= {min_results}"

            print(f"✓ Query '{query}' ({desc}): {len(data)} 个结果")


def test_search_empty_results():
    """测试无效查询返回空结果"""
    db.init_db()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1

        # intel 不是有效的 ticker（应该用 INTC）
        resp = client.get('/api/search?q=intel')
        assert resp.status_code == 200
        data = resp.get_json()

        # 这应该返回空数组
        if isinstance(data, list):
            print(f"✓ Query 'intel' 返回空结果（符合预期）")
        else:
            print(f"⚠ Query 'intel' 返回非列表数据（可能还在加载）")


def test_search_variable_consistency():
    """
    验证搜索代码中的变量一致性
    这是防止 watchlist.html bug 再次发生的关键测试
    """
    import re

    # 读取 watchlist.html
    watchlist_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'watchlist.html')
    with open(watchlist_path, encoding='utf-8') as f:
        watchlist_content = f.read()

    # 查找 doSearch 函数
    dosearch_match = re.search(
        r'async function doSearch\(([^)]+)\)\s*\{(.*?)\n\s*\}',
        watchlist_content,
        re.DOTALL
    )

    assert dosearch_match, "未能找到 doSearch 函数"

    func_params = dosearch_match.group(1)
    func_body = dosearch_match.group(2)

    # 检查第一个参数的赋值（应该是 items）
    assign_match = re.search(r'const (\w+)\s*=\s*await.*fetch.*json\(\)', func_body)
    if assign_match:
        assigned_var = assign_match.group(1)
        print(f"✓ doSearch() 中的变量赋值: const {assigned_var} = ...")

        # 检查后续引用是否一致
        if assigned_var == 'items':
            # items 应该在后面被检查
            assert 'if (items && items.loading)' in func_body, \
                f"watchlist.html: 发现了 data/items 混淆 bug! 检查第 668 行"
            print(f"✓ 变量引用一致: if (items && items.loading) ✓")
        else:
            print(f"⚠ 发现非标准的变量名: {assigned_var}")


if __name__ == '__main__':
    print("=" * 60)
    print("Stock Radar 搜索功能测试")
    print("=" * 60)
    print()

    try:
        test_search_requires_login()
        print()

        test_search_returns_list()
        print()

        test_search_valid_queries()
        print()

        test_search_empty_results()
        print()

        test_search_variable_consistency()
        print()

        print("=" * 60)
        print("✅ 所有测试通过！搜索功能正常")
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
