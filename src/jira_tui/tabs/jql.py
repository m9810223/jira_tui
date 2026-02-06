"""JQL 查詢分頁"""

import httpx
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.widgets import Button
from textual.widgets import DataTable
from textual.widgets import LoadingIndicator
from textual.widgets import Static
from textual.widgets import TextArea

from ..config import JiraClient
from ..models import JiraIssue
from ..models import JiraSearchResult
from ..widgets.inputs import BlurTextArea
from ..widgets.table import JqlDataTable
from ._mixin import JiraClientMixin


class JqlTab(JiraClientMixin, Vertical):
    """JQL 查詢分頁"""

    def __init__(self) -> None:
        super().__init__()
        self._search_total = 0
        self._search_loaded = 0
        self._search_next_token: str | None = None
        self._search_is_last = True
        self._search_loading = False

    def compose(self) -> ComposeResult:
        with Horizontal(id='jql-bar'):
            yield BlurTextArea(id='jql-input')
            yield Button('搜尋', id='search-btn', variant='primary')
        yield LoadingIndicator(id='jql-loading', classes='hidden')
        yield JqlDataTable(id='results-table')
        yield Static('', id='results-status')

    def _show_loading(self) -> None:
        """顯示載入指示器，隱藏表格"""
        self.query_one('#jql-loading', LoadingIndicator).remove_class('hidden')
        self.query_one('#results-table', DataTable).add_class('hidden')

    def _hide_loading(self) -> None:
        """隱藏載入指示器，顯示表格"""
        self.query_one('#jql-loading', LoadingIndicator).add_class('hidden')
        self.query_one('#results-table', DataTable).remove_class('hidden')

    def on_mount(self) -> None:
        """初始化"""
        # 載入 JQL
        jql_input = self.query_one('#jql-input', TextArea)
        jql_input.text = self.config.jql
        self._update_jql_input_height(jql_input)

        # 初始化結果表格欄位
        table = self.query_one('#results-table', DataTable)
        table.add_columns('Key', 'Summary', 'Status', 'Assignee', 'Priority')

        # 監聽表格捲動事件
        self.app.watch(table, 'scroll_y', self._on_table_scroll)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """JQL 輸入變更時更新（不儲存）"""
        if event.text_area.id == 'jql-input':
            self.config.jql = event.text_area.text
            self._update_jql_input_height(event.text_area)

    def _update_jql_input_height(self, text_area: TextArea) -> None:
        """根據內容行數調整 JQL 輸入區高度"""
        line_count = text_area.text.count('\n') + 1
        height = min(10, max(1, line_count))
        text_area.styles.height = height

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """按鈕點擊事件"""
        if event.button.id == 'search-btn':
            self.run_search()

    def run_search(self) -> None:
        """執行 JQL 搜尋（重置並載入第一頁）"""
        jql = self.config.jql.strip()
        if not jql:
            jql = 'key != EMPTY'
            jql_input = self.query_one('#jql-input', TextArea)
            jql_input.text = jql
            self.config.jql = jql
            self._update_jql_input_height(jql_input)

        client = self._get_jira_client(silent=True)
        if not client:
            return

        # 重置搜尋狀態
        self._search_total = 0
        self._search_loaded = 0
        self._search_next_token = None
        self._search_is_last = True
        self._search_loading = True

        # 顯示載入中
        self._show_loading()
        status = self.query_one('#results-status', Static)
        status.update('Loading...')

        self._do_search(client, jql)

    @work(thread=True)
    def _do_search(self, client: JiraClient, jql: str) -> None:
        """背景執行搜尋"""
        try:
            total = client.count_jql(jql)
            result = client.search_jql(jql)
            self.app.call_from_thread(self._on_search_complete, total, result)
        except httpx.HTTPStatusError as e:
            self.app.call_from_thread(
                self.app.notify,
                f'搜尋失敗: HTTP {e.response.status_code}',
                severity='error',
            )
            self.app.call_from_thread(self._on_search_complete, 0, None)
        except httpx.RequestError as e:
            self.app.call_from_thread(self.app.notify, f'搜尋錯誤: {e}', severity='error')
            self.app.call_from_thread(self._on_search_complete, 0, None)

    def _on_search_complete(self, total: int, result: JiraSearchResult | None) -> None:
        """搜尋完成"""
        self._search_loading = False
        self._search_total = total

        if result:
            self._search_loaded = len(result.issues)
            self._search_next_token = result.next_page_token
            self._search_is_last = result.is_last

            table = self.query_one('#results-table', DataTable)
            table.clear()
            self._append_issues_to_table(table, result.issues)

        self._hide_loading()
        self._update_results_status()

    def _update_results_status(self) -> None:
        """更新結果狀態列"""
        status = self.query_one('#results-status', Static)
        status.update(f'{self._search_loaded} of {self._search_total}')

    def _append_issues_to_table(self, table: DataTable, issues: list[JiraIssue]) -> None:
        """將 issues 加入表格"""
        for issue in issues:
            status_name = issue.fields.status.name if issue.fields.status else ''
            assignee_name = issue.fields.assignee.display_name if issue.fields.assignee else ''
            priority_name = issue.fields.priority.name if issue.fields.priority else ''

            table.add_row(
                issue.key,
                issue.fields.summary,
                status_name,
                assignee_name,
                priority_name,
            )

    def _load_more_results(self) -> None:
        """載入更多搜尋結果"""
        if self._search_is_last or self._search_loading or not self._search_next_token:
            return

        jql = self.config.jql.strip()
        if not jql:
            return

        client = self._get_jira_client(silent=True)
        if not client:
            return

        self._search_loading = True
        status = self.query_one('#results-status', Static)
        status.update('Loading more...')

        self._do_load_more(client, jql)

    @work(thread=True)
    def _do_load_more(self, client: JiraClient, jql: str) -> None:
        """背景執行載入更多"""
        try:
            result = client.search_jql(jql, next_page_token=self._search_next_token)
            self.app.call_from_thread(self._on_load_more_complete, result)
        except (httpx.HTTPStatusError, httpx.RequestError):
            self.app.call_from_thread(self._on_load_more_complete, None)

    def _on_load_more_complete(self, result: JiraSearchResult | None) -> None:
        """載入完成回調"""
        if result:
            self._search_loaded += len(result.issues)
            self._search_next_token = result.next_page_token
            self._search_is_last = result.is_last

            table = self.query_one('#results-table', DataTable)
            self._append_issues_to_table(table, result.issues)

        self._search_loading = False
        self._update_results_status()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """當列被高亮時檢查是否需要載入更多"""
        if event.cursor_row >= self._search_loaded - 10:
            self._load_more_results()

    def _on_table_scroll(self) -> None:
        """當表格捲動時檢查是否需要載入更多"""
        table = self.query_one('#results-table', DataTable)
        if table.scroll_y >= table.max_scroll_y - 3:
            self._load_more_results()
