"""Worklog day grid widget."""

from zoneinfo import ZoneInfo

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import Static

from ..worklog import DAY_START_HOUR
from ..worklog import SLOT_MINUTES
from ..worklog import SLOTS_PER_DAY
from ..worklog import WorklogEntry
from ..worklog import normalize_slot_range
from ..worklog import seconds_to_slots_ceil


class WorklogDayGrid(Static):
    """A simple day-view grid for worklog selection."""

    _ENTRY_COLORS = [
        '#808aff', '#78c9ff', '#9b80ff', '#70e0cf', '#ff80ab', '#ffd54f'
    ]

    class SelectionChanged(Message):
        """Emitted when the draft selection changes."""

        def __init__(self, start_slot: int, end_slot: int):
            self.start_slot = start_slot
            self.end_slot = end_slot
            super().__init__()

    class EntrySelected(Message):
        """Emitted when an existing worklog entry is selected."""

        def __init__(self, entry: WorklogEntry):
            self.entry = entry
            super().__init__()

    def __init__(self, *args, allow_entry_selection: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.worklog_entries: list[WorklogEntry] = []
        self.draft_slots: tuple[int, int] | None = None
        self._drag_anchor_slot: int | None = None
        self._pending_entry_selection: WorklogEntry | None = None
        self._entry_style_map: dict[str, str] = {}
        self._allow_entry_selection = allow_entry_selection
        self._display_timezone: ZoneInfo | None = None
        self.can_focus = True

    def set_display_timezone(self, timezone: ZoneInfo | None) -> None:
        self._display_timezone = timezone
        self.refresh()

    def set_worklog_entries(self, entries: list[WorklogEntry]) -> None:
        self.worklog_entries = entries
        self._entry_style_map = {}
        sorted_entries = sorted(
            entries,
            key=lambda entry: (entry.started, entry.ended, entry.issue_key, entry.worklog_id),
        )
        for index, entry in enumerate(sorted_entries):
            self._entry_style_map[self._entry_identifier(entry)] = self._ENTRY_COLORS[index % len(self._ENTRY_COLORS)]
        self.refresh()

    def set_draft_slots(self, start_slot: int, end_slot: int) -> None:
        self.draft_slots = (start_slot, end_slot)
        self.post_message(self.SelectionChanged(start_slot, end_slot))
        self.refresh()

    def _render_time_axis_label(self, slot: int) -> Text:
        """Render a formatted time label for a given slot."""
        hour = DAY_START_HOUR + (slot * SLOT_MINUTES) // 60
        if slot % 2 == 0:
            return Text(f"{hour:02d}:00 ", style="bold")
        return Text("  --  ", style="dim")

    def clear_draft(self) -> None:
        self.draft_slots = None
        self._drag_anchor_slot = None
        self._pending_entry_selection = None
        self.refresh()

    def _render_width(self) -> int:
        content_width = self.content_region.width or self.size.width
        return max(content_width, 24)

    def render(self) -> Text:
        width = self._render_width()
        lines: list[Text] = []
        for slot in range(SLOTS_PER_DAY):
            lines.append(self._render_slot_line(slot, width))

        result = Text()
        for index, line in enumerate(lines):
            if index:
                result.append('\n')
            result.append_text(line)
        return result

    def _render_slot_line(self, slot: int, width: int) -> Text:
        # 1. 處理 Draft 選擇
        if self.draft_slots is not None and self.draft_slots[0] <= slot < self.draft_slots[1]:
            line = Text()
            is_start = slot == self.draft_slots[0]
            label = " Draft selection" if is_start else ""
            line.append("▌", style="bold")
            line.append(label.ljust(width - 1), style="reverse")
            return line

        # 2. 處理現有 Entry
        entry = self._entry_for_slot(slot)
        if entry is not None:
            start_slot = self._slot_index_for_entry(entry)
            duration_slots = seconds_to_slots_ceil(entry.time_spent_seconds)
            slot_offset = slot - start_slot
            color = self._entry_style(entry)

            line = Text()
            # 左側重音線 (每一行都顯示，保持區塊感)
            line.append("▌", style=f"bold {color}")

            # 內容區域
            content = Text()
            if slot_offset == 0:
                content.append(f" {entry.issue_key}", style="bold")
                content.append(f" {entry.issue_summary}")
            elif slot_offset == 1 and duration_slots >= 2:
                # 恢復 1 小時 (2 slots) 即可顯示內容的邏輯，讓空間利用更好
                if entry.comment_text:
                    content.append(f" {entry.comment_text}", style="italic")

            content.truncate(width - 1, pad=True)
            line.append_text(content)
            return line

        # 3. 空白時段
        return Text(" ".ljust(width))

    def _slot_index_for_entry(self, entry: WorklogEntry) -> int:
        started = entry.started
        if self._display_timezone is not None:
            started = started.astimezone(self._display_timezone)
        return int((started.hour - DAY_START_HOUR) * 2 + started.minute // SLOT_MINUTES)

    def _entry_for_slot(self, slot: int) -> WorklogEntry | None:
        for entry in self.worklog_entries:
            start_slot = self._slot_index_for_entry(entry)
            duration_slots = seconds_to_slots_ceil(entry.time_spent_seconds)
            if start_slot <= slot < start_slot + duration_slots:
                return entry
        return None

    def _format_entry_label(self, entry: WorklogEntry) -> str:
        return f' {entry.issue_key} {entry.issue_summary}'

    def _entry_identifier(self, entry: WorklogEntry) -> str:
        return entry.worklog_id or f'{entry.issue_key}:{entry.started.isoformat()}'

    def _entry_style(self, entry: WorklogEntry) -> str:
        """Get the accent color for a worklog entry."""
        return self._entry_style_map.get(self._entry_identifier(entry), self._ENTRY_COLORS[0])

    def _format_entry_line(self, entry: WorklogEntry, slot: int) -> str:
        start_slot = self._slot_index_for_entry(entry)
        slot_offset = slot - start_slot
        duration_slots = seconds_to_slots_ceil(entry.time_spent_seconds)
        if slot_offset == 0:
            return self._format_entry_label(entry)
        if slot_offset == 1 and duration_slots >= 4:
            if entry.comment_text:
                return f' {entry.comment_text}'
        return ' '

    def _slot_from_y(self, y: int) -> int | None:
        content_y = y - self.gutter.top
        if 0 <= content_y < SLOTS_PER_DAY:
            return content_y
        return None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        slot = self._slot_from_y(event.y)
        if slot is None:
            return
        entry = self._entry_for_slot(slot)
        if entry is not None and self._allow_entry_selection:
            self._pending_entry_selection = entry
            self._drag_anchor_slot = None
            event.stop()
            return
        self._pending_entry_selection = None
        self._drag_anchor_slot = slot
        self.set_draft_slots(slot, slot + 1)
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag_anchor_slot is None:
            return
        slot = self._slot_from_y(event.y)
        if slot is None:
            return
        start_slot, end_slot = normalize_slot_range(self._drag_anchor_slot, slot)
        self.set_draft_slots(start_slot, end_slot)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        slot = self._slot_from_y(event.y)
        if self._pending_entry_selection is not None:
            entry = self._entry_for_slot(slot) if slot is not None else None
            pending = self._pending_entry_selection
            self._pending_entry_selection = None
            if entry is not None and entry.worklog_id == pending.worklog_id:
                self.post_message(self.EntrySelected(pending))
            event.stop()
            return
        if self._drag_anchor_slot is None:
            return
        if slot is not None:
            start_slot, end_slot = normalize_slot_range(self._drag_anchor_slot, slot)
            self.set_draft_slots(start_slot, end_slot)
        self._drag_anchor_slot = None
        event.stop()
