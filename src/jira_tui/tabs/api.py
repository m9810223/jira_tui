"""API 設定分頁"""

import httpx
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Static

from ..auth import Profile
from ..auth import ProfileStore
from ..config import JiraClient
from ..config import load_config
from ..widgets.inputs import BlurInput
from ._mixin import JiraClientMixin


class _SaveProfileModal(ModalScreen[str | None]):
    """輸入 Profile 名稱的小型 Modal"""

    DEFAULT_CSS = """
    _SaveProfileModal {
        align: center middle;
    }

    #profile-name-dialog {
        width: 44;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #profile-name-dialog Label {
        margin-bottom: 1;
    }

    #profile-name-dialog Input {
        margin-bottom: 1;
    }

    #profile-name-hint {
        color: $text-muted;
        margin-bottom: 1;
    }

    #profile-name-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #profile-name-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [Binding('escape', 'cancel', '取消')]

    def __init__(self, *, default_name: str = ''):
        super().__init__()
        self._default_name = default_name

    def compose(self) -> ComposeResult:
        with Vertical(id='profile-name-dialog'):
            yield Label('另存為 Profile')
            yield Input(
                value=self._default_name,
                placeholder='例如：work、personal',
                id='profile-name-input',
            )
            yield Static(
                '輸入名稱後儲存目前的 Host / User / Token', id='profile-name-hint'
            )
            with Horizontal(id='profile-name-buttons'):
                yield Button('儲存', id='save-profile-confirm', variant='primary')
                yield Button('取消', id='save-profile-cancel', variant='default')

    def on_mount(self) -> None:
        self.query_one('#profile-name-input', Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'save-profile-confirm':
            self._confirm()
        elif event.button.id == 'save-profile-cancel':
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'profile-name-input':
            self._confirm()

    def _confirm(self) -> None:
        name = self.query_one('#profile-name-input', Input).value.strip()
        if not name:
            self.app.notify('請輸入 Profile 名稱', severity='error')
            return
        self.dismiss(name)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ApiTab(JiraClientMixin, Vertical):
    """API 設定分頁"""

    def compose(self) -> ComposeResult:
        with Horizontal(id='profile-bar'):
            pass  # 由 _refresh_profile_bar() 動態填入
        yield Static('歡迎使用 Jira Dashboard')
        with Vertical(id='config-form'):
            yield Label('Jira Host')
            yield BlurInput(placeholder='https://your-domain.atlassian.net', id='jira-host')
            yield Label('User (Email)')
            yield BlurInput(placeholder='your-email@example.com', id='jira-user')
            yield Label('API Token ([@click=app.open_link("https://id.atlassian.com/manage-profile/security/api-tokens")]建立 Token[/])', markup=True)
            yield BlurInput(placeholder='API Token', password=True, id='jira-token')
            yield Static('', id='api-status')
            with Horizontal(id='api-buttons'):
                yield Button('驗證連線', id='verify-btn', variant='primary')
                yield Button(
                    '另存為 Profile...', id='save-profile-btn', variant='default'
                )

    def on_mount(self) -> None:
        """載入設定"""
        self.query_one('#jira-host', Input).value = self.config.host
        self.query_one('#jira-user', Input).value = self.config.user
        self.query_one('#jira-token', Input).value = self.config.token
        self._refresh_profile_bar()

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
        elif event.button.id == 'save-profile-btn':
            self._open_save_profile_modal()
        elif event.button.id and event.button.id.startswith('switch-profile-'):
            name = event.button.id.removeprefix('switch-profile-')
            self._switch_to_profile(name)

    def _refresh_profile_bar(self) -> None:
        """重新建立 profile 切換列"""
        bar = self.query_one('#profile-bar', Horizontal)
        profiles = ProfileStore.list_profiles()
        active = ProfileStore.get_active_name()
        if len(profiles) <= 1:
            bar.add_class('hidden')
            return
        bar.remove_class('hidden')
        bar.remove_children()
        for name in profiles:
            bar.mount(Label(name, classes='profile-bar-name'))
            if name == active:
                bar.mount(
                    Button('● 使用中', disabled=True, classes='profile-active-btn')
                )
            else:
                bar.mount(
                    Button(
                        '切換',
                        id=f'switch-profile-{name}',
                        classes='profile-switch-btn',
                    )
                )

    def _switch_to_profile(self, name: str) -> None:
        """切換至指定 profile 並自動重新連線"""
        ProfileStore.switch(name)
        self.app.config = load_config()
        self.query_one('#jira-host', Input).value = self.app.config.host
        self.query_one('#jira-user', Input).value = self.app.config.user
        self.query_one('#jira-token', Input).value = self.app.config.token
        self._refresh_profile_bar()
        self._do_switch_verify()

    @work(thread=True)
    def _do_switch_verify(self) -> None:
        """切換 profile 後在背景重新驗證連線"""
        self.verify_connection(silent=True)

    def _open_save_profile_modal(self) -> None:
        """開啟另存 Profile 的 Modal"""
        # 先檢查欄位是否完整
        host = self.query_one('#jira-host', Input).value.strip()
        user = self.query_one('#jira-user', Input).value.strip()
        token = self.query_one('#jira-token', Input).value.strip()
        if not all([host, user, token]):
            self.app.notify('請先填寫完整的 Host、User 與 Token', severity='warning')
            return

        # 以目前 active profile 名稱作為預設值
        default_name = ProfileStore.get_active_name() or ''
        self.app.push_screen(
            _SaveProfileModal(default_name=default_name),
            self._on_profile_name_chosen,
        )

    def _on_profile_name_chosen(self, name: str | None) -> None:
        """收到 profile 名稱後執行驗證並儲存"""
        if not name:
            return
        host = self.query_one('#jira-host', Input).value.strip().rstrip('/')
        user = self.query_one('#jira-user', Input).value.strip()
        token = self.query_one('#jira-token', Input).value.strip()
        self._verify_and_save_profile(name, host, user, token)

    def _verify_and_save_profile(
        self, name: str, host: str, user: str, token: str
    ) -> None:
        """驗證連線後儲存 profile（觸發背景 worker）"""
        self._do_verify_and_save(name, host, user, token)

    @work(thread=True)
    def _do_verify_and_save(self, name: str, host: str, user: str, token: str) -> None:
        """背景執行驗證並儲存 profile"""
        try:
            client = JiraClient(host=host, user=user, token=token)
            myself = client.get_myself()
            display_name = myself.get('displayName', user)
            profile = Profile(
                name=name, host=host, user=user, token=token, jql=self.config.jql
            )
            ProfileStore.add_or_update(profile, set_active=True)
            # 更新 app config（在主線程設定）
            self.app.call_from_thread(self._apply_profile_to_config, host, user, token)
            self.app.call_from_thread(
                self.app.notify,
                f'Profile "{name}" 已儲存（{display_name}）',
                severity='information',
                timeout=3,
            )
        except httpx.HTTPStatusError as e:
            self.app.call_from_thread(
                self.app.notify,
                f'驗證失敗：HTTP {e.response.status_code}，Profile 未儲存',
                severity='error',
            )
        except httpx.RequestError as e:
            self.app.call_from_thread(
                self.app.notify,
                f'連線錯誤：{e}，Profile 未儲存',
                severity='error',
            )
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify,
                f'儲存失敗：{e}',
                severity='error',
            )

    def _apply_profile_to_config(self, host: str, user: str, token: str) -> None:
        """在主線程更新 config"""
        self.config.host = host
        self.config.user = user
        self.config.token = token

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
