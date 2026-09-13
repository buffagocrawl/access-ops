"""Resolve one manager or exception reviewer from trusted configuration."""
from .models import ApproverType, Decision, EmployeeStatus


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
