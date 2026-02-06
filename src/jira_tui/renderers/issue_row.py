"""Issue 行渲染器"""

from datetime import datetime

from rich.style import Style
from rich.text import Text

from ..models import JiraIssue
from .layout import TreeLayout


class IssueRowRenderer:
    """Issue 行渲染器"""

    ISSUE_TYPE_ICONS: dict[str, str] = {
        'Bug': 'B',
        'Task': 'T',
        'Story': 'S',
        'Epic': 'E',
        'Sub-task': 't',
        'Subtask': 't',
    }

    ISSUE_TYPE_COLORS: dict[str, str] = {
        'Bug': '#e5493a',
        'Task': '#4bade8',
        'Story': '#63ba3c',
        'Epic': '#904ee2',
        'Sub-task': '#4bade8',
        'Subtask': '#4bade8',
    }

    def __init__(
        self,
        *,
        layout: TreeLayout,
        jira_host: str = '',
    ):
        self._layout = layout
        self._jira_host = jira_host.rstrip('/') if jira_host else ''

    @property
    def layout(self) -> TreeLayout:
        return self._layout

    def render_issue(
        self,
        issue: JiraIssue,
        *,
        style: Style | str,
        depth: int,
        is_expanded: bool = False,
        allow_expand: bool = False,
        external: bool = False,
    ) -> Text:
        """渲染 Issue 行

        Args:
            issue: Jira Issue
            style: 文字樣式
            depth: 節點深度
            is_expanded: 是否展開
            allow_expand: 是否允許展開
            external: 是否為外部 issue（不在查詢結果中），會加上 - 標記和 dim 樣式
        """
        result = Text()
        text_style: Style | str = 'dim' if external else style

        self._append_expand_icon(result, is_expanded, allow_expand, style=style)
        self._append_type_icon(result, issue, external=external, style=style)
        key_width = self._append_key(result, issue.key, text_style)
        self._append_summary(
            result,
            issue.fields.summary,
            text_style,
            self._layout.depth_padding(depth),
            key_width,
        )
        self._append_status(result, issue.fields.status.name if issue.fields.status else '', style)
        self._append_sp(result, issue.fields.story_points, style)
        self._append_est(result, issue.fields.aggregate_time_original_estimate, style)
        self._append_date(result, issue.fields.start_date, style)
        self._append_date(result, issue.fields.duedate, style)

        return result

    def render_title(
        self,
        title: str,
        *,
        style: Style,
        count: int | None = None,
        depth: int,
        is_expanded: bool = False,
        allow_expand: bool = False,
    ) -> Text:
        """渲染標題行（PROJECT, EPIC_GROUP, SPRINT 等）"""
        result = Text()

        self._append_expand_icon(result, is_expanded, allow_expand, style=style)

        # 標題文字
        label = title
        if count is not None:
            label = f'{label} ({count})'
        result.append(label, style=style)

        # 對齊計算：讓標題行的內容結束位置對齊到 Issue 行的 Timeline 開始位置
        # width_before_timeline - EXPAND_WIDTH（因為 expand icon 已經加了）
        label_width = Text(label).cell_len
        content_width = self._layout.width_before_timeline(depth) - self._layout.EXPAND_WIDTH
        padding_needed = content_width - label_width
        if padding_needed > 0:
            result.append(' ' * padding_needed, style=style)

        return result

    def render_header(self, *, depth: int) -> Text:
        """渲染欄位標題行（SP, A/TOEst, Status, Start, Due）"""
        layout = self._layout
        result = Text()

        # 前綴空白：width_before_timeline - fields_width
        prefix_width = layout.width_before_timeline(depth) - layout.fields_width
        result.append(' ' * prefix_width)

        # 欄位標題
        if layout.show_status:
            result.append(f' {"Status":<{layout.STATUS_WIDTH}}', style='bold')
        if layout.show_sp:
            result.append(f' {"SP":<{layout.SP_WIDTH}}', style='bold')
        if layout.show_est:
            result.append(f' {"A/TOEst":<{layout.EST_WIDTH}}', style='bold')
        if layout.show_dates:
            result.append(f' {"Start":<{layout.DATE_WIDTH}}', style='bold')
            result.append(f' {"Due":<{layout.DATE_WIDTH}}', style='bold')
        result.append(' ')  # space before timeline

        return result

    def _append_expand_icon(
        self,
        result: Text,
        is_expanded: bool,
        allow_expand: bool,
        style: Style | str | None = None,
    ) -> None:
        """加入展開/收合指示符"""
        if allow_expand:
            icon = '▼ ' if is_expanded else '▶ '
            result.append(icon, style=style)
        else:
            result.append('  ', style=style)

    def _append_type_icon(
        self,
        result: Text,
        issue: JiraIssue,
        *,
        external: bool = False,
        style: Style | str | None = None,
    ) -> None:
        """加入 Issue Type icon

        Args:
            result: 要加入的 Text 物件
            issue: Jira Issue
            external: 是否為外部 issue（不在查詢結果中），會加上 - 標記和 dim 樣式
            style: 基底樣式（用於 cursor 反白）
        """
        issue_type = issue.fields.issuetype.name if issue.fields.issuetype else ''
        type_icon = self.ISSUE_TYPE_ICONS.get(issue_type, '?')
        type_color = self.ISSUE_TYPE_COLORS.get(issue_type, 'white')
        base_style = Style.parse(style) if isinstance(style, str) else (style or Style())
        color_style = Style.parse(type_color)
        if external:
            dim_style = Style.parse('dim')
            result.append(f'{type_icon}-', style=base_style + dim_style + color_style)
        else:
            result.append(f'{type_icon:<{self._layout.TYPE_WIDTH}}', style=base_style + color_style)

    def _append_key(self, result: Text, key: str, style: Style | str) -> int:
        """加入 Issue Key（含超連結）+ 2 空白，回傳實際寬度"""
        if self._jira_host:
            url = f'{self._jira_host}/browse/{key}'
            if isinstance(style, Style):
                result.append(key, style=Style.parse(f'link {url}') + style)
            else:
                result.append(key, style=f'{style} link {url}')
        else:
            result.append(key, style=style)
        result.append('  ', style=style)
        return len(key) + 2

    def _append_summary(
        self,
        result: Text,
        summary: str,
        style: Style | str,
        depth_padding: int,
        key_width: int,
    ) -> None:
        """加入 Summary + 深度補齊空白"""
        # key 省下的空間給 summary
        summary_width = self._layout.summary_width + self._layout.KEY_WIDTH - key_width
        summary, cell_len = self._truncate_text(summary, summary_width)
        padding = summary_width - cell_len + depth_padding
        result.append(summary + ' ' * padding, style=style)

    def _truncate_text(self, text: str, max_width: int) -> tuple[str, int]:
        """截斷文字以符合最大顯示寬度，回傳 (截斷後文字, cell_len)"""
        text_obj = Text(text)
        if text_obj.cell_len <= max_width:
            return text, text_obj.cell_len

        truncated = ''
        width = 0
        for char in text:
            char_width = Text(char).cell_len
            if width + char_width + 1 > max_width:  # +1 for …
                break
            truncated += char
            width += char_width
        return truncated + '…', width + 1

    def _append_sp(self, result: Text, story_points: float | None, style: Style | str = 'dim') -> None:
        """加入 Story Points"""
        if not self._layout.show_sp:
            return
        sp_width = self._layout.SP_WIDTH
        if story_points is not None and story_points != 0:
            # 如果是整數，只顯示整數
            if story_points == int(story_points):
                sp_str = str(int(story_points))
            else:
                # 有小數，移除尾部的 0
                sp_str = f'{story_points:.3f}'.rstrip('0')
        else:
            sp_str = ''
        result.append(f' {sp_str:<{sp_width}}', style=style)

    def _append_est(
        self,
        result: Text,
        aggregate_time_original_estimate: int | None,
        style: Style | str = 'dim',
    ) -> None:
        """加入 Original Estimate"""
        if not self._layout.show_est:
            return
        est_width = self._layout.EST_WIDTH
        if aggregate_time_original_estimate:
            est_str = self._format_seconds(aggregate_time_original_estimate)
            # 截斷過長的估算值
            if len(est_str) > est_width:
                est_str = est_str[:est_width - 1] + '…'
        else:
            est_str = ''
        result.append(f' {est_str:>{est_width}}', style=style)

    def _format_seconds(self, seconds: int) -> str:
        """將秒數轉換成固定格式 _d_h__m (如 1d2h30m)，0 的部分用空格"""
        if seconds <= 0:
            return ''
        total_minutes = seconds // 60
        hours = total_minutes // 60
        minutes = total_minutes % 60
        days = hours // 8
        remaining_hours = hours % 8
        # 各部分：0 用空格代替
        d_str = f'{days}d' if days > 0 else '  '
        h_str = f'{remaining_hours}h' if remaining_hours > 0 else '  '
        m_str = f'{minutes:02d}m' if minutes > 0 else '   '
        return f'{d_str}{h_str}{m_str}'

    def _append_status(self, result: Text, status: str, style: Style | str = 'dim') -> None:
        """加入 Status（超過寬度則截斷）"""
        if not self._layout.show_status:
            return
        status_width = self._layout.STATUS_WIDTH
        if len(status) > status_width:
            status = status[:status_width - 1] + '…'
        result.append(f' {status:<{status_width}}', style=style)

    def _append_date(self, result: Text, dt: datetime | None, style: Style | str = 'dim') -> None:
        """加入日期欄位 (MM/DD 格式)"""
        if not self._layout.show_dates:
            return
        if dt:
            date_str = dt.strftime('%m/%d')
        else:
            date_str = ''
        result.append(f' {date_str:<{self._layout.DATE_WIDTH}}', style=style)
