"""Time Original Estimate 編輯對話框"""

import re

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label


class TimeEstimateEditModal(ModalScreen[int | None]):
    """Time Original Estimate 編輯對話框"""

    DEFAULT_CSS = """
    TimeEstimateEditModal {
        align: center middle;
    }

    #time-edit-dialog {
        width: 45;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #time-edit-dialog Label {
        margin-bottom: 1;
    }

    #time-edit-dialog Input {
        margin-bottom: 1;
    }

    #time-edit-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #time-edit-buttons Button {
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
        current_seconds: int | None,
    ):
        super().__init__()
        self._issue_key = issue_key
        self._current_seconds = current_seconds

    def compose(self) -> ComposeResult:
        with Vertical(id='time-edit-dialog'):
            yield Label(f'編輯 {self._issue_key} 的 Time Original Estimate')
            current_str = self._format_seconds(self._current_seconds) if self._current_seconds else ''
            yield Input(value=current_str, placeholder='例如: 1d, 2h, 30m, 1d2h30m', id='time-input')
            yield Label('格式: Xd Xh Xm (1d=8h, 留空清除)', classes='hint')
            with Horizontal(id='time-edit-buttons'):
                yield Button('確認', id='confirm-btn', variant='primary')
                yield Button('取消', id='cancel-btn', variant='default')

    def on_mount(self) -> None:
        self.query_one('#time-input', Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'confirm-btn':
            self._confirm()
        elif event.button.id == 'cancel-btn':
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'time-input':
            self._confirm()

    def _confirm(self) -> None:
        value = self.query_one('#time-input', Input).value.strip()
        if not value:
            # 空值表示清除
            self.dismiss(0)  # 用 0 表示清除
            return

        # 解析時間格式
        seconds = self._parse_time(value)
        if seconds is None:
            self.app.notify('格式錯誤，請使用 Xd Xh Xm 格式', severity='error')
            return
        self.dismiss(seconds)

    def _parse_time(self, value: str) -> int | None:
        """解析時間字串為秒數 (1d=8h)"""
        value = value.lower().replace(' ', '')
        total_seconds = 0
        # 匹配 d, h, m
        pattern = r'(\d+)([dhm])'
        matches = re.findall(pattern, value)
        if not matches:
            # 嘗試純數字（當作小時）
            try:
                hours = float(value)
                return int(hours * 3600)
            except ValueError:
                return None
        for num_str, unit in matches:
            num = int(num_str)
            if unit == 'd':
                total_seconds += num * 8 * 3600  # 1d = 8h
            elif unit == 'h':
                total_seconds += num * 3600
            elif unit == 'm':
                total_seconds += num * 60
        return total_seconds if total_seconds > 0 else None

    def _format_seconds(self, seconds: int) -> str:
        """將秒數轉換成 XdXhXm 格式"""
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
        return ''.join(parts) if parts else ''

    def action_cancel(self) -> None:
        self.dismiss(None)
