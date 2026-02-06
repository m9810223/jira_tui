"""Status 編輯對話框"""

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..models import JiraTransition


@dataclass
class StatusEditResult:
    """Status 編輯結果"""

    transition_id: str
    new_status_name: str


class StatusEditModal(ModalScreen[StatusEditResult | None]):
    """Status 編輯對話框"""

    DEFAULT_CSS = """
    StatusEditModal {
        align: center middle;
    }

    #status-edit-dialog {
        width: 50;
        height: auto;
        max-height: 20;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #status-edit-dialog Label {
        margin-bottom: 1;
    }

    #status-edit-dialog OptionList {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }

    #status-edit-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #status-edit-buttons Button {
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
        current_status: str,
        transitions: list[JiraTransition],
    ):
        super().__init__()
        self._issue_key = issue_key
        self._current_status = current_status
        self._transitions = transitions

    def compose(self) -> ComposeResult:
        with Vertical(id='status-edit-dialog'):
            yield Label(f'變更 {self._issue_key} 的狀態')
            yield Label(f'目前: {self._current_status}', classes='hint')
            option_list = OptionList(id='transition-list')
            for t in self._transitions:
                option_list.add_option(Option(f'{t.name} → {t.to.name}', id=t.id))
            yield option_list
            with Horizontal(id='status-edit-buttons'):
                yield Button('確認', id='confirm-btn', variant='primary')
                yield Button('取消', id='cancel-btn', variant='default')

    def on_mount(self) -> None:
        option_list = self.query_one('#transition-list', OptionList)
        option_list.focus()
        if self._transitions:
            option_list.highlighted = 0

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'confirm-btn':
            self._confirm()
        elif event.button.id == 'cancel-btn':
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """雙擊選項時直接確認"""
        self._confirm()

    def _confirm(self) -> None:
        option_list = self.query_one('#transition-list', OptionList)
        if option_list.highlighted is None:
            self.app.notify('請選擇一個狀態', severity='warning')
            return

        selected_idx = option_list.highlighted
        if selected_idx < 0 or selected_idx >= len(self._transitions):
            return

        transition = self._transitions[selected_idx]
        result = StatusEditResult(
            transition_id=transition.id,
            new_status_name=transition.to.name,
        )
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)
