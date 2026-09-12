"""Exact policy selection; a match is not authorization to provision."""
from .config import Configuration, ConfigurationError
from .models import AccessPolicy, EmployeeStatus


def match_policy(
    configuration: Configuration, requester_slack_id: str, application: str, access_level: str
) -> AccessPolicy | None:
    """Return one rule or None (manual review); never infer permission.

    Duration and reviewer authorization belong to the future workflow.
    """
    employee = configuration.employee(requester_slack_id)
    if employee is None or employee.status != EmployeeStatus.ACTIVE:
        raise ValueError("Policy matching requires a known, active employee")
    matches = [
        p for p in configuration.policies
        if p.enabled and p.application == application and p.access_level == access_level
        and ("*" in p.eligible_departments or employee.department in p.eligible_departments)
        and ("*" in p.eligible_titles or employee.title in p.eligible_titles)
    ]
    if len(matches) > 1:
        raise ConfigurationError("Multiple policies match; no policy selected")
    return matches[0] if matches else None
