# Weekly_report_helper

讓 Claude Code **自動記錄每一次 AI 互動的工時與摘要**，週末再一鍵把整週記錄**整理成 AI 使用週報並寫入 Excel**。

包含兩個 Claude Code skill：

| Skill | 做什麼 |
| --- | --- |
| `ai-cowork-log` | 每次你問 Claude 一個問題，自動記下發問時間、回覆完成時間、主題、問題摘要、回應摘要、標籤，存到 `~/AI_coworkRec/YYYY-MM-DD.log`。也能幫你「總結今天」。 |
| `ai-weekly-report` | 讀取一整週的 log，算出工時，由 Claude 判斷專案／階段／AI 應用類型並撰寫備註，確認後寫入週報 Excel（`AI_Weekly_Data` 工作表）。 |

```
你問 Claude ──► hook 自動記錄 ──► ~/AI_coworkRec/2026-11-27.log ──► 週報 skill ──► 週報 Excel
```

---

## 適用環境

記錄是靠 **Claude Code 的 hook** 觸發，所以只有「在你自己電腦上執行的 Claude Code」才會記錄：

| 使用方式 | 會記錄？ |
| --- | --- |
| Claude Code CLI（終端機） | ✅ |
| Claude 桌面版 App 的 **Code** 分頁（本機 session） | ✅ |
| VS Code 的 **Claude Code 擴充套件** | ✅ |
| Claude 桌面版／claude.ai 網頁的**一般聊天** | ❌ 沒有 hook 機制 |
| claude.ai/code（雲端 Claude Code） | ❌ 在雲端主機執行，記錄不會回到你的電腦 |
| ChatGPT、VS Code Copilot 等其他 AI 工具 | ❌ |

作業系統：**macOS**、**Windows** 皆可。

> ⚠️ **Windows 尚未經過實機測試。** 已針對 Windows 處理 Python 指令名稱、路徑、中文編碼與 `claude` 指令呼叫等差異，並在 macOS 上模擬 Windows 編碼環境驗證過，但還沒有在真正的 Windows 電腦上跑過。遇到問題請回報。

---

## 安裝前準備

1. **Claude Code**：已安裝並登入（終端機輸入 `claude --version` 有版本號即可）。
2. **Python 3.10 以上**
   - macOS：終端機輸入 `python3 --version` 確認。版本太舊可用 [python.org](https://www.python.org/downloads/) 或 `brew install python` 安裝。
   - Windows：到 [python.org](https://www.python.org/downloads/) 下載安裝，**安裝第一個畫面務必勾選「Add python.exe to PATH」**。裝好後在 PowerShell 輸入 `py --version` 確認。
3. **週報 Excel 範本**：使用部門提供的 FSB AI 週報 Excel，裡面要有 `AI_Weekly_Data` 工作表。（只用記錄功能的話可以先不用。）

---

## 安裝

### 1. 下載

有 Git 的話：

```bash
git clone https://github.com/Nick-Wang322/Weekly_report_helper.git
cd Weekly_report_helper
```

沒有 Git：在 GitHub 頁面按綠色的 **Code → Download ZIP**，解壓縮後進入資料夾。

### 2. 執行安裝程式

**macOS**（終端機）：

```bash
python3 install.py
```

**Windows**（PowerShell，先 `cd` 到解壓縮的資料夾）：

```powershell
py install.py
```

安裝程式會：

- 把兩個 skill 複製到 `~/.claude/skills/`（Windows 是 `C:\Users\你的帳號\.claude\skills\`）
- 在 `~/.claude/settings.json` 加入記錄用的 hook（**保留你原有的其他設定**，修改前會先備份到 `~/.claude/backups/`）
- 安裝 Excel 套件 `openpyxl`
- 建立記錄資料夾 `~/AI_coworkRec/`，並**依序詢問你的姓名、角色、週報 Excel 位置**，存成週報設定檔

| 詢問項目 | 怎麼填 |
| --- | --- |
| 姓名 | 會填進週報的「姓名」欄 |
| 角色 | `PM`、`SA`、`SD`、`PG` 擇一（大小寫皆可） |
| 週報 Excel | **直接把你的週報 Excel 檔案拖進終端機／PowerShell 視窗**再按 Enter（也可以手動輸入完整路徑）。安裝程式會檢查檔案存在、而且裡面有 `AI_Weekly_Data` 工作表 |

輸入不正確會請你重新輸入；任何一項還不確定，直接按 Enter 跳過，之後重跑安裝程式再補。

重複執行是安全的：不會產生重複的 hook，已設定好的項目會沿用、不再詢問。

### 3. （需要時）修改個人設定

安裝時填的資料存在 `~/AI_coworkRec/.weekly_config.json`（Windows：`C:\Users\你的帳號\AI_coworkRec\.weekly_config.json`）。之後要改（例如 Excel 換了位置），用文字編輯器直接改這個檔即可：

```json
{
  "name": "王小明",
  "role": "SA",
  "excel_path": "~/Documents/2026_FSB_AI_Weekly.xlsx"
}
```

- `role`：PM、SA、SD、PG 擇一
- `excel_path`：週報 Excel 的完整路徑。Windows 請用正斜線，例如 `"C:/Users/xiaoming/Documents/2026_FSB_AI_Weekly.xlsx"`

> 這個檔名以 `.` 開頭，macOS Finder 預設看不到，可在 Finder 按 `Cmd + Shift + .` 顯示隱藏檔，或直接用終端機 `open -e ~/AI_coworkRec/.weekly_config.json` 開啟。

### 4. 重新啟動 Claude Code

關掉所有 Claude Code 視窗（CLI、桌面版、VS Code）後重開，hook 才會生效。

### 5. 確認有在記錄

隨便問 Claude 一個問題，等它回答完，打開今天的記錄檔：

- macOS：`~/AI_coworkRec/2026-11-27.log`（換成今天日期）
- Windows：`C:\Users\你的帳號\AI_coworkRec\2026-11-27.log`

看到 `[互動 #1]` 開頭的記錄就代表成功。

---

## 使用方式

| 想做的事 | 對 Claude 說 |
| --- | --- |
| 記錄 | 不用做任何事，每次問答都會自動記錄 |
| 看今天做了什麼 | 「總結今天」、「今天的工作摘要」 |
| 看某一天 | 「總結 2026-11-25 的 log」 |
| 填週報 | 「幫我填本週的 AI 週報」 |

**填週報的流程**：Claude 會先算好工時、判斷專案資訊，**先給你看預覽（不寫檔）**，你確認或修改「無 AI 預估工時」等欄位後才會寫入 Excel。寫入前會自動備份成 `.xlsx.bak`。

> Windows 使用者：寫入前請先**關閉該 Excel 檔**，Excel 開著時檔案會被鎖住而無法寫入。

---

## 你需要知道的事

- **記錄只存在你自己的電腦**（`~/AI_coworkRec/`），不會上傳到任何地方。
- **每次問答會額外呼叫一次 Claude（Haiku 模型）來產生摘要**，會用到一點點你的 Claude 用量。
- **工時的意義**：
  - `使用AI總工時` = 每次「送出問題 → Claude 回答完」的時間加總，只包含 Claude 處理的時間。
  - `本專案本週工時` = 投入時距，相鄰兩次互動間隔 30 分鐘以內視為同一段工作。覺得不準可以請 Claude 調整間隔重算。
- 記錄檔請不要手動改表頭那一行（`[互動 #N] ... (123s)`），統計靠它計算。

---

## 常見問題

**摘要顯示「待補」或「摘要失敗（找不到 claude 指令）」**
hook 執行時找不到 `claude` 指令。確認在終端機輸入 `claude --version` 有反應；若是從桌面版或 VS Code 使用，請完整重開該程式。記錄本身（時間）仍會寫入，只有摘要缺漏。

**沒有產生記錄檔**
1. 確認已重新啟動 Claude Code。
2. 打開 `~/.claude/settings.json`，確認 `hooks` 裡有 `UserPromptSubmit` 與 `Stop` 兩段，內容包含 `log_writer.py`。
3. 確認是用上面「適用環境」表中 ✅ 的方式使用。

**Windows 顯示 `需要 Python 3.10 以上` 或找不到 `py`**
重新安裝 Python 並勾選「Add python.exe to PATH」，然後重開 PowerShell。

**想調整摘要時間上限或模型**
可設定環境變數：`AI_COWORK_LOG_TIMEOUT`（秒，預設 25）、`AI_COWORK_LOG_MODEL`（預設 `haiku`）、`AI_COWORK_LOG_DIR`（記錄資料夾）。

---

## 更新

```bash
git pull          # 或重新下載 ZIP
python3 install.py   # Windows：py install.py
```

你的記錄檔與 `.weekly_config.json` 不會被覆蓋。

## 移除

1. 刪除 `~/.claude/skills/ai-cowork-log` 與 `~/.claude/skills/ai-weekly-report` 兩個資料夾。
2. 打開 `~/.claude/settings.json`，刪掉 `hooks` 中 `command` 含有 `log_writer.py` 的兩段。
3. 記錄檔在 `~/AI_coworkRec/`，要保留或刪除自行決定。
