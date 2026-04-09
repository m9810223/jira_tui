"""Worklog editor modal."""

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label
from textual.widgets import Static

from ..worklog import WorklogEntry
from ..worklog import datetime_to_slot_range
from ..worklog import format_duration_label
from ..worklog import has_overlap
from ..worklog import selection_to_datetimes
from ..worklog import selection_to_seconds
from ..widgets.inputs import BlurTextArea
from ..widgets.worklog_day_grid import WorklogDayGrid


@dataclass(slots=True)
class WorklogEditorResult:
    issue_key: str
    worklog_id: str | None
    started: datetime
    time_spent_seconds: int
    comment_text: str


@dataclass(slots=True)
class WorklogDeleteResult:
    issue_key: str
    worklog_id: str


class WorklogEditorModal(ModalScreen[WorklogEditorResult | WorklogDeleteResult | None]):
    """Create or edit a worklog in a compact day-view modal."""

    DEFAULT_CSS = """
    WorklogEditorModal {
        align: center middle;
    }

    #worklog-editor-dialog {
        width: 120;
        height: 34;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #worklog-editor-header {
        height: auto;
        margin-bottom: 1;
    }

    #worklog-editor-body {
        height: 1fr;
    }

    #worklog-editor-axis {
        width: 8;
        color: $text-muted;
    }

    #worklog-editor-grid {
        width: 1fr;
        border: round $primary-background;
    }

    #worklog-editor-side {
        width: 36;
        margin-left: 2;
    }

    #worklog-editor-comment {
        height: 8;
        margin-top: 1;
    }

    #worklog-editor-summary {
        margin-top: 1;
        color: $text-muted;
    }

    #worklog-editor-buttons {
        height: auto;
        align: right middle;
        margin-top: 1;
    }

    #worklog-editor-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ('escape', 'cancel', '取消'),
    ]

    def __init__(
        self,
        *,
        issue_key: str,
        issue_summary: str,
        selected_day: date,
        timezone: ZoneInfo,
        existing_entries: list[WorklogEntry],
        current_entry: WorklogEntry | None = None,
    ) -> None:
        super().__init__()
        self._issue_key = issue_key
        self._issue_summary = issue_summary
        self._selected_day = selected_day
        self._timezone = timezone
        self._existing_entries = existing_entries
        self._current_entry = current_entry

    def compose(self) -> ComposeResult:
        title = 'Edit Worklog' if self._current_entry else 'Add Worklog'
        with Vertical(id='worklog-editor-dialog'):
            with Horizontal(id='worklog-editor-header'):
                yield Label(f'{title}: {self._issue_key}')
                yield Static(self._selected_day.strftime('%Y-%m-%d'))
            with Horizontal(id='worklog-editor-body'):
                yield Static(self._build_axis_labels(), id='worklog-editor-axis')
                yield WorklogDayGrid(
                    id='worklog-editor-grid',
                    allow_entry_selection=False,
                )
                with Vertical(id='worklog-editor-side'):
                    yield Label(self._issue_summary)
                    yield Label('Comment')
                    yield BlurTextArea(id='worklog-editor-comment')
                    yield Static('', id='worklog-editor-summary')
            with Horizontal(id='worklog-editor-buttons'):
                if self._current_entry is not None:
                    yield Button('Delete', id='worklog-delete-btn', variant='error')
                yield Button('Save', id='worklog-save-btn', variant='primary')
                yield Button('Cancel', id='worklog-cancel-btn')

    def on_mount(self) -> None:
        grid = self.query_one('#worklog-editor-grid', WorklogDayGrid)
        grid.set_worklog_entries(self._existing_entries)
        if self._current_entry is not None:
            start_slot, end_slot = datetime_to_slot_range(
                self._current_entry.started.astimezone(self._timezone),
                self._current_entry.time_spent_seconds,
            )
            grid.set_draft_slots(start_slot, end_slot)
            self.query_one('#worklog-editor-comment', BlurTextArea).text = self._current_entry.comment_text
        self._update_summary()
        self.query_one('#worklog-editor-comment', BlurTextArea).focus()

    def _build_axis_labels(self) -> str:
        labels = []
        hour = 8
        minute = 0
        for _ in range(24):
            labels.append(f'{hour:02d}:{minute:02d}')
            minute += 30
            if minute >= 60:
                hour += 1
                minute = 0
        return '\n'.join(labels)

    def _update_summary(self) -> None:
        summary = self.query_one('#worklog-editor-summary', Static)
        grid = self.query_one('#worklog-editor-grid', WorklogDayGrid)
        if grid.draft_slots is None:
            summary.update('No time range selected')
            return
        start_slot, end_slot = grid.draft_slots
        started, ended = selection_to_datetimes(
            self._selected_day,
            start_slot,
            end_slot,
            self._timezone,
        )
        duration = format_duration_label(selection_to_seconds(start_slot, end_slot))
        summary.update(f'{started:%H:%M}-{ended:%H:%M} ({duration})')

    @on(WorklogDayGrid.SelectionChanged)
    def on_selection_changed(self, event: WorklogDayGrid.SelectionChanged) -> None:
        self.query_one('#worklog-editor-grid', WorklogDayGrid).draft_slots = (
            event.start_slot,
            event.end_slot,
        )
        self._update_summary()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'worklog-save-btn':
            self._confirm()
        elif event.button.id == 'worklog-delete-btn':
            self._delete()
        elif event.button.id == 'worklog-cancel-btn':
            self.dismiss(None)

    def _confirm(self) -> None:
        grid = self.query_one('#worklog-editor-grid', WorklogDayGrid)
        if grid.draft_slots is None:
            self.app.notify('Please drag a time range first.', severity='error')
            return
        start_slot, end_slot = grid.draft_slots
        started, ended = selection_to_datetimes(
            self._selected_day,
            start_slot,
            end_slot,
            self._timezone,
        )
        if has_overlap(
            started,
            ended,
            self._existing_entries,
            ignore_worklog_id=self._current_entry.worklog_id if self._current_entry else None,
        ):
            self.app.notify('The selected range overlaps an existing worklog.', severity='error')
            return
        self.dismiss(
            WorklogEditorResult(
                issue_key=self._issue_key,
                worklog_id=self._current_entry.worklog_id if self._current_entry else None,
                started=started,
                time_spent_seconds=selection_to_seconds(start_slot, end_slot),
                comment_text=self.query_one('#worklog-editor-comment', BlurTextArea).text.strip(),
            )
        )

    def _delete(self) -> None:
        if self._current_entry is None:
            return
        self.dismiss(
            WorklogDeleteResult(
                issue_key=self._issue_key,
                worklog_id=self._current_entry.worklog_id,
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
