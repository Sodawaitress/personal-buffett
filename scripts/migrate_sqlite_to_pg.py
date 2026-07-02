#!/usr/bin/env python3
"""
一次性数据迁移：SQLite → Postgres(Neon)。schema 需先用 init_db 在 PG 建好。
保留主键 id（FK 完整性）；父表(users/stocks)优先；批量插入失败则逐行(跳过FK违规行)；
最后重置各表 id 序列。

用法：
  PG_URL='postgresql://...' python3 scripts/migrate_sqlite_to_pg.py prod_snap.db
"""
import os
import sqlite3
import sys

import psycopg2

SQLITE = sys.argv[1] if len(sys.argv) > 1 else "prod_snap.db"
PG = os.environ["PG_URL"]
PRIORITY = ["users", "stocks"]  # 父表先插

src = sqlite3.connect(SQLITE)
src.row_factory = sqlite3.Row
dst = psycopg2.connect(PG)

tables = [r[0] for r in src.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
ordered = [t for t in PRIORITY if t in tables] + [t for t in tables if t not in PRIORITY]

total_ok = total_fail = 0
for t in ordered:
    scols = [c[1] for c in src.execute(f"PRAGMA table_info({t})")]
    with dst.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (t,))
        pcols = {r[0] for r in cur.fetchall()}
    if not pcols:
        print(f"  跳过 {t}（PG 无此表）")
        continue
    cols = [c for c in scols if c in pcols]
    rows = src.execute(f"SELECT {','.join(cols)} FROM {t}").fetchall()
    if not rows:
        print(f"  {t}: 0 行")
        continue

    collist = ",".join(f'"{c}"' for c in cols)
    ph = "(" + ",".join(["%s"] * len(cols)) + ")"
    ins = f'INSERT INTO "{t}" ({collist}) VALUES {ph} ON CONFLICT DO NOTHING'
    tuples = [tuple(r[c] for c in cols) for r in rows]

    ok = fail = 0
    # 先试整表批量（快）
    try:
        with dst.cursor() as cur:
            cur.executemany(ins, tuples)
        dst.commit()
        ok = len(tuples)
    except Exception:
        dst.rollback()
        # 回退逐行（跳过 FK 违规等坏行）
        for tup in tuples:
            try:
                with dst.cursor() as cur:
                    cur.execute(ins, tup)
                dst.commit()
                ok += 1
            except Exception as e:
                dst.rollback()
                fail += 1
                if fail <= 2:
                    print(f"    {t} 行失败: {str(e)[:90]}")
    total_ok += ok
    total_fail += fail
    print(f"  {t}: {ok} 成功 / {fail} 失败")

# 重置 id 序列
for t in ordered:
    try:
        with dst.cursor() as cur:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{t}\"),1))")
        dst.commit()
    except Exception:
        dst.rollback()

print(f"\n完成：{total_ok} 行迁入 / {total_fail} 行跳过")
src.close()
dst.close()
