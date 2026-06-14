"""Worklog domain helpers."""

import typing as t
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from pydantic import model_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from .models import JiraIssue
from .models import JiraWorklog


class _GridConfig(BaseSettings):
    """Worklog grid bounds, overridable via JIRA_ env vars / .env."""

    model_config = SettingsConfigDict(
        env_prefix='JIRA_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    worklog_day_start_hour: int = 6
    worklog_day_end_hour: int = 28
    worklog_slot_minutes: int = 60

    @model_validator(mode='after')
    def _check_grid_bounds(self) -> t.Self:
        if not 0 <= self.worklog_day_start_hour <= 23:
            raise ValueError('worklog_day_start_hour must be in 0..23')
        # 跨午夜的格子靠把小時 +24 換算，終點最遠只能到隔日 24:00 (=48)
        if not self.worklog_day_start_hour < self.worklog_day_end_hour <= 48:
            raise ValueError('worklog_day_end_hour must be in (worklog_day_start_hour, 48]')
        if self.worklog_slot_minutes not in ZOOM_SLOT_MINUTES:
            raise ValueError(f'worklog_slot_minutes must be one of {ZOOM_SLOT_MINUTES}')
        return self


ZOOM_SLOT_MINUTES: t.Final[tuple[int, ...]] = (30, 60, 120)
"""Selectable grid granularities, finest first (30m / 1h / 2h)."""

_grid_config = _GridConfig()

DAY_START_HOUR = _grid_config.worklog_day_start_hour
DAY_END_HOUR = _grid_config.worklog_day_end_hour
"""Exclusive grid end; values past 24 extend the logical day after midnight (max 48 = next-day 24:00)."""
DEFAULT_SLOT_MINUTES = _grid_config.worklog_slot_minutes


@dataclass(frozen=True, slots=True)
class GridScale:
    """Time-grid geometry: a fixed day window with a zoomable slot size."""

    slot_minutes: int = DEFAULT_SLOT_MINUTES
    day_start_hour: int = DAY_START_HOUR
    day_end_hour: int = DAY_END_HOUR

    @property
    def slot_seconds(self) -> int:
        return self.slot_minutes * 60

    @property
    def slots_per_day(self) -> int:
        return (self.day_end_hour - self.day_start_hour) * 60 // self.slot_minutes

    def seconds_to_slots_ceil(self, seconds: int) -> int:
        """Convert seconds into grid slots with ceil behavior."""
        if seconds <= 0:
            return 1
        return (seconds + self.slot_seconds - 1) // self.slot_seconds

    def started_to_slot(self, started: datetime) -> int:
        """Map a start time to its grid slot, wrapping after-midnight hours past 24."""
        hour = started.hour if started.hour >= self.day_start_hour else started.hour + 24
        minutes_from_start = (hour - self.day_start_hour) * 60 + started.minute
        return minutes_from_start // self.slot_minutes

    def datetime_to_slot_range(self, started: datetime, time_spent_seconds: int) -> tuple[int, int]:
        """Convert a worklog datetime range into grid slots."""
        start_slot = self.started_to_slot(started)
        return start_slot, start_slot + self.seconds_to_slots_ceil(time_spent_seconds)

    def selection_to_datetimes(
        self,
        selected_day: date,
        start_slot: int,
        end_slot: int,
        timezone: ZoneInfo,
    ) -> tuple[datetime, datetime]:
        """Convert slot offsets into timezone-aware datetimes."""
        day_start = datetime.combine(selected_day, time(hour=self.day_start_hour), tzinfo=timezone)
        return (
            day_start + timedelta(minutes=start_slot * self.slot_minutes),
            day_start + timedelta(minutes=end_slot * self.slot_minutes),
        )

    def selection_to_seconds(self, start_slot: int, end_slot: int) -> int:
        """Convert a slot range to seconds."""
        return max(0, end_slot - start_slot) * self.slot_seconds

    def is_hour_boundary(self, slot: int) -> bool:
        """Whether a slot starts exactly on a whole hour (so it gets a label)."""
        return (slot * self.slot_minutes) % 60 == 0

    def hour_at(self, slot: int) -> int:
        """The wall-clock hour (0..23) at the start of a slot."""
        return (self.day_start_hour + (slot * self.slot_minutes) // 60) % 24

    def zoomed(self, step: int) -> 'GridScale':
        """Return a scale one zoom step away (step<0 = finer, step>0 = coarser)."""
        levels = ZOOM_SLOT_MINUTES
        index = levels.index(self.slot_minutes) if self.slot_minutes in levels else levels.index(DEFAULT_SLOT_MINUTES)
        index = max(0, min(len(levels) - 1, index + step))
        return replace(self, slot_minutes=levels[index])


def resolve_timezone(timezone_name: str | None, fallback: str = 'Asia/Taipei') -> ZoneInfo:
    """Resolve timezone with a consistent fallback."""
    try:
        return ZoneInfo(timezone_name or fallback)
    except Exception:
        return ZoneInfo(fallback)


@dataclass(slots=True)
class WorklogEntry:
    """A day-view worklog block."""

    worklog_id: str
    issue_key: str
    issue_summary: str
    author_account_id: str
    started: datetime
    time_spent_seconds: int
    comment_text: str = ''

    @property
    def ended(self) -> datetime:
        return self.started + timedelta(seconds=self.time_spent_seconds)


def normalize_slot_range(anchor_slot: int, current_slot: int) -> tuple[int, int]:
    """Normalize a drag range to a start/end pair."""
    start_slot = min(anchor_slot, current_slot)
    end_slot = max(anchor_slot, current_slot) + 1
    return start_slot, end_slot


def clamp_remaining_estimate(
    remaining_seconds: int | None,
    logged_seconds: int,
) -> int | None:
    """Reduce remaining estimate without going below zero."""
    if remaining_seconds is None:
        return None
    return max(remaining_seconds - logged_seconds, 0)


def filter_candidate_issues(issues: list[JiraIssue], filter_text: str) -> list[JiraIssue]:
    """Filter candidate issues by key or summary."""
    normalized = filter_text.strip().lower()
    if not normalized:
        return list(issues)
    return [
        issue
        for issue in issues
        if normalized in issue.key.lower() or normalized in issue.fields.summary.lower()
    ]


def worklog_to_entry(worklog: JiraWorklog, issue: JiraIssue) -> WorklogEntry:
    """Convert Jira API worklog data to a day-view entry."""
    return WorklogEntry(
        worklog_id=worklog.id,
        issue_key=issue.key,
        issue_summary=issue.fields.summary,
        author_account_id=worklog.author.account_id if worklog.author else '',
        started=worklog.started,
        time_spent_seconds=worklog.time_spent_seconds,
        comment_text=extract_comment_text(worklog.comment),
    )


def collect_day_worklog_entries(
    day_issues: list[JiraIssue],
    *,
    selected_day: date,
    account_id: str,
    timezone: ZoneInfo,
    fetch_issue_worklogs: Callable[[str], list[JiraWorklog]] | None = None,
) -> list[WorklogEntry]:
    """Collect filtered worklog entries for a selected day."""
    entries: list[WorklogEntry] = []
    for issue in day_issues:
        worklog_page = issue.fields.worklog
        if worklog_page is None:
            worklogs = fetch_issue_worklogs(issue.key) if fetch_issue_worklogs else []
        elif worklog_page.total is not None and worklog_page.total > len(worklog_page.worklogs):
            worklogs = fetch_issue_worklogs(issue.key) if fetch_issue_worklogs else worklog_page.worklogs
        else:
            worklogs = worklog_page.worklogs
        for worklog in worklogs:
            entries.append(worklog_to_entry(worklog, issue))

    return filter_worklogs_for_day(
        entries,
        selected_day=selected_day,
        account_id=account_id,
        timezone=timezone,
    )


def filter_worklogs_for_day(
    entries: list[WorklogEntry],
    *,
    selected_day: date,
    account_id: str,
    timezone: ZoneInfo,
) -> list[WorklogEntry]:
    """Keep only the user's entries whose logical day matches; after-midnight entries count as the previous day."""
    overflow = timedelta(hours=max(0, DAY_END_HOUR - 24))
    return [
        entry
        for entry in entries
        if entry.author_account_id == account_id
        and (entry.started.astimezone(timezone) - overflow).date() == selected_day
    ]


def has_overlap(
    start_at: datetime,
    end_at: datetime,
    entries: list[WorklogEntry],
    *,
    ignore_worklog_id: str | None = None,
) -> bool:
    """Check if a proposed block overlaps an existing one."""
    for entry in entries:
        if ignore_worklog_id is not None and entry.worklog_id == ignore_worklog_id:
            continue
        if start_at < entry.ended and end_at > entry.started:
            return True
    return False


def seconds_to_jira_duration(seconds: int) -> str:
    """Convert seconds into Jira duration syntax."""
    if seconds <= 0:
        return '0m'

    total_minutes = seconds // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    days = hours // 8
    remaining_hours = hours % 8
    parts: list[str] = []
    if days > 0:
        parts.append(f'{days}d')
    if remaining_hours > 0:
        parts.append(f'{remaining_hours}h')
    if minutes > 0:
        parts.append(f'{minutes}m')
    return ' '.join(parts) if parts else '0m'


def format_duration_label(seconds: int | None) -> str:
    """Format a compact duration label for UI text."""
    if seconds is None:
        return '--'
    return seconds_to_jira_duration(seconds).replace(' ', '')


def extract_comment_text(comment: dict | None) -> str:
    """Extract plain text from Jira ADF comment payload."""
    if not comment:
        return ''
    if isinstance(comment, str):
        return comment
    content = comment.get('content', [])
    parts: list[str] = []
    for block in content:
        for item in block.get('content', []):
            text = item.get('text')
            if text:
                parts.append(str(text))
    return ''.join(parts)
