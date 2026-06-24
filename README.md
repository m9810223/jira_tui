> # See https://jira-key.vercel.app/ 

# Jira TUI

使用 [Textual](https://textual.textualize.io/) 框架打造的終端機 Jira 儀表板，支援 Issue 瀏覽、編輯與時間軸視覺化。

## 功能

- **樹狀瀏覽** — Issue 依 Project / Epic / Sprint 階層分組
- **時間軸** — 以彩色條狀圖顯示起迄日期，可水平捲動
- **即時編輯** — 在 TUI 中直接修改日期、Story Points、時間預估、狀態
- **JQL 查詢** — 自訂 JQL 搜尋，分頁載入結果
- **Assignee 切換** — 快速檢視不同成員的 Issues

## 安裝

需要 Python 3.12+ 與 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <repo-url> && cd jira_tui
cp .env.example .env
# 編輯 .env 填入你的 Jira 設定
uv sync
```

## 設定

在 `.env` 中填入：

```
JIRA_HOST=https://your-domain.atlassian.net
JIRA_USER=your-email@example.com
JIRA_TOKEN=your-api-token
```

API Token 可在 [Atlassian 帳號安全設定](https://id.atlassian.com/manage-profile/security/api-tokens) 建立。

## 執行

```bash
uv run -m jira_tui
```

## 快捷鍵

### 全域

| 鍵 | 功能 |
|---|---|
| `q` | 離開 |
| `r` | 重新整理 |

### Issues 分頁

**瀏覽**

| 鍵 | 功能 |
|---|---|
| `space` | 展開/收合節點 |
| `c` | 展開/收合同層節點 |
| `C` | 展開/收合全部 |
| `-` / `=` | 縮小/放大 Summary 欄寬 |
| `[` / `]` | Timeline 左/右捲動 |

**欄位顯示切換**

| 鍵 | 功能 |
|---|---|
| `p` | Story Points |
| `e` | Time Estimates |
| `s` | Status |
| `d` | Dates |

**編輯**

| 鍵 | 功能 |
|---|---|
| `S` | 編輯 Start Date |
| `D` | 編輯 Due Date |
| `P` | 編輯 Story Points |
| `E` | 編輯 Time Estimate |
| `T` | 變更 Status |
| `m` | 移動/重新排序 Issue |

## 技術

- [Textual](https://textual.textualize.io/) — TUI 框架
- [httpx](https://www.python-httpx.org/) — HTTP 客戶端
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — 環境變數設定管理
