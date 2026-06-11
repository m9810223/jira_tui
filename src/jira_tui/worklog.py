"""Worklog domain helpers."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from .models import JiraIssue
from .models import JiraWorklog


DAY_START_HOUR = 8
DAY_END_HOUR = 26
"""Exclusive grid end; values past 24 extend the logical day after midnight (26 = 02:00)."""
SLOT_MINUTES = 30
SLOT_SECONDS = SLOT_MINUTES * 60
SLOTS_PER_DAY = (DAY_END_HOUR - DAY_START_HOUR) * 60 // SLOT_MINUTES


def seconds_to_slots_ceil(seconds: int) -> int:
    """Convert seconds into 30-minute slots with ceil behavior."""
    if seconds <= 0:
        return 1
    return (seconds + SLOT_SECONDS - 1) // SLOT_SECONDS


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


def selection_to_datetimes(
    selected_day: date,
    start_slot: int,
    end_slot: int,
    timezone: ZoneInfo,
) -> tuple[datetime, datetime]:
    """Convert slot offsets into timezone-aware datetimes."""
    day_start = datetime.combine(selected_day, time(hour=DAY_START_HOUR), tzinfo=timezone)
    start_at = day_start + timedelta(minutes=start_slot * SLOT_MINUTES)
    end_at = day_start + timedelta(minutes=end_slot * SLOT_MINUTES)
    return start_at, end_at


def selection_to_seconds(start_slot: int, end_slot: int) -> int:
    """Convert a slot range to seconds."""
    return max(0, end_slot - start_slot) * SLOT_SECONDS


def started_to_slot(started: datetime) -> int:
    """Map a start time to its grid slot, wrapping after-midnight hours past 24."""
    hour = started.hour if started.hour >= DAY_START_HOUR else started.hour + 24
    return (hour - DAY_START_HOUR) * 2 + started.minute // SLOT_MINUTES


def datetime_to_slot_range(started: datetime, time_spent_seconds: int) -> tuple[int, int]:
    """Convert a worklog datetime range into grid slots."""
    start_slot = started_to_slot(started)
    duration_slots = seconds_to_slots_ceil(time_spent_seconds)
    return start_slot, start_slot + duration_slots


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
