"""Worklog issue picker widget."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import OptionList
from textual.widgets import Static
from textual.widgets.option_list import Option

from ..models import JiraIssue
from ..worklog import filter_candidate_issues
from ..worklog import format_duration_label
from .inputs import BlurInput
from .inputs import BlurTextArea


class WorklogIssuePicker(Vertical):
    """Search, select, and submit worklog issue data."""

    class SubmitRequested(Message):
        """Emitted when submit is requested."""

    class IssueSelected(Message):
        """Emitted when an issue is selected."""

        def __init__(self, issue: JiraIssue | None):
            self.issue = issue
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._issues: list[JiraIssue] = []
        self._filtered_issues: list[JiraIssue] = []
        self._selected_issue_key: str | None = None

    def compose(self) -> ComposeResult:
        yield Static('Subtask', classes='worklog-pane-title')
        yield BlurInput(placeholder='Search title or key', id='worklog-issue-filter')
        yield OptionList(id='worklog-issue-list')
        yield Static('', id='worklog-issue-meta')
        yield Static('Message', classes='worklog-pane-title')
        yield BlurTextArea(id='worklog-message')
        yield Button('Add Worklog', id='worklog-submit-btn', variant='primary')

    def set_issues(self, issues: list[JiraIssue]) -> None:
        self._issues = issues
        self._selected_issue_key = None if self._selected_issue_key not in {issue.key for issue in issues} else self._selected_issue_key
        self._refresh_options()
        self._update_meta()

    def select_issue(self, issue_key: str) -> None:
        self._selected_issue_key = issue_key
        self._update_meta()
        self.post_message(self.IssueSelected(self.selected_issue))

    def set_message(self, message: str) -> None:
        self.query_one('#worklog-message', BlurTextArea).text = message

    def get_message(self) -> str:
        return self.query_one('#worklog-message', BlurTextArea).text.strip()

    def clear_message(self) -> None:
        self.query_one('#worklog-message', BlurTextArea).text = ''

    @property
    def selected_issue(self) -> JiraIssue | None:
        if self._selected_issue_key is None:
            return None
        for issue in self._issues:
            if issue.key == self._selected_issue_key:
                return issue
        return None

    def _refresh_options(self) -> None:
        filter_text = self.query_one('#worklog-issue-filter', Input).value if self.is_mounted else ''
        self._filtered_issues = filter_candidate_issues(self._issues, filter_text)
        option_list = self.query_one('#worklog-issue-list', OptionList)
        option_list.clear_options()
        for issue in self._filtered_issues:
            option_list.add_option(Option(self._format_issue_label(issue), id=issue.key))

    def _format_issue_label(self, issue: JiraIssue) -> str:
        remaining = format_duration_label(issue.fields.time_estimate)
        spent = format_duration_label(issue.fields.time_spent)
        return f'{issue.key} {issue.fields.summary} [{spent}/{remaining}]'

    def _update_meta(self) -> None:
        meta = self.query_one('#worklog-issue-meta', Static)
        issue = self.selected_issue
        if issue is None:
            meta.update('No subtask selected')
            return
        remaining = format_duration_label(issue.fields.time_estimate)
        spent = format_duration_label(issue.fields.time_spent)
        meta.update(f'Selected: {issue.key}  Spent: {spent}  Remaining: {remaining}')

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == 'worklog-issue-filter':
            self._refresh_options()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != 'worklog-issue-list':
            return
        self._selected_issue_key = str(event.option.id)
        self._update_meta()
        self.post_message(self.IssueSelected(self.selected_issue))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'worklog-submit-btn':
            self.post_message(self.SubmitRequested())
