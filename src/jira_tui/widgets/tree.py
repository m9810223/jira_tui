"""JiraTree Widget"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from enum import auto
from zoneinfo import ZoneInfo

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ..controllers.date_edit import DateEditController
from ..controllers.move import MoveController
from ..models import JiraIssue
from ..models import JiraSprint
from ..screens.worklog_editor import WorklogDeleteResult
from ..screens.worklog_editor import WorklogEditorModal
from ..screens.worklog_editor import WorklogEditorResult
from ..renderers.issue_row import IssueRowRenderer
from ..renderers.layout import TreeLayout
from ..renderers.timeline import TimelineRenderer
from ..worklog import clamp_remaining_estimate


class JiraNodeType(Enum):
    """JiraTree 節點類型"""
    PROJECT = auto()
    EPIC_GROUP = auto()
    EXTERNAL_EPIC = auto()  # 不在查詢結果中的 Epic
    SPRINT = auto()
    PAST_SPRINTS = auto()
    NO_SPRINT = auto()
    ISSUE = auto()


@dataclass
class JiraNodeData:
    """JiraTree 節點資料"""
    node_type: JiraNodeType
    issue: JiraIssue | None = None
    sprint: JiraSprint | None = None
    project_key: str = ''
    title: str = ''
    summary: str = ''  # 用於 EXTERNAL_EPIC
    count: int = 0


class _ProjectData:
    """Project 資料處理 - 支援 Epic 分組和 Sprint 分組（同一 issue 可能重複出現）"""

    def __init__(
        self,
        issues: list[JiraIssue],
        *,
        external_parents: list[JiraIssue] | None = None,
    ):
        # 過濾掉 Subtask（Subtask 會在其 parent 下顯示）
        self.all_issues = [i for i in issues if not self._is_subtask(i)]
        self.subtask_map = self._build_subtask_map(issues)

        # 外部 parent（不在查詢結果中但被引用的 parent）
        external_parents = external_parents or []
        self.external_parent_map: dict[str, JiraIssue] = {p.key: p for p in external_parents}

        # Epic 分組
        self.epics: list[JiraIssue] = []
        self.epic_children: dict[str, list[JiraIssue]] = {}  # epic_key -> children
        self.no_epic_issues: list[JiraIssue] = []
        self.external_epic_keys: set[str] = set()  # 不在查詢結果中的 Epic keys
        self.external_epics: list[JiraIssue] = []  # 外部 Epic (從 external_parents 篩選)
        self._classify_by_epic()

        # Sprint 分組（所有非 subtask 的 issues，不管有沒有 epic）
        self.sprints: dict[str, tuple[JiraSprint, list[JiraIssue]]] = {}
        self.no_sprint: list[JiraIssue] = []
        self.active_sprints: list[str] = []
        self.completed_sprints: list[str] = []
        self._classify_by_sprint()

        # 按 rank 排序所有 list
        self._sort_all_by_rank()

    def _is_subtask(self, issue: JiraIssue) -> bool:
        """判斷是否為 Subtask"""
        if not issue.fields.issuetype:
            return False
        return issue.fields.issuetype.name in ('Sub-task', 'Subtask')

    def _sort_by_rank(self, issues: list[JiraIssue]) -> list[JiraIssue]:
        """按 rank (customfield_10019) 排序"""
        return sorted(issues, key=lambda i: i.fields.rank or '')

    def _sort_all_by_rank(self) -> None:
        """對所有分類後的 list 按 rank 排序"""
        # Epic 分組（包含外部 Epic）
        all_epics = self.epics + self.external_epics
        all_epics = self._sort_by_rank(all_epics)
        self.epics = [e for e in all_epics if e.key not in self.external_epic_keys]
        self.external_epics = [e for e in all_epics if e.key in self.external_epic_keys]

        for key in self.epic_children:
            self.epic_children[key] = self._sort_by_rank(self.epic_children[key])
        self.no_epic_issues = self._sort_by_rank(self.no_epic_issues)

        # Sprint 分組
        for sprint_name in self.sprints:
            sprint_obj, issues = self.sprints[sprint_name]
            self.sprints[sprint_name] = (sprint_obj, self._sort_by_rank(issues))
        self.no_sprint = self._sort_by_rank(self.no_sprint)

        # Subtask map
        for key in self.subtask_map:
            self.subtask_map[key] = self._sort_by_rank(self.subtask_map[key])

    def _is_epic(self, issue: JiraIssue) -> bool:
        """判斷是否為 Epic"""
        if not issue.fields.issuetype:
            return False
        return issue.fields.issuetype.name == 'Epic'

    def _build_subtask_map(self, issues: list[JiraIssue]) -> dict[str, list[JiraIssue]]:
        """建立 parent_key -> subtasks 的對應"""
        subtask_map: dict[str, list[JiraIssue]] = {}
        for issue in issues:
            if self._is_subtask(issue) and issue.fields.parent:
                parent_key = issue.fields.parent.key
                if parent_key not in subtask_map:
                    subtask_map[parent_key] = []
                subtask_map[parent_key].append(issue)
        return subtask_map

    def _classify_by_epic(self) -> None:
        """按 Epic 分類"""
        epic_keys: set[str] = set()

        # 找出所有 Epic（查詢結果中的）
        for issue in self.all_issues:
            if self._is_epic(issue):
                self.epics.append(issue)
                epic_keys.add(issue.key)
                self.epic_children[issue.key] = []

        # 收集外部 Epic（parent 是 Epic 且不在查詢結果中）
        for issue in self.all_issues:
            if self._is_epic(issue):
                continue
            parent = issue.fields.parent
            if parent:
                parent_type = parent.fields.issuetype.name if parent.fields and parent.fields.issuetype else None
                if parent_type == 'Epic' and parent.key not in epic_keys:
                    # 如果這個 Epic 不在查詢結果中，記錄為外部 Epic
                    if parent.key not in self.epic_children:
                        self.external_epic_keys.add(parent.key)
                        self.epic_children[parent.key] = []
                        # 從 external_parent_map 取得完整資訊
                        if parent.key in self.external_parent_map:
                            self.external_epics.append(self.external_parent_map[parent.key])

        # 分類其他 issues
        for issue in self.all_issues:
            if self._is_epic(issue):
                continue

            # 檢查是否屬於某個 Epic
            parent = issue.fields.parent
            parent_key = parent.key if parent else None
            parent_type = parent.fields.issuetype.name if parent and parent.fields and parent.fields.issuetype else None

            if parent_key and parent_type == 'Epic':
                self.epic_children[parent_key].append(issue)
            else:
                self.no_epic_issues.append(issue)

    def _classify_by_sprint(self) -> None:
        """按 Sprint 分類（所有非 Subtask 的 issues）"""
        for issue in self.all_issues:
            if self._is_epic(issue):
                # Epic 本身不放在 Sprint 分組
                continue

            if issue.fields.sprint:
                sprint_obj = issue.fields.sprint[0]
                sprint_name = sprint_obj.name
                if sprint_name not in self.sprints:
                    self.sprints[sprint_name] = (sprint_obj, [])
                self.sprints[sprint_name][1].append(issue)
            else:
                self.no_sprint.append(issue)

        # 分類 active/completed sprints
        for sprint_name, (sprint_obj, _) in self.sprints.items():
            if sprint_obj.state == 'closed':
                self.completed_sprints.append(sprint_name)
            else:
                self.active_sprints.append(sprint_name)


class JiraTree(Tree[JiraNodeData]):
    """以 Tree 顯示 Jira Issues 的 Widget"""

    BINDINGS = [
        Binding('space', 'toggle_node', '展開/收合', show=False),
        Binding('ctrl+s', 'edit_dates_continuous', '連續編輯日期', show=False),
        Binding('l', 'add_worklog', 'Add Worklog'),
    ]

    DEFAULT_CSS = """
    JiraTree {
        scrollbar-gutter: stable;
    }
    """

    class UpdateIssueDate(Message):
        """請求更新 issue 日期的 Message"""

        def __init__(self, issue_key: str, field: str, date_str: str | None):
            self.issue_key = issue_key
            self.field = field  # 'start_date' | 'duedate'
            self.date_str = date_str
            super().__init__()

    class UpdateIssueSP(Message):
        """請求更新 issue Story Points 的 Message"""

        def __init__(self, issue_key: str, sp_value: float | None):
            self.issue_key = issue_key
            self.sp_value = sp_value
            super().__init__()

    class UpdateIssueTimeEstimate(Message):
        """請求更新 issue Time Estimate 的 Message"""

        def __init__(self, issue_key: str, seconds: int | None):
            self.issue_key = issue_key
            self.seconds = seconds
            super().__init__()

    class UpdateIssueRank(Message):
        """請求更新 issue rank 的 Message"""

        def __init__(self, issue_key: str, rank_before: str | None, rank_after: str | None):
            self.issue_key = issue_key
            self.rank_before = rank_before
            self.rank_after = rank_after
            super().__init__()

    class RequestTransitions(Message):
        """請求取得 issue transitions 的 Message"""

        def __init__(self, issue_key: str, current_status: str):
            self.issue_key = issue_key
            self.current_status = current_status
            super().__init__()

    class UpdateIssueStatus(Message):
        """請求更新 issue status 的 Message"""

        def __init__(self, issue_key: str, transition_id: str, new_status_name: str):
            self.issue_key = issue_key
            self.transition_id = transition_id
            self.new_status_name = new_status_name
            super().__init__()

    class AddIssueWorklog(Message):
        """請求新增 issue worklog。"""

        def __init__(
            self,
            issue_key: str,
            started: datetime,
            time_spent_seconds: int,
            comment_text: str,
            remaining_estimate_seconds: int | None,
        ):
            self.issue_key = issue_key
            self.started = started
            self.time_spent_seconds = time_spent_seconds
            self.comment_text = comment_text
            self.remaining_estimate_seconds = remaining_estimate_seconds
            super().__init__()

    def __init__(
        self,
        *,
        label: str = 'Jira Issues',
        layout: TreeLayout,
        timeline_width: int = 21,
        jira_host: str = '',
        show_root: bool = False,
        **kwargs,
    ):
        super().__init__(label, **kwargs)
        self.show_root = show_root
        self.guide_depth = layout.GUIDE_DEPTH
        self._layout = layout
        self._row_renderer = IssueRowRenderer(layout=layout, jira_host=jira_host)
        self._timeline = TimelineRenderer(width=timeline_width)
        self._scroll_offset = 0
        self._jira_host = jira_host
        # Controllers
        self._date_edit = DateEditController(timeline=self._timeline)
        self._move = MoveController()

    def load_issues(
        self,
        issues: list[JiraIssue],
        *,
        external_parents: list[JiraIssue] | None = None,
        group_by_project: bool = True,
    ) -> None:
        """載入 issues 到 tree"""
        # 重置 controllers
        self._date_edit.cancel()
        self._move.cancel()
        self.clear()
        external_parents = external_parents or []

        if group_by_project:
            # 按 project 分組
            projects: dict[str, list[JiraIssue]] = {}
            for issue in issues:
                project_key = issue.fields.project.key if issue.fields.project else 'Unknown'
                if project_key not in projects:
                    projects[project_key] = []
                projects[project_key].append(issue)

            # 外部 parent 按 project 分組
            external_by_project: dict[str, list[JiraIssue]] = {}
            for parent in external_parents:
                project_key = parent.fields.project.key if parent.fields.project else 'Unknown'
                if project_key not in external_by_project:
                    external_by_project[project_key] = []
                external_by_project[project_key].append(parent)

            for project_key in sorted(projects.keys()):
                project_issues = projects[project_key]
                project_external = external_by_project.get(project_key, [])
                self._add_project_node(project_key, project_issues, project_external)
        else:
            # 不分組，直接加入 issues
            for issue in issues:
                self._add_issue_node(self.root, issue)

    def _add_project_node(
        self,
        project_key: str,
        issues: list[JiraIssue],
        external_parents: list[JiraIssue] | None = None,
    ) -> None:
        """加入 Project 節點"""
        project_data = JiraNodeData(
            node_type=JiraNodeType.PROJECT,
            project_key=project_key,
            title=project_key,
            count=len(issues),
        )
        project_node = self.root.add(
            f'{project_key} ({len(issues)})',
            data=project_data,
            expand=True,
        )

        # 分類 issues
        data = _ProjectData(issues, external_parents=external_parents)

        # Level 2: Epics group (Epic 分組)
        if data.epics or data.no_epic_issues:
            self._add_epics_group_node(project_node, data)

        # Level 2: Completed Sprints group
        if data.completed_sprints:
            self._add_completed_sprints_group_node(project_node, data)

        # Level 2: Active Sprints group
        if data.active_sprints:
            self._add_active_sprints_group_node(project_node, data)

        # Level 2: No Sprint (Backlog)
        if data.no_sprint:
            self._add_no_sprint_node(project_node, data.no_sprint, data.subtask_map)

    def _add_epics_group_node(
        self,
        parent: TreeNode[JiraNodeData],
        data: _ProjectData,
    ) -> None:
        """加入 Epics 群組節點（包含所有 Epic 和 No Epic）"""
        # 計算總數
        total_count = len(data.epics) + len(data.external_epics) + len(data.no_epic_issues)
        epics_group_data = JiraNodeData(
            node_type=JiraNodeType.EPIC_GROUP,
            title='Epics',
            count=total_count,
        )
        epics_group_node = parent.add(
            f'Epics ({total_count})',
            data=epics_group_data,
            expand=False,
        )

        # 合併 epics 和 external_epics 並按 rank 排序
        all_epics = data.epics + data.external_epics
        all_epics_sorted = sorted(all_epics, key=lambda i: i.fields.rank or '')

        # 按排序後的順序加入 Epic 節點
        for epic in all_epics_sorted:
            is_external = epic.key in data.external_epic_keys
            children = data.epic_children.get(epic.key, [])
            if is_external:
                self._add_external_epic_node(epics_group_node, epic, children, data.subtask_map)
            else:
                self._add_epic_node(epics_group_node, epic, children, data.subtask_map)

        # 加入 No Epic
        if data.no_epic_issues:
            self._add_no_epic_node(epics_group_node, data.no_epic_issues, data.subtask_map)

    def _add_epic_node(
        self,
        parent: TreeNode[JiraNodeData],
        epic: JiraIssue,
        children: list[JiraIssue],
        subtask_map: dict[str, list[JiraIssue]],
    ) -> None:
        """加入單個 Epic 節點和其 children"""
        epic_node = self._add_issue_node(parent, epic, subtask_map, expand=False)
        for child in children:
            self._add_issue_node(epic_node, child, subtask_map)

    def _add_external_epic_node(
        self,
        parent: TreeNode[JiraNodeData],
        epic: JiraIssue,
        children: list[JiraIssue],
        subtask_map: dict[str, list[JiraIssue]],
    ) -> None:
        """加入不在查詢結果中的 Epic 節點"""
        epic_data = JiraNodeData(
            node_type=JiraNodeType.EXTERNAL_EPIC,
            issue=epic,
            title=epic.key,
            summary=epic.fields.summary,
            count=len(children),
        )

        # Label 會在 render_label 中格式化
        epic_node = parent.add(
            epic.key,
            data=epic_data,
            expand=False,
        )
        for child in children:
            self._add_issue_node(epic_node, child, subtask_map)

    def _add_no_epic_node(
        self,
        parent: TreeNode[JiraNodeData],
        issues: list[JiraIssue],
        subtask_map: dict[str, list[JiraIssue]],
    ) -> None:
        """加入 No Epic 節點"""
        no_epic_data = JiraNodeData(
            node_type=JiraNodeType.NO_SPRINT,  # 重用類型
            title='No Epic',
            count=len(issues),
        )
        no_epic_node = parent.add(
            f'No Epic ({len(issues)})',
            data=no_epic_data,
            expand=False,
        )
        for issue in issues:
            self._add_issue_node(no_epic_node, issue, subtask_map)

    def _add_active_sprints_group_node(
        self,
        parent: TreeNode[JiraNodeData],
        data: _ProjectData,
    ) -> None:
        """加入 Active Sprints 群組節點"""
        total_count = sum(len(data.sprints[n][1]) for n in data.active_sprints)
        group_data = JiraNodeData(
            node_type=JiraNodeType.SPRINT,
            title='Active Sprints',
            count=total_count,
        )
        group_node = parent.add(
            f'Active Sprints ({total_count})',
            data=group_data,
            expand=True,
        )

        for sprint_name in sorted(data.active_sprints):
            sprint_obj, sprint_issues = data.sprints[sprint_name]
            is_active = sprint_obj.state == 'active'
            self._add_sprint_node(group_node, sprint_obj, sprint_issues, data.subtask_map, expand=is_active)

    def _add_completed_sprints_group_node(
        self,
        parent: TreeNode[JiraNodeData],
        data: _ProjectData,
    ) -> None:
        """加入 Completed Sprints 群組節點"""
        total_count = sum(len(data.sprints[n][1]) for n in data.completed_sprints)
        group_data = JiraNodeData(
            node_type=JiraNodeType.PAST_SPRINTS,
            title='Completed Sprints',
            count=total_count,
        )
        group_node = parent.add(
            f'Completed Sprints ({total_count})',
            data=group_data,
            expand=False,
        )

        for sprint_name in sorted(data.completed_sprints):
            sprint_obj, sprint_issues = data.sprints[sprint_name]
            self._add_sprint_node(group_node, sprint_obj, sprint_issues, data.subtask_map, expand=False)

    def _add_sprint_node(
        self,
        parent: TreeNode[JiraNodeData],
        sprint: JiraSprint,
        issues: list[JiraIssue],
        subtask_map: dict[str, list[JiraIssue]],
        *,
        expand: bool = False,
    ) -> None:
        """加入 Sprint 節點"""
        sprint_data = JiraNodeData(
            node_type=JiraNodeType.SPRINT,
            sprint=sprint,
            title=sprint.name,
            count=len(issues),
        )
        sprint_node = parent.add(
            f'{sprint.name} ({len(issues)})',
            data=sprint_data,
            expand=expand,
        )

        # 加入 issues
        for issue in issues:
            self._add_issue_node(sprint_node, issue, subtask_map)

    def _add_no_sprint_node(
        self,
        parent: TreeNode[JiraNodeData],
        issues: list[JiraIssue],
        subtask_map: dict[str, list[JiraIssue]],
    ) -> None:
        """加入 No Sprint 節點"""
        no_sprint_data = JiraNodeData(
            node_type=JiraNodeType.NO_SPRINT,
            title='No Sprint',
            count=len(issues),
        )
        no_sprint_node = parent.add(
            f'No Sprint ({len(issues)})',
            data=no_sprint_data,
            expand=False,
        )
        for issue in issues:
            self._add_issue_node(no_sprint_node, issue, subtask_map)

    def _add_issue_node(
        self,
        parent: TreeNode[JiraNodeData],
        issue: JiraIssue,
        subtask_map: dict[str, list[JiraIssue]] | None = None,
        *,
        expand: bool = False,
    ) -> TreeNode[JiraNodeData]:
        """加入單一 Issue 節點（含其 subtasks）"""
        issue_data = JiraNodeData(
            node_type=JiraNodeType.ISSUE,
            issue=issue,
        )

        # 檢查是否有 subtasks
        subtasks = subtask_map.get(issue.key, []) if subtask_map else []
        has_subtasks = len(subtasks) > 0

        # Label 會在 render_label 中格式化
        issue_node = parent.add(
            issue.key,
            data=issue_data,
            expand=expand and has_subtasks,
        )

        # 加入 subtasks
        for subtask in subtasks:
            self._add_issue_node(issue_node, subtask)  # subtask 沒有再下一層了

        return issue_node

    def render_label(
        self,
        node: TreeNode[JiraNodeData],
        base_style: Style,
        style: Style,
    ) -> Text:
        """自訂節點標籤渲染"""
        data = node.data
        if data is None:
            return super().render_label(node, base_style, style)

        depth = self._get_node_depth(node)

        has_children = bool(node.children)

        # ISSUE 或 EXTERNAL_EPIC 節點
        if data.issue is not None and data.node_type in (JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC):
            external = data.node_type == JiraNodeType.EXTERNAL_EPIC
            result = self._row_renderer.render_issue(
                data.issue,
                style=style,
                depth=depth,
                is_expanded=node.is_expanded,
                allow_expand=has_children,
                external=external,
            )
            # 加上 Timeline（前面加空格分隔）
            result.append(' ', style=style)
            # 編輯模式時顯示游標
            if self._date_edit.is_active and self._date_edit.current_node is node:
                timeline = self._timeline.format_with_cursor(
                    data.issue.fields.start_date,
                    data.issue.fields.duedate,
                    self._scroll_offset,
                    self._date_edit.cursor_day,
                    self._date_edit.mode,
                    style=style,
                )
            else:
                timeline = self._timeline.format_bar(
                    data.issue.fields.start_date,
                    data.issue.fields.duedate,
                    self._scroll_offset,
                    style=style,
                )
            result.append_text(timeline)
            return result

        # 其他節點（標題類）
        result = self._row_renderer.render_title(
            data.title,
            style=style,
            depth=depth,
            is_expanded=node.is_expanded,
            allow_expand=has_children,
        )
        # 加上 Timeline（只顯示 today 底色）
        timeline = self._timeline.format_bar(None, None, self._scroll_offset)
        result.append_text(timeline)
        return result

    def _get_node_depth(self, node: TreeNode[JiraNodeData]) -> int:
        """計算節點深度（root = 0）"""
        depth = 0
        current = node
        while current.parent is not None:
            depth += 1
            current = current.parent
        return depth

    def action_collapse_all_children(self) -> None:
        """收合/展開當前節點的所有子節點"""
        if self.cursor_node is None:
            return

        children = list(self.cursor_node.children)
        if not children:
            return

        # 如果全部都收合，則展開全部；否則收合全部
        all_collapsed = all(c.is_collapsed for c in children if c._allow_expand)
        for child in children:
            if child._allow_expand:
                if all_collapsed:
                    child.expand()
                else:
                    child.collapse()

    def action_toggle_siblings(self) -> None:
        """展開/收合同層的所有節點"""
        if self.cursor_node is None or self.cursor_node.parent is None:
            return

        siblings = list(self.cursor_node.parent.children)
        expandable = [s for s in siblings if s._allow_expand]
        if not expandable:
            return

        all_collapsed = all(s.is_collapsed for s in expandable)
        for sibling in expandable:
            if all_collapsed:
                sibling.expand()
            else:
                sibling.collapse()

    def action_collapse_all(self) -> None:
        """收合/展開所有節點"""
        # 取得所有可展開的節點
        nodes = [n for n in self._tree_nodes.values() if n._allow_expand and n != self.root]
        if not nodes:
            return

        all_collapsed = all(n.is_collapsed for n in nodes)
        for node in nodes:
            if all_collapsed:
                node.expand()
            else:
                node.collapse()

    def update_timeline_width(self, width: int) -> None:
        """更新 Timeline 寬度"""
        self._timeline.width = width
        self._invalidate()

    def get_timeline_prefix_width(self) -> int:
        """取得 timeline 欄位前的總寬度（用於 header 對齊）"""
        return self._layout.total_fixed_width

    def set_timeline_offset(self, offset: int) -> None:
        """設定 Timeline 捲動偏移量"""
        self._scroll_offset = offset
        self._invalidate()

    async def _on_click(self, event) -> None:
        """取消滑鼠點擊行為"""

    # === 日期編輯模式 ===

    def on_key(self, event) -> None:
        """處理編輯模式/移動模式的按鍵"""
        # 移動模式
        if self._move.is_active:
            if event.key == 'escape':
                self._move.cancel()
                self._invalidate()
                self.app.notify('已取消移動', timeout=2)
                event.stop()
            return

        # 日期編輯模式
        if not self._date_edit.is_active:
            return

        if event.key == 'escape':
            self._date_edit.cancel()
            self._invalidate()
            event.stop()
        elif event.key == 'left':
            if self._date_edit.cursor_left():
                self._invalidate()
            event.stop()
        elif event.key == 'right':
            if self._date_edit.cursor_right():
                self._invalidate()
            event.stop()
        elif event.key in ('x', 'delete', 'backspace'):
            self._clear_date()
            event.stop()

    def action_edit_start_date(self) -> None:
        """進入編輯 Start Date 模式"""
        if self.cursor_node is None:
            return
        if self._date_edit.start(
            mode='start',
            node=self.cursor_node,
            scroll_offset=self._scroll_offset,
            allowed_types=(JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC),
        ):
            self._invalidate()

    def action_edit_due_date(self) -> None:
        """進入編輯 Due Date 模式"""
        if self.cursor_node is None:
            return
        if self._date_edit.start(
            mode='due',
            node=self.cursor_node,
            scroll_offset=self._scroll_offset,
            allowed_types=(JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC),
        ):
            self._invalidate()

    def action_edit_dates_continuous(self) -> None:
        """進入連續編輯日期模式（start → due → 下一個 issue）"""
        if self.cursor_node is None:
            return
        if self._date_edit.start(
            mode="start",
            node=self.cursor_node,
            scroll_offset=self._scroll_offset,
            allowed_types=(JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC),
            continuous=True,
        ):
            self._invalidate()

    def action_select_cursor(self) -> None:
        """選擇當前節點（或確認日期編輯/移動）"""
        if self._date_edit.is_active:
            self._confirm_edit()
        elif self._move.is_active:
            self._confirm_move()
        else:
            super().action_select_cursor()

    def _confirm_edit(self) -> None:
        """確認日期編輯"""
        if self._date_edit.is_continuous:
            self._confirm_edit_continuous()
        else:
            result = self._date_edit.confirm(self._scroll_offset)
            if result:
                issue_key, field, date_str = result
                self._invalidate()
                self.post_message(self.UpdateIssueDate(issue_key, field, date_str))

    def _confirm_edit_continuous(self) -> None:
        """連續模式下確認編輯"""
        if self._date_edit.mode == "start":
            # 確認 start date，切換到 due date
            result = self._date_edit.confirm_and_switch_to_due(self._scroll_offset)
            if result:
                issue_key, field, date_str = result
                self._invalidate()
                self.post_message(self.UpdateIssueDate(issue_key, field, date_str))
        else:
            # 確認 due date，尋找下一個 sibling issue
            next_node = self._get_next_sibling_issue(self._date_edit.current_node)
            if next_node:
                result = self._date_edit.confirm_and_switch_to_node(
                    self._scroll_offset,
                    next_node,
                )
                if result:
                    issue_key, field, date_str = result
                    self.select_node(next_node)  # 移動 tree cursor
                    self._invalidate()
                    self.post_message(self.UpdateIssueDate(issue_key, field, date_str))
            else:
                # 沒有下一個，結束連續模式
                result = self._date_edit.confirm(self._scroll_offset)
                if result:
                    issue_key, field, date_str = result
                    self._invalidate()
                    self.post_message(self.UpdateIssueDate(issue_key, field, date_str))
                self.app.notify("已完成該 issue 下所有 tasks 的日期設定", timeout=3)

    def _get_next_sibling_issue(
        self,
        node: TreeNode[JiraNodeData] | None,
    ) -> TreeNode[JiraNodeData] | None:
        """取得同 parent 下的下一個 ISSUE 節點"""
        if node is None or node.parent is None:
            return None

        siblings = list(node.parent.children)
        try:
            current_idx = siblings.index(node)
        except ValueError:
            return None

        # 從當前節點之後尋找下一個 ISSUE
        for sibling in siblings[current_idx + 1 :]:
            data = sibling.data
            if data and data.node_type in (
                JiraNodeType.ISSUE,
                JiraNodeType.EXTERNAL_EPIC,
            ):
                return sibling

        return None

    def _clear_date(self) -> None:
        """清除日期"""
        result = self._date_edit.clear()
        if result:
            issue_key, field = result
            self._invalidate()
            self.post_message(self.UpdateIssueDate(issue_key, field, None))

    # === Story Points 編輯功能 ===

    def action_edit_sp(self) -> None:
        """編輯 Story Points"""
        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return
        # 只有 ISSUE 類型可以編輯
        if data.node_type not in (JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC):
            return

        from ..screens.sp_edit import SPEditModal
        screen = SPEditModal(
            issue_key=data.issue.key,
            current_value=data.issue.fields.story_points,
        )
        self.app.push_screen(screen, self._on_sp_edit_complete)

    def _on_sp_edit_complete(self, result: float | None) -> None:
        """SP 編輯完成"""
        if result is None:
            return  # 取消

        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return

        issue_key = data.issue.key
        # 0.0 表示清除
        sp_value = result if result != 0.0 else None

        # 更新本地資料
        data.issue.fields.story_points = sp_value
        self._invalidate()

        # 發送 Message 給 App 處理 API 呼叫
        self.post_message(self.UpdateIssueSP(issue_key, sp_value))

    # === Time Original Estimate 編輯功能 ===

    def action_edit_time_estimate(self) -> None:
        """編輯 Time Original Estimate"""
        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return
        # 只有 ISSUE 類型可以編輯
        if data.node_type not in (JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC):
            return

        from ..screens.time_estimate import TimeEstimateEditModal
        screen = TimeEstimateEditModal(
            issue_key=data.issue.key,
            current_seconds=data.issue.fields.time_original_estimate,
        )
        self.app.push_screen(screen, self._on_time_estimate_edit_complete)

    def _on_time_estimate_edit_complete(self, result: int | None) -> None:
        """Time Estimate 編輯完成"""
        if result is None:
            return  # 取消

        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return

        issue_key = data.issue.key
        # 0 表示清除
        seconds_value = result if result != 0 else None

        # 更新本地資料
        data.issue.fields.time_original_estimate = seconds_value
        # 也更新 aggregate (顯示用)
        data.issue.fields.aggregate_time_original_estimate = seconds_value
        self._invalidate()

        # 發送 Message 給 App 處理 API 呼叫
        self.post_message(self.UpdateIssueTimeEstimate(issue_key, seconds_value))

    # === Rank (Move) 功能 ===

    def action_move_mark(self) -> None:
        """標記當前 issue 準備移動"""
        if self.cursor_node is None:
            return

        if self._move.mark(self.cursor_node, JiraNodeType.ISSUE):
            data = self.cursor_node.data
            if data and data.issue:
                self.app.notify(f'已標記 {data.issue.key}，移動游標到目標位置後按 Enter', timeout=3)
            self._invalidate()

    def _confirm_move(self) -> None:
        """確認移動到當前位置"""
        if not self._move.source_node or not self.cursor_node:
            return

        # 驗證目標
        error = self._move.validate_target(self.cursor_node)
        if error:
            if error != '不能移動到自己' and error != '目標不是有效的 issue':
                self.app.notify(error, severity='warning', timeout=2)
            self._move.cancel()
            self._invalidate()
            return

        # 取得移動資訊
        source_node = self._move.source_node
        result = self._move.confirm(self.cursor_node)
        if not result:
            return

        source_key, rank_before, rank_after = result

        # 本地移動節點
        self._move_node_to(source_node, self.cursor_node)

        # 發送 Message 給 App 處理 API 呼叫
        self.post_message(self.UpdateIssueRank(source_key, rank_before, rank_after))

        # 保持游標在移動的節點上
        self.select_node(source_node)

    def _move_node_to(
        self,
        source: TreeNode[JiraNodeData],
        target: TreeNode[JiraNodeData],
    ) -> None:
        """將 source 節點移動到 target 節點的位置"""
        parent = source.parent
        if parent is None or parent != target.parent:
            return

        children = list(parent._children)
        try:
            source_idx = children.index(source)
            target_idx = children.index(target)
        except ValueError:
            return

        # 移除 source
        children.pop(source_idx)
        # 重新計算 target 的 index（因為 source 被移除了）
        if source_idx < target_idx:
            target_idx -= 1
        # 插入到 target 之後（如果向下移動）或之前（如果向上移動）
        if source_idx < target_idx:
            children.insert(target_idx + 1, source)
        else:
            children.insert(target_idx, source)

        parent._children = children
        self._invalidate()

    # === Status 編輯功能 ===

    def action_edit_status(self) -> None:
        """編輯 Status（請求 transitions）"""
        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return
        # 只有 ISSUE 類型可以編輯
        if data.node_type not in (JiraNodeType.ISSUE, JiraNodeType.EXTERNAL_EPIC):
            return

        current_status = ''
        if data.issue.fields.status:
            current_status = data.issue.fields.status.name

        # 發送 Message 請求取得 transitions
        self.post_message(self.RequestTransitions(data.issue.key, current_status))

    def show_status_modal(
        self,
        *,
        issue_key: str,
        current_status: str,
        transitions: list,
    ) -> None:
        """顯示 status 編輯 modal（由 App 呼叫）"""
        if not transitions:
            self.app.notify('沒有可用的狀態變更', severity='warning')
            return

        from ..screens.status_edit import StatusEditModal
        screen = StatusEditModal(
            issue_key=issue_key,
            current_status=current_status,
            transitions=transitions,
        )
        self.app.push_screen(screen, self._on_status_edit_complete)

    def _on_status_edit_complete(self, result) -> None:
        """Status 編輯完成"""
        if result is None:
            return  # 取消

        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return

        issue_key = data.issue.key

        # 更新本地資料
        if data.issue.fields.status:
            data.issue.fields.status.name = result.new_status_name
        self._invalidate()

        # 發送 Message 給 App 處理 API 呼叫
        self.post_message(self.UpdateIssueStatus(
            issue_key,
            result.transition_id,
            result.new_status_name,
        ))

    def action_add_worklog(self) -> None:
        """在 subtask 節點上開啟 quick add worklog modal。"""
        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return
        self._open_add_worklog_modal(data.issue)

    def _open_add_worklog_modal(self, issue: JiraIssue) -> None:
        """為指定 subtask issue 開啟 quick add worklog modal。"""
        if issue is None:
            return

        issue_type = issue.fields.issuetype.name if issue.fields.issuetype else ''
        if issue_type not in ('Sub-task', 'Subtask'):
            self.app.notify('Only subtasks support quick add worklog here.', severity='warning')
            return

        myself = getattr(self.app, 'myself', None)
        timezone_name = myself.get('timeZone') if isinstance(myself, dict) else 'Asia/Taipei'
        try:
            timezone = ZoneInfo(timezone_name or 'Asia/Taipei')
        except Exception:
            timezone = ZoneInfo('Asia/Taipei')

        self.app.push_screen(
            WorklogEditorModal(
                issue_key=issue.key,
                issue_summary=issue.fields.summary,
                selected_day=datetime.now(timezone).date(),
                timezone=timezone,
                existing_entries=[],
            ),
            self._on_worklog_add_complete,
        )

    def _on_worklog_add_complete(
        self,
        result: WorklogEditorResult | WorklogDeleteResult | None,
    ) -> None:
        if result is None or isinstance(result, WorklogDeleteResult):
            return
        if self.cursor_node is None:
            return
        data = self.cursor_node.data
        if data is None or data.issue is None:
            return
        issue = data.issue
        self.post_message(
            self.AddIssueWorklog(
                issue.key,
                result.started,
                result.time_spent_seconds,
                result.comment_text,
                clamp_remaining_estimate(issue.fields.time_estimate, result.time_spent_seconds),
            )
        )
