"""移動節點控制器"""

from dataclasses import dataclass
import typing as t


if t.TYPE_CHECKING:
    from textual.widgets.tree import TreeNode

    from ..widgets.tree import JiraNodeData
    from ..widgets.tree import JiraNodeType


@dataclass
class MoveState:
    """移動狀態"""

    source_node: 'TreeNode[JiraNodeData]'


class MoveController:
    """管理節點移動的狀態機"""

    def __init__(self):
        self._state: MoveState | None = None

    @property
    def is_active(self) -> bool:
        return self._state is not None

    @property
    def source_node(self) -> 'TreeNode[JiraNodeData] | None':
        return self._state.source_node if self._state else None

    def mark(self, node: 'TreeNode[JiraNodeData]', allowed_type: 'JiraNodeType') -> bool:
        """標記 node 準備移動，回傳是否成功"""
        data = node.data
        if not data or not data.issue:
            return False
        if data.node_type != allowed_type:
            return False

        self._state = MoveState(source_node=node)
        return True

    def cancel(self) -> None:
        """取消移動模式"""
        self._state = None

    def validate_target(self, target: 'TreeNode[JiraNodeData]') -> str | None:
        """驗證目標節點，回傳錯誤訊息或 None（表示有效）"""
        if not self._state:
            return '不在移動模式中'

        source = self._state.source_node
        target_data = target.data

        if not target_data or not target_data.issue:
            return '目標不是有效的 issue'

        if source is target:
            return '不能移動到自己'

        if source.parent != target.parent:
            return '只能在同一層級內移動'

        return None

    def confirm(
        self,
        target: 'TreeNode[JiraNodeData]',
    ) -> tuple[str, str | None, str | None] | None:
        """確認移動，回傳 (issue_key, rank_before, rank_after) 或 None"""
        if not self._state:
            return None

        source = self._state.source_node
        source_data = source.data
        target_data = target.data

        if not source_data or not source_data.issue:
            return None
        if not target_data or not target_data.issue:
            return None

        parent = target.parent
        if parent is None:
            return None

        children = list(parent._children)
        try:
            source_idx = children.index(source)
            target_idx = children.index(target)
        except ValueError:
            return None

        source_key = source_data.issue.key
        target_key = target_data.issue.key

        if source_idx < target_idx:
            # 向下移動：排在目標之後
            rank_before = None
            rank_after = target_key
        else:
            # 向上移動：排在目標之前
            rank_before = target_key
            rank_after = None

        self._state = None
        return (source_key, rank_before, rank_after)
