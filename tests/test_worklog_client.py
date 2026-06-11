from datetime import date
from datetime import datetime
import unittest

import httpx

from jira_tui.config import JiraClient


class _FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class CapturingJiraClient(JiraClient):
    def __init__(self) -> None:
        super().__init__(
            host='https://example.atlassian.net',
            user='user@example.com',
            token='token',
        )
        self.calls: list[tuple[str, str, dict]] = []

    def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        self.calls.append((method, endpoint, kwargs))
        payload = {
            'id': 'worklog-1',
            'started': '2026-04-09T08:00:00.000+0000',
            'timeSpentSeconds': 7200,
            'author': {'accountId': 'me', 'displayName': 'Test User'},
            'comment': 'test',
        }
        return _FakeResponse(payload)  # type: ignore[returnValue]


class WorklogClientTests(unittest.TestCase):
    def test_add_issue_worklog_uses_jira_assistant_style_payload(self) -> None:
        client = CapturingJiraClient()

        client.add_issue_worklog(
            'DP-835',
            started=datetime.fromisoformat('2026-04-09T08:00:00+00:00'),
            time_spent_seconds=7200,
            comment_text='test',
        )

        method, endpoint, kwargs = client.calls[-1]
        self.assertEqual('POST', method)
        self.assertEqual('/rest/api/2/issue/DP-835/worklog', endpoint)
        self.assertEqual({'adjustEstimate': 'AUTO'}, kwargs['params'])
        self.assertEqual(
            {
                'comment': 'test',
                'started': '2026-04-09T08:00:00.000+0000',
                'timeSpent': '2h',
            },
            kwargs['json'],
        )

    def test_update_issue_worklog_uses_jira_assistant_style_payload(self) -> None:
        client = CapturingJiraClient()

        client.update_issue_worklog(
            'DP-835',
            '20547',
            started=datetime.fromisoformat('2026-04-09T08:00:00+00:00'),
            time_spent_seconds=3600,
            comment_text='edited',
        )

        method, endpoint, kwargs = client.calls[-1]
        self.assertEqual('PUT', method)
        self.assertEqual('/rest/api/2/issue/DP-835/worklog/20547', endpoint)
        self.assertEqual(
            {
                'comment': 'edited',
                'started': '2026-04-09T08:00:00.000+0000',
                'timeSpent': '1h',
            },
            kwargs['json'],
        )

    def test_search_day_worklog_issues_jql_covers_after_midnight_window(self) -> None:
        client = CapturingJiraClient()

        client.search_day_worklog_issues_for_current_user(date(2026, 4, 9))

        method, endpoint, kwargs = client.calls[-1]
        self.assertEqual('GET', method)
        self.assertEqual('/rest/api/3/search/jql', endpoint)
        jql = kwargs['params']['jql']
        self.assertIn("worklogDate >= '2026-04-09'", jql)
        self.assertIn("worklogDate < '2026-04-11'", jql)

    def test_delete_issue_worklog_calls_api_2_endpoint(self) -> None:
        client = CapturingJiraClient()

        client.delete_issue_worklog('DP-835', '20547')

        method, endpoint, kwargs = client.calls[-1]
        self.assertEqual('DELETE', method)
        self.assertEqual('/rest/api/2/issue/DP-835/worklog/20547', endpoint)
        self.assertEqual({}, kwargs)
