import os
import unittest
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

from jira_tui.app import JiraDashboard
from jira_tui.models import JiraIssue
from jira_tui.models import JiraWorklog
from jira_tui.screens.worklog_editor import WorklogDeleteResult
from jira_tui.screens.worklog_editor import WorklogEditorResult
from jira_tui.tabs.worklog import WorklogTab
from jira_tui.tabs.my_issues import MyIssuesTab
from jira_tui.widgets.tree import JiraTree
from jira_tui.widgets.worklog_day_grid import WorklogDayGrid
from jira_tui.worklog import WorklogEntry
from textual.geometry import Region
from textual.geometry import Size
from textual.geometry import Spacing
from textual.widgets import LoadingIndicator
from textual.widgets import Static
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
        self.day_worklog_issues = [
            JiraIssue.model_validate(
                {
                    'key': 'PROJ-1',
                    'fields': {
                        'summary': 'Alpha task',
                        'worklog': {
                            'worklogs': [
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
                            ]
                        },
                    },
                }
            )
        ]
        self.added_worklogs: list[dict] = []
        self.updated_worklogs: list[dict] = []
        self.deleted_worklogs: list[dict] = []

    def get_myself(self) -> dict:
        return self.myself

    def search_active_sprint_subtasks_for_current_user(self) -> list[JiraIssue]:
        return self.active_sprint_issues

    def search_day_worklog_issues_for_current_user(self, selected_day: date) -> list[JiraIssue]:
        if selected_day == date(2026, 4, 9):
            return self.day_worklog_issues
        return []

    def get_issue_worklogs(self, issue_key: str) -> list[JiraWorklog]:
        raise AssertionError('day view should use embedded worklogs from search results')

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

    def update_issue_worklog(
        self,
        issue_key: str,
        worklog_id: str,
        *,
        started: datetime,
        time_spent_seconds: int,
        comment_text: str,
    ) -> JiraWorklog:
        self.updated_worklogs.append(
            {
                'issue_key': issue_key,
                'worklog_id': worklog_id,
                'started': started,
                'time_spent_seconds': time_spent_seconds,
                'comment_text': comment_text,
            }
        )
        return JiraWorklog.model_validate(
            {
                'id': worklog_id,
                'author': {'accountId': 'me', 'displayName': 'Test User'},
                'started': started.strftime('%Y-%m-%dT%H:%M:%S.000%z'),
                'timeSpentSeconds': time_spent_seconds,
                'comment': comment_text,
            }
        )

    def delete_issue_worklog(self, issue_key: str, worklog_id: str) -> None:
        self.deleted_worklogs.append(
            {
                'issue_key': issue_key,
                'worklog_id': worklog_id,
            }
        )


class WorklogTestApp(JiraDashboard):
    def __init__(self, client: FakeJiraClient) -> None:
        self._test_client = client
        super().__init__()

    def _get_jira_client(self) -> FakeJiraClient:
        return self._test_client


class MeasuredWorklogDayGrid(WorklogDayGrid):
    def __init__(self, *, content_width: int, size_width: int, gutter_top: int) -> None:
        super().__init__()
        self._content_region = Region(0, 0, content_width, 24)
        self._size = Size(size_width, 24)
        self._gutter = Spacing(gutter_top, 0, 0, 0)

    @property
    def content_region(self) -> Region:
        return self._content_region

    @property
    def size(self) -> Size:
        return self._size

    @property
    def gutter(self) -> Spacing:
        return self._gutter


def make_tree_issue(
    key: str,
    summary: str,
    *,
    issue_type: str,
    project_key: str = 'PROJ',
    parent_key: str | None = None,
    parent_summary: str = '',
    parent_type: str = 'Story',
) -> JiraIssue:
    fields: dict = {
        'summary': summary,
        'issuetype': {'name': issue_type},
        'project': {'key': project_key, 'name': project_key},
    }
    if parent_key:
        fields['parent'] = {
            'key': parent_key,
            'fields': {
                'summary': parent_summary,
                'issuetype': {'name': parent_type},
            },
        }
    return JiraIssue.model_validate({'key': key, 'fields': fields})


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

    async def test_existing_worklog_first_line_shows_issue_key_and_summary(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            rendered = grid._render_slot_line(2, 80).plain
            self.assertIn('PROJ-1', rendered)
            self.assertIn('Alpha task', rendered)

    def test_one_hour_worklog_does_not_show_second_line_comment(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        entry = WorklogEntry(
            worklog_id='w1',
            issue_key='PROJ-1',
            issue_summary='Alpha task',
            author_account_id='me',
            started=datetime(2026, 4, 9, 9, 0, tzinfo=tz),
            time_spent_seconds=3600,
            comment_text='Focused implementation',
        )
        grid = WorklogDayGrid()
        grid.set_worklog_entries([entry])
        rendered = grid._render_slot_line(3, 80).plain.strip()
        self.assertEqual('', rendered)

    def test_two_hour_worklog_second_line_shows_comment_text(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        entry = WorklogEntry(
            worklog_id='w1',
            issue_key='PROJ-1',
            issue_summary='Alpha task',
            author_account_id='me',
            started=datetime(2026, 4, 9, 9, 0, tzinfo=tz),
            time_spent_seconds=7200,
            comment_text='Focused implementation',
        )
        grid = WorklogDayGrid()
        grid.set_worklog_entries([entry])
        rendered = grid._render_slot_line(3, 80).plain
        self.assertIn('Focused implementation', rendered)

    def test_existing_worklog_line_is_truncated_to_grid_width(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        entry = WorklogEntry(
            worklog_id='w1',
            issue_key='DP-834',
            issue_summary='嘗試 rebase 或其他做法 e.g. 重寫, 修改其他沒改到的',
            author_account_id='me',
            started=datetime(2026, 4, 9, 11, 0, tzinfo=tz),
            time_spent_seconds=3600,
            comment_text='comment',
        )
        grid = WorklogDayGrid()
        grid.set_worklog_entries([entry])
        rendered = grid._render_slot_line(6, 24)
        self.assertLessEqual(rendered.cell_len, 24)

    def test_adjacent_existing_worklogs_use_different_card_styles(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        first_entry = WorklogEntry(
            worklog_id='w1',
            issue_key='DP-833',
            issue_summary='Morning work',
            author_account_id='me',
            started=datetime(2026, 4, 9, 9, 0, tzinfo=tz),
            time_spent_seconds=2 * 3600,
            comment_text='first block',
        )
        second_entry = WorklogEntry(
            worklog_id='w2',
            issue_key='DP-834',
            issue_summary='Hand-off work',
            author_account_id='me',
            started=datetime(2026, 4, 9, 11, 0, tzinfo=tz),
            time_spent_seconds=3600,
            comment_text='second block',
        )
        third_entry = WorklogEntry(
            worklog_id='w3',
            issue_key='DP-835',
            issue_summary='Afternoon work',
            author_account_id='me',
            started=datetime(2026, 4, 9, 13, 0, tzinfo=tz),
            time_spent_seconds=3600,
            comment_text='third block',
        )
        grid = WorklogDayGrid()
        grid.set_worklog_entries([first_entry, second_entry, third_entry])
        self.assertNotEqual(grid._entry_style(first_entry), grid._entry_style(second_entry))
        self.assertEqual(grid._entry_style(first_entry), grid._entry_style(third_entry))

    def test_grid_uses_content_width_for_rendered_lines(self) -> None:
        grid = MeasuredWorklogDayGrid(content_width=50, size_width=52, gutter_top=1)
        self.assertEqual(50, grid._render_width())

    def test_grid_slot_mapping_accounts_for_top_gutter(self) -> None:
        grid = MeasuredWorklogDayGrid(content_width=50, size_width=52, gutter_top=1)
        self.assertIsNone(grid._slot_from_y(0))
        self.assertEqual(0, grid._slot_from_y(1))

    def test_grid_slot_uses_display_timezone_for_entry_placement(self) -> None:
        grid = WorklogDayGrid()
        grid.set_display_timezone(ZoneInfo('Asia/Taipei'))
        entry = WorklogEntry(
            worklog_id='w1',
            issue_key='PROJ-1',
            issue_summary='Alpha task',
            author_account_id='me',
            started=datetime(2026, 4, 9, 1, 0, tzinfo=ZoneInfo('UTC')),
            time_spent_seconds=3600,
            comment_text='',
        )
        self.assertEqual(2, grid._slot_index_for_entry(entry))

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

    async def test_stale_day_load_response_does_not_override_latest_selection(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            latest_day = date(2026, 4, 10)
            stale_day = date(2026, 4, 9)
            tab.set_selected_day(latest_day)
            tab._day_load_request_id = 2

            tab._apply_day_data(
                1,
                stale_day,
                ZoneInfo('Asia/Taipei'),
                self.client.active_sprint_issues,
                [],
            )
            await pilot.pause()
            self.assertEqual(latest_day, tab.selected_day)

    async def test_day_load_error_clears_loading_and_sets_status(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab._day_load_request_id = 1
            loading = tab.query_one('#worklog-loading', LoadingIndicator)
            loading.remove_class('hidden')

            tab._handle_day_load_error(1, 'load failed')
            await pilot.pause()

            self.assertTrue(loading.has_class('hidden'))
            status = tab.query_one('#worklog-status', Static)
            self.assertEqual('load failed', str(status.render()))

    async def test_mouse_drag_creates_a_draft_selection(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            await pilot.mouse_down('#worklog-day-grid', offset=(2, 6))
            await pilot.mouse_up('#worklog-day-grid', offset=(2, 8))
            await pilot.pause()

            grid = tab.query_one(WorklogDayGrid)
            self.assertEqual((5, 8), grid.draft_slots)

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

    async def test_click_existing_worklog_opens_editor_modal(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            await pilot.click('#worklog-day-grid', offset=(2, 3))
            await pilot.pause()

            self.assertEqual('WorklogEditorModal', self.app.screen_stack[-1].__class__.__name__)

    async def test_apply_worklog_editor_result_updates_existing_worklog(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            entry = tab.query_one(WorklogDayGrid).worklog_entries[0]
            result = WorklogEditorResult(
                issue_key=entry.issue_key,
                worklog_id=entry.worklog_id,
                started=datetime(2026, 4, 9, 10, 0, tzinfo=ZoneInfo('Asia/Taipei')),
                time_spent_seconds=1800,
                comment_text='Edited comment',
            )

            tab._on_worklog_editor_complete(result)
            await pilot.pause()

            self.assertEqual(1, len(self.client.updated_worklogs))
            payload = self.client.updated_worklogs[0]
            self.assertEqual('w1', payload['worklog_id'])
            self.assertEqual(1800, payload['time_spent_seconds'])
            self.assertEqual('Edited comment', payload['comment_text'])

    async def test_apply_worklog_delete_result_deletes_existing_worklog(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'worklog-tab'
            tab = self.app.query_one(WorklogTab)
            tab.set_selected_day(date(2026, 4, 9))
            tab.refresh_day()
            await pilot.pause()

            tab._on_worklog_editor_complete(
                WorklogDeleteResult(issue_key='PROJ-1', worklog_id='w1')
            )
            await pilot.pause()

            self.assertEqual([{'issue_key': 'PROJ-1', 'worklog_id': 'w1'}], self.client.deleted_worklogs)

    async def test_issue_tree_can_open_quick_add_worklog_modal_for_subtask(self) -> None:
        async with self.app.run_test() as pilot:
            self.app.query_one(TabbedContent).active = 'my-issues-tab'
            issues_tab = self.app.query_one(MyIssuesTab)
            issues_tab._on_search_complete(
                [
                    make_tree_issue('PROJ-100', 'Parent story', issue_type='Story'),
                    make_tree_issue(
                        'PROJ-101',
                        'Child subtask',
                        issue_type='Sub-task',
                        parent_key='PROJ-100',
                        parent_summary='Parent story',
                    ),
                ],
                [],
            )
            await pilot.pause()

            tree = issues_tab.query_one(JiraTree)
            subtask_node = next(
                node for node in tree._tree_nodes.values()
                if node.data and node.data.issue and node.data.issue.key == 'PROJ-101'
            )
            pushed: list[object] = []

            def _capture_push(screen, callback=None):
                pushed.append(screen)
                return None

            self.app.push_screen = _capture_push  # type: ignore[method-assign]
            tree._open_add_worklog_modal(subtask_node.data.issue)  # type: ignore[arg-type]
            await pilot.pause()

            self.assertEqual('WorklogEditorModal', pushed[-1].__class__.__name__)
            self.assertEqual(1, len(pushed[-1]._existing_entries))  # type: ignore[attr-defined]

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
