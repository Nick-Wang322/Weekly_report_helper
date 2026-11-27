#!/usr/bin/env python3
"""
Weekly_report_helper 安裝程式（macOS / Windows 共用）

    macOS  ：python3 install.py
    Windows：py install.py

做的事：
  1. 把 skills/ 底下的兩個 skill 複製到 ~/.claude/skills/（舊版先備份）
  2. 在 ~/.claude/settings.json 加入記錄用的兩個 hook（舊的同名 hook 會先移除，不會重複）
  3. 安裝 openpyxl（週報寫 Excel 用）
  4. 建立 ~/AI_coworkRec/ 與週報設定檔，並詢問週報 Excel 的路徑（已設定且有效就沿用）

hook 與 SKILL.md 裡的指令一律寫成「執行這支安裝程式的 Python 絕對路徑」，
避開 Windows 沒有 python3、cmd 不認得 $HOME 這類平台差異。
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit(f"需要 Python 3.10 以上，目前是 {sys.version.split()[0]}")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent
SKILLS = ["ai-cowork-log", "ai-weekly-report"]
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
SETTINGS = CLAUDE_DIR / "settings.json"
LOG_DIR = HOME / "AI_coworkRec"
CONFIG = LOG_DIR / ".weekly_config.json"
HOOK_MARK = "ai-cowork-log/scripts/log_writer.py"  # 用來辨識「我們的」hook
SHEET = "AI_Weekly_Data"

PY = Path(sys.executable).as_posix()
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # 含微秒：連續重跑也不會撞名
BACKUP_DIR = CLAUDE_DIR / "backups" / f"weekly_report_helper-{STAMP}"


def q(path: str) -> str:
    return f'"{path}"'


def backup(src: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dst = BACKUP_DIR / src.name
    (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    print(f"  已備份 {src} → {dst}")


def install_skills() -> None:
    print("[1/4] 安裝 skill")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for name in SKILLS:
        dst = SKILLS_DIR / name
        if dst.exists():
            backup(dst)
            shutil.rmtree(dst)
        shutil.copytree(REPO / "skills" / name, dst,
                        ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        # SKILL.md 裡的範例指令換成這台電腦的 Python 絕對路徑
        md = dst / "SKILL.md"
        text = md.read_text(encoding="utf-8")
        md.write_text(text.replace("python3 ~/.claude/skills/", f"{q(PY)} ~/.claude/skills/"),
                      encoding="utf-8")
        print(f"  {dst}")


def install_hooks() -> None:
    print("[2/4] 設定 hook")
    settings = {}
    if SETTINGS.exists():
        try:
            settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"  {SETTINGS} 不是合法的 JSON（{e}），為避免覆蓋你的設定，安裝中止。請先修正該檔。")
        backup(SETTINGS)

    writer = (SKILLS_DIR / "ai-cowork-log" / "scripts" / "log_writer.py").as_posix()
    wanted = {
        "UserPromptSubmit": {"type": "command", "timeout": 10,
                             "command": f"{q(PY)} {q(writer)} --event start"},
        "Stop": {"type": "command", "timeout": 40,
                 "command": f"{q(PY)} {q(writer)} --event end --from-transcript"},
    }
    hooks = settings.setdefault("hooks", {})
    for event, hook in wanted.items():
        groups = []
        for g in hooks.get(event, []):  # 移除舊版的同一組 hook，保留使用者其他 hook
            kept = [h for h in g.get("hooks", []) if HOOK_MARK not in h.get("command", "")]
            if kept:
                groups.append({**g, "hooks": kept})
        groups.append({"hooks": [hook]})
        hooks[event] = groups
        print(f"  {event}: {hook['command']}")

    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install_openpyxl() -> bool:
    print("[3/4] 檢查 openpyxl")
    try:
        import openpyxl  # noqa: F401
        print("  已安裝")
        return True
    except ImportError:
        pass
    for extra in ([], ["--user", "--break-system-packages"]):
        cmd = [sys.executable, "-m", "pip", "install", *extra, "openpyxl"]
        if subprocess.run(cmd).returncode == 0:
            print("  安裝完成")
            return True
    print(f"  ⚠ 自動安裝失敗，請手動執行：{q(PY)} -m pip install openpyxl")
    return False


def clean_path(raw: str) -> Path:
    """處理拖曳檔案進視窗時的格式：Windows 會加引號，macOS 會把空白跳脫成「\\ 」。"""
    s = raw.strip().strip('"').strip("'")
    if os.name != "nt":
        s = s.replace("\\ ", " ")
    return Path(s).expanduser().resolve()


def check_excel(p: Path) -> str | None:
    """可用就回 None，否則回原因。"""
    if not p.is_file():
        return "找不到這個檔案"
    if p.suffix.lower() not in (".xlsx", ".xlsm"):
        return "不是 .xlsx / .xlsm 檔"
    try:
        import openpyxl
    except ImportError:
        return None  # openpyxl 沒裝好就無法檢查工作表，先接受；寫入時 write_excel.py 會再檢查
    try:
        wb = openpyxl.load_workbook(p, read_only=True)
        names = wb.sheetnames
        wb.close()
    except Exception as e:
        return f"無法開啟（{e}）"
    if SHEET not in names:
        return f"裡面沒有 '{SHEET}' 工作表（現有：{'、'.join(names)}）"
    return None


def ask_excel() -> str | None:
    print("  請輸入你的週報 Excel 完整路徑（可直接把檔案拖進這個視窗；直接按 Enter 先跳過）")
    while True:
        try:
            raw = input("  > ")
        except EOFError:
            return None
        if not raw.strip():
            return None
        p = clean_path(raw)
        err = check_excel(p)
        if err is None:
            return p.as_posix()
        print(f"  ✗ {err}：{p}")
        print("    請重新輸入，或直接按 Enter 跳過")


def init_config() -> list[str]:
    """回傳安裝後使用者還要處理的事。"""
    print("[4/4] 週報設定檔")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    config = {"name": "請填你的名字", "role": "PM / SA / SD / PG 擇一", "excel_path": ""}
    if CONFIG.exists():
        try:
            config.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            return [f"{CONFIG} 不是合法的 JSON（{e}），未修改，請手動修正。"]
    before = dict(config)

    current = str(config.get("excel_path") or "")
    excel_ok = bool(current) and check_excel(Path(current).expanduser()) is None
    if excel_ok:
        print(f"  週報 Excel：{current}（已設定，沿用）")
    else:
        if current:
            print(f"  目前設定的 Excel 無法使用：{current}")
        picked = ask_excel()
        if picked:
            config["excel_path"] = picked
            excel_ok = True
            print(f"  已設定週報 Excel：{picked}")

    if config != before or not CONFIG.exists():
        CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    todo = []
    if not excel_ok:
        todo.append(f"尚未設定週報 Excel：重跑一次安裝程式，或編輯 {CONFIG} 的 excel_path。")
    if str(config.get("name", "")).startswith("請填") or config.get("role") not in ("PM", "SA", "SD", "PG"):
        todo.append(f"請編輯 {CONFIG}，填入姓名（name）與角色（role：PM / SA / SD / PG）。")
    return todo


def main() -> None:
    print(f"Python：{PY}\n")
    install_skills()
    install_hooks()
    ok_xlsx = install_openpyxl()
    todo = init_config()

    print("\n==== 安裝完成 ====")
    warnings = []
    if not shutil.which("claude"):
        warnings.append("找不到 claude 指令：記錄仍會寫入，但摘要會變成「待補」。請確認 Claude Code CLI 已安裝並在 PATH 中。")
    warnings += todo
    if not ok_xlsx:
        warnings.append("openpyxl 未安裝，週報無法寫入 Excel。")
    for w in warnings:
        print(f"⚠ {w}")
    print("請重新啟動 Claude Code（CLI / 桌面版 / VS Code）讓 hook 生效。")
    if BACKUP_DIR.exists():
        print(f"原本的設定已備份在：{BACKUP_DIR}")


if __name__ == "__main__":
    main()
