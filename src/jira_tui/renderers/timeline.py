# ruff: noqa: DTZ005
"""Timeline 格式化渲染器"""

from datetime import datetime
from datetime import timedelta

from rich.style import Style
from rich.text import Text


class TimelineRenderer:
    """Timeline 格式化渲染器"""

    CHARS_PER_DAY = 3
    DAY_WIDTH = 2       # 日期寬度（用於底色）
    DAY_SEP = ' '       # 日期之間的分隔符
    DAYS_BEFORE_TODAY = 7
    TODAY_BG = 'dodger_blue1'

    def __init__(self, *, width: int = 21):
        self._width = width

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        self._width = max(12, value)

    @property
    def visible_days(self) -> int:
        return self._width // self.CHARS_PER_DAY

    def get_today(self) -> datetime:
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    def get_base_date(self) -> datetime:
        """取得時間軸的基準日期"""
        today = self.get_today()
        days_before = self._get_days_before_today()
        return today - timedelta(days=days_before)

    def _get_days_before_today(self) -> int:
        """根據時間軸寬度計算要顯示多少天前的日期"""
        if self.visible_days >= 21:
            return self.DAYS_BEFORE_TODAY
        return max(0, self.visible_days - 14)

    def format_header(self, scroll_offset: int) -> Text:
        """格式化 Timeline 欄位標題"""
        base_date = self.get_base_date()
        today = self.get_today()
        result = Text()

        for i in range(self.visible_days):
            current_date = base_date + timedelta(days=scroll_offset + i)
            day_str = current_date.strftime('%d')
            if current_date == today:
                result.append(day_str, style=f'bold on {self.TODAY_BG}')
                result.append(' ')
            else:
                result.append(day_str + ' ', style='bold')

        return result

    def format_bar(
        self,
        start_date: datetime | None,
        due_date: datetime | None,
        scroll_offset: int,
        *,
        style: Style | str | None = None,
    ) -> Text:
        """格式化時間軸色塊"""
        base_date = self.get_base_date()
        today = self.get_today()

        if not start_date and not due_date:
            return self._format_empty(base_date, today, scroll_offset, style=style)

        issue_start, issue_due, only_start, only_due = self._normalize_range(start_date, due_date)
        if issue_due < today:
            color = 'red'
        elif issue_due == today:
            color = 'yellow'
        else:
            color = 'green'

        visible_start = base_date + timedelta(days=scroll_offset)
        result = Text()
        for i in range(self.visible_days):
            current_date = base_date + timedelta(days=scroll_offset + i)
            day_text = self._format_day(
                current_date=current_date,
                today=today,
                issue_start=issue_start,
                issue_due=issue_due,
                only_start=only_start,
                only_due=only_due,
                color=color,
                visible_start=visible_start,
                style=style,
            )
            result.append_text(day_text)

        return result

    def format_with_cursor(
        self,
        start_date: datetime | None,
        due_date: datetime | None,
        scroll_offset: int,
        cursor_day: int,
        edit_mode: str,
        *,
        style: Style | str | None = None,
    ) -> Text:
        """格式化帶有編輯游標的時間軸"""
        base_date = self.get_base_date()
        today = self.get_today()
        result = Text()

        issue_start = start_date.replace(tzinfo=None) if start_date else None
        issue_due = due_date.replace(tzinfo=None) if due_date else None

        base_style = Style.parse(style) if isinstance(style, str) else (style or Style())
        today_bg_style = Style.parse(f'on {self.TODAY_BG}')

        for i in range(self.visible_days):
            current_date = base_date + timedelta(days=scroll_offset + i)
            is_cursor = (i == cursor_day)
            is_today = current_date == today

            if is_cursor:
                cursor_char = '[S' if edit_mode == 'start' else 'D]'
                result.append(cursor_char, style='bold reverse yellow')
                result.append(self.DAY_SEP, style=style)
            else:
                in_range = self._is_in_range(current_date, issue_start, issue_due)
                if in_range:
                    is_overdue = issue_due and issue_due < today
                    color_style = Style.parse('red' if is_overdue else 'green')
                    if is_today:
                        result.append('--', style=base_style + color_style + today_bg_style)
                    else:
                        result.append('--', style=base_style + color_style)
                    result.append(self.DAY_SEP, style=style)
                else:
                    is_weekday = current_date.weekday() < 5
                    chars = '..' if is_weekday else '  '
                    dim_style = Style.parse('dim')
                    if is_today:
                        result.append(chars, style=base_style + dim_style + today_bg_style)
                    else:
                        result.append(chars, style=base_style + dim_style)
                    result.append(self.DAY_SEP, style=style)

        return result

    def _format_empty(
        self,
        base_date: datetime,
        today: datetime,
        scroll_offset: int,
        *,
        style: Style | str | None = None,
    ) -> Text:
        """格式化沒有日期的時間軸"""
        result = Text()
        base_style = Style.parse(style) if isinstance(style, str) else (style or Style())
        today_bg_style = Style.parse(f'on {self.TODAY_BG}')

        dim_style = Style.parse('dim')
        for i in range(self.visible_days):
            current_date = base_date + timedelta(days=scroll_offset + i)
            is_weekday = current_date.weekday() < 5
            chars = '..' if is_weekday else '  '
            if current_date == today:
                result.append(chars, style=base_style + dim_style + today_bg_style)
            else:
                result.append(chars, style=base_style + dim_style)
            result.append(self.DAY_SEP, style=style)
        return result

    def _normalize_range(
        self,
        start_date: datetime | None,
        due_date: datetime | None,
    ) -> tuple[datetime, datetime, bool, bool]:
        """正規化日期範圍"""
        issue_start = start_date.replace(tzinfo=None) if start_date else None
        issue_due = due_date.replace(tzinfo=None) if due_date else None

        only_start = bool(issue_start and not issue_due)
        only_due = bool(issue_due and not issue_start)

        if only_start:
            issue_due = issue_start
        elif only_due:
            issue_start = issue_due

        return issue_start, issue_due, only_start, only_due  # type: ignore[return-value]

    def _is_in_range(
        self,
        current_date: datetime,
        issue_start: datetime | None,
        issue_due: datetime | None,
    ) -> bool:
        """檢查日期是否在範圍內"""
        if issue_start and issue_due:
            return issue_start <= current_date <= issue_due
        if issue_start:
            return current_date == issue_start
        if issue_due:
            return current_date == issue_due
        return False

    def _format_day(
        self,
        *,
        current_date: datetime,
        today: datetime,
        issue_start: datetime,
        issue_due: datetime,
        only_start: bool,
        only_due: bool,
        color: str,
        visible_start: datetime,
        style: Style | str | None = None,
    ) -> Text:
        """格式化時間軸上的單一天（每天 3 字元，today 底色 2 字元）"""
        is_today = current_date == today
        in_range = issue_start <= current_date <= issue_due

        if not in_range:
            is_weekday = current_date.weekday() < 5
            chars = '..' if is_weekday else '  '
            return self._render_day(chars, is_today, color='', style=style)

        is_start = current_date == issue_start
        is_end = current_date == issue_due

        # 決定顯示字元
        if is_start and is_end:
            if only_start:
                chars = '|>'
            elif only_due:
                chars = '<|'
            else:
                chars = '[]'
        elif is_start:
            chars = '|-'
        elif is_end:
            chars = '-|'
        else:
            chars = '--'

        return self._render_day(chars, is_today, color, style=style)

    def _render_day(
        self,
        chars: str,
        is_today: bool,
        color: str,
        *,
        style: Style | str | None = None,
    ) -> Text:
        """渲染單日字元（2字元）+ 分隔符（1字元），today 的 2 字元加底色"""
        result = Text()
        # 建立基本樣式
        base_style = Style.parse(style) if isinstance(style, str) else (style or Style())
        color_style = Style.parse(color) if color else Style()
        today_bg_style = Style.parse(f'on {self.TODAY_BG}')

        if is_today:
            combined = base_style + color_style + today_bg_style
            if not color:
                combined = combined + Style.parse('dim')
            result.append(chars, style=combined)
        else:
            if color:
                combined = base_style + color_style
            else:
                combined = base_style + Style.parse('dim')
            result.append(chars, style=combined if combined else None)
        result.append(self.DAY_SEP, style=style)
        return result
