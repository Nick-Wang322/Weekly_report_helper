#!/usr/bin/env python3
"""
AI CoWork Log Writer — 由 Claude Code hook 驅動

  --event start                 UserPromptSubmit hook：記下發問時間
  --event end --from-transcript  Stop hook：讀 transcript 產生摘要並寫入記錄
  --event end --topic ... --tags ...   手動 / 測試用（不讀 transcript）

資料流：
  ~/AI_coworkRec/YYYY-MM-DD.log  ← 唯一檔案。記錄用 append，末端統計區塊每次重寫。
  統計只讀「表頭行」與「標籤行」（本程式產生的單行、格式受控），
  摘要本文縮排兩格、不參與比對，所以摘要內容再怎麼變都不會弄壞統計。

設計約束：
  * 絕不 exit(2)。Stop 的 2 會讓對話無法結束，UserPromptSubmit 的 2 會吃掉使用者的提問。
  * start 事件不得寫 stdout：UserPromptSubmit 的 stdout 會被當成附加 context 注入。
  * 失敗一律 stderr + exit(1)，不靜默吞掉。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows 的主控台／管線預設是 cp950：hook 傳入的中文會亂碼、印出 ⚠ 會直接報錯。統一用 UTF-8。
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# 遞迴防護：摘要是用 `claude -p` 產生的，那個子程序會讀同一份 settings.json、
# 因此也會觸發 Stop hook 跑到這支腳本。帶旗標進去，子程序直接退出。
# ---------------------------------------------------------------------------
if os.environ.get("AI_COWORK_LOG_CHILD"):
    sys.exit(0)

LOG_DIR = Path(os.environ.get("AI_COWORK_LOG_DIR", str(Path.home() / "AI_coworkRec")))
PENDING_DIR = LOG_DIR / ".pending"
STATE_FILE = LOG_DIR / ".state.json"

SUMMARY_MODEL = os.environ.get("AI_COWORK_LOG_MODEL", "haiku")
SUMMARY_TIMEOUT = int(os.environ.get("AI_COWORK_LOG_TIMEOUT", "25"))

VALID_TAGS = [
    "#程式碼", "#文件撰寫", "#研究分析", "#設計",
    "#翻譯", "#會議準備", "#腦力激盪", "#skill建置",
]
TAG_HINT = {
    "#程式碼": "寫程式、debug、code review",
    "#文件撰寫": "寫報告、文件、郵件",
    "#研究分析": "查資料、比較、分析",
    "#設計": "UI/UX、系統設計、架構",
    "#翻譯": "翻譯或語言相關",
    "#會議準備": "準備簡報、會議記錄",
    "#腦力激盪": "想法發想、討論策略",
    "#skill建置": "建立或修改 Claude skill",
}
SEP = "=" * 80
SUB = "-" * 80
# 統計區塊的起點標記。切檔案靠這一行，不靠數 dash。
STATS_SENTINEL = "# ==== 今日統計（以下由程式自動重寫，請勿手改）===="


def warn(msg: str) -> None:
    print(f"[ai-cowork-log] {msg}", file=sys.stderr)


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", s)[:80] or "unknown"


def read_hook_payload() -> dict:
    """Claude Code 從 stdin 餵進 hook JSON；手動執行時 stdin 是空的。"""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        warn("stdin 不是合法 JSON，忽略 hook payload")
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

def cmd_start(payload: dict) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    session = safe_name(str(payload.get("session_id", "unknown")))
    body = {
        "start": datetime.now().isoformat(timespec="seconds"),
        "cwd": payload.get("cwd", ""),
    }
    (PENDING_DIR / f"{session}.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8"
    )
    # 這裡刻意不 print 到 stdout。


def take_pending(session: str) -> dict:
    path = PENDING_DIR / f"{safe_name(session)}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    try:
        path.unlink()
    except OSError:
        pass
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# transcript
# ---------------------------------------------------------------------------

# 使用者貼上的長文字會被包成 <pasted_content ...>...</pasted_content ...>。
# 縮成一行標記：否則訊息以 "<" 開頭會被當內部訊息丟掉，而且摘要只取前 2000 字，
# 貼上的內容一長，使用者寫在後面的問題就會被截掉。
PASTED_RE = re.compile(r"<pasted_content\b[^>]*>(.*?)</pasted_content\b[^>]*>", re.DOTALL)


def collapse_pasted(s: str) -> str:
    return PASTED_RE.sub(
        lambda m: f"[貼上內容 {len(m.group(1).strip())} 字，開頭：{clip(m.group(1), 150)}]", s
    )


def block_text(content) -> str:
    """從 Anthropic message content 抽純文字，忽略 tool_use / tool_result / 圖片。"""
    if isinstance(content, str):
        return collapse_pasted(content).strip()
    if not isinstance(content, list):
        return ""
    # IDE 擴充（VS Code 等）會在使用者訊息前插入 <ide_opened_file> / <ide_selection>
    # 這類 context block；只丟這些 block，不能讓它們連帶把使用者的問題一起濾掉。
    parts = [
        collapse_pasted(b["text"]) for b in content
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        and not b["text"].lstrip().startswith("<ide_")
    ]
    return "\n".join(parts).strip()


def extract_last_exchange(transcript_path: str | None) -> dict | None:
    """
    取這個 session 最後一組「使用者發問 → Claude 回覆」。
    transcript 的 JSONL 欄位未正式文件化，因此全程防禦性解析，抓不到就回 None。
    """
    if not transcript_path:
        return None
    path = Path(transcript_path).expanduser()
    if not path.is_file():
        warn(f"找不到 transcript：{path}")
        return None

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        warn(f"讀不到 transcript：{e}")
        return None

    turns = []
    for line in lines[-600:]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("isSidechain") or rec.get("isMeta"):  # 子代理 / 系統訊息不算
            continue
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        role = msg.get("role") or rec.get("type")
        if role not in ("user", "assistant"):
            continue
        text = block_text(msg.get("content"))
        if not text or text.startswith("<"):  # <command-name> 之類的內部訊息
            continue
        turns.append({
            "role": role,
            "text": text,
            "uuid": rec.get("uuid", ""),
            "ts": rec.get("timestamp", ""),
        })

    last_assistant = next((t for t in reversed(turns) if t["role"] == "assistant"), None)
    if last_assistant is None:
        return None
    idx = turns.index(last_assistant)
    last_user = next((t for t in reversed(turns[:idx]) if t["role"] == "user"), None)

    return {
        "user": last_user["text"] if last_user else "",
        "assistant": last_assistant["text"],
        "uuid": last_assistant["uuid"],
        "user_ts": last_user["ts"] if last_user else "",
    }


# ---------------------------------------------------------------------------
# 摘要
# ---------------------------------------------------------------------------

def clip(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def normalize_tags(raw: str) -> str:
    hits = [t for t in VALID_TAGS if t in (raw or "")]
    return " ".join(hits) if hits else "#待補"


def fallback_fields(ex: dict, reason: str) -> dict:
    warn(f"摘要失敗（{reason}），改寫入原文節錄")
    return {
        "topic": f"(摘要失敗：{reason})",
        "q_summary": clip(ex.get("user", ""), 200) or "(無)",
        "a_summary": clip(ex.get("assistant", ""), 200) or "(無)",
        "tags": "#待補",
    }


def find_claude() -> str:
    """
    PATH 找不到時，退回官方安裝程式的固定位置 ~/.local/bin（macOS、Windows 相同）。
    hook 繼承 Claude Code 的環境：從 Dock 開的 App、或在 PATH 更新前就開著的 VS Code，
    PATH 常常不完整。
    """
    found = shutil.which("claude")
    if found:
        return found
    native = Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    return str(native) if native.is_file() else "claude"


def summarize(ex: dict) -> dict:
    tag_list = "\n".join(f"{t} = {TAG_HINT[t]}" for t in VALID_TAGS)
    prompt = (
        "讀下面這組對話，用繁體中文輸出一個 JSON 物件，不要 markdown 圍欄、不要任何說明文字。\n"
        '格式：{"topic": "", "q_summary": "", "a_summary": ""}\n'
        "topic 一句話描述主題；q_summary 使用者問了什麼；a_summary Claude 做了什麼。\n"
        "另外加一個 tags 欄位，從下列選最貼切的一個（只回標籤本身）：\n"
        f"{tag_list}\n\n"
        f"[使用者]\n{clip(ex.get('user', ''), 2000)}\n\n"
        f"[Claude]\n{clip(ex.get('assistant', ''), 4000)}\n"
    )
    env = {**os.environ, "AI_COWORK_LOG_CHILD": "1"}
    # Windows：npm 裝的是 claude.cmd，要靠 which 才找得到；多行 prompt 當參數傳給 .cmd
    # 會被 cmd.exe 拆壞，所以 prompt 一律走 stdin，並明確用 UTF-8 收發。
    try:
        proc = subprocess.run(
            [find_claude(), "-p", "--model", SUMMARY_MODEL],
            input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=SUMMARY_TIMEOUT, env=env,
        )
    except FileNotFoundError:
        return fallback_fields(ex, "找不到 claude 指令")
    except subprocess.TimeoutExpired:
        return fallback_fields(ex, f"逾時 {SUMMARY_TIMEOUT}s")

    if proc.returncode != 0:
        return fallback_fields(ex, f"claude -p exit {proc.returncode}: {clip(proc.stderr, 80)}")

    text = re.sub(r"^```(?:json)?|```$", "", proc.stdout.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return fallback_fields(ex, "回應不含 JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback_fields(ex, "JSON 解析失敗")

    return {
        "topic": clip(str(data.get("topic", "")), 120) or "(無主題)",
        "q_summary": clip(str(data.get("q_summary", "")), 300) or "(無)",
        "a_summary": clip(str(data.get("a_summary", "")), 300) or "(無)",
        "tags": normalize_tags(str(data.get("tags", ""))),
    }


# ---------------------------------------------------------------------------
# 去重：Stop hook 在同一次回覆中可能被觸發多次
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    if len(state) > 100:  # 只留最近 100 個 session
        newest = sorted(state.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)
        state = dict(newest[:100])
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# 寫入與渲染
# ---------------------------------------------------------------------------

def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def fmt_secs(secs: int) -> str:
    if secs < 60:
        return f"{secs} 秒"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m} 分 {s} 秒" if s else f"{m} 分鐘"
    h, m = divmod(m, 60)
    return f"{h} 小時 {m} 分鐘"


def header_block(date: str) -> str:
    return "\n".join([
        "#" * 80,
        "# AI 工作互動記錄",
        f"# 日期：{date}",
        f"# 建立：{datetime.now().strftime('%H:%M:%S')}",
        "#" * 80,
        "", "",
    ])


def entry_block(n: int, r: dict) -> str:
    secs = int(r["duration_secs"])
    # 表頭行尾端的 (NNNs) 是給統計讀的機器欄位，人看 fmt_secs 那段就好。
    return "\n".join([
        SEP,
        f"[互動 #{n}] 發問：{r['start']} | 回覆完成：{r['end']} | 時長：{fmt_secs(secs)} ({secs}s)",
        f"主題：{r['topic']}",
        SUB,
        "問題摘要：",
        f"  {r['q_summary']}",
        "",
        "回應摘要：",
        f"  {r['a_summary']}",
        "",
        f"標籤：{r['tags']}",
        SEP,
        "", "",
    ])


def collect_stats(content: str) -> tuple[int, int, dict]:
    """回傳 (筆數, 總秒數, 標籤次數)。只看行首錨定的表頭行與標籤行。"""
    n_entries = total = unreadable = 0
    for line in re.findall(r"^\[互動 #\d+\].*$", content, re.MULTILINE):
        n_entries += 1
        m = re.search(r"\((\d+)s\)$", line)
        if m:
            total += int(m.group(1))
            continue
        m = re.search(r"時長：(\d+) 分鐘$", line)   # 舊版格式，以分鐘為單位
        if m:
            total += int(m.group(1)) * 60
            continue
        unreadable += 1
    if unreadable:
        # 例如表頭被手改過。出聲，不要靜默少算時數。
        warn(f"{unreadable} 筆記錄的表頭讀不到時長，總時數會偏低")

    counts: dict[str, int] = {}
    for line in re.findall(r"^標籤：(.+)$", content, re.MULTILINE):
        for tag in line.split():
            if tag.startswith("#"):
                counts[tag] = counts.get(tag, 0) + 1
    return n_entries, total, counts


def stats_block(count: int, total: int, counts: dict) -> str:
    dist = " / ".join(f"{t} x{c}" for t, c in sorted(counts.items(), key=lambda kv: -kv[1]))
    return "\n".join([
        STATS_SENTINEL,
        SUB,
        f"【今日統計 - 最後更新 {datetime.now().strftime('%H:%M:%S')}】",
        f"總互動次數：{count} 次",
        f"總互動時間：{fmt_secs(total)}",
        f"各類標籤分布：{dist or '（尚無標籤）'}",
        SUB,
        "",
    ])


def write_entry(date: str, record: dict) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{date}.log"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if not content.strip():
        content = header_block(date)

    idx = content.find(STATS_SENTINEL)
    if idx == -1:
        legacy = content.rfind("【今日統計")     # 舊版沒有 sentinel
        if legacy != -1:
            cut = content.rfind(SUB, 0, legacy)
            idx = cut if cut != -1 else legacy
    if idx != -1:
        content = content[:idx]                  # 砍掉舊統計區塊
    body = content.rstrip("\n") + "\n\n"

    n_prev, _, _ = collect_stats(body)
    body += entry_block(n_prev + 1, record)
    count, total, counts = collect_stats(body)

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body + stats_block(count, total, counts), encoding="utf-8")
    tmp.replace(path)                    # 原子替換：中斷不會留下半份檔案
    return path


def cmd_end(args: argparse.Namespace, payload: dict) -> None:
    session = str(payload.get("session_id", "unknown"))
    end_dt = datetime.now()
    pending = take_pending(session)

    fields = {
        "topic": args.topic or "(未提供)",
        "q_summary": args.q_summary or "(未提供)",
        "a_summary": args.a_summary or "(未提供)",
        "tags": normalize_tags(args.tags) if args.tags else "#待補",
    }
    exchange = None

    if args.from_transcript:
        exchange = extract_last_exchange(payload.get("transcript_path"))
        if exchange is None:
            warn("transcript 抓不到對話內容，這次不記錄")
            return
        state = load_state()
        if exchange["uuid"] and state.get(session, {}).get("uuid") == exchange["uuid"]:
            return  # 同一次回覆重複觸發
        fields = summarize(exchange)

    # 起算時間：pending > transcript 的使用者訊息時間 > 結束時間
    start_dt = parse_iso(pending.get("start", "")) \
        or (parse_iso(exchange["user_ts"]) if exchange else None) \
        or end_dt
    duration = max(int((end_dt - start_dt).total_seconds()), 0)
    if start_dt > end_dt:
        warn("開始時間晚於結束時間，時長記為 0")

    date = end_dt.strftime("%Y-%m-%d")
    write_entry(date, {
        "start": start_dt.strftime("%H:%M:%S"),
        "end": end_dt.strftime("%H:%M:%S"),
        "duration_secs": duration,
        **fields,
    })

    if exchange and exchange["uuid"]:
        state = load_state()
        state[session] = {"uuid": exchange["uuid"], "at": end_dt.isoformat(timespec="seconds")}
        save_state(state)


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI CoWork 工時記錄（hook 驅動）")
    parser.add_argument("--event", choices=["start", "end"], required=True)
    parser.add_argument("--from-transcript", action="store_true",
                        help="從 transcript 自動產生摘要（Stop hook 用）")
    parser.add_argument("--topic", default="")
    parser.add_argument("--q_summary", default="")
    parser.add_argument("--a_summary", default="")
    parser.add_argument("--tags", default="")
    args = parser.parse_args()

    payload = read_hook_payload()
    try:
        if args.event == "start":
            cmd_start(payload)
        else:
            cmd_end(args, payload)
    except Exception as e:  # 絕不 exit(2)；出聲但不擋住對話
        warn(f"{type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
