# Worklog 日曆美化設計文件 (2026-04-10)

## 1. 專案目標 (Goals)
目前的 `WorklogDayGrid` 介面較為簡陋，缺乏視覺層次且顏色對比生硬。本設計旨在導入「區塊化 (Blocky)」風格，特別是採用「左側重音線 (Left Accent)」方案，以提升資訊可讀性與視覺美感，同時保持 TUI 的高效空間利用。

## 2. 視覺規格 (Visual Specifications)

### 2.1 核心佈局 (Core Layout)
- **左側重音線**：每個 Worklog 區塊左側使用粗體 Unicode 字符 `▌` (U+258C) 標示。
- **邊界標記**：
    - 任務起始行：顯示 `Issue Key` 與 `Summary`。
    - 任務中間行：顯示 `Comment` (若有) 或空白填充。
    - 任務結尾行：僅顯示重音線，可視情況加入細分隔線。
- **時間軸 (Time Axis)**：
    - **整點 (On the hour)**：如 `09:00`，使用亮色 (Primary) 並加粗。
    - **半點 (Half hour)**：如 `09:30`，使用淡灰色 (Muted) 或 ` -- ` 符號替代。

### 2.2 顏色方案 (Color Scheme)
- **Entry 背景**：使用深灰色或略微帶有色偏的背景色（如 `$surface` 或自定義深色），而非亮色背景。
- **Entry 邊框/重音**：根據任務類型或 Issue 狀態分配 2-3 種主色調（如藍、綠、紫），用於重音線與 Issue Key 文字。
- **Draft 選擇**：選取範圍使用反色 (Reverse) 或高亮邊框（如 Unicode 虛線 `┆`）以示區別。

## 3. 技術實作 (Technical Implementation)

### 3.1 元件修改 (`src/jira_tui/widgets/worklog_day_grid.py`)
- **`render()` 邏輯優化**：
    - 重構 `_render_slot_line`，使其能根據 Slot 在 Entry 中的位置（起始、中間、結束）返回不同的 Rich Text 構建。
    - 處理「左側重音線」與「內容區域」的對齊。
- **`Text` 構建**：利用 `rich.text.Text` 的鏈式調用，精確控制每一行的樣式、截斷 (Truncate) 與填充 (Pad)。

### 3.2 樣式表修改 (`src/jira_tui/styles/app.tcss`)
- 新增或更新 `.worklog-entry-start`, `.worklog-entry-mid`, `.worklog-entry-end` 等 class 或在代碼中動態生成樣式。
- 優化時間軸樣式定義。

## 4. 驗證標準 (Success Criteria)
- [ ] 不同長度（30 分鐘 vs 多小時）的 Worklog 均能清晰區分。
- [ ] 視覺層次分明：時間點 -> Issue Key -> 內容描述。
- [ ] 在暗色終端主題下，對比度舒適，無刺眼的大色塊。
- [ ] 滑鼠拖拉選取 (Draft) 的回饋直覺且與現有 Entry 有明顯差異。

## 5. 測試計畫 (Testing Plan)
- **視覺測試**：手動載入多組不同時間重疊的 Worklog，檢查渲染邊界是否正確。
- **邊界案例**：
    - 僅佔 1 個 Slot (30 分鐘) 的任務是否顯示 Issue Key。
    - 非常長的 Summary 是否正確截斷且不破壞邊框。
    - 選取邊界與已有任務重疊時的渲染行為。
