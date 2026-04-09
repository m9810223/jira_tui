"""Worklog day grid widget."""

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import Static

from ..worklog import SLOTS_PER_DAY
from ..worklog import WorklogEntry
from ..worklog import format_duration_label
from ..worklog import normalize_slot_range


class WorklogDayGrid(Static):
    """A simple day-view grid for worklog selection."""

    _ENTRY_STYLES = (
        'bold black on #808aff',
        'bold black on #78c9ff',
    )

    class SelectionChanged(Message):
        """Emitted when the draft selection changes."""

        def __init__(self, start_slot: int, end_slot: int):
            self.start_slot = start_slot
            self.end_slot = end_slot
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worklog_entries: list[WorklogEntry] = []
        self.draft_slots: tuple[int, int] | None = None
        self._drag_anchor_slot: int | None = None
        self._entry_style_map: dict[str, str] = {}
        self.can_focus = True

    def set_worklog_entries(self, entries: list[WorklogEntry]) -> None:
        self.worklog_entries = entries
        self._entry_style_map = {}
        sorted_entries = sorted(
            entries,
            key=lambda entry: (entry.started, entry.ended, entry.issue_key, entry.worklog_id),
        )
        for index, entry in enumerate(sorted_entries):
            self._entry_style_map[self._entry_identifier(entry)] = self._ENTRY_STYLES[index % 2]
        self.refresh()

    def set_draft_slots(self, start_slot: int, end_slot: int) -> None:
        self.draft_slots = (start_slot, end_slot)
        self.post_message(self.SelectionChanged(start_slot, end_slot))
        self.refresh()

    def clear_draft(self) -> None:
        self.draft_slots = None
        self.refresh()

    def render(self) -> Text:
        width = max(self.size.width, 24)
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
        label = ' '
        if self.draft_slots is not None and self.draft_slots[0] <= slot < self.draft_slots[1]:
            if slot == self.draft_slots[0]:
                label = ' Draft selection'
            else:
                label = ' '
            return Text(label.ljust(width), style='reverse')

        entry = self._entry_for_slot(slot)
        if entry is not None:
            text = self._format_entry_line(entry, slot)
            return Text(text[:width].ljust(width), style=self._entry_style(entry))

        return Text(' '.ljust(width))

    def _slot_index_for_entry(self, entry: WorklogEntry) -> int:
        return int((entry.started.hour - 8) * 2 + entry.started.minute // 30)

    def _entry_for_slot(self, slot: int) -> WorklogEntry | None:
        for entry in self.worklog_entries:
            start_slot = self._slot_index_for_entry(entry)
            duration_slots = max(1, entry.time_spent_seconds // (30 * 60))
            if start_slot <= slot < start_slot + duration_slots:
                return entry
        return None

    def _format_entry_label(self, entry: WorklogEntry) -> str:
        start_label = entry.started.strftime('%H:%M')
        end_label = entry.ended.strftime('%H:%M')
        duration_label = format_duration_label(entry.time_spent_seconds)
        return f' {start_label}-{end_label} ({duration_label}) {entry.issue_key} {entry.issue_summary}'

    def _entry_identifier(self, entry: WorklogEntry) -> str:
        return entry.worklog_id or f'{entry.issue_key}:{entry.started.isoformat()}'

    def _entry_style(self, entry: WorklogEntry) -> str:
        return self._entry_style_map.get(self._entry_identifier(entry), self._ENTRY_STYLES[0])

    def _format_entry_line(self, entry: WorklogEntry, slot: int) -> str:
        start_slot = self._slot_index_for_entry(entry)
        slot_offset = slot - start_slot
        if slot_offset == 0:
            return self._format_entry_label(entry)
        if slot_offset == 1:
            if entry.comment_text:
                return f' {entry.comment_text}'
            return f' {entry.issue_key}'
        if slot_offset == 2:
            return f' {entry.issue_summary}'
        return ' '

    def _slot_from_y(self, y: int) -> int | None:
        if 0 <= y < SLOTS_PER_DAY:
            return y
        return None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        slot = self._slot_from_y(event.y)
        if slot is None:
            return
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
        if self._drag_anchor_slot is None:
            return
        slot = self._slot_from_y(event.y)
        if slot is not None:
            start_slot, end_slot = normalize_slot_range(self._drag_anchor_slot, slot)
            self.set_draft_slots(start_slot, end_slot)
        self._drag_anchor_slot = None
        event.stop()
