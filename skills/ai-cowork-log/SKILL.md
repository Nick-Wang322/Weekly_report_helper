---
name: ai-cowork-log
description: |
  查詢與總結使用者的 AI 互動工時記錄。當使用者：
  - 請求今日或某日的工作摘要（如「總結今天」、「今天的 log 摘要」）
  - 想查看或統計 AI 使用時間、工作類型分布
  - 提到 AI_coworkRec 或 AI 工作記錄的內容
  - 反映記錄沒寫進去、時長不對、摘要顯示「待補」
  時使用此 skill。
  注意：記錄的「寫入」由 Claude Code hook 自動完成，不屬於此 skill 的職責。
---

# AI CoWork Log Skill

工時記錄由 `~/.claude/settings.json` 裡的 hook 自動寫入：

| 事件 | Hook | 動作 |
| --- | --- | --- |
| 使用者送出訊息 | `UserPromptSubmit` | 記下發問時間到 `~/AI_coworkRec/.pending/<session_id>.json` |
| Claude 回覆結束 | `Stop` | 讀 transcript 產生摘要，寫入當天 `.log` |

## ⚠️ 不要手動呼叫 log_writer.py

hook 已經負責記錄。手動再跑一次會產生重複記錄（時長 0 秒、`session_id` 為 `unknown`），把統計弄歪。

唯一例外：使用者**明確要求**補記某次沒被記到的互動時，才可執行

```bash
python3 ~/.claude/skills/ai-cowork-log/scripts/log_writer.py --event end \
  --topic "..." --q_summary "..." --a_summary "..." --tags "#標籤"
```

補記前先看當天 `.log` 確認那筆真的不存在。

---

## 生成摘要

使用者說「總結今天」、「今天的工作摘要」時：

```bash
python3 ~/.claude/skills/ai-cowork-log/scripts/summarize.py
```

指定日期：`--date 2026-08-04`（預設今天）。

依輸出整理成：

```
📅 YYYY-MM-DD 工作摘要
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱  總 AI 互動時間：X 小時 XX 分（共 N 次）

🗂  今日工作項目：
  1. [任務] — 時長
  2. [任務] — 時長

💡 主要產出：
  - [簡述]

🏷  標籤分布：#程式碼 (N) / #研究分析 (N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**必須忠實反映 summarize.py 的警示**，不要吞掉：

- 「其中 N 筆時長不明，未計入」→ 總時數偏低，要在摘要裡說
- 「N 筆摘要待補」→ 那幾筆只有原文節錄，主題可能不準
- 「N 行表頭格式不合已跳過」→ log 檔可能被手動改壞

summarize.py 以 exit code 1 結束時代表解析不到任何記錄，stderr 會說明原因。直接回報原因，不要假裝有摘要。

---

## Log 格式

位置：`~/AI_coworkRec/YYYY-MM-DD.log`（可用 `AI_COWORK_LOG_DIR` 覆寫）

```
================================================================================
[互動 #N] 發問：HH:MM:SS | 回覆完成：HH:MM:SS | 時長：2 分 5 秒 (125s)
主題：一句話描述
--------------------------------------------------------------------------------
問題摘要：
  使用者問了什麼

回應摘要：
  Claude 做了什麼

標籤：#標籤1
================================================================================
```

- 表頭尾端的 `(125s)` 是給統計讀的機器欄位，**不要手動修改或刪除**
- 摘要本文一律縮排兩格且為單行，統計不會誤讀
- 檔案末端的統計區塊以 `# ==== 今日統計（以下由程式自動重寫，請勿手改）====` 起頭，每次寫入時整段重算

---

## 標籤

| 標籤 | 說明 |
|------|------|
| `#程式碼` | 寫程式、debug、code review |
| `#文件撰寫` | 寫報告、文件、郵件 |
| `#研究分析` | 查資料、比較、分析 |
| `#設計` | UI/UX、系統設計、架構 |
| `#翻譯` | 翻譯或語言相關 |
| `#會議準備` | 準備簡報、會議記錄 |
| `#腦力激盪` | 想法發想、討論策略 |
| `#skill建置` | 建立或修改 Claude skill |
| `#待補` | 自動摘要失敗，標籤未能判定 |

---

## 排錯

使用者反映記錄有問題時，先看 hook 的 stderr 訊息（Claude Code 會顯示）：

| 訊息 | 意義 | 處理 |
| --- | --- | --- |
| `摘要失敗（找不到 claude 指令）` | hook 環境的 PATH 沒有 `claude` | 在 hook command 改用絕對路徑 |
| `摘要失敗（逾時 Ns）` | 摘要花太久 | 調大 `AI_COWORK_LOG_TIMEOUT`，或把 Stop hook 的 `timeout` 一起調大 |
| `transcript 抓不到對話內容，這次不記錄` | transcript 格式可能隨 Claude Code 改版變動 | 檢查 `transcript_path` 內容結構 |
| `N 筆記錄的表頭讀不到時長` | log 的表頭被手改過 | 把該行的 `(NNNs)` 補回去 |
| `開始時間晚於結束時間` | 系統時間跳動或 pending 檔殘留 | 時長記為 0，可忽略 |

環境變數：`AI_COWORK_LOG_DIR`、`AI_COWORK_LOG_MODEL`（預設 `haiku`）、`AI_COWORK_LOG_TIMEOUT`（預設 25 秒）。

其他檔案：`.pending/` 是各 session 的暫存發問時間，正常會在記錄後刪除；session 異常中斷會留下孤兒檔，可安全刪除。`.state.json` 存去重用的 session → 訊息 uuid 對應。
