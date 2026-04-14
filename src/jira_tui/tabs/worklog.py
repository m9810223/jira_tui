"""Worklog day-view tab."""

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

from rich.text import Text
from textual import on
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.widgets import Button
from textual.widgets import LoadingIndicator
from textual.widgets import Static

from ..config import JiraClient
from ..models import JiraIssue
from ..screens.worklog_editor import WorklogDeleteResult
from ..screens.worklog_editor import WorklogEditorModal
from ..screens.worklog_editor import WorklogEditorResult
from ..worklog import SLOTS_PER_DAY
from ..worklog import WorklogEntry
from ..worklog import collect_day_worklog_entries
from ..worklog import format_duration_label
from ..worklog import has_overlap
from ..worklog import resolve_timezone
from ..worklog import selection_to_datetimes
from ..worklog import selection_to_seconds
from ..widgets.worklog_day_grid import WorklogDayGrid
from ..widgets.worklog_issue_picker import WorklogIssuePicker
from ._mixin import JiraClientMixin


@dataclass(slots=True)
class WorklogDayData:
    selected_day: date
    timezone: ZoneInfo
    candidate_issues: list[JiraIssue]
    worklog_entries: list[WorklogEntry]


@dataclass(slots=True)
class WorklogTabState:
    selected_day: date
    timezone: ZoneInfo
    candidate_issues: list[JiraIssue]
    worklog_entries: list[WorklogEntry]


class WorklogTab(JiraClientMixin, Vertical):
    """Calendar-like worklog entry tab."""

    def __init__(self) -> None:
        super().__init__()
        self._state = WorklogTabState(
            selected_day=datetime.now().date(),
            timezone=resolve_timezone(None),
            candidate_issues=[],
            worklog_entries=[],
        )
        self._day_load_request_id = 0

    @property
    def selected_day(self) -> date:
        return self._state.selected_day

    @property
    def issue_picker(self) -> WorklogIssuePicker:
        return self.query_one(WorklogIssuePicker)

    def compose(self) -> ComposeResult:
        with Horizontal(id='worklog-toolbar'):
            yield Button('Prev', id='worklog-prev-day-btn')
            yield Button('Today', id='worklog-today-btn')
            yield Button('Next', id='worklog-next-day-btn')
            yield Static('', id='worklog-date-label')
            yield Static('', id='worklog-draft-summary')
        yield LoadingIndicator(id='worklog-loading', classes='hidden')
        with Horizontal(id='worklog-body'):
            yield Static('', id='worklog-time-axis')
            yield WorklogDayGrid(id='worklog-day-grid')
            yield WorklogIssuePicker(id='worklog-issue-picker')
        yield Static('', id='worklog-status')

    def on_mount(self) -> None:
        self._state = WorklogTabState(
            selected_day=self._today(),
            timezone=self._state.timezone,
            candidate_issues=self._state.candidate_issues,
            worklog_entries=self._state.worklog_entries,
        )
        self._update_time_axis()
        self._update_selected_day_label()
        self._update_draft_summary()
        self.refresh_day()

    def _today(self) -> date:
        return datetime.now(self._state.timezone).date()

    def set_selected_day(self, selected_day: date) -> None:
        self._state = WorklogTabState(
            selected_day=selected_day,
            timezone=self._state.timezone,
            candidate_issues=self._state.candidate_issues,
            worklog_entries=self._state.worklog_entries,
        )
        self._update_selected_day_label()
        self._update_draft_summary()

    def go_to_previous_day(self) -> None:
        selected_day = self.selected_day
        self.set_selected_day(selected_day.fromordinal(selected_day.toordinal() - 1))
        self.refresh_day()

    def go_to_next_day(self) -> None:
        selected_day = self.selected_day
        self.set_selected_day(selected_day.fromordinal(selected_day.toordinal() + 1))
        self.refresh_day()

    def go_to_today(self) -> None:
        self.set_selected_day(self._today())
        self.refresh_day()

    def refresh_day(self) -> None:
        client = self._get_jira_client(silent=True)
        if not client:
            return
        self._day_load_request_id += 1
        request_id = self._day_load_request_id
        self.query_one('#worklog-loading', LoadingIndicator).remove_class('hidden')
        self.query_one('#worklog-status', Static).update('Loading worklog data...')
        self._load_day_data(client, self.selected_day, request_id)

    @work(thread=True)
    def _load_day_data(self, client: JiraClient, selected_day: date, request_id: int) -> None:
        try:
            myself = self.app.myself  # pyright: ignore[reportAttributeAccessIssue]
            if myself is None:
                myself = client.get_myself()
                self.app.myself = myself  # pyright: ignore[reportAttributeAccessIssue]

            day_data = self._build_day_load_data(
                client,
                selected_day=selected_day,
                myself=myself,
            )

            self.app.call_from_thread(
                self._apply_day_data,
                request_id,
                day_data,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self._handle_day_load_error,
                request_id,
                f'Failed to load worklog data: {exc}',
            )

    @staticmethod
    def _build_day_load_data(client: JiraClient, *, selected_day: date, myself: dict) -> WorklogDayData:
        timezone = resolve_timezone(myself.get('timeZone'))
        candidate_issues = client.search_active_sprint_subtasks_for_current_user()
        day_issues = client.search_day_worklog_issues_for_current_user(selected_day)
        filtered_entries = collect_day_worklog_entries(
            day_issues,
            selected_day=selected_day,
            account_id=myself.get('accountId', ''),
            timezone=timezone,
            fetch_issue_worklogs=client.get_issue_worklogs,
        )
        return WorklogDayData(
            selected_day=selected_day,
            timezone=timezone,
            candidate_issues=candidate_issues,
            worklog_entries=filtered_entries,
        )

    def _apply_day_data(
        self,
        request_id: int,
        day_data: WorklogDayData,
    ) -> None:
        if request_id != self._day_load_request_id:
            return
        self._state = WorklogTabState(
            selected_day=day_data.selected_day,
            timezone=day_data.timezone,
            candidate_issues=day_data.candidate_issues,
            worklog_entries=day_data.worklog_entries,
        )
        self.issue_picker.set_issues(day_data.candidate_issues)
        grid = self.query_one(WorklogDayGrid)
        grid.set_display_timezone(day_data.timezone)
        grid.set_worklog_entries(day_data.worklog_entries)
        self.query_one('#worklog-loading', LoadingIndicator).add_class('hidden')
        self.query_one('#worklog-status', Static).update(
            f'{len(day_data.worklog_entries)} worklogs, {len(day_data.candidate_issues)} candidate subtasks'
        )
        self._update_selected_day_label()
        self._update_draft_summary()

    def _handle_day_load_error(self, request_id: int, message: str) -> None:
        if request_id != self._day_load_request_id:
            return
        self.query_one('#worklog-loading', LoadingIndicator).add_class('hidden')
        self.query_one('#worklog-status', Static).update(message)
        self.app.notify(message, severity='error', timeout=2)

    def submit_worklog(self) -> None:
        issue = self.issue_picker.selected_issue
        grid = self.query_one(WorklogDayGrid)
        if issue is None:
            self._set_status('Please select a subtask before submitting.', severity='error')
            return
        if grid.draft_slots is None:
            self._set_status('Please drag a time range before submitting.', severity='error')
            return

        start_slot, end_slot = grid.draft_slots
        started, ended = selection_to_datetimes(
            self.selected_day,
            start_slot,
            end_slot,
            self._state.timezone,
        )
        if has_overlap(started, ended, self._state.worklog_entries):
            self._set_status('The selected range overlaps an existing worklog.', severity='error')
            return

        client = self._get_jira_client(silent=True)
        if not client:
            return

        selected_seconds = selection_to_seconds(start_slot, end_slot)
        self._submit_worklog(
            client,
            issue,
            started,
            selected_seconds,
            self.issue_picker.get_message(),
        )

    def open_existing_worklog_editor(self, entry: WorklogEntry) -> None:
        myself = self.app.myself  # pyright: ignore[reportAttributeAccessIssue]
        if not myself or entry.author_account_id != myself.get('accountId'):
            self._set_status('You can only edit your own worklogs.', severity='warning')
            return
        self.app.push_screen(
            WorklogEditorModal(
                issue_key=entry.issue_key,
                issue_summary=entry.issue_summary,
                selected_day=self.selected_day,
                timezone=self._state.timezone,
                existing_entries=self._state.worklog_entries,
                current_entry=entry,
            ),
            self._on_worklog_editor_complete,
        )

    def _on_worklog_editor_complete(
        self,
        result: WorklogEditorResult | WorklogDeleteResult | None,
    ) -> None:
        if result is None:
            return

        client = self._get_jira_client(silent=True)
        if not client:
            return

        if isinstance(result, WorklogDeleteResult):
            self._delete_worklog(client, result.issue_key, result.worklog_id)
            return

        if result.worklog_id is None:
            issue = self.issue_picker.selected_issue
            if issue is None:
                self._set_status('Please select a subtask before submitting.', severity='error')
                return
            self._submit_worklog(
                client,
                issue,
                result.started,
                result.time_spent_seconds,
                result.comment_text,
            )
            return

        self._update_worklog(
            client,
            result.issue_key,
            result.worklog_id,
            result.started,
            result.time_spent_seconds,
            result.comment_text,
        )

    @work(thread=True)
    def _submit_worklog(
        self,
        client: JiraClient,
        issue: JiraIssue,
        started: datetime,
        time_spent_seconds: int,
        comment_text: str,
    ) -> None:
        try:
            client.add_issue_worklog(
                issue.key,
                started=started,
                time_spent_seconds=time_spent_seconds,
                comment_text=comment_text,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self._handle_background_error,
                f'Failed to add worklog for {issue.key}: {exc}',
            )
            return
        self.app.call_from_thread(self._after_submit, issue.key)

    @work(thread=True)
    def _update_worklog(
        self,
        client: JiraClient,
        issue_key: str,
        worklog_id: str,
        started: datetime,
        time_spent_seconds: int,
        comment_text: str,
    ) -> None:
        try:
            client.update_issue_worklog(
                issue_key,
                worklog_id,
                started=started,
                time_spent_seconds=time_spent_seconds,
                comment_text=comment_text,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self._handle_background_error,
                f'Failed to update worklog for {issue_key}: {exc}',
            )
            return
        self.app.call_from_thread(self._after_update, issue_key)

    @work(thread=True)
    def _delete_worklog(
        self,
        client: JiraClient,
        issue_key: str,
        worklog_id: str,
    ) -> None:
        try:
            client.delete_issue_worklog(issue_key, worklog_id)
        except Exception as exc:
            self.app.call_from_thread(
                self._handle_background_error,
                f'Failed to delete worklog for {issue_key}: {exc}',
            )
            return
        self.app.call_from_thread(self._after_delete, issue_key)

    def _after_submit(self, issue_key: str) -> None:
        self.query_one(WorklogDayGrid).clear_draft()
        self.issue_picker.clear_message()
        self._set_status(f'Worklog added for {issue_key}.', severity='information')
        self.refresh_day()

    def _after_update(self, issue_key: str) -> None:
        self._set_status(f'Worklog updated for {issue_key}.', severity='information')
        self.refresh_day()

    def _after_delete(self, issue_key: str) -> None:
        self._set_status(f'Worklog deleted for {issue_key}.', severity='information')
        self.refresh_day()

    def _set_status(self, message: str, *, severity: str) -> None:
        self.query_one('#worklog-status', Static).update(message)
        self.app.notify(message, severity=severity, timeout=2)

    def _handle_background_error(self, message: str) -> None:
        self._set_status(message, severity='error')

    def _update_time_axis(self) -> None:
        if not self.is_mounted:
            return

        grid = self.query_one(WorklogDayGrid)
        axis = self.query_one('#worklog-time-axis', Static)

        result = Text()
        # 增加一個空白行以與 Toolbar 對齊
        result.append('\n')
        for slot in range(SLOTS_PER_DAY):
            if slot > 0:
                result.append('\n')
            result.append_text(grid._render_time_axis_label(slot))

        axis.update(result)

    def _update_selected_day_label(self) -> None:
        label = self.query_one('#worklog-date-label', Static)
        label.update(self.selected_day.strftime('%Y-%m-%d'))

    def _update_draft_summary(self) -> None:
        label = self.query_one('#worklog-draft-summary', Static)
        grid = self.query_one(WorklogDayGrid) if self.is_mounted else None
        if grid is None or grid.draft_slots is None:
            label.update('No draft selected')
            return
        start_slot, end_slot = grid.draft_slots
        started, ended = selection_to_datetimes(
            self.selected_day,
            start_slot,
            end_slot,
            self._state.timezone,
        )
        duration = format_duration_label(selection_to_seconds(start_slot, end_slot))
        label.update(f'{started:%H:%M}-{ended:%H:%M} ({duration})')

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'worklog-prev-day-btn':
            self.go_to_previous_day()
        elif event.button.id == 'worklog-today-btn':
            self.go_to_today()
        elif event.button.id == 'worklog-next-day-btn':
            self.go_to_next_day()

    @on(WorklogDayGrid.SelectionChanged)
    def on_selection_changed(self, event: WorklogDayGrid.SelectionChanged) -> None:
        self.query_one(WorklogDayGrid).draft_slots = (event.start_slot, event.end_slot)
        self._update_draft_summary()

    @on(WorklogIssuePicker.SubmitRequested)
    def on_submit_requested(self) -> None:
        self.submit_worklog()

    @on(WorklogIssuePicker.IssueSelected)
    def on_issue_selected(self) -> None:
        self._update_draft_summary()

    @on(WorklogDayGrid.EntrySelected)
    def on_existing_entry_selected(self, event: WorklogDayGrid.EntrySelected) -> None:
        self.open_existing_worklog_editor(event.entry)
