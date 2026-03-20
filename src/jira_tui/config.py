"""設定檔管理與 Jira API 客戶端"""

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from .auth import ProfileStore
from .models import JiraSearchResult
from .models import JiraTransition
from .models import JiraUser


class Config(BaseSettings):
    """設定檔管理，從 .env 讀取設定"""

    model_config = SettingsConfigDict(
        env_prefix='JIRA_',
        env_file='.env',
        env_file_encoding='utf-8',
    )

    host: str =Field(default='',examples=['https://ccccc.atlassian.net'])
    user: str =Field(default='',examples=['xxxxx@ccccc.com'])
    token: str = Field(default='')
    jql: str = Field(default='')

    @property
    def is_configured(self) -> bool:
        """是否已有完整設定"""
        return bool(self.host and self.user and self.token)


def load_config() -> 'Config':
    """建立 Config 實例

    優先順序：
    1. 環境變數 / .env（pydantic-settings 原生行為）
    2. ~/.config/jira_tui/profiles.json active profile
    3. 空值
    """
    cfg = Config()
    if cfg.is_configured:
        return cfg

    profile = ProfileStore.get_active()
    if profile is None:
        return cfg
    return Config(
        host=cfg.host or profile.host,
        user=cfg.user or profile.user,
        token=cfg.token or profile.token,
        jql=cfg.jql or profile.jql,
    )


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
