"""API 設定分頁"""

import httpx
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Static

from ..widgets.inputs import BlurInput
from ._mixin import JiraClientMixin


class ApiTab(JiraClientMixin, Vertical):
    """API 設定分頁"""

    def compose(self) -> ComposeResult:
        yield Static('歡迎使用 Jira Dashboard')
        with Vertical(id='config-form'):
            yield Label('Jira Host')
            yield BlurInput(placeholder='https://your-domain.atlassian.net', id='jira-host')
            yield Label('User (Email)')
            yield BlurInput(placeholder='your-email@example.com', id='jira-user')
            yield Label('API Token ([@click=app.open_link("https://id.atlassian.com/manage-profile/security/api-tokens")]建立 Token[/])', markup=True)
            yield BlurInput(placeholder='API Token', password=True, id='jira-token')
            yield Static('', id='api-status')
            yield Button('驗證連線', id='verify-btn', variant='primary')

    def on_mount(self) -> None:
        """載入設定"""
        self.query_one('#jira-host', Input).value = self.config.host
        self.query_one('#jira-user', Input).value = self.config.user
        self.query_one('#jira-token', Input).value = self.config.token

    def on_input_changed(self, event: Input.Changed) -> None:
        """輸入變更時更新設定（不儲存）"""
        if event.input.id == 'jira-host':
            self.config.host = event.value
        elif event.input.id == 'jira-user':
            self.config.user = event.value
        elif event.input.id == 'jira-token':
            self.config.token = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """按鈕點擊事件"""
        if event.button.id == 'verify-btn':
            self.verify_connection()

    def verify_connection(self, *, silent: bool = False) -> bool:
        """驗證 Jira API 連線"""
        client = self._get_jira_client(silent=silent)
        if not client:
            return False

        try:
            data = client.get_myself()
            self.app.myself = data  # pyright: ignore[reportAttributeAccessIssue]
            self.update_status(success=True, myself=data)
            if not silent:
                self.app.notify(f'連線成功: {data.get("displayName", client.user)}', severity='information', timeout=2)
            # 驗證成功後載入 issues 和 users
            self._start_loading_issues(data)
            return True
        except httpx.HTTPStatusError as e:
            self.update_status(success=False, error=f'HTTP {e.response.status_code}')
            if not silent:
                self.app.notify(f'連線失敗: HTTP {e.response.status_code}', severity='error')
            return False
        except httpx.RequestError as e:
            self.update_status(success=False, error=str(e))
            if not silent:
                self.app.notify(f'連線錯誤: {e}', severity='error')
            return False

    def _start_loading_issues(self, myself: dict) -> None:
        """開始載入 issues 和 users"""
        from .my_issues import MyIssuesTab

        display_name = myself.get('displayName', 'Current User')
        my_issues_tab = self.app.query_one(MyIssuesTab)
        my_issues_tab._current_user_display = display_name
        my_issues_tab._selected_display = display_name
        my_issues_tab._update_assignee_display()
        my_issues_tab._load_users()
        # 載入完成後切換 tab
        my_issues_tab.run_search(switch_tab=True)

    def update_status(
        self,
        *,
        success: bool,
        myself: dict | None = None,
        error: str = '',
    ) -> None:
        """更新連線狀態顯示"""
        status = self.query_one('#api-status', Static)
        if success and myself:
            lines = [f'✓ 連線成功: {myself.get("displayName", "")}']
            if email := myself.get('emailAddress'):
                lines.append(f'  Email: {email}')
            if account_id := myself.get('accountId'):
                lines.append(f'  Account ID: {account_id}')
            if account_type := myself.get('accountType'):
                lines.append(f'  Account Type: {account_type}')
            if timezone := myself.get('timeZone'):
                lines.append(f'  Time Zone: {timezone}')
            if locale := myself.get('locale'):
                lines.append(f'  Locale: {locale}')
            if myself.get('active') is not None:
                lines.append(f'  Active: {myself["active"]}')
            if groups := myself.get('groups'):
                lines.append(f'  Groups: {groups.get("size", 0)}')
            if roles := myself.get('applicationRoles'):
                lines.append(f'  Application Roles: {roles.get("size", 0)}')
            status.update('\n'.join(lines))
            status.set_classes('success')
            self.app.notify('正在載入個人 Issues, 完成後將自動跳轉 ...', timeout=5)
        else:
            status.update(f'✗ 連線失敗: {error}')
            status.set_classes('error')
