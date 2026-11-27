#!/usr/bin/env python3
"""
把週報資料寫入 FSB_AI_Weekly Excel，以新列累加。

分工原則：
  * 週次、工時：由本腳本從 read_logs.py 的 metrics 計算，不接受 AI 給的數字
  * 專案名稱／類型／階段／AI應用／備註／無AI預估：由 AI 判斷後經 --data-json 傳入
  * 多專案時 AI 只給分配比例 share，小時數由本腳本乘出來

安全措施：寫入前備份 .bak、以暫存檔原子替換、同週同專案重複偵測、--dry-run。
"""

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

# Windows 的主控台／管線預設是 cp950：hook 傳入的中文會亂碼、印出 ⚠ 會直接報錯。統一用 UTF-8。
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

try:
    import openpyxl
except ImportError:
    print(f"需要 openpyxl：{sys.executable} -m pip install openpyxl", file=sys.stderr)
    sys.exit(1)

CONFIG_PATH = Path(os.environ.get(
    "AI_WEEKLY_CONFIG", str(Path.home() / "AI_coworkRec/.weekly_config.json")))
SHEET_NAME = "AI_Weekly_Data"

# 欄位 → 模板表頭關鍵字。實際欄位位置以表頭比對結果為準，不寫死 A~N。
FIELD_HEADERS = [
    ("year", "年度"), ("week", "週次"), ("report_date", "填報日期"),
    ("name", "姓名"), ("role", "角色"),
    ("project_name", "專案名稱"), ("client_name", "客戶名稱"),
    ("project_type", "專案類型"), ("project_phase", "專案階段"),
    ("ai_type", "AI應用類型"),
    ("total_hours", "本週工時"), ("ai_hours", "使用AI"), ("no_ai_hours", "無AI"),
    ("notes", "備註"),
]
AI_FIELDS = ["project_name", "client_name", "project_type", "project_phase",
             "ai_type", "notes", "no_ai_hours"]


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def load_json(spec: str):
    if spec.strip().startswith(("{", "[")):
        return json.loads(spec)
    p = Path(spec).expanduser()
    if not p.exists():
        die(f"找不到檔案：{p}")
    return json.loads(p.read_text(encoding="utf-8"))


def norm(s) -> str:
    return "".join(str(s or "").split()).replace("(Hour)", "").replace("（Hour）", "")


def map_columns(ws) -> tuple[int, dict]:
    """在前 10 列找表頭，回傳 (表頭列號, {欄位: 欄號})。找不到就 fail loud。"""
    for row in range(1, min(10, ws.max_row) + 1):
        cells = {c: norm(ws.cell(row, c).value) for c in range(1, ws.max_column + 1)}
        mapping = {}
        for field, key in FIELD_HEADERS:
            k = norm(key)
            hit = next((c for c, text in cells.items()
                        if text and (text == k or k in text or text in k)), None)
            if hit:
                mapping[field] = hit
        if len(mapping) >= 10:
            missing = [f for f, _ in FIELD_HEADERS if f not in mapping]
            if missing:
                print(f"注意：表頭找不到這些欄位，將略過不寫：{'、'.join(missing)}", file=sys.stderr)
            return row, mapping
    die(f"在 '{ws.title}' 前 10 列找不到可辨識的表頭列。"
        f"請確認這是正確的工作表，或模板欄位名稱是否改過。")


def find_next_row(ws, header_row: int, cols: dict) -> int:
    used = list(cols.values())
    last = header_row
    for r in range(header_row + 1, ws.max_row + 1):
        if any(str(ws.cell(r, c).value or "").strip() for c in used):
            last = r
    return last + 1


def existing_rows(ws, header_row: int, cols: dict, week: str) -> list[tuple[int, str]]:
    """回傳該週已存在的 (列號, 專案名稱)。"""
    out = []
    wcol, pcol = cols.get("week"), cols.get("project_name")
    if not wcol:
        return out
    for r in range(header_row + 1, ws.max_row + 1):
        if str(ws.cell(r, wcol).value or "").strip() == week:
            out.append((r, str(ws.cell(r, pcol).value or "").strip() if pcol else ""))
    return out


def build_rows(projects: list[dict], metrics: dict, config: dict) -> list[dict]:
    total_engaged = metrics["totals"]["engaged_hours"]
    total_ai = metrics["totals"]["ai_hours"]

    shares = [float(p.get("share", 1 / len(projects))) for p in projects]
    if abs(sum(shares) - 1.0) > 0.02:
        die(f"share 加總為 {sum(shares):.2f}，應為 1.0。請修正 --data-json 的分配比例。")

    today = date.today().isoformat()
    rows = []
    for p, share in zip(projects, shares):
        missing = [f for f in AI_FIELDS if f not in p or p[f] in ("", None)]
        if missing:
            print(f"注意：專案「{p.get('project_name', '?')}」缺少欄位，將留空："
                  f"{'、'.join(missing)}", file=sys.stderr)
        row = {
            "year": date.today().year,
            "week": metrics["week"],
            "report_date": today,
            "name": config.get("name", ""),
            "role": config.get("role", ""),
            "total_hours": round(total_engaged * share, 1),
            "ai_hours": round(total_ai * share, 1),
        }
        for f in AI_FIELDS:
            row[f] = p.get(f)
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="寫入 FSB AI 週報 Excel")
    ap.add_argument("--data-json", required=True, help="AI 判斷結果（檔案路徑或 JSON 字串）")
    ap.add_argument("--metrics", required=True, help="read_logs.py --json 的輸出")
    ap.add_argument("--excel-path", default=None)
    ap.add_argument("--dry-run", action="store_true", help="只顯示要寫什麼，不寫檔")
    ap.add_argument("--force", action="store_true", help="該週已有記錄時仍然新增")
    args = ap.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    excel_path = args.excel_path or config.get("excel_path")
    if not excel_path:
        die(f"沒有 excel_path。請在 {CONFIG_PATH} 設定，或用 --excel-path 指定。")
    excel_path = Path(excel_path).expanduser()
    if not excel_path.exists():
        die(f"找不到 Excel：{excel_path}")

    metrics = load_json(args.metrics)
    if "totals" not in metrics or "week" not in metrics:
        die("--metrics 不是 read_logs.py --json 的輸出格式。")
    data = load_json(args.data_json)
    projects = data if isinstance(data, list) else [data]
    if not projects:
        die("--data-json 沒有任何專案資料。")

    wb = openpyxl.load_workbook(excel_path)
    if SHEET_NAME not in wb.sheetnames:
        die(f"找不到工作表 '{SHEET_NAME}'，現有：{wb.sheetnames}。"
            f"不猜測寫入位置，請確認模板或改 SHEET_NAME。")
    ws = wb[SHEET_NAME]

    header_row, cols = map_columns(ws)
    rows = build_rows(projects, metrics, config)
    week = metrics["week"]

    dupes = existing_rows(ws, header_row, cols, week)
    if dupes:
        names = [n for _, n in dupes]
        clash = [r["project_name"] for r in rows if r["project_name"] in names]
        msg = (f"{week} 在 Excel 已有 {len(dupes)} 列（列 "
               f"{', '.join(str(r) for r, _ in dupes)}：{'、'.join(names) or '未填專案'}）")
        if clash and not args.force:
            die(msg + f"\n其中專案「{'、'.join(clash)}」重複。"
                      f"要仍然新增請加 --force；要改既有列請手動編輯 Excel。")
        print("注意：" + msg, file=sys.stderr)

    start_row = find_next_row(ws, header_row, cols)
    t = metrics["totals"]

    print(f"週次：{week}｜有 log {len(metrics['found'])} 天"
          + (f"，缺 {len(metrics['missing'])} 天" if metrics["missing"] else ""))
    print(f"工時來源：投入時距 {t['engaged_hours']}h"
          f"（間隔 >{metrics['gap_minutes']} 分算換工作）"
          f"｜AI 互動累計 {t['ai_hours']}h")
    if t.get("unknown_duration"):
        print(f"⚠ {t['unknown_duration']} 筆時長不明未計入，工時偏低")
    print(f"寫入位置：{excel_path} → '{ws.title}' 第 {start_row} 列起，共 {len(rows)} 列\n")

    for i, r in enumerate(rows):
        print(f"[{i + 1}] {r['project_name']}｜{r['client_name']}｜{r['project_type']}／{r['project_phase']}")
        print(f"    本週工時 {r['total_hours']}h｜使用AI {r['ai_hours']}h｜無AI預估 {r['no_ai_hours']}h")
        if r["ai_hours"] and r["no_ai_hours"] and float(r["no_ai_hours"]) < float(r["ai_hours"]):
            print("    ⚠ 無AI預估工時低於使用AI工時，代表 AI 反而更慢，確認這是你要填的")
        print(f"    AI應用：{r['ai_type']}")
        print(f"    備註：{str(r['notes'])[:100]}{'…' if len(str(r['notes'])) > 100 else ''}")
        print()

    if args.dry_run:
        print("--dry-run：未寫入任何內容。確認無誤後移除 --dry-run 重跑。")
        return

    backup = excel_path.with_suffix(excel_path.suffix + ".bak")
    shutil.copy2(excel_path, backup)

    for offset, r in enumerate(rows):
        for field, col in cols.items():
            if field in r:
                ws.cell(start_row + offset, col).value = r[field]

    tmp = excel_path.with_name(excel_path.name + ".tmp")
    wb.save(tmp)
    os.replace(tmp, excel_path)
    print(f"已寫入 {len(rows)} 列（第 {start_row} 列起）。備份：{backup}")


if __name__ == "__main__":
    main()
