import os
import unittest
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

from jira_tui.app import JiraDashboard
from jira_tui.models import JiraIssue
from jira_tui.models import JiraWorklog
from jira_tui.tabs.worklog import WorklogTab
from jira_tui.widgets.worklog_day_grid import WorklogDayGrid
from textual.widgets import TabbedContent


def make_issue(
    key: str,
    summary: str,
    *,
    remaining_seconds: int | None = None,
    spent_seconds: int | None = None,
) -> JiraIssue:
    return JiraIssue.model_validate(
        {
            'key': key,
            'fields': {
                'summary': summary,
                'issuetype': {'name': 'Sub-task'},
                'timeestimate': remaining_seconds,
                'timespent': spent_seconds,
            },
        }
    )


class FakeJiraClient:
    def __init__(self) -> None:
        self.myself = {
            'accountId': 'me',
            'displayName': 'Test User',
            'timeZone': 'Asia/Taipei',
        }
        self.active_sprint_issues = [
            make_issue('PROJ-1', 'Alpha task', remaining_seconds=3600, spent_seconds=0),
            make_issue('PROJ-2', 'Beta bugfix', remaining_seconds=None, spent_seconds=1800),
        ]
        self.day_worklog_issues = [self.active_sprint_issues[0]]
        self.issue_worklogs = {
            'PROJ-1': [
                JiraWorklog.model_validate(
                    {
                        'id': 'w1',
                        'author': {'accountId': 'me', 'displayName': 'Test User'},
                        'started': '2026-04-09T09:00:00.000+0800',
                        'timeSpentSeconds': 3600,
                        'comment': {
                            'type': 'doc',
                            'version': 1,
                            'content': [
                                {
                                    'type': 'paragraph',
                                    'content': [
                                        {
                                            'type': 'text',
                                            'text': 'Focused implementation',
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                )
            ]
        }
        self.added_worklogs: list[dict] = []

    def get_myself(self) -> dict:
        return self.myself

    def search_active_sprint_subtasks_for_current_user(self) -> list[JiraIssue]:
        return self.active_sprint_issues

    def search_day_worklog_issues_for_current_user(self, selected_day: date) -> list[JiraIssue]:
        if selected_day == date(2026, 4, 9):
            return self.day_worklog_issues
        return []

    def get_issue_worklogs(self, issue_key: str) -> list[JiraWorklog]:
        return self.issue_worklogs.get(issue_key, [])

    def add_issue_worklog(
        self,
        issue_key: str,
        *,
        started: datetime,
        time_spent_seconds: int,
        comment_text: str,
        remaining_estimate_seconds: int | None,
    ) -> JiraWorklog:
        self.added_worklogs.append(
            {
                'issue_key': issue_key,
                'started': started,
                'time_spent_seconds': time_spent_seconds,
                'comment_text': comment_text,
                'remaining_estimate_seconds': remaining_estimate_seconds,
            }
        )
        return JiraWorklog.model_validate(
            {
                'id': f'new-{len(self.added_worklogs)}',
                'author': {'accountId': 'me', 'displayName': 'Test User'},
                'started': started.strftime('%Y-%m-%dT%H:%M:%S.000%z'),
                'timeSpentSeconds': time_spent_seconds,
            }
        )


class WorklogTestApp(JiraDashboard):
    def __init__(self, client: FakeJiraClient) -> None:
        self._test_client = client
        super().__init__()

    def _get_jira_client(self) -> FakeJiraClient:
        return self._test_client


class WorklogTabTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        os.environ['JIRA_HOST'] = 'https://example.atlassian.net'
        os.environ['JIRA_USER'] = 'user@example.com'
        os.environ['JIRA_TOKEN'] = 'token'
        self.client = FakeJiraClient()
        self.app = WorklogTestApp(self.client)

    async def test_worklog_tab_defaults_to_today_and_loads_existing_blocks(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            self.assertEqual(date(2026, 4, 9), tab.selected_day)
            self.assertEqual(1, len(grid.worklog_entries))

    async def test_existing_worklog_line_shows_time_range_and_duration(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            rendered = grid._render_slot_line(2, 80).plain
            self.assertIn('09:00-10:00 (1h)', rendered)
            self.assertIn('PROJ-1', rendered)

    async def test_existing_worklog_second_line_shows_comment_text(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            rendered = grid._render_slot_line(3, 80).plain
            self.assertIn('Focused implementation', rendered)

    async def test_worklog_day_navigation_actions_change_selected_day(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))

            self.app.action_worklog_next_day()
            await pilot.pause()
            self.assertEqual(date(2026, 4, 10), tab.selected_day)

            self.app.action_worklog_prev_day()
            await pilot.pause()
            self.assertEqual(date(2026, 4, 9), tab.selected_day)

    async def test_mouse_drag_creates_a_draft_selection(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            await pilot.mouse_down('#worklog-day-grid', offset=(2, 2))
            await pilot.mouse_up('#worklog-day-grid', offset=(2, 4))
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            self.assertEqual((2, 5), grid.draft_slots)

    async def test_submit_worklog_uses_selected_subtask_and_message(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            grid.set_draft_slots(4, 6)
            tab.issue_picker.select_issue('PROJ-1')
            tab.issue_picker.set_message('Deep focus')
            tab.submit_worklog()
            await pilot.pause()

            self.assertEqual(1, len(self.client.added_worklogs))
            payload = self.client.added_worklogs[0]
            self.assertEqual('PROJ-1', payload['issue_key'])
            self.assertEqual(3600, payload['time_spent_seconds'])
            self.assertEqual('Deep focus', payload['comment_text'])
            self.assertEqual(0, payload['remaining_estimate_seconds'])

    async def test_submit_without_selected_issue_is_rejected(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            grid.set_draft_slots(4, 6)
            tab.submit_worklog()
            await pilot.pause()

            self.assertEqual([], self.client.added_worklogs)
