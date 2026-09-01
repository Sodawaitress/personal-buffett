"""US-206：量流水线的准点率。

改 cron 时间是个赌注 —— 不量就不知道赌赢没有。

用户观察到「每日五选的时间似乎在数据真的更新完前面」。查下来是
schedule 事件本身漂了 5-12 小时（不是排队，`createdAt` 就是晚的），
而下游 routine 在 UTC 13:2x 固定触发，于是读到前一天的数据。

这个脚本把漂移量打出来，好让「改成 :23 之后有没有变好」是可测的，
而不是感觉。
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta


def _runs(workflow: str, limit: int = 40):
    out = subprocess.run(
        ["gh", "run", "list", "--workflow", workflow, "-L", str(limit),
         "--json", "createdAt,updatedAt,conclusion,event"],
        capture_output=True, text=True, check=True).stdout
    return [r for r in json.loads(out) if r["event"] == "schedule"]


def _scheduled_minute(path: str):
    """从 workflow 文件里读出 cron 的 (时, 分)。写死会和文件失联。"""
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"cron:\s*'(\d+)\s+(\d+)\s", txt)
    return (int(m.group(2)), int(m.group(1))) if m else (None, None)


def report(workflow="pipeline.yml", limit=40):
    hh, mm = _scheduled_minute(f".github/workflows/{workflow}")
    if hh is None:
        return {"error": "cron 读不出来"}
    rows, delays = [], []
    for r in _runs(workflow, limit):
        started = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(r["updatedAt"].replace("Z", "+00:00"))
        due = started.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if started < due:                      # 早于当天预定 → 算前一天的
            due -= timedelta(days=1)
        delay_min = (started - due).total_seconds() / 60
        delays.append(delay_min)
        rows.append({
            "date": started.strftime("%m-%d"),
            "started": started.strftime("%H:%M"),
            "ended": ended.strftime("%H:%M"),
            "delay_min": round(delay_min),
            "dur_min": round((ended - started).total_seconds() / 60),
            "conclusion": r["conclusion"],
        })
    delays.sort()
    n = len(delays)
    return {
        "cron": f"{mm:02d}:{hh:02d} UTC" if False else f"{hh:02d}:{mm:02d} UTC",
        "runs": rows,
        "n": n,
        "median_delay_min": round(delays[n // 2]) if n else None,
        "worst_delay_min": round(delays[-1]) if n else None,
        # 下游 routine 固定 13:2x UTC。晚于它出数据 = 五选读到旧数据。
        "late_for_routine": sum(
            1 for r in rows if r["ended"] > "13:20") if rows else 0,
    }


if __name__ == "__main__":
    wf = sys.argv[1] if len(sys.argv) > 1 else "pipeline.yml"
    rep = report(wf)
    print(f"cron 预定：{rep.get('cron')}   样本 {rep.get('n')} 次")
    print(f"{'日期':<7}{'启动':>7}{'结束':>7}{'迟到(分)':>10}{'时长(分)':>10}  结果")
    for r in rep.get("runs", []):
        print(f"{r['date']:<7}{r['started']:>7}{r['ended']:>7}"
              f"{r['delay_min']:>10}{r['dur_min']:>10}  {r['conclusion']}")
    print(f"\n迟到中位数 {rep.get('median_delay_min')} 分 · "
          f"最差 {rep.get('worst_delay_min')} 分")
    print(f"⚠️ 结束时间晚于 routine（13:20 UTC）的有 "
          f"{rep.get('late_for_routine')} 次 —— 这些天的五选读的是前一天数据")
