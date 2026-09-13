"""Resolve one manager or exception reviewer from trusted configuration."""
from .models import ApproverType, Decision, EmployeeStatus


def configured_reviewer_ids(configuration):
    """Return active people who can currently be assigned a configured review.

    This only limits the local demo's identity picker. ``reviewer_for`` and the
    workflow still decide whether a specific person may act on a request.
    """
    reviewers = set()
    employees = [employee for employee in configuration.employees if employee.status == EmployeeStatus.ACTIVE]
    for policy in configuration.policies:
        app = configuration.application(policy.application)
        if (not policy.enabled or app is None or not app.enabled
                or policy.decision not in (Decision.APPROVAL_REQUIRED, Decision.EXCEPTION_REVIEW)):
            continue
        if policy.approver_type == ApproverType.MANAGER:
            for employee in employees:
                matches = (("*" in policy.eligible_departments or employee.department in policy.eligible_departments)
                           and ("*" in policy.eligible_titles or employee.title in policy.eligible_titles))
                manager = configuration.employee(employee.manager_slack_id)
                if matches and manager and manager.status == EmployeeStatus.ACTIVE and manager.slack_user_id != employee.slack_user_id:
                    reviewers.add(manager.slack_user_id)
        elif policy.approver_type in (ApproverType.APPLICATION_OWNER, ApproverType.IT_SECURITY):
            reviewer = configuration.employee(policy.approver_id)
            if reviewer and reviewer.status == EmployeeStatus.ACTIVE:
                reviewers.add(reviewer.slack_user_id)
    return tuple(sorted(reviewers))


def manager_for(configuration, requester_id, policy):
    employee = configuration.employee(requester_id)
    if employee is None or policy.approver_type != ApproverType.MANAGER:
        return None
    manager = configuration.employee(employee.manager_slack_id)
    if (manager is None or manager.status != EmployeeStatus.ACTIVE
            or manager.slack_user_id == requester_id):
        return None
    return manager.slack_user_id


def exception_reviewer_for(configuration, requester_id, policy):
    if (policy.decision != Decision.EXCEPTION_REVIEW or policy.approver_type not in
            (ApproverType.APPLICATION_OWNER, ApproverType.IT_SECURITY)):
        return None
    reviewer = configuration.employee(policy.approver_id)
    if (reviewer is None or reviewer.status != EmployeeStatus.ACTIVE
            or reviewer.slack_user_id == requester_id):
        return None
    return reviewer.slack_user_id


def reviewer_for(configuration, requester_id, policy):
    """Resolve the one reviewer required by the configured decision and type."""
    if policy.decision == Decision.EXCEPTION_REVIEW:
        return exception_reviewer_for(configuration, requester_id, policy)
    if policy.decision != Decision.APPROVAL_REQUIRED:
        return None
    if policy.approver_type == ApproverType.MANAGER:
        return manager_for(configuration, requester_id, policy)
    if policy.approver_type not in (ApproverType.APPLICATION_OWNER, ApproverType.IT_SECURITY):
        return None
    reviewer = configuration.employee(policy.approver_id)
    if (reviewer is None or reviewer.status != EmployeeStatus.ACTIVE
            or reviewer.slack_user_id == requester_id):
        return None
    return reviewer.slack_user_id
