"""Story Points 編輯對話框"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label


class SPEditModal(ModalScreen[float | None]):
    """Story Points 編輯對話框"""

    DEFAULT_CSS = """
    SPEditModal {
        align: center middle;
    }

    #sp-edit-dialog {
        width: 40;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #sp-edit-dialog Label {
        margin-bottom: 1;
    }

    #sp-edit-dialog Input {
        margin-bottom: 1;
    }

    #sp-edit-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #sp-edit-buttons Button {
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
        current_value: float | None,
    ):
        super().__init__()
        self._issue_key = issue_key
        self._current_value = current_value

    def compose(self) -> ComposeResult:
        with Vertical(id='sp-edit-dialog'):
            yield Label(f'編輯 {self._issue_key} 的 Story Points')
            current_str = str(self._current_value) if self._current_value is not None else ''
            yield Input(value=current_str, placeholder='例如: 3, 0.5, 1.5', id='sp-input')
            yield Label('輸入數字 (留空清除)', classes='hint')
            with Horizontal(id='sp-edit-buttons'):
                yield Button('確認', id='confirm-btn', variant='primary')
                yield Button('取消', id='cancel-btn', variant='default')

    def on_mount(self) -> None:
        self.query_one('#sp-input', Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'confirm-btn':
            self._confirm()
        elif event.button.id == 'cancel-btn':
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'sp-input':
            self._confirm()

    def _confirm(self) -> None:
        value = self.query_one('#sp-input', Input).value.strip()
        if not value:
            # 空值表示清除
            self.dismiss(0.0)  # 用 0.0 表示清除
            return

        # 驗證數字格式
        try:
            sp_value = float(value)
            if sp_value < 0:
                self.app.notify('Story Points 不能為負數', severity='error')
                return
            self.dismiss(sp_value)
        except ValueError:
            self.app.notify('請輸入有效的數字', severity='error')

    def action_cancel(self) -> None:
        self.dismiss(None)
