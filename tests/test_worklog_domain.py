from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from jira_tui.models import JiraIssue
from jira_tui.worklog import WorklogEntry
from jira_tui.worklog import clamp_remaining_estimate
from jira_tui.worklog import datetime_to_slot_range
from jira_tui.worklog import extract_comment_text
from jira_tui.worklog import filter_candidate_issues
from jira_tui.worklog import filter_worklogs_for_day
from jira_tui.worklog import has_overlap
from jira_tui.worklog import normalize_slot_range
from jira_tui.worklog import selection_to_datetimes
from jira_tui.worklog import selection_to_seconds


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


class WorklogDomainTests(unittest.TestCase):
    def test_normalize_slot_range_orders_slots_and_keeps_end_exclusive(self) -> None:
        self.assertEqual((3, 7), normalize_slot_range(6, 3))

    def test_selection_to_datetimes_snaps_to_half_hour_slots(self) -> None:
        tz = ZoneInfo('Asia/Taipei')

        start_at, end_at = selection_to_datetimes(
            date(2026, 4, 9),
            2,
            5,
            tz,
        )

        self.assertEqual(datetime(2026, 4, 9, 9, 0, tzinfo=tz), start_at)
        self.assertEqual(datetime(2026, 4, 9, 10, 30, tzinfo=tz), end_at)

    def test_selection_to_seconds_returns_thirty_minute_units(self) -> None:
        self.assertEqual(90 * 60, selection_to_seconds(1, 4))

    def test_datetime_to_slot_range_rounds_non_half_hour_duration_up(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        start_slot, end_slot = datetime_to_slot_range(
            datetime(2026, 4, 9, 9, 0, tzinfo=tz),
            45 * 60,
        )
        self.assertEqual((2, 4), (start_slot, end_slot))

    def test_clamp_remaining_estimate_stops_at_zero(self) -> None:
        self.assertEqual(0, clamp_remaining_estimate(1800, 3600))

    def test_clamp_remaining_estimate_preserves_none(self) -> None:
        self.assertIsNone(clamp_remaining_estimate(None, 3600))

    def test_filter_candidate_issues_matches_key_and_summary_case_insensitively(self) -> None:
        issues = [
            make_issue('PROJ-1', 'Alpha task'),
            make_issue('PROJ-2', 'Beta task'),
            make_issue('OPS-3', 'Incident cleanup'),
        ]

        filtered = filter_candidate_issues(issues, 'proj-2')
        self.assertEqual(['PROJ-2'], [issue.key for issue in filtered])

        filtered = filter_candidate_issues(issues, 'alpha')
        self.assertEqual(['PROJ-1'], [issue.key for issue in filtered])

    def test_filter_worklogs_for_day_keeps_only_target_user_and_date(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        entries = [
            WorklogEntry(
                worklog_id='1',
                issue_key='PROJ-1',
                issue_summary='Alpha task',
                author_account_id='me',
                started=datetime(2026, 4, 9, 9, 0, tzinfo=tz),
                time_spent_seconds=3600,
                comment_text='focus work',
            ),
            WorklogEntry(
                worklog_id='2',
                issue_key='PROJ-2',
                issue_summary='Beta task',
                author_account_id='someone-else',
                started=datetime(2026, 4, 9, 10, 0, tzinfo=tz),
                time_spent_seconds=3600,
                comment_text='other user',
            ),
            WorklogEntry(
                worklog_id='3',
                issue_key='PROJ-3',
                issue_summary='Gamma task',
                author_account_id='me',
                started=datetime(2026, 4, 10, 9, 0, tzinfo=tz),
                time_spent_seconds=3600,
                comment_text='tomorrow',
            ),
        ]

        filtered = filter_worklogs_for_day(
            entries,
            selected_day=date(2026, 4, 9),
            account_id='me',
            timezone=tz,
        )

        self.assertEqual(['1'], [entry.worklog_id for entry in filtered])

    def test_has_overlap_detects_existing_block_collision(self) -> None:
        tz = ZoneInfo('Asia/Taipei')
        entries = [
            WorklogEntry(
                worklog_id='1',
                issue_key='PROJ-1',
                issue_summary='Alpha task',
                author_account_id='me',
                started=datetime(2026, 4, 9, 9, 0, tzinfo=tz),
                time_spent_seconds=3600,
                comment_text='focus work',
            )
        ]

        self.assertTrue(
            has_overlap(
                datetime(2026, 4, 9, 9, 30, tzinfo=tz),
                datetime(2026, 4, 9, 10, 30, tzinfo=tz),
                entries,
            )
        )

    def test_extract_comment_text_supports_plain_string_comments(self) -> None:
        self.assertEqual('plain text', extract_comment_text('plain text'))  # type: ignore[arg-type]
