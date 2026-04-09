"""Worklog day-view tab."""

from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

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
from ..worklog import DAY_END_HOUR
from ..worklog import DAY_START_HOUR
from ..worklog import SLOT_MINUTES
from ..worklog import WorklogEntry
from ..worklog import clamp_remaining_estimate
from ..worklog import filter_worklogs_for_day
from ..worklog import format_duration_label
from ..worklog import has_overlap
from ..worklog import selection_to_datetimes
from ..worklog import selection_to_seconds
from ..worklog import worklog_to_entry
from ..widgets.worklog_day_grid import WorklogDayGrid
from ..widgets.worklog_issue_picker import WorklogIssuePicker
from ._mixin import JiraClientMixin


class WorklogTab(JiraClientMixin, Vertical):
    """Calendar-like worklog entry tab."""

    def __init__(self) -> None:
        super().__init__()
        self._selected_day = datetime.now().date()
        self._timezone = ZoneInfo('Asia/Taipei')
        self._worklog_entries: list[WorklogEntry] = []
        self._candidate_issues: list[JiraIssue] = []

    @property
    def selected_day(self) -> date:
        return self._selected_day

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
        self._selected_day = self._today()
        self._update_time_axis()
        self._update_selected_day_label()
        self._update_draft_summary()
        self.refresh_day()

    def _today(self) -> date:
        return datetime.now(self._timezone).date()

    def set_selected_day(self, selected_day: date) -> None:
        self._selected_day = selected_day
        self._update_selected_day_label()
        self._update_draft_summary()

    def go_to_previous_day(self) -> None:
        self.set_selected_day(self._selected_day.fromordinal(self._selected_day.toordinal() - 1))
        self.refresh_day()

    def go_to_next_day(self) -> None:
        self.set_selected_day(self._selected_day.fromordinal(self._selected_day.toordinal() + 1))
        self.refresh_day()

    def go_to_today(self) -> None:
        self.set_selected_day(self._today())
        self.refresh_day()

    def refresh_day(self) -> None:
        client = self._get_jira_client(silent=True)
        if not client:
            return
        self.query_one('#worklog-loading', LoadingIndicator).remove_class('hidden')
        self.query_one('#worklog-status', Static).update('Loading worklog data...')
        self._load_day_data(client, self._selected_day)

    @work(thread=True)
    def _load_day_data(self, client: JiraClient, selected_day: date) -> None:
        myself = self.app.myself  # pyright: ignore[reportAttributeAccessIssue]
        if myself is None:
            myself = client.get_myself()
            self.app.myself = myself  # pyright: ignore[reportAttributeAccessIssue]

        timezone_name = myself.get('timeZone') or 'Asia/Taipei'
        try:
            timezone = ZoneInfo(timezone_name)
        except Exception:
            timezone = ZoneInfo('Asia/Taipei')

        candidate_issues = client.search_active_sprint_subtasks_for_current_user()
        day_issues = client.search_day_worklog_issues_for_current_user(selected_day)
        entries: list[WorklogEntry] = []
        for issue in day_issues:
            worklog_page = issue.fields.worklog
            if worklog_page is None:
                worklogs = client.get_issue_worklogs(issue.key)
            elif worklog_page.total is not None and worklog_page.total > len(worklog_page.worklogs):
                worklogs = client.get_issue_worklogs(issue.key)
            else:
                worklogs = worklog_page.worklogs
            for worklog in worklogs:
                entries.append(worklog_to_entry(worklog, issue))

        filtered_entries = filter_worklogs_for_day(
            entries,
            selected_day=selected_day,
            account_id=myself.get('accountId', ''),
            timezone=timezone,
        )

        self.app.call_from_thread(
            self._apply_day_data,
            selected_day,
            timezone,
            candidate_issues,
            filtered_entries,
        )

    def _apply_day_data(
        self,
        selected_day: date,
        timezone: ZoneInfo,
        candidate_issues: list[JiraIssue],
        worklog_entries: list[WorklogEntry],
    ) -> None:
        self._selected_day = selected_day
        self._timezone = timezone
        self._candidate_issues = candidate_issues
        self._worklog_entries = worklog_entries
        self.issue_picker.set_issues(candidate_issues)
        self.query_one(WorklogDayGrid).set_worklog_entries(worklog_entries)
        self.query_one('#worklog-loading', LoadingIndicator).add_class('hidden')
        self.query_one('#worklog-status', Static).update(
            f'{len(worklog_entries)} worklogs, {len(candidate_issues)} candidate subtasks'
        )
        self._update_selected_day_label()
        self._update_draft_summary()

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
            self._selected_day,
            start_slot,
            end_slot,
            self._timezone,
        )
        if has_overlap(started, ended, self._worklog_entries):
            self._set_status('The selected range overlaps an existing worklog.', severity='error')
            return

        client = self._get_jira_client(silent=True)
        if not client:
            return

        remaining_estimate_seconds = clamp_remaining_estimate(
            issue.fields.time_estimate,
            selection_to_seconds(start_slot, end_slot),
        )
        self._submit_worklog(
            client,
            issue,
            started,
            selection_to_seconds(start_slot, end_slot),
            self.issue_picker.get_message(),
            remaining_estimate_seconds,
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
                selected_day=self._selected_day,
                timezone=self._timezone,
                existing_entries=self._worklog_entries,
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
                None,
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
        remaining_estimate_seconds: int | None,
    ) -> None:
        client.add_issue_worklog(
            issue.key,
            started=started,
            time_spent_seconds=time_spent_seconds,
            comment_text=comment_text,
            remaining_estimate_seconds=remaining_estimate_seconds,
        )
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
        client.update_issue_worklog(
            issue_key,
            worklog_id,
            started=started,
            time_spent_seconds=time_spent_seconds,
            comment_text=comment_text,
        )
        self.app.call_from_thread(self._after_update, issue_key)

    @work(thread=True)
    def _delete_worklog(
        self,
        client: JiraClient,
        issue_key: str,
        worklog_id: str,
    ) -> None:
        client.delete_issue_worklog(issue_key, worklog_id)
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

    def _update_time_axis(self) -> None:
        axis = self.query_one('#worklog-time-axis', Static)
        labels = []
        total_slots = (DAY_END_HOUR - DAY_START_HOUR) * 60 // SLOT_MINUTES
        for slot in range(total_slots):
            hour = DAY_START_HOUR + (slot * SLOT_MINUTES) // 60
            minute = (slot * SLOT_MINUTES) % 60
            labels.append(f'{hour:02d}:{minute:02d}')
        axis.update('\n'.join(labels))

    def _update_selected_day_label(self) -> None:
        label = self.query_one('#worklog-date-label', Static)
        label.update(self._selected_day.strftime('%Y-%m-%d'))

    def _update_draft_summary(self) -> None:
        label = self.query_one('#worklog-draft-summary', Static)
        grid = self.query_one(WorklogDayGrid) if self.is_mounted else None
        if grid is None or grid.draft_slots is None:
            label.update('No draft selected')
            return
        start_slot, end_slot = grid.draft_slots
        started, ended = selection_to_datetimes(
            self._selected_day,
            start_slot,
            end_slot,
            self._timezone,
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
