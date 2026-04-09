"""Jira API Pydantic Models"""

from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic.alias_generators import to_camel


class JiraModel(BaseModel):
    """Jira API Model 基底類別"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class JiraStatusCategory(JiraModel):
    """Jira 狀態分類"""

    key: str  # 'done', 'indeterminate', 'new'
    name: str = ''


class JiraStatus(JiraModel):
    """Jira Issue 狀態"""

    name: str
    status_category: JiraStatusCategory | None = Field(default=None, alias='statusCategory')


class JiraAssignee(JiraModel):
    """Jira Issue 負責人"""

    display_name: str = ''


class JiraPriority(JiraModel):
    """Jira Issue 優先權"""

    name: str


class JiraIssueType(JiraModel):
    """Jira Issue 類型"""

    name: str
    hierarchy_level: int = 0


class JiraProject(JiraModel):
    """Jira 專案"""

    key: str
    name: str = ''


class JiraParentFields(JiraModel):
    """Jira 父 Issue 欄位"""

    summary: str = ''
    issuetype: JiraIssueType | None = None
    status: JiraStatus | None = None


class JiraParent(JiraModel):
    """Jira 父 Issue（Epic/Initiative）"""

    key: str
    fields: JiraParentFields | None = None


class JiraSprint(JiraModel):
    """Jira Sprint"""

    id: int
    name: str = ''
    state: str = ''
    start_date: datetime | None = None
    end_date: datetime | None = None


class JiraTimeTracking(JiraModel):
    """Jira Time Tracking"""

    original_estimate: str | None = None


class JiraWorklogAuthor(JiraModel):
    """Jira Worklog 作者"""

    account_id: str = ''
    display_name: str = ''


class JiraWorklog(JiraModel):
    """Jira Worklog"""

    id: str
    author: JiraWorklogAuthor | None = None
    started: datetime
    time_spent_seconds: int = 0
    comment: dict | str | None = None


class JiraWorklogPage(JiraModel):
    """Jira Issue 欄位中的 worklog 分頁資料"""

    start_at: int = 0
    max_results: int = 0
    total: int | None = None
    worklogs: list[JiraWorklog] = []


class JiraIssueFields(JiraModel):
    """Jira Issue 欄位"""

    summary: str = ''
    status: JiraStatus | None = None
    assignee: JiraAssignee | None = None
    priority: JiraPriority | None = None
    issuetype: JiraIssueType | None = None
    project: JiraProject | None = None
    parent: JiraParent | None = None
    created: datetime | None = None
    updated: datetime | None = None
    duedate: datetime | None = None
    start_date: datetime | None = Field(default=None, validation_alias='customfield_10015')
    sprint: list[JiraSprint] | None = Field(default=None, validation_alias='customfield_10020')
    rank: str | None = Field(default=None, validation_alias='customfield_10019')
    story_points: float | None = Field(default=None, validation_alias='customfield_10033')
    time_tracking: JiraTimeTracking | None = Field(default=None, alias='timetracking')
    aggregate_time_original_estimate: int | None = Field(
        default=None, validation_alias='aggregatetimeoriginalestimate'
    )
    aggregate_time_estimate: int | None = Field(
        default=None, validation_alias='aggregatetimeestimate'
    )
    time_original_estimate: int | None = Field(
        default=None, validation_alias='timeoriginalestimate'
    )
    time_estimate: int | None = Field(
        default=None, validation_alias='timeestimate'
    )
    aggregate_time_spent: int | None = Field(
        default=None, validation_alias='aggregatetimespent'
    )
    time_spent: int | None = Field(
        default=None, validation_alias='timespent'
    )
    worklog: JiraWorklogPage | None = None


class JiraIssue(JiraModel):
    """Jira Issue"""

    key: str
    fields: JiraIssueFields


class JiraSearchResult(JiraModel):
    """Jira JQL 搜尋結果"""

    issues: list[JiraIssue] = []
    next_page_token: str | None = None
    is_last: bool = True


class JiraUser(JiraModel):
    """Jira 使用者"""

    account_id: str
    display_name: str = ''
    active: bool = True


class JiraTransitionTo(JiraModel):
    """Jira Transition 目標狀態"""

    id: str
    name: str
    status_category: JiraStatusCategory | None = Field(default=None, alias='statusCategory')


class JiraTransition(JiraModel):
    """Jira Transition"""

    id: str
    name: str
    to: JiraTransitionTo
