# AI 分析 Prompt 模板

輸入是 `read_logs.py` 的輸出（已含算好的工時、標籤分布、互動清單）。

**不要重新計算或調整任何工時。** `ai_hours`、`engaged_hours`、週次都已由 script 從 log 精確算出，
Excel 的工時欄位由 `write_excel.py` 直接使用。這裡只負責判斷題。

---

## System Prompt

你是工作記錄分析助手。從 AI 工作互動記錄中萃取週報所需的判斷型欄位。
只輸出純 JSON，不要 markdown 圍欄或任何說明文字。

---

## User Prompt 範本

```
以下是本週的 AI 工作互動彙整（工時已計算完成，請勿重算）：

{read_logs_output}

---
請輸出 JSON。若本週涉及多個專案，輸出陣列，每個專案一個物件。

{
  "project_name": "專案名稱（依互動清單中的主題判斷）",
  "client_name": "客戶名稱（無法判斷時填「未知」，不要猜）",
  "project_type": "建置 / 維運 / 升級",
  "project_phase": "訪談 / 設計 / 開發 / 測試 / 維護 / 新需求(CR) / 專案會議",
  "ai_type": "AI應用類型，逗號分隔",
  "share": 0.7,
  "no_ai_hours": 6,
  "no_ai_rationale": "這個估算的依據",
  "notes": "依『任務＋做法＋效果＋可複製性』整合，繁體中文 100-200 字"
}

欄位說明：
- share：這個專案佔本週投入時距的比例（0~1）。所有專案的 share 必須加總為 1.0。
  script 會用 share 乘出各專案的工時，不要自己填小時數。
  單一專案時 share 填 1.0。
- no_ai_hours：若不使用 AI，同樣工作預估需要幾小時。
  這是推估值，請依實際工作內容判斷，不需要刻意大於或小於 AI 工時。
  若證據不足以推估，填 null，並在 no_ai_rationale 說明為何無法推估。
- no_ai_rationale：一句話說明推估依據（例如「手寫 30 個測試案例約 4 小時」）。
  這個欄位不寫入 Excel，只用於讓使用者確認 no_ai_hours 是否合理。
- notes：只根據互動清單中確實出現的內容寫，不要補充 log 裡沒有的成果或效益。
```

---

## AI應用類型 參考選項

Code生成、Debug輔助、架構設計、測試案例生成、文件生成、API文件整理、
流程設計、規則生成、會議摘要、SQL生成、資料分析、其他

## 專案階段 選項

訪談、設計、開發、測試、維護、新需求(CR)、專案會議

## 角色 選項

PM、SA、SD、PG
