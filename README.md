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
   - Windows：在 PowerShell 輸入 `py --version`，顯示 `Python 3.10` 以上即可；`py` 找不到的話改輸入 `python --version`，兩個指令**只要有一個能用就行**，後面的步驟就用那個指令。都不行的話，從 [python.org](https://www.python.org/downloads/) 或 Microsoft Store 安裝 **Python install manager**，裝好後重開 PowerShell 再確認一次。
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

（`py` 找不到的話改用 `python install.py`，結果完全相同：安裝程式會記下執行它的 Python 完整路徑寫進 hook。）

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
| 填週報 | 「幫我填本週的 AI 週報」（或輸入 `/ai-weekly-report`），詳見下一節 |

---

## 填寫週報

### 什麼時候填、填哪一週

| 你說 | 讀取範圍 |
| --- | --- |
| 「幫我填本週的 AI 週報」（週一～週五） | 本週一到今天 |
| 「幫我填本週的 AI 週報」（週六、日） | 本週一到週五 |
| 「幫我填 2026-W47 的 AI 週報」 | 指定那一週的週一到週五（週次是 ISO 週） |

某幾天沒有 log（請假、外勤、沒用 AI）是正常的，不影響填寫，Claude 會告訴你缺了哪幾天。

### 流程

1. **算工時**：程式讀取那一週的 log，算出工時。**工時一律由程式計算，Claude 不會改動數字。**
2. **Claude 判斷內容**：依照你這週問過的問題，判斷專案名稱、客戶、類型、階段、AI 應用類型，撰寫備註，並推估「無 AI 預估工時」。
3. **預覽（不寫檔）**：Claude 先把要寫入的內容列給你看，例如：

   ```
   週次：2026-W48｜有 log 5 天
   工時來源：投入時距 16.6h（間隔 >30 分算換工作）｜AI 互動累計 3.8h
   寫入位置：.../2026_FSB_AI_Weekly.xlsx → 'AI_Weekly_Data' 第 12 列起，共 2 列

   [1] CSIMS 電台執照系統｜NCC｜建置／設計
       本週工時 11.6h｜使用AI 2.7h｜無AI預估 24h
       AI應用：文件生成, 架構設計
       備註：以 Claude 分析既有程式並產出 SA 文件與 prototype……
   [2] 內部工具｜未知｜維運／開發
       本週工時 5.0h｜使用AI 1.1h｜無AI預估 8h
       ...
   ```

4. **你確認或修改**：直接用一般對話的方式告訴 Claude 要改什麼（見下表），改到滿意為止。
5. **寫入 Excel**：你說「沒問題，寫入」之後才會寫進去。寫入前會自動備份成 `<檔名>.xlsx.bak`。

### 預覽時可以這樣調整

| 想改的 | 對 Claude 說（範例） |
| --- | --- |
| 專案名稱、客戶、類型、階段 | 「專案名稱改成 CSIMS」、「客戶是 NCC」、「階段改成測試」 |
| 無 AI 預估工時 | 「無 AI 預估改成 16 小時」（**這是推估值，請務必確認**，Claude 會附上推估理由） |
| 多個專案的工時分配 | 「拆成兩個專案，CSIMS 佔 70%、內部工具 30%」 |
| 備註 | 「備註補上：產出 12 頁 SA 文件」 |
| 工時看起來太少／太多 | 「間隔改成 60 分鐘重算」（工時的算法見下方「你需要知道的事」） |

Claude 從 log 判斷不出來的欄位（例如客戶名稱）會填「未知」，**不會自己編**，請你補上。

### Excel 每一欄從哪來

| 欄位 | 來源 |
| --- | --- |
| 年度、填報日期 | 系統日期 |
| 週次 | 程式計算（ISO 週次，例如 `2026-W48`） |
| 姓名、角色 | 安裝時填的設定 |
| 專案名稱、客戶名稱、專案類型、專案階段、AI應用類型 | Claude 判斷，你確認 |
| 本專案本週工時 | 程式計算：投入時距 × 該專案比例 |
| 使用AI總工時 | 程式計算：AI 互動時長 × 該專案比例 |
| 無AI預估工時 | Claude 推估，**你確認** |
| 備註 | Claude 依「任務＋做法＋效果＋可複製性」撰寫，只寫 log 裡確實有的內容 |

欄位是依照表頭名稱比對的，範本即使插入了其他欄位也不會寫錯位置；找不到 `AI_Weekly_Data` 工作表或認不出表頭時，會直接停止，不會亂寫。

### 注意事項

- **同一週不會重複寫入**：該週同一個專案已經寫過時，程式會拒絕寫入。確定要再新增一列，請跟 Claude 說「仍然新增」；要修改已經寫入的那一列，請直接打開 Excel 手動改。
- **Windows：寫入前請先關閉該 Excel 檔**，Excel 開著時檔案會被鎖住而無法寫入。
- **第一次寫入後請打開 Excel 檢查一次版面**：寫入時會重存整個檔案，範本裡如果有圖表、圖片或樞紐分析表，理論上可能受影響。萬一有問題，用旁邊的 `.xlsx.bak` 還原。

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

**Windows 顯示 `需要 Python 3.10 以上`**
`py`／`python` 用到的 Python 版本太舊。安裝新版 Python（見「安裝前準備」）後重開 PowerShell，再執行一次安裝程式。

**Windows 找不到 `py`**
先改用 `python install.py`。`python --version` 能顯示 3.10 以上就沒問題，不需要特別讓 `py` 能用。

**Windows `py` 和 `python` 都找不到，或輸入 `python` 會跳出 Microsoft Store**
依序檢查（出自 [Python 官方 Windows 說明](https://docs.python.org/3/using/windows.html) 的疑難排解）：
1. 確認已安裝 **Python install manager**（python.org 或 Microsoft Store）。
2. 開始選單搜尋「管理應用程式執行別名」，確認 Python 相關的別名是開啟的；已開啟的話，關掉再打開一次。
3. 確認 PATH 環境變數裡有 `%UserProfile%\AppData\Local\Microsoft\WindowsApps`。

每一步做完都要重開 PowerShell，再輸入 `py --version` 或 `python --version` 確認。

**想調整摘要時間上限或模型**
可設定環境變數：`AI_COWORK_LOG_TIMEOUT`（秒，預設 25）、`AI_COWORK_LOG_MODEL`（預設 `haiku`）、`AI_COWORK_LOG_DIR`（記錄資料夾）。

---

## 更新

```bash
git pull          # 或重新下載 ZIP
python3 install.py   # Windows：py install.py 或 python install.py
```

你的記錄檔與 `.weekly_config.json` 不會被覆蓋。

## 移除

1. 刪除 `~/.claude/skills/ai-cowork-log` 與 `~/.claude/skills/ai-weekly-report` 兩個資料夾。
2. 打開 `~/.claude/settings.json`，刪掉 `hooks` 中 `command` 含有 `log_writer.py` 的兩段。
3. 記錄檔在 `~/AI_coworkRec/`，要保留或刪除自行決定。
