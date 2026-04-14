"""Jira Dashboard TUI 主應用程式"""

from datetime import datetime
from pathlib import Path

from textual import on
from textual import work
from textual.app import App
from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer
from textual.widgets import TabbedContent
from textual.widgets import TabPane

from .config import Config
from .config import JiraClient
from .renderers.layout import TreeLayout
from .renderers.timeline import TimelineRenderer
from .tabs.api import ApiTab
from .tabs.jql import JqlTab
from .tabs.my_issues import MyIssuesTab
from .tabs.worklog import WorklogTab
from .widgets.tree import JiraTree


class JiraDashboard(App):
    """Jira Dashboard TUI 應用程式"""

    CSS_PATH = Path(__file__).parent / 'styles' / 'app.tcss'

    BINDINGS = [
        ('q', 'quit', '離開'),
        ('r', 'refresh', '重新整理'),
        Binding('-', 'decrease_summary_width', '縮小 Summary'),
        Binding('=', 'increase_summary_width', '放大 Summary'),
        Binding('[', 'timeline_scroll_left', 'Timeline ←'),
        Binding(']', 'timeline_scroll_right', 'Timeline →'),
        Binding('c', 'toggle_siblings', '展開/收合同層'),
        Binding('C', 'collapse_all', '收合/展開全部'),
        Binding('p', 'toggle_sp', '顯示/隱藏 SP'),
        Binding('e', 'toggle_est', '顯示/隱藏 A/TOEst'),
        Binding('w', 'toggle_spent', '顯示/隱藏 A/Spent'),
        Binding('s', 'toggle_status', '顯示/隱藏 Status'),
        Binding('d', 'toggle_dates', '顯示/隱藏 Dates'),
        Binding('S', 'edit_start_date', '編輯 Start'),
        Binding('D', 'edit_due_date', '編輯 Due'),
        Binding('P', 'edit_sp', '編輯 SP'),
        Binding('E', 'edit_time_estimate', '編輯 Time Est'),
        Binding('m', 'move_mark', '移動 Issue'),
        Binding('T', 'edit_status', '編輯 Status'),
        Binding('l', 'add_worklog', 'Add Worklog'),
    ]

    timeline_scroll_offset: reactive[int] = reactive(0)
    timeline_width: reactive[int] = reactive(21)  # 會在 on_mount 時根據畫面寬度重新計算

    # 只在 my-issues-tab 有效的 actions
    _ISSUES_TAB_ACTIONS = {
        'decrease_summary_width',
        'increase_summary_width',
        'timeline_scroll_left',
        'timeline_scroll_right',
        'toggle_siblings',
        'collapse_all',
        'toggle_sp',
        'toggle_est',
        'toggle_spent',
        'toggle_status',
        'toggle_dates',
        'edit_start_date',
        'edit_due_date',
        'edit_sp',
        'edit_time_estimate',
        'move_mark',
        'edit_status',
        'add_worklog',
    }
    _WORKLOG_TAB_ACTIONS = {
        'worklog_prev_day',
        'worklog_next_day',
        'worklog_today',
    }

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """檢查 action 是否可用"""
        if action in self._ISSUES_TAB_ACTIONS:
            try:
                return self.query_one(TabbedContent).active == 'my-issues-tab'
            except Exception:
                return False
        if action in self._WORKLOG_TAB_ACTIONS:
            try:
                return self.query_one(TabbedContent).active == 'worklog-tab'
            except Exception:
                return False
        return True

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane('API', id='home-tab'):
                yield ApiTab()
            with TabPane('Issues', id='my-issues-tab'):
                yield MyIssuesTab()
            with TabPane('Worklog', id='worklog-tab'):
                yield WorklogTab()
            with TabPane('JQL', id='jql-tab'):
                yield JqlTab()
        yield Footer()

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.myself: dict | None = None

    def _get_jira_client(self) -> JiraClient:
        """建立 JiraClient"""
        return JiraClient(
            host=self.config.host,
            user=self.config.user,
            token=self.config.token,
        )

    def on_mount(self) -> None:
        """App 啟動時初始化"""
        # 計算初始 timeline 寬度
        self._update_timeline_width()

    # === JiraTree Message Handlers ===

    @on(JiraTree.UpdateIssueDate)
    def handle_update_issue_date(self, event: JiraTree.UpdateIssueDate) -> None:
        """處理日期更新請求"""
        self._do_update_issue_date(event.issue_key, event.field, event.date_str)

    @work(thread=True)
    def _do_update_issue_date(self, issue_key: str, field: str, date_str: str | None) -> None:
        """背景更新 issue 日期"""
        try:
            client = self._get_jira_client()
            api_field = 'customfield_10015' if field == 'start_date' else 'duedate'
            client.update_issue(issue_key, {api_field: date_str})
            if date_str:
                msg = f'{issue_key} {field} 已更新為 {date_str}'
            else:
                msg = f'{issue_key} {field} 已清除'
            self.call_from_thread(self.notify, msg, timeout=2)
        except Exception as e:
            self.call_from_thread(self.notify, f'更新失敗: {e}', severity='error')

    @on(JiraTree.UpdateIssueSP)
    def handle_update_issue_sp(self, event: JiraTree.UpdateIssueSP) -> None:
        """處理 Story Points 更新請求"""
        self._do_update_issue_sp(event.issue_key, event.sp_value)

    @work(thread=True)
    def _do_update_issue_sp(self, issue_key: str, sp_value: float | None) -> None:
        """背景更新 issue Story Points"""
        try:
            client = self._get_jira_client()
            client.update_issue(issue_key, {'customfield_10033': sp_value})
            if sp_value is not None:
                msg = f'{issue_key} SP 已更新為 {sp_value}'
            else:
                msg = f'{issue_key} SP 已清除'
            self.call_from_thread(self.notify, msg, timeout=2)
        except Exception as e:
            self.call_from_thread(self.notify, f'更新失敗: {e}', severity='error')

    @on(JiraTree.UpdateIssueTimeEstimate)
    def handle_update_issue_time_estimate(self, event: JiraTree.UpdateIssueTimeEstimate) -> None:
        """處理 Time Estimate 更新請求"""
        self._do_update_issue_time_estimate(event.issue_key, event.seconds)

    @work(thread=True)
    def _do_update_issue_time_estimate(self, issue_key: str, seconds: int | None) -> None:
        """背景更新 issue Time Original Estimate"""
        try:
            client = self._get_jira_client()
            time_str = self._seconds_to_jira_format(seconds) if seconds else None
            client.update_issue_timetracking(issue_key, time_str)
            if seconds is not None:
                msg = f'{issue_key} Time Estimate 已更新'
            else:
                msg = f'{issue_key} Time Estimate 已清除'
            self.call_from_thread(self.notify, msg, timeout=2)
        except Exception as e:
            self.call_from_thread(self.notify, f'更新失敗: {e}', severity='error')

    def _seconds_to_jira_format(self, seconds: int) -> str:
        """將秒數轉換成 Jira API 接受的格式 (如 '1d 2h 30m')"""
        if seconds <= 0:
            return ''
        total_minutes = seconds // 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        days = hours // 8
        remaining_hours = hours % 8
        parts = []
        if days > 0:
            parts.append(f'{days}d')
        if remaining_hours > 0:
            parts.append(f'{remaining_hours}h')
        if minutes > 0:
            parts.append(f'{minutes}m')
        return ' '.join(parts) if parts else ''

    @on(JiraTree.UpdateIssueRank)
    def handle_update_issue_rank(self, event: JiraTree.UpdateIssueRank) -> None:
        """處理 Rank 更新請求"""
        self._do_update_issue_rank(event.issue_key, event.rank_before, event.rank_after)

    @work(thread=True)
    def _do_update_issue_rank(
        self,
        issue_key: str,
        rank_before: str | None,
        rank_after: str | None,
    ) -> None:
        """背景更新 issue rank"""
        try:
            client = self._get_jira_client()
            client.rank_issue(issue_key, rank_before=rank_before, rank_after=rank_after)
            self.call_from_thread(self.notify, f'{issue_key} 已移動', timeout=2)
        except Exception as e:
            self.call_from_thread(self.notify, f'移動失敗: {e}', severity='error')

    @on(JiraTree.RequestTransitions)
    def handle_request_transitions(self, event: JiraTree.RequestTransitions) -> None:
        """處理取得 transitions 請求"""
        self._do_get_transitions(event.issue_key, event.current_status)

    @work(thread=True)
    def _do_get_transitions(self, issue_key: str, current_status: str) -> None:
        """背景取得 issue transitions"""
        try:
            client = self._get_jira_client()
            transitions = client.get_transitions(issue_key)
            # 回到主線程顯示 modal
            self.call_from_thread(
                self._show_status_modal,
                issue_key,
                current_status,
                transitions,
            )
        except Exception as e:
            self.call_from_thread(self.notify, f'取得狀態失敗: {e}', severity='error')

    def _show_status_modal(self, issue_key: str, current_status: str, transitions: list) -> None:
        """顯示 status 編輯 modal"""
        for tree in self.query(JiraTree):
            tree.show_status_modal(
                issue_key=issue_key,
                current_status=current_status,
                transitions=transitions,
            )
            break  # 只需要一個 tree 處理

    @on(JiraTree.UpdateIssueStatus)
    def handle_update_issue_status(self, event: JiraTree.UpdateIssueStatus) -> None:
        """處理 Status 更新請求"""
        self._do_update_issue_status(event.issue_key, event.transition_id, event.new_status_name)

    @work(thread=True)
    def _do_update_issue_status(
        self,
        issue_key: str,
        transition_id: str,
        new_status_name: str,
    ) -> None:
        """背景更新 issue status"""
        try:
            client = self._get_jira_client()
            client.transition_issue(issue_key, transition_id)
            self.call_from_thread(
                self.notify,
                f'{issue_key} 狀態已變更為 {new_status_name}',
                timeout=2,
            )
        except Exception as e:
            self.call_from_thread(self.notify, f'變更狀態失敗: {e}', severity='error')

    @on(JiraTree.AddIssueWorklog)
    def handle_add_issue_worklog(self, event: JiraTree.AddIssueWorklog) -> None:
        self._do_add_issue_worklog(
            event.issue_key,
            event.started,
            event.time_spent_seconds,
            event.comment_text,
            event.remaining_estimate_seconds,
        )

    @work(thread=True)
    def _do_add_issue_worklog(
        self,
        issue_key: str,
        started: datetime,
        time_spent_seconds: int,
        comment_text: str,
        remaining_estimate_seconds: int | None,
    ) -> None:
        try:
            client = self._get_jira_client()
            client.add_issue_worklog(
                issue_key,
                started=started,
                time_spent_seconds=time_spent_seconds,
                comment_text=comment_text,
                remaining_estimate_seconds=remaining_estimate_seconds,
            )
            self.call_from_thread(self._after_issue_worklog_added, issue_key)
        except Exception as e:
            self.call_from_thread(self.notify, f'新增 worklog 失敗: {e}', severity='error')

    def _after_issue_worklog_added(self, issue_key: str) -> None:
        self.notify(f'{issue_key} worklog 已新增', timeout=2)
        try:
            self.query_one(MyIssuesTab).run_search()
        except Exception:
            pass
        try:
            self.query_one(WorklogTab).refresh_day()
        except Exception:
            pass


    def _update_timeline_width(self) -> None:
        """重新計算並更新 timeline 寬度"""
        new_width = self._calculate_timeline_width(
            console_width=self.size.width,
        )
        if new_width != self.timeline_width:
            self.timeline_width = new_width

    def action_open_link(self, url: str) -> None:
        """開啟網址"""
        import webbrowser
        webbrowser.open(url)

    def action_switch_to_issues(self) -> None:
        """切換到 Issues Tab"""
        self.set_focus(None)  # 先移除 focus，避免 focus 導致 tab 切回去
        self.query_one(TabbedContent).active = 'my-issues-tab'

    def action_refresh(self) -> None:
        """重新整理資料"""
        active_tab = self.query_one(TabbedContent).active
        if active_tab == 'my-issues-tab':
            self.query_one(MyIssuesTab).start_loading()
        elif active_tab == 'jql-tab':
            self.query_one(JqlTab).run_search()
        elif active_tab == 'worklog-tab':
            self.query_one(WorklogTab).refresh_day()

    def action_decrease_summary_width(self) -> None:
        """縮小 Summary 寬度"""
        if self.query_one(TabbedContent).active == 'my-issues-tab':
            self.query_one(MyIssuesTab).decrease_summary_width()
            self._update_timeline_width()

    def action_increase_summary_width(self) -> None:
        """放大 Summary 寬度"""
        if self.query_one(TabbedContent).active == 'my-issues-tab':
            self.query_one(MyIssuesTab).increase_summary_width()
            self._update_timeline_width()

    def action_timeline_scroll_left(self) -> None:
        """Timeline 向左捲動（顯示更早的日期）"""
        if self.query_one(TabbedContent).active == 'my-issues-tab':
            self.timeline_scroll_offset -= 1

    def action_timeline_scroll_right(self) -> None:
        """Timeline 向右捲動"""
        if self.query_one(TabbedContent).active == 'my-issues-tab':
            self.timeline_scroll_offset += 1

    def watch_timeline_scroll_offset(self, new_offset: int) -> None:
        """當 timeline_scroll_offset 變化時，更新所有 JiraTree 的 Timeline"""
        if self.query_one(TabbedContent).active == 'my-issues-tab':
            for tree in self.query(JiraTree):
                tree.set_timeline_offset(new_offset)
            # 更新 MyIssuesTab 的 timeline header
            try:
                my_issues_tab = self.query_one(MyIssuesTab)
                my_issues_tab.set_timeline_offset(new_offset)
            except Exception:
                pass

    def watch_timeline_width(self, new_width: int) -> None:
        """當 timeline_width 變化時，更新所有 JiraTree 的 Timeline 寬度"""
        for tree in self.query(JiraTree):
            tree.update_timeline_width(new_width)
            tree._invalidate()
        # 更新 MyIssuesTab 的 timeline header
        try:
            my_issues_tab = self.query_one(MyIssuesTab)
            my_issues_tab.update_timeline_width(new_width)
        except Exception:
            pass

    def _calculate_timeline_width(
        self,
        *,
        console_width: int,
    ) -> int:
        """根據 console 寬度計算 timeline 寬度"""
        try:
            layout = self.query_one(MyIssuesTab)._layout
        except Exception:
            layout = TreeLayout()
        # 額外邊距 (scrollbar, borders, TabbedContent, tree indent, etc.)
        extra_margin = 15
        fixed_width = layout.total_fixed_width + extra_margin
        available = console_width - fixed_width
        # 對齊到 3 的倍數（每天 3 字元），至少顯示 7 天 (21 字元)
        chars_per_day = TimelineRenderer.CHARS_PER_DAY
        days = max(7, available // chars_per_day)
        return days * chars_per_day

    def on_resize(self, event) -> None:
        """視窗大小改變時更新 timeline 寬度"""
        new_width = self._calculate_timeline_width(
            console_width=self.size.width,
        )
        # 強制更新所有 tree 的 timeline 寬度
        for tree in self.query(JiraTree):
            tree.update_timeline_width(new_width)
        # 更新 header
        try:
            my_issues_tab = self.query_one(MyIssuesTab)
            my_issues_tab.update_timeline_width(new_width)
        except Exception:
            pass
        # 更新 reactive 變數
        self.timeline_width = new_width

    def action_toggle_siblings(self) -> None:
        """展開/收合目前同層的所有節點"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_toggle_siblings()

    def action_collapse_all(self) -> None:
        """收合/展開所有節點"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_collapse_all()

    def action_toggle_sp(self) -> None:
        """顯示/隱藏 Story Points 欄位"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        my_issues_tab = self.query_one(MyIssuesTab)
        my_issues_tab._layout.show_sp = not my_issues_tab._layout.show_sp
        # 重繪所有 tree
        my_issues_tab._update_all_tables_summary_width()
        # 更新 timeline 寬度
        self._update_timeline_width()

    def action_toggle_est(self) -> None:
        """顯示/隱藏 Original Estimate 欄位"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        my_issues_tab = self.query_one(MyIssuesTab)
        my_issues_tab._layout.show_est = not my_issues_tab._layout.show_est
        # 重繪所有 tree
        my_issues_tab._update_all_tables_summary_width()
        # 更新 timeline 寬度
        self._update_timeline_width()

    def action_toggle_spent(self) -> None:
        """顯示/隱藏 Time Spent 欄位"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        my_issues_tab = self.query_one(MyIssuesTab)
        my_issues_tab._layout.show_spent = not my_issues_tab._layout.show_spent
        # 重繪所有 tree
        my_issues_tab._update_all_tables_summary_width()
        # 更新 timeline 寬度
        self._update_timeline_width()

    def action_toggle_status(self) -> None:
        """顯示/隱藏 Status 欄位"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        my_issues_tab = self.query_one(MyIssuesTab)
        my_issues_tab._layout.show_status = not my_issues_tab._layout.show_status
        # 重繪所有 tree
        my_issues_tab._update_all_tables_summary_width()
        # 更新 timeline 寬度
        self._update_timeline_width()

    def action_toggle_dates(self) -> None:
        """顯示/隱藏 Dates 欄位"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        my_issues_tab = self.query_one(MyIssuesTab)
        my_issues_tab._layout.show_dates = not my_issues_tab._layout.show_dates
        # 重繪所有 tree
        my_issues_tab._update_all_tables_summary_width()
        # 更新 timeline 寬度
        self._update_timeline_width()

    def action_edit_start_date(self) -> None:
        """編輯 Start Date"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_edit_start_date()

    def action_edit_due_date(self) -> None:
        """編輯 Due Date"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_edit_due_date()

    def action_edit_sp(self) -> None:
        """編輯 Story Points"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_edit_sp()

    def action_edit_time_estimate(self) -> None:
        """編輯 Time Original Estimate"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_edit_time_estimate()

    def action_move_mark(self) -> None:
        """標記 Issue 準備移動"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_move_mark()

    def action_edit_status(self) -> None:
        """編輯 Status"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return

        for tree in self.query(JiraTree):
            tree.action_edit_status()

    def action_add_worklog(self) -> None:
        """在 Issues 樹上對目前選取的 subtask 新增 worklog。"""
        if self.query_one(TabbedContent).active != 'my-issues-tab':
            return
        for tree in self.query(JiraTree):
            tree.action_add_worklog()

    def action_worklog_prev_day(self) -> None:
        """前一天"""
        self.query_one(WorklogTab).go_to_previous_day()

    def action_worklog_next_day(self) -> None:
        """下一天"""
        self.query_one(WorklogTab).go_to_next_day()

    def action_worklog_today(self) -> None:
        """今天"""
        self.query_one(WorklogTab).go_to_today()
