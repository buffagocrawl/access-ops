"""Read-only request aging for the local Operations view."""
from datetime import datetime, timedelta, timezone


DEMO_SLA_HOURS = 24
DEMO_SLA_TARGET = timedelta(hours=DEMO_SLA_HOURS)
UNRESOLVED_SLA_STATUSES = frozenset({
    "PENDING_APPROVAL",
    "EXCEPTION_REVIEW",
    "MANUAL_REVIEW",
    "PROVISIONING",
    "PROVISIONING_FAILED",
    "REVOCATION_FAILED",
})


def request_age(created_at: datetime, now: datetime) -> timedelta:
    """Return elapsed age using UTC, without changing any request data."""
    created = _as_utc(created_at)
    current = _as_utc(now)
    return max(current - created, timedelta(0))


def sla_status(created_at: datetime, now: datetime) -> str:
    """Return the presentation-only status for the illustrative 24-hour target."""
    return "Past target" if request_age(created_at, now) >= DEMO_SLA_TARGET else "Within target"


def format_age(age: timedelta) -> str:
    """Format a request age compactly for the Operations view."""
    total_minutes = max(0, int(age.total_seconds() // 60))
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes:02d}m"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
