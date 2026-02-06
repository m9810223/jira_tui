"""日期編輯控制器"""

from dataclasses import dataclass
from datetime import timedelta
import typing as t

from ..renderers.timeline import TimelineRenderer


if t.TYPE_CHECKING:
    from textual.widgets.tree import TreeNode

    from ..widgets.tree import JiraNodeData
    from ..widgets.tree import JiraNodeType


@dataclass
class DateEditState:
    """日期編輯狀態"""

    mode: str  # 'start' | 'due'
    cursor_day: int
    node: 'TreeNode[JiraNodeData]'


class DateEditController:
    """管理日期編輯的狀態機"""

    def __init__(self, *, timeline: TimelineRenderer):
        self._timeline = timeline
        self._state: DateEditState | None = None

    @property
    def is_active(self) -> bool:
        return self._state is not None

    @property
    def current_node(self) -> 'TreeNode[JiraNodeData] | None':
        return self._state.node if self._state else None

    @property
    def mode(self) -> str | None:
        return self._state.mode if self._state else None

    @property
    def cursor_day(self) -> int:
        return self._state.cursor_day if self._state else 0

    def start(
        self,
        *,
        mode: str,
        node: 'TreeNode[JiraNodeData]',
        scroll_offset: int,
        allowed_types: tuple['JiraNodeType', ...],
    ) -> bool:
        """開始編輯模式，回傳是否成功"""
        data = node.data
        if data is None or data.issue is None:
            return False
        if data.node_type not in allowed_types:
            return False

        # 計算游標初始位置
        base_date = self._timeline.get_base_date()
        if mode == 'start' and data.issue.fields.start_date:
            target = data.issue.fields.start_date.replace(tzinfo=None)
        elif mode == 'due' and data.issue.fields.duedate:
            target = data.issue.fields.duedate.replace(tzinfo=None)
        else:
            target = self._timeline.get_today()

        days_from_base = (target - base_date).days - scroll_offset
        cursor_day = max(0, min(self._timeline.visible_days - 1, days_from_base))

        self._state = DateEditState(mode=mode, cursor_day=cursor_day, node=node)
        return True

    def cancel(self) -> None:
        """取消編輯模式"""
        self._state = None

    def cursor_left(self) -> bool:
        """編輯游標左移，回傳是否有移動"""
        if not self._state:
            return False
        if self._state.cursor_day > 0:
            self._state.cursor_day -= 1
            return True
        return False

    def cursor_right(self) -> bool:
        """編輯游標右移，回傳是否有移動"""
        if not self._state:
            return False
        if self._state.cursor_day < self._timeline.visible_days - 1:
            self._state.cursor_day += 1
            return True
        return False

    def confirm(self, scroll_offset: int) -> tuple[str, str, str | None] | None:
        """確認編輯，回傳 (issue_key, field, date_str) 或 None"""
        if not self._state:
            return None

        data = self._state.node.data
        if not data or not data.issue:
            return None

        # 計算選擇的日期
        base_date = self._timeline.get_base_date()
        selected_date = base_date + timedelta(days=scroll_offset + self._state.cursor_day)

        issue_key = data.issue.key
        field = 'start_date' if self._state.mode == 'start' else 'duedate'
        date_str = selected_date.strftime('%Y-%m-%d')

        # 更新本地資料
        if self._state.mode == 'start':
            data.issue.fields.start_date = selected_date
        else:
            data.issue.fields.duedate = selected_date

        self._state = None
        return (issue_key, field, date_str)

    def clear(self) -> tuple[str, str] | None:
        """清除日期，回傳 (issue_key, field) 或 None"""
        if not self._state:
            return None

        data = self._state.node.data
        if not data or not data.issue:
            return None

        issue_key = data.issue.key
        field = 'start_date' if self._state.mode == 'start' else 'duedate'

        # 更新本地資料
        if self._state.mode == 'start':
            data.issue.fields.start_date = None
        else:
            data.issue.fields.duedate = None

        self._state = None
        return (issue_key, field)
