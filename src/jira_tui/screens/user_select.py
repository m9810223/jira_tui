"""使用者選擇對話框"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..models import JiraUser


class UserSelectScreen(ModalScreen[tuple[str | None, str] | None]):
    """使用者選擇對話框"""

    CSS = """
    UserSelectScreen {
        align: center middle;
    }

    #user-select-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #user-select-dialog Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #user-select-filter {
        margin-bottom: 1;
    }

    #user-select-list {
        height: 15;
        margin-bottom: 1;
    }

    #user-select-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #user-select-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ('escape', 'cancel', '取消'),
    ]

    def __init__(
        self,
        *,
        users: list[JiraUser],
        current_user_display: str,
    ):
        super().__init__()
        self._users = users
        self._current_user_display = current_user_display

    def compose(self) -> ComposeResult:
        with Vertical(id='user-select-dialog'):
            yield Label('選擇 Assignee')
            yield Input(placeholder='過濾使用者...', id='user-select-filter')
            yield OptionList(id='user-select-list')
            with Horizontal(id='user-select-buttons'):
                yield Button('取消', id='cancel-btn', variant='default')

    def on_mount(self) -> None:
        self._update_list('')

    def _update_list(self, filter_text: str) -> None:
        """更新使用者列表"""
        user_list = self.query_one('#user-select-list', OptionList)
        user_list.clear_options()

        # 當前使用者選項
        current_label = f'{self._current_user_display} (me)'
        user_list.add_option(Option(current_label, id='__current_user__'))

        # 過濾並按顯示名稱排序
        filter_lower = filter_text.lower()
        filtered_users = [
            user for user in self._users
            if not filter_text or filter_lower in user.display_name.lower()
        ]
        filtered_users.sort(key=lambda u: u.display_name.lower())

        for user in filtered_users:
            user_list.add_option(Option(user.display_name, id=user.account_id))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == 'user-select-filter':
            self._update_list(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == 'user-select-list':
            option_id = event.option.id
            if option_id == '__current_user__':
                self.dismiss((None, self._current_user_display))
            else:
                self.dismiss((str(option_id), str(event.option.prompt)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'cancel-btn':
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
