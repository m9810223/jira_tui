"""我的 Issues 分頁"""

from concurrent.futures import ThreadPoolExecutor

import httpx
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.widgets import Button
from textual.widgets import LoadingIndicator
from textual.widgets import Static
from textual.widgets import TabbedContent
from textual.widgets import Tree

from ..config import JiraClient
from ..models import JiraIssue
from ..models import JiraUser
from ..renderers.issue_row import IssueRowRenderer
from ..renderers.layout import TreeLayout
from ..renderers.timeline import TimelineRenderer
from ..screens.user_select import UserSelectScreen
from ..widgets.tree import JiraNodeType
from ..widgets.tree import JiraTree
from ._mixin import JiraClientMixin


class MyIssuesTab(JiraClientMixin, Vertical):
    """我的 Issues 分頁"""

    def __init__(self) -> None:
        super().__init__()
        self._users: list[JiraUser] = []
        self._selected_account_id: str | None = None  # None = currentUser()
        self._current_user_display = ''
        self._selected_display = ''
        self._users_loaded = False
        self._layout = TreeLayout(summary_width=50)
        self._timeline = TimelineRenderer(width=21)
        self._switch_tab_on_load = False  # 載入完成後是否切換到此 tab

    def compose(self) -> ComposeResult:
        with Horizontal(id='assignee-bar'):
            yield Button('變更', id='change-assignee-btn', variant='primary')
            yield Static(' assignee: ', id='assignee-label')
            yield Static(self._selected_display, id='assignee-value')
        yield Static(id='breadcrumb', classes='hidden')
        yield Static(id='timeline-header', classes='hidden')
        yield LoadingIndicator(id='my-issues-loading')
        yield Vertical(id='my-issues-container', classes='hidden')

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """按鈕點擊事件"""
        if event.button.id == 'change-assignee-btn':
            if not self._users_loaded:
                self.app.notify('使用者列表載入中...', severity='warning', timeout=2)
                return
            self._show_user_select()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """當 Tree 節點高亮時更新 breadcrumb"""
        self._update_breadcrumb(event.node)

    def _update_breadcrumb(self, node: 'Tree.NodeHighlighted | None') -> None:
        """更新 breadcrumb 顯示"""
        try:
            breadcrumb = self.query_one('#breadcrumb', Static)
        except Exception:
            return

        if node is None:
            breadcrumb.update('')
            return

        # 收集從 root 到當前節點的路徑
        path_parts: list[str] = []
        current = node
        while current is not None and current.parent is not None:
            data = current.data
            if data is not None:
                if data.node_type == JiraNodeType.ISSUE:
                    if data.issue:
                        path_parts.insert(0, data.issue.key)
                elif data.node_type == JiraNodeType.EXTERNAL_EPIC:
                    if data.issue:
                        path_parts.insert(0, f'{data.issue.key}')
                else:
                    path_parts.insert(0, data.title)
            current = current.parent

        breadcrumb.update(' > '.join(path_parts) if path_parts else '')

    def decrease_summary_width(self) -> None:
        """縮小 Summary 寬度"""
        if self._layout.summary_width > 20:
            self._layout.summary_width -= 1
            self._update_all_tables_summary_width()

    def increase_summary_width(self) -> None:
        """放大 Summary 寬度"""
        if self._layout.summary_width < 100:
            self._layout.summary_width += 1
            self._update_all_tables_summary_width()

    def _update_all_tables_summary_width(self) -> None:
        """更新所有 JiraTree 的 Summary 欄位寬度（layout 已更新）"""
        for tree in self.query(JiraTree):
            tree._invalidate()
        self._update_timeline_header()

    def _update_timeline_header(self, scroll_offset: int = 0) -> None:
        """更新 Timeline header 顯示"""
        try:
            header_widget = self.query_one('#timeline-header', Static)
        except Exception:
            return

        # 使用 IssueRowRenderer 產生 header
        renderer = IssueRowRenderer(layout=self._layout)

        result = Text(' ' * self._layout.max_guide_width)
        result.append_text(renderer.render_header(depth=self._layout.MAX_DEPTH))
        result.append_text(self._timeline.format_header(scroll_offset))

        header_widget.update(result)

    def update_timeline_width(self, width: int) -> None:
        """更新 Timeline 寬度"""
        self._timeline.width = width
        self._update_timeline_header()

    def set_timeline_offset(self, offset: int) -> None:
        """設定 Timeline 捲動偏移"""
        self._update_timeline_header(offset)

    def start_loading(self) -> None:
        """開始載入資料"""
        client = self._get_jira_client(silent=True)
        if not client:
            return

        # 如果還沒有 myself 資訊，先獲取
        if self.app.myself is None:  # pyright: ignore[reportAttributeAccessIssue]
            try:
                self.app.myself = client.get_myself()  # pyright: ignore[reportAttributeAccessIssue]
            except Exception:
                pass

        # 設定當前使用者顯示
        myself = self.app.myself  # pyright: ignore[reportAttributeAccessIssue]
        if myself:
            self._current_user_display = myself.get('displayName', 'Current User')
            self._selected_display = self._current_user_display
            self._update_assignee_display()

        # 並行執行：載入 issues 和載入使用者列表
        self.run_search()
        self._load_users()

    def _load_users(self) -> None:
        """啟動背景載入使用者列表"""
        client = self._get_jira_client(silent=True)
        if not client:
            return
        self._do_load_users(client)

    @work(thread=True)
    def _do_load_users(self, client: JiraClient) -> None:
        """背景載入使用者列表"""
        all_users: dict[str, JiraUser] = {}
        try:
            projects = client.get_projects()
            project_keys = [p.get('key') for p in projects if p.get('key')] if projects else []

            if project_keys:
                def fetch_users(project_key: str) -> list[JiraUser]:
                    try:
                        return client.search_assignable_users(project=project_key)
                    except (httpx.HTTPStatusError, httpx.RequestError):
                        return []

                with ThreadPoolExecutor(max_workers=min(10, len(project_keys))) as executor:
                    results = executor.map(fetch_users, project_keys)
                    for users in results:
                        for user in users:
                            if user.active and user.account_id not in all_users:
                                all_users[user.account_id] = user
        except (httpx.HTTPStatusError, httpx.RequestError):
            pass  # 載入使用者列表失敗，但不影響基本功能

        self.app.call_from_thread(
            self._on_users_loaded,
            list(all_users.values()),
        )

    def _on_users_loaded(self, users: list[JiraUser]) -> None:
        """使用者列表載入完成"""
        self._users = users
        self._users_loaded = True

    def _hide_loading(self) -> None:
        """隱藏載入指示器，顯示容器和 timeline header"""
        self.query_one('#my-issues-loading', LoadingIndicator).add_class('hidden')
        self.query_one('#my-issues-container', Vertical).remove_class('hidden')
        self.query_one('#breadcrumb', Static).remove_class('hidden')
        self.query_one('#timeline-header', Static).remove_class('hidden')
        self._update_timeline_header()

    def _update_assignee_display(self) -> None:
        """更新 assignee 顯示"""
        label = self.query_one('#assignee-value', Static)
        label.update(self._selected_display)

    def _show_user_select(self) -> None:
        """顯示使用者選擇對話框"""
        screen = UserSelectScreen(
            users=self._users,
            current_user_display=self._current_user_display,
        )
        self.app.push_screen(screen, self._on_user_selected)

    def _on_user_selected(self, result: tuple[str | None, str] | None) -> None:
        """使用者選擇完成"""
        if result is None:
            return
        account_id, display_name = result
        self._selected_account_id = account_id
        self._selected_display = display_name
        self._update_assignee_display()
        self.run_search()

    def _build_jql(self) -> str:
        """根據選擇的使用者建立 JQL"""
        if self._selected_account_id is None:
            return 'assignee = currentUser()'
        return f'assignee = "{self._selected_account_id}"'

    def run_search(self, *, switch_tab: bool = False) -> None:
        """執行搜尋

        Args:
            switch_tab: 載入完成後是否切換到此 tab
        """
        client = self._get_jira_client(silent=True)
        if not client:
            # 即使沒有 client 也要切換 tab
            if switch_tab:
                self.app.query_one(TabbedContent).active = 'my-issues-tab'
            return

        self._switch_tab_on_load = switch_tab
        self._show_loading()
        jql = self._build_jql()
        self._do_search(client, jql)

    def _show_loading(self) -> None:
        """顯示載入指示器，隱藏容器"""
        self.query_one('#my-issues-loading', LoadingIndicator).remove_class('hidden')
        self.query_one('#my-issues-container', Vertical).add_class('hidden')

    @work(thread=True)
    def _do_search(self, client: JiraClient, jql: str) -> None:
        """背景執行搜尋，一次載入全部 issues"""
        try:
            all_issues: list[JiraIssue] = []
            next_token: str | None = None

            while True:
                result = client.search_jql(jql, next_page_token=next_token)
                all_issues.extend(result.issues)
                if result.is_last or not result.next_page_token:
                    break
                next_token = result.next_page_token

            # 找出外部 parent keys（不在查詢結果中的 parent）
            issue_keys = {i.key for i in all_issues}
            external_parent_keys: set[str] = set()
            for issue in all_issues:
                parent = issue.fields.parent
                if parent and parent.key not in issue_keys:
                    external_parent_keys.add(parent.key)

            # 抓取外部 parent 資訊
            external_parents: list[JiraIssue] = []
            if external_parent_keys:
                parent_jql = f'key in ({",".join(external_parent_keys)})'
                parent_result = client.search_jql(parent_jql)
                external_parents = parent_result.issues

            self.app.call_from_thread(self._on_search_complete, all_issues, external_parents)
        except httpx.HTTPStatusError as e:
            self.app.call_from_thread(
                self.app.notify,
                f'搜尋失敗: HTTP {e.response.status_code}',
                severity='error',
            )
            self.app.call_from_thread(self._on_search_complete, [], [])
        except httpx.RequestError as e:
            self.app.call_from_thread(self.app.notify, f'搜尋錯誤: {e}', severity='error')
            self.app.call_from_thread(self._on_search_complete, [], [])

    def _on_search_complete(
        self,
        issues: list[JiraIssue],
        external_parents: list[JiraIssue] | None = None,
    ) -> None:
        """搜尋完成"""
        container = self.query_one('#my-issues-container', Vertical)
        container.remove_children()

        # 同步 timeline 設定
        self._timeline.width = self.app.timeline_width  # pyright: ignore[reportAttributeAccessIssue]

        if issues:
            tree = JiraTree(
                layout=self._layout,
                timeline_width=self.app.timeline_width,  # pyright: ignore[reportAttributeAccessIssue]
                jira_host=self.config.host,
            )
            tree.load_issues(issues, external_parents=external_parents or [], group_by_project=True)
            container.mount(tree)
            # 選擇第一個節點以顯示 breadcrumb（延遲執行以確保 mount 完成）
            def select_first():
                if tree.root.children:
                    first_node = tree.root.children[0]
                    tree.select_node(first_node)
                    self._update_breadcrumb(first_node)
            self.set_timer(0.1, select_first)

        self._hide_loading()

        # 如果需要切換到此 tab
        if self._switch_tab_on_load:
            self._switch_tab_on_load = False
            self.app.notify(f'已載入 {len(issues)} 個 Issues', timeout=3)
            self.app.action_switch_to_issues()  # pyright: ignore[reportAttributeAccessIssue]
