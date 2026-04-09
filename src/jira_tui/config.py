"""設定檔管理與 Jira API 客戶端"""

from datetime import date
from datetime import datetime

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from .models import JiraSearchResult
from .models import JiraTransition
from .models import JiraUser
from .models import JiraWorklog
from .worklog import seconds_to_jira_duration


class Config(BaseSettings):
    """設定檔管理，從 .env 讀取設定"""

    model_config = SettingsConfigDict(
        env_prefix='JIRA_',
        env_file='.env',
        env_file_encoding='utf-8',
    )

    host: str =Field(default=...,examples=['https://ccccc.atlassian.net'])
    user: str =Field(default=...,examples=['xxxxx@ccccc.com'])
    token: str = Field(default=...)
    jql: str = Field(default='')


class JiraClient:
    """Jira API 客戶端"""

    def __init__(self, *, host: str, user: str, token: str):
        self.host = host.rstrip('/')
        self.user = user
        self.token = token

    def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """發送 API 請求"""
        url = f'{self.host}{endpoint}'
        return httpx.request(
            method,
            url,
            auth=(self.user, self.token),
            **kwargs,
        )

    def get_myself(self) -> dict:
        """取得目前使用者資訊"""
        response = self._request('GET', '/rest/api/3/myself')
        response.raise_for_status()
        return response.json()

    SEARCH_FIELDS = ','.join([
        'summary', 'status', 'assignee', 'priority', 'issuetype', 'project',
        'parent', 'created', 'updated', 'duedate', 'customfield_10015', 'customfield_10019', 'customfield_10020',
        'customfield_10033', 'aggregatetimeoriginalestimate', 'timeoriginalestimate',
        'aggregatetimeestimate', 'timeestimate', 'aggregatetimespent', 'timespent',
    ])

    def search_jql(self, jql: str, *, next_page_token: str | None = None) -> JiraSearchResult:
        """使用 JQL 搜尋 issues"""
        params: dict = {
            'jql': jql,
            'maxResults': 100,
            'fields': self.SEARCH_FIELDS,
        }
        if next_page_token:
            params['nextPageToken'] = next_page_token

        response = self._request('GET', '/rest/api/3/search/jql', params=params)
        response.raise_for_status()
        return JiraSearchResult(**response.json())

    def count_jql(self, jql: str) -> int:
        """取得 JQL 搜尋結果的大約數量"""
        response = self._request(
            'POST',
            '/rest/api/3/search/approximate-count',
            json={'jql': jql},
        )
        response.raise_for_status()
        return response.json().get('count', 0)

    def get_projects(self) -> list[dict]:
        """取得專案列表"""
        response = self._request('GET', '/rest/api/3/project')
        response.raise_for_status()
        return response.json()

    def search_assignable_users(self, *, project: str, max_results: int = 1000) -> list[JiraUser]:
        """取得專案可指派的使用者列表"""
        response = self._request(
            'GET',
            '/rest/api/3/user/assignable/search',
            params={'project': project, 'maxResults': max_results},
        )
        response.raise_for_status()
        return [JiraUser(**u) for u in response.json()]

    def search_active_sprint_subtasks_for_current_user(self) -> list:
        """取得目前使用者在 active sprint 的 subtasks。"""
        jql = 'assignee = currentUser() AND sprint in openSprints() AND issuetype in subTaskIssueTypes()'
        return self.search_jql(jql).issues

    def search_day_worklog_issues_for_current_user(self, selected_day: date) -> list:
        """取得指定日期有 worklog 的 issues。"""
        day_str = selected_day.strftime('%Y-%m-%d')
        jql = f'worklogAuthor = currentUser() AND worklogDate = "{day_str}"'
        return self.search_jql(jql).issues

    def get_issue_worklogs(self, issue_key: str) -> list[JiraWorklog]:
        """取得 issue worklogs。"""
        response = self._request(
            'GET',
            f'/rest/api/3/issue/{issue_key}/worklog',
        )
        response.raise_for_status()
        data = response.json()
        return [JiraWorklog(**worklog) for worklog in data.get('worklogs', [])]

    def add_issue_worklog(
        self,
        issue_key: str,
        *,
        started: datetime,
        time_spent_seconds: int,
        comment_text: str,
        remaining_estimate_seconds: int | None,
    ) -> JiraWorklog:
        """新增 worklog，並視情況更新 remaining estimate。"""
        params: dict[str, str] = {}
        if remaining_estimate_seconds is None:
            params['adjustEstimate'] = 'leave'
        else:
            params['adjustEstimate'] = 'new'
            params['newEstimate'] = seconds_to_jira_duration(remaining_estimate_seconds)

        payload: dict = {
            'started': started.strftime('%Y-%m-%dT%H:%M:%S.000%z'),
            'timeSpentSeconds': time_spent_seconds,
        }
        if comment_text:
            payload['comment'] = {
                'type': 'doc',
                'version': 1,
                'content': [
                    {
                        'type': 'paragraph',
                        'content': [
                            {
                                'type': 'text',
                                'text': comment_text,
                            }
                        ],
                    }
                ],
            }

        response = self._request(
            'POST',
            f'/rest/api/3/issue/{issue_key}/worklog',
            params=params,
            json=payload,
        )
        response.raise_for_status()
        return JiraWorklog(**response.json())

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """更新 issue 欄位"""
        response = self._request(
            'PUT',
            f'/rest/api/3/issue/{issue_key}',
            json={'fields': fields},
        )
        response.raise_for_status()

    def update_issue_timetracking(self, issue_key: str, original_estimate: str | None) -> None:
        """更新 issue 的 time tracking (original estimate)"""
        if original_estimate:
            payload = {
                'update': {
                    'timetracking': [{'edit': {'originalEstimate': original_estimate}}]
                }
            }
        else:
            # 清除時設為空字串
            payload = {
                'update': {
                    'timetracking': [{'edit': {'originalEstimate': ''}}]
                }
            }
        response = self._request(
            'PUT',
            f'/rest/api/3/issue/{issue_key}',
            json=payload,
        )
        response.raise_for_status()

    def rank_issue(
        self,
        issue_key: str,
        *,
        rank_before: str | None = None,
        rank_after: str | None = None,
    ) -> None:
        """更新 issue 的 rank（排序位置）

        Args:
            issue_key: 要移動的 issue key
            rank_before: 排在此 issue 之前
            rank_after: 排在此 issue 之後
        """
        data: dict = {'issues': [issue_key]}
        if rank_before:
            data['rankBeforeIssue'] = rank_before
        elif rank_after:
            data['rankAfterIssue'] = rank_after
        else:
            return

        response = self._request(
            'PUT',
            '/rest/agile/1.0/issue/rank',
            json=data,
        )
        response.raise_for_status()

    def get_transitions(self, issue_key: str) -> list[JiraTransition]:
        """取得 issue 可用的 transitions

        Args:
            issue_key: Issue key (例如 'PROJ-123')

        Returns:
            可用的 transitions 列表
        """
        response = self._request(
            'GET',
            f'/rest/api/3/issue/{issue_key}/transitions',
        )
        response.raise_for_status()
        data = response.json()
        return [JiraTransition(**t) for t in data.get('transitions', [])]

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        """執行 issue transition（變更狀態）

        Args:
            issue_key: Issue key (例如 'PROJ-123')
            transition_id: Transition ID
        """
        response = self._request(
            'POST',
            f'/rest/api/3/issue/{issue_key}/transitions',
            json={'transition': {'id': transition_id}},
        )
        response.raise_for_status()
