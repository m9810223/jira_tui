"""首次設定 / 帳號設定全螢幕 Screen"""

from __future__ import annotations

import httpx
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Static

from ..auth import Profile
from ..auth import ProfileStore
from ..config import JiraClient


class SetupScreen(Screen[Profile | None]):
    """首次設定全螢幕 — 讓使用者填入 Jira 帳號資訊並驗證後儲存

    dismiss 時：
    - 回傳 Profile 物件表示成功儲存並設為 active
    - 回傳 None 表示使用者略過
    """

    BINDINGS = [
        Binding("escape", "skip", "略過"),
    ]

    DEFAULT_CSS = """
    SetupScreen {
        align: center middle;
        background: $background 80%;
    }

    #setup-container {
        width: 60;
        height: auto;
        padding: 2 3;
        border: solid $primary;
        background: $surface;
    }

    #setup-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #setup-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    .setup-label {
        margin-top: 1;
        color: $text;
    }

    .setup-input {
        margin-bottom: 0;
        border: solid $primary-darken-2;
    }

    .setup-input:focus {
        border: solid $primary;
    }

    #setup-status {
        margin-top: 1;
        height: auto;
        text-align: center;
    }

    #setup-status.success {
        color: $success;
    }

    #setup-status.error {
        color: $error;
    }

    #setup-status.info {
        color: $warning;
    }

    #setup-buttons {
        margin-top: 2;
        height: auto;
        align: center middle;
        layout: horizontal;
    }

    #save-btn {
        margin-right: 2;
    }

    #skip-btn {
        background: $surface-darken-1;
    }
    """

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="setup-container"):
                yield Static("Jira TUI 帳號設定", id="setup-title")
                yield Static("請填入 Jira 帳號資訊以開始使用", id="setup-subtitle")

                yield Label("Profile 名稱", classes="setup-label")
                yield Input(
                    value="default",
                    placeholder="例如：work、personal",
                    id="setup-profile-name",
                    classes="setup-input",
                )

                yield Label("Jira Host", classes="setup-label")
                yield Input(
                    placeholder="https://your-domain.atlassian.net",
                    id="setup-host",
                    classes="setup-input",
                )

                yield Label("User (Email)", classes="setup-label")
                yield Input(
                    placeholder="your-email@example.com",
                    id="setup-user",
                    classes="setup-input",
                )

                yield Label(
                    'API Token ([@click=app.open_link("https://id.atlassian.com/manage-profile/security/api-tokens")]建立 Token[/])',
                    markup=True,
                    classes="setup-label",
                )
                yield Input(
                    placeholder="API Token",
                    password=True,
                    id="setup-token",
                    classes="setup-input",
                )

                yield Label("預設 JQL（選填）", classes="setup-label")
                yield Input(
                    placeholder="assignee = currentUser() ORDER BY updated DESC",
                    id="setup-jql",
                    classes="setup-input",
                )

                yield Static("", id="setup-status")

                with Vertical(id="setup-buttons"):
                    yield Button("驗證並儲存", id="save-btn", variant="primary")
                    yield Button("略過", id="skip-btn", variant="default")

    def on_mount(self) -> None:
        """聚焦第一個輸入框"""
        self.query_one("#setup-host", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._do_save()
        elif event.button.id == "skip-btn":
            self.action_skip()

    def action_skip(self) -> None:
        """略過設定，回傳 None"""
        self.dismiss(None)

    def _get_status(self) -> Static:
        return self.query_one("#setup-status", Static)

    def _set_status(self, msg: str, kind: str = "info") -> None:
        """更新狀態文字，kind: 'info' | 'success' | 'error'"""
        status = self._get_status()
        status.update(msg)
        status.set_classes(kind)

    def _get_inputs(self) -> tuple[str, str, str, str, str]:
        """取得所有欄位值"""
        name = self.query_one("#setup-profile-name", Input).value.strip()
        host = self.query_one("#setup-host", Input).value.strip().rstrip("/")
        user = self.query_one("#setup-user", Input).value.strip()
        token = self.query_one("#setup-token", Input).value.strip()
        jql = self.query_one("#setup-jql", Input).value.strip()
        return name, host, user, token, jql

    def _do_save(self) -> None:
        """驗證欄位並啟動背景驗證"""
        name, host, user, token, jql = self._get_inputs()

        # 欄位驗證
        if not name:
            self._set_status("請輸入 Profile 名稱", "error")
            self.query_one("#setup-profile-name", Input).focus()
            return
        if not host:
            self._set_status("請輸入 Jira Host", "error")
            self.query_one("#setup-host", Input).focus()
            return
        if not host.startswith("http"):
            self._set_status("Host 格式錯誤，請以 https:// 開頭", "error")
            self.query_one("#setup-host", Input).focus()
            return
        if not user:
            self._set_status("請輸入 Email", "error")
            self.query_one("#setup-user", Input).focus()
            return
        if not token:
            self._set_status("請輸入 API Token", "error")
            self.query_one("#setup-token", Input).focus()
            return

        self._set_status("驗證中...", "info")
        self.query_one("#save-btn", Button).disabled = True
        self._verify_and_save(name, host, user, token, jql)

    @work(thread=True)
    def _verify_and_save(
        self,
        name: str,
        host: str,
        user: str,
        token: str,
        jql: str,
    ) -> None:
        """背景執行驗證，成功後儲存並 dismiss"""
        try:
            client = JiraClient(host=host, user=user, token=token)
            myself = client.get_myself()
            display_name = myself.get("displayName", user)

            profile = Profile(name=name, host=host, user=user, token=token, jql=jql)
            ProfileStore.add_or_update(profile, set_active=True)

            self.app.call_from_thread(
                self._on_verify_success,
                profile,
                display_name,
            )
        except httpx.HTTPStatusError as e:
            self.app.call_from_thread(
                self._on_verify_error,
                f"驗證失敗：HTTP {e.response.status_code}，請確認 Token 是否正確",
            )
        except httpx.RequestError as e:
            self.app.call_from_thread(
                self._on_verify_error,
                f"連線錯誤：{e}，請確認 Host 是否正確",
            )
        except Exception as e:
            self.app.call_from_thread(self._on_verify_error, f"未預期錯誤：{e}")

    def _on_verify_success(self, profile: Profile, display_name: str) -> None:
        """驗證成功的 UI 更新，然後 dismiss"""
        self._set_status(f"驗證成功！歡迎，{display_name}", "success")
        self.query_one("#save-btn", Button).disabled = False
        # 短暫顯示成功訊息後 dismiss
        self.set_timer(0.8, lambda: self.dismiss(profile))

    def _on_verify_error(self, msg: str) -> None:
        """驗證失敗的 UI 更新"""
        self._set_status(msg, "error")
        self.query_one("#save-btn", Button).disabled = False
