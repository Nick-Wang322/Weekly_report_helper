#!/usr/bin/env python3
"""
讀取指定週的每日 log，算出工時，輸出精簡結構化資料供 AI 判斷。

刻意不做的事：
  * 不把 log 全文餵給 AI（一週全文約 4~5 萬 tokens）
  * 不讓 AI 加總工時——加總是確定性運算，這裡算完直接給數字

兩種工時，語意不同，都輸出：
  ai_secs      各筆互動時長加總（送出訊息→回覆完成）。這是 AI 的處理時間，
               不含你閱讀、思考、改程式的時間，會明顯低於實際投入。
  engaged_secs 投入時距。相鄰互動間隔在 --gap 分鐘內視為同一段工作，
               取每段首尾時距相加。較接近「這週實際花在這件事上多久」。
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Windows 的主控台／管線預設是 cp950：hook 傳入的中文會亂碼、印出 ⚠ 會直接報錯。統一用 UTF-8。
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LOG_DIR = Path(os.environ.get("AI_COWORK_LOG_DIR", str(Path.home() / "AI_coworkRec")))

# log 格式的解析器只維護一份（在 ai-cowork-log skill 裡），避免各腳本正則各自漂移。
COWORK_SCRIPTS = Path(os.environ.get(
    "AI_COWORK_SCRIPTS", str(Path.home() / ".claude/skills/ai-cowork-log/scripts")))
sys.path.insert(0, str(COWORK_SCRIPTS))
try:
    from summarize import parse_log, fmt_secs
except ImportError:
    print(f"找不到 log 解析器：{COWORK_SCRIPTS}/summarize.py\n"
          f"若 ai-cowork-log skill 裝在別處，請設 AI_COWORK_SCRIPTS 環境變數。",
          file=sys.stderr)
    sys.exit(1)


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def resolve_week(spec: str | None) -> tuple[str, list[date]]:
    """回傳 (週次字串, 要讀的工作日清單)。預設本週週一到今天（最多到週五）。"""
    if spec:
        try:
            y, w = spec.upper().split("-W")
            monday = date.fromisocalendar(int(y), int(w), 1)
        except (ValueError, IndexError):
            die(f"--week 格式應為 YYYY-Www，例如 2026-W32（收到：{spec}）")
        end = monday + timedelta(days=4)
    else:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        end = min(today, monday + timedelta(days=4))  # 週六日則讀到週五
    y, w, _ = monday.isocalendar()
    days = []
    d = monday
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return f"{y}-W{w:02d}", days


def to_dt(day: date, hms: str) -> datetime | None:
    parts = hms.split(":")
    if len(parts) == 2:
        parts.append("00")
    try:
        return datetime(day.year, day.month, day.day,
                        int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def engaged_secs(entries: list[dict], gap_min: int) -> int:
    """相鄰互動間隔 <= gap 視為同段工作，回傳各段首尾時距之和。"""
    times = [(e["_start_dt"], e["_end_dt"]) for e in entries
             if e.get("_start_dt") and e.get("_end_dt")]
    if not times:
        return 0
    times.sort()
    gap = timedelta(minutes=gap_min)
    total = 0
    block_start, block_end = times[0]
    for s, e in times[1:]:
        if s - block_end > gap:
            total += int((block_end - block_start).total_seconds())
            block_start, block_end = s, e
        else:
            block_end = max(block_end, e)
    total += int((block_end - block_start).total_seconds())
    return total


def collect(days: list[date], gap_min: int) -> dict:
    found, missing, per_day, all_entries = [], [], [], []
    unknown = 0
    bad_lines = 0

    for day in days:
        path = LOG_DIR / f"{day.isoformat()}.log"
        if not path.exists():
            missing.append(day.isoformat())
            continue
        entries, bad = parse_log(path.read_text(encoding="utf-8", errors="replace"))
        bad_lines += len(bad)
        if not entries:
            missing.append(day.isoformat())
            continue
        found.append(day.isoformat())
        for e in entries:
            e["_date"] = day.isoformat()
            e["_start_dt"] = to_dt(day, e["start"])
            e["_end_dt"] = to_dt(day, e["end"])
            if e["secs"] is None:
                unknown += 1
        day_ai = sum(e["secs"] for e in entries if e["secs"] is not None)
        per_day.append({
            "date": day.isoformat(),
            "entries": len(entries),
            "ai_secs": day_ai,
            "engaged_secs": engaged_secs(entries, gap_min),
        })
        all_entries += entries

    tags: dict[str, int] = {}
    for e in all_entries:
        for t in e["tags"].split():
            if t.startswith("#"):
                tags[t] = tags.get(t, 0) + 1

    return {
        "found": found, "missing": missing, "per_day": per_day,
        "entries": all_entries, "tags": tags,
        "unknown_duration": unknown, "bad_header_lines": bad_lines,
        "ai_secs": sum(d["ai_secs"] for d in per_day),
        "engaged_secs": sum(d["engaged_secs"] for d in per_day),
    }


def hours(secs: int) -> float:
    return round(secs / 3600, 1)


def main() -> None:
    global LOG_DIR
    ap = argparse.ArgumentParser(description="彙整某週的 AI 互動 log 並算出工時")
    ap.add_argument("--log-dir", default=None, help=f"預設 {LOG_DIR}")
    ap.add_argument("--week", default=None, help="YYYY-Www，預設本週")
    ap.add_argument("--gap", type=int, default=30, help="間隔幾分鐘算換工作（預設 30）")
    ap.add_argument("--max-entries", type=int, default=200, help="互動清單最多列幾筆")
    ap.add_argument("--json", action="store_true", help="輸出 JSON（供 write_excel.py 使用）")
    args = ap.parse_args()

    if args.log_dir:
        LOG_DIR = Path(args.log_dir).expanduser()
    if not LOG_DIR.is_dir():
        die(f"log 目錄不存在：{LOG_DIR}")

    week, days = resolve_week(args.week)
    data = collect(days, args.gap)

    if not data["found"]:
        die(f"{week}（{days[0]} ~ {days[-1]}）找不到任何可解析的 log，目錄：{LOG_DIR}")

    payload = {
        "week": week,
        "range": [days[0].isoformat(), days[-1].isoformat()],
        "gap_minutes": args.gap,
        "found": data["found"], "missing": data["missing"],
        "per_day": data["per_day"],
        "totals": {
            "entries": len(data["entries"]),
            "ai_secs": data["ai_secs"], "ai_hours": hours(data["ai_secs"]),
            "engaged_secs": data["engaged_secs"], "engaged_hours": hours(data["engaged_secs"]),
            "unknown_duration": data["unknown_duration"],
            "bad_header_lines": data["bad_header_lines"],
        },
        "tags": data["tags"],
    }

    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    t = payload["totals"]
    print(f"週次：{week}（{days[0]} ~ {days[-1]}）")
    print(f"有 log：{', '.join(data['found'])}")
    if data["missing"]:
        print(f"無 log：{', '.join(data['missing'])}（請假／外勤／未記錄皆屬正常）")
    print()
    print("【工時：已由 script 計算完成，不要再自行加總】")
    print(f"  AI 互動累計時長 ai_hours = {t['ai_hours']} 小時"
          f"（{fmt_secs(t['ai_secs'])}，共 {t['entries']} 筆）")
    print(f"    ↑ 只含 Claude 處理時間，不含閱讀、思考、改程式，會低於實際投入")
    print(f"  投入時距 engaged_hours = {t['engaged_hours']} 小時"
          f"（{fmt_secs(t['engaged_secs'])}，間隔 >{args.gap} 分視為換工作）")
    if t["unknown_duration"]:
        print(f"  ⚠ {t['unknown_duration']} 筆時長不明，未計入")
    if t["bad_header_lines"]:
        print(f"  ⚠ {t['bad_header_lines']} 行表頭格式不合，已跳過")
    print()
    print("  分日：" + " / ".join(
        f"{d['date'][5:]} 投入 {hours(d['engaged_secs'])}h（AI {hours(d['ai_secs'])}h，{d['entries']} 筆）"
        for d in data["per_day"]))
    print()
    print("【標籤分布】" + (" / ".join(
        f"{k} x{v}" for k, v in sorted(data["tags"].items(), key=lambda kv: -kv[1])) or "（無）"))
    print()

    shown = data["entries"][:args.max_entries]
    print(f"【互動清單】共 {len(data['entries'])} 筆" +
          (f"，以下列出前 {len(shown)} 筆" if len(shown) < len(data["entries"]) else ""))
    for e in shown:
        dur = fmt_secs(e["secs"]) if e["secs"] is not None else "?"
        topic = e["topic"][:60]
        print(f"  {e['_date'][5:]} {e['start'][:5]} ({dur}) {e['tags']} {topic}")


if __name__ == "__main__":
    main()
