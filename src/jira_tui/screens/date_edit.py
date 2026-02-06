# ruff: noqa: DTZ007
"""日期編輯對話框"""

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label


class DateEditModal(ModalScreen[str | None]):
    """日期編輯對話框"""

    DEFAULT_CSS = """
    DateEditModal {
        align: center middle;
    }

    #date-edit-dialog {
        width: 40;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #date-edit-dialog Label {
        margin-bottom: 1;
    }

    #date-edit-dialog Input {
        margin-bottom: 1;
    }

    #date-edit-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #date-edit-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ('escape', 'cancel', '取消'),
    ]

    def __init__(
        self,
        *,
        issue_key: str,
        field_name: str,
        field_label: str,
        current_value: datetime | None,
    ):
        super().__init__()
        self._issue_key = issue_key
        self._field_name = field_name
        self._field_label = field_label
        self._current_value = current_value

    def compose(self) -> ComposeResult:
        with Vertical(id='date-edit-dialog'):
            yield Label(f'編輯 {self._issue_key} 的 {self._field_label}')
            current_str = self._current_value.strftime('%Y-%m-%d') if self._current_value else ''
            yield Input(value=current_str, placeholder='YYYY-MM-DD', id='date-input')
            yield Label('格式: YYYY-MM-DD (留空清除)', classes='hint')
            with Horizontal(id='date-edit-buttons'):
                yield Button('確認', id='confirm-btn', variant='primary')
                yield Button('取消', id='cancel-btn', variant='default')

    def on_mount(self) -> None:
        self.query_one('#date-input', Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'confirm-btn':
            self._confirm()
        elif event.button.id == 'cancel-btn':
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'date-input':
            self._confirm()

    def _confirm(self) -> None:
        value = self.query_one('#date-input', Input).value.strip()
        if not value:
            # 空值表示清除日期
            self.dismiss('')
            return

        # 驗證日期格式
        try:
            datetime.strptime(value, '%Y-%m-%d')
            self.dismiss(value)
        except ValueError:
            self.app.notify('日期格式錯誤，請使用 YYYY-MM-DD', severity='error')

    def action_cancel(self) -> None:
        self.dismiss(None)
