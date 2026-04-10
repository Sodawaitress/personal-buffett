#!/usr/bin/env python3
"""
删除不好的分析报告脚本

用法:
  python3 delete_analysis.py INTC C      # 删除 INTC 的所有 C 级（卖出）分析
  python3 delete_analysis.py INTC 2      # 删除 INTC 的 ID=2 的分析记录
  python3 delete_analysis.py INTC list   # 列出 INTC 的所有分析
"""

import sys
import db

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

code = sys.argv[1].upper()
action = sys.argv[2] if len(sys.argv) > 2 else "list"

db.init_db()

with db.get_conn() as c:
    # 先检查这个股票是否存在
    stock = c.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
    if not stock:
        print(f"❌ 股票 {code} 不存在")
        sys.exit(1)

    if action == "list":
        # 列出所有分析
        rows = c.execute("""
            SELECT id, analysis_date, period, grade, conclusion
            FROM analysis_results
            WHERE code = ?
            ORDER BY analysis_date DESC
        """, (code,)).fetchall()

        print(f"【{code} 的所有分析记录】\n")
        for row in rows:
            print(f"  ID {row[0]}: {row[1]} | {row[2]:6} | {row[3]} | {row[4]}")

        if not rows:
            print(f"  （暂无分析记录）")

        print(f"\n删除操作:")
        print(f"  python3 delete_analysis.py {code} ID      # 按 ID 删除")
        print(f"  python3 delete_analysis.py {code} C       # 删除所有 C 级分析")
        print(f"  python3 delete_analysis.py {code} B       # 删除所有 B 级分析")
        print(f"  python3 delete_analysis.py {code} A       # 删除所有 A 级分析")

    elif action.isdigit():
        # 按 ID 删除
        id_to_delete = int(action)
        result = c.execute("""
            DELETE FROM analysis_results
            WHERE code = ? AND id = ?
        """, (code, id_to_delete))

        if result.rowcount > 0:
            print(f"✅ 已删除 {code} 的 ID={id_to_delete} 的分析记录")
        else:
            print(f"❌ 未找到 {code} 的 ID={id_to_delete} 的分析记录")

    elif action in ["A", "B", "C", "A+", "A-", "B+", "B-"]:
        # 按等级删除
        result = c.execute("""
            DELETE FROM analysis_results
            WHERE code = ? AND grade = ?
        """, (code, action))

        if result.rowcount > 0:
            print(f"✅ 已删除 {code} 的所有 {action} 级分析记录（{result.rowcount} 条）")
        else:
            print(f"❌ 未找到 {code} 的 {action} 级分析记录")

    else:
        print(f"❌ 不支持的操作: {action}")
        print(__doc__)
        sys.exit(1)
