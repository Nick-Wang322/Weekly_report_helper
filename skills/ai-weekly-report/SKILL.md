---
name: ai-weekly-report
description: |
  從每日 AI 工作 log 整理並填寫每週 AI 使用情況 Excel 報表（FSB_AI_Weekly）。
  當使用者：
  - 輸入 /ai_weekly_report 或 /weekly_report
  - 說「幫我填本週的 AI 週報」、「整理本週 log 填到 Excel」
  - 想把 ~/AI_coworkRec/ 的日誌彙整到 FSB_AI_Weekly Excel
  時使用此 skill。
  依賴 ai-cowork-log skill 產生的 log 檔。
---

# AI Weekly Report Skill

從 `~/AI_coworkRec/YYYY-MM-DD.log` 彙整本週工作，填入 FSB AI 使用週報 Excel。

## 分工原則

| 誰負責 | 內容 |
| --- | --- |
| `read_logs.py` | 週次、各種工時、標籤統計。**確定性計算，Claude 不得重算或調整** |
| Claude | 專案名稱、客戶、類型、階段、AI應用類型、備註、多專案分配比例、無AI預估工時 |
| `write_excel.py` | 用 `share` 乘出各專案工時、寫入、備份、重複偵測 |

工時數字不經過 Claude 的心算。Claude 只回答判斷題。

---

## 前置需求

- Log 目錄：`~/AI_coworkRec/`（由 ai-cowork-log skill 的 hook 自動產生）
- 設定檔：`~/AI_coworkRec/.weekly_config.json`
- Excel：路徑寫在設定檔的 `excel_path`，工作表必須有 `AI_Weekly_Data`
- 依賴：`openpyxl`（`install.py` 會自動安裝）
- `read_logs.py` 會 import ai-cowork-log skill 的 `summarize.py` 作為 log 解析器。
  若該 skill 裝在非預設位置，設定 `AI_COWORK_SCRIPTS` 環境變數。

---

## 執行流程

腳本目錄：`~/.claude/skills/ai-weekly-report/scripts/`

### 步驟 1：彙整本週 log

```bash
python3 ~/.claude/skills/ai-weekly-report/scripts/read_logs.py
```

- 預設讀本週週一到今天（僅工作日）；週六日則讀完整的週一到週五
- 指定其他週：`--week 2026-W31`
- 部分天數無 log 屬正常（請假／外勤），不影響執行

**輸出中的兩個工時語意不同，不可混用：**

| 欄位 | 含義 | 用途 |
| --- | --- | --- |
| `ai_hours` | 各筆互動時長加總（送出訊息→回覆完成） | Excel「使用AI總工時」 |
| `engaged_hours` | 投入時距，相鄰互動間隔 30 分鐘內視為同段工作 | Excel「本專案本週工時」 |

`ai_hours` 只含 Claude 的處理時間，不含使用者閱讀、思考、寫程式的時間，必然低於實際投入。

`engaged_hours` 對 `--gap` 參數敏感（同一份 log 用 30 分與 60 分可能差一倍以上）。
若使用者覺得數字明顯偏離實際，建議調整 `--gap` 重跑，並讓使用者自己選一個貼近真實工作節奏的值。

### 步驟 2：Claude 分析，產生判斷欄位

依 `analysis_prompt.md` 的格式，將步驟 1 的輸出轉成 JSON 存檔：

```bash
cat > ~/AI_coworkRec/.weekly_report_data.json << 'ENDJSON'
[{"project_name": "...", "share": 1.0, ...}]
ENDJSON
```

- 多專案時每個專案一個物件，`share` 加總必須為 1.0（script 會驗證）
- 不要填 `total_hours` / `ai_hours` / `week`，這些由 script 計算
- 無法從 log 判斷的欄位填「未知」或 `null`，不要編造

### 步驟 3：先 dry-run 給使用者確認

```bash
python3 ~/.claude/skills/ai-weekly-report/scripts/read_logs.py --json > ~/AI_coworkRec/.weekly_metrics.json

python3 ~/.claude/skills/ai-weekly-report/scripts/write_excel.py \
  --data-json ~/AI_coworkRec/.weekly_report_data.json \
  --metrics ~/AI_coworkRec/.weekly_metrics.json \
  --dry-run
```

把 dry-run 結果呈現給使用者，**特別是 `no_ai_hours`**——那是推估值，要使用者確認或改掉才寫入。

### 步驟 4：確認後寫入

移除 `--dry-run` 重跑。

- 寫入前自動備份為 `<檔名>.xlsx.bak`
- 以暫存檔原子替換，中斷不會留下半份檔案
- 該週同專案已存在時會拒絕寫入，需 `--force` 才會新增

### 步驟 5：回報

```
✅ 已寫入週報 Excel
週次：2026-W32 | 填報日期：2026-08-05 | 第 3 列起，共 2 列
專案：FSB核心系統（本週 2.2h / AI 0.6h / 無AI預估 6h）
      內部工具（本週 1.0h / AI 0.2h / 無AI預估 4h）
備份：.../2026_FSB_AI_Weekly.xlsx.bak
```

**必須一併回報 script 的所有警示**，不要吞掉：缺 log 的天數、時長不明的筆數、
`無AI預估低於使用AI工時`、`--force` 覆蓋提醒。

---

## Excel 欄位對應

欄位位置由表頭名稱比對決定，不寫死 A~N（模板插入欄位也不會錯位）。

| 欄位名稱 | 來源 |
|---------|------|
| 年度 / 填報日期 | 系統日期 |
| 週次 | `read_logs.py` 的 ISO 週次 |
| 姓名 / 角色 | 設定檔 |
| 專案名稱 / 客戶名稱 / 專案類型 / 專案階段 / AI應用類型 | Claude 判斷 |
| 本專案本週工時(Hour) | `engaged_hours × share` |
| 使用AI總工時(Hour) | `ai_hours × share` |
| 無AI預估工時(Hour) | Claude 推估，需使用者確認 |
| 備註 | Claude 整合（任務＋做法＋效果＋可複製性） |

找不到 `AI_Weekly_Data` 工作表或辨識不出表頭時，script 會直接中止而不猜測寫入位置。

---

## 設定檔

`~/AI_coworkRec/.weekly_config.json`：

```json
{
  "name": "王小明",
  "role": "SA",
  "excel_path": "~/Documents/2026_FSB_AI_Weekly.xlsx"
}
```

初次設定：`install.py` 會建立這個檔的範本，使用者把 `name`、`role`、`excel_path` 改成自己的即可。
設定檔不存在或欄位還是範本值時，請使用者先填好再繼續，不要代填。

環境變數可覆寫：`AI_COWORK_LOG_DIR`、`AI_WEEKLY_CONFIG`、`AI_COWORK_SCRIPTS`。

---

## 注意事項

- 角色選項：PM、SA、SD、PG
- 專案階段選項：訪談、設計、開發、測試、維護、新需求(CR)、專案會議
- 備註欄兼任 AI 應用場景說明，需具體，但只寫 log 裡確實有的內容
- 找不到本週 log 時，提示使用者確認 `~/AI_coworkRec/` 與 hook 是否正常運作
- openpyxl 重寫整個檔案，理論上可能影響 Excel 原生的圖表、圖片或樞紐分析。
  首次使用後請開啟 Excel 確認模板外觀無誤；`.bak` 是還原用的
