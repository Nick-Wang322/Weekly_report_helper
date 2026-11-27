#!/usr/bin/env python3
"""
AI CoWork Log Summarizer
讀取指定日期的 log，輸出結構化資料供 Claude 生成今日工作總結。

解析策略：逐行掃，寬容比對。
  * 表頭同時接受「發問/回覆完成」與舊版「開始/結束」
  * 時間接受 HH:MM 與 HH:MM:SS
  * 時長接受 (123s)、「3 分鐘」、「2 分 5 秒」、「40 秒」
這支是 reader，只吃 writer 格式的超集；writer 微調欄位不該讓整支失效。
"""

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

# Windows 的主控台／管線預設是 cp950：hook 傳入的中文會亂碼、印出 ⚠ 會直接報錯。統一用 UTF-8。
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

LOG_DIR = Path(os.environ.get("AI_COWORK_LOG_DIR", str(Path.home() / "AI_coworkRec")))

HEADER_RE = re.compile(
    r"^\[互動 #(\d+)\]\s*(?:發問|開始)：([\d:]+)\s*\|\s*(?:回覆完成|結束)：([\d:]+)\s*\|\s*時長：(.+?)\s*$"
)
STATS_START_RE = re.compile(r"^(?:# ==== 今日統計|【今日統計)")


def parse_duration(text: str) -> int | None:
    """把時長欄位轉成秒。讀不到回 None，不要猜 0。"""
    m = re.search(r"\((\d+)s\)", text)          # 新版機器欄位優先
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*小時\s*(\d+)\s*分", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    m = re.search(r"(\d+)\s*分\s*(\d+)\s*秒", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"(\d+)\s*分", text)           # 舊版「3 分鐘」
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*秒", text)
    if m:
        return int(m.group(1))
    return None


def fmt_secs(secs: int) -> str:
    if secs < 60:
        return f"{secs}秒"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}分{s}秒" if s else f"{m}分"
    h, m = divmod(m, 60)
    return f"{h}小時{m}分"


def parse_log(content: str) -> tuple[list[dict], list[str]]:
    """回傳 (記錄清單, 無法解析的表頭行)。"""
    entries: list[dict] = []
    bad: list[str] = []
    current: dict | None = None
    expect: str | None = None       # 下一行要收進哪個欄位

    for line in content.splitlines():
        if STATS_START_RE.match(line):
            break                   # 統計區塊之後不再解析

        header = HEADER_RE.match(line)
        if header:
            current = {
                "n": int(header.group(1)),
                "start": header.group(2),
                "end": header.group(3),
                "secs": parse_duration(header.group(4)),
                "raw_duration": header.group(4),
                "topic": "", "q": "", "a": "", "tags": "",
            }
            entries.append(current)
            expect = None
            continue

        if line.startswith("[互動 #"):      # 是記錄表頭但格式不合
            bad.append(line)
            current = None
            continue

        if current is None:
            continue

        if expect:
            if line.strip():
                current[expect] = line.strip()
                expect = None
            continue

        if line.startswith("主題："):
            current["topic"] = line[3:].strip()
        elif line.startswith("問題摘要："):
            expect = "q"
        elif line.startswith("回應摘要："):
            expect = "a"
        elif line.startswith("標籤："):
            current["tags"] = line[3:].strip()

    return entries, bad


def main() -> None:
    parser = argparse.ArgumentParser(description="輸出某日 AI 互動記錄的結構化摘要")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD，預設今天")
    args = parser.parse_args()

    log_path = LOG_DIR / f"{args.date}.log"
    if not log_path.exists():
        print(f"找不到 {log_path}，{args.date} 尚無 AI 互動記錄。")
        return

    entries, bad = parse_log(log_path.read_text(encoding="utf-8", errors="replace"))

    if not entries:
        # 舊版只印「無法解析」，不說為什麼。這裡把證據附上。
        print(f"Log 檔存在但解析不到任何記錄：{log_path}", file=sys.stderr)
        if bad:
            print(f"有 {len(bad)} 行看起來是表頭但格式不合，例如：\n  {bad[0]}", file=sys.stderr)
        else:
            print("檔案裡找不到任何 '[互動 #N]' 表頭。", file=sys.stderr)
        sys.exit(1)

    known = [e["secs"] for e in entries if e["secs"] is not None]
    unknown = len(entries) - len(known)
    total = sum(known)

    tag_counts: dict[str, int] = {}
    for e in entries:
        for tag in e["tags"].split():
            if tag.startswith("#"):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    pending = [e for e in entries if "#待補" in e["tags"] or e["topic"].startswith("(摘要失敗")]

    print(f"=== {args.date} AI 工作 Log 原始資料 ===\n")
    print(f"總互動次數：{len(entries)} 次")
    print(f"總互動時間：{fmt_secs(total)}" + (f"（其中 {unknown} 筆時長不明，未計入）" if unknown else ""))
    if entries:
        print(f"時間範圍：{entries[0]['start']} ～ {entries[-1]['end']}")
    print()

    for e in entries:
        dur = fmt_secs(e["secs"]) if e["secs"] is not None else f"時長不明({e['raw_duration']})"
        print(f"[{e['n']}] {e['start']}～{e['end']} ({dur}) | {e['topic']}")
        print(f"    問：{e['q']}")
        print(f"    答：{e['a']}")
        print(f"    標籤：{e['tags']}")
        print()

    if tag_counts:
        print("標籤統計：")
        for tag, count in sorted(tag_counts.items(), key=lambda kv: -kv[1]):
            print(f"  {tag}: {count} 次")
        print()

    # 這些是 hook 摘要失敗留下的坑，要讓使用者知道總結會不完整。
    if pending:
        print(f"注意：{len(pending)} 筆摘要待補（#{'、#'.join(str(e['n']) for e in pending)}），"
              f"這些記錄的主題與摘要可能只有原文節錄。")
    if bad:
        print(f"注意：{len(bad)} 行表頭格式不合已跳過，第一筆：{bad[0]}")


if __name__ == "__main__":
    main()
