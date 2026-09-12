"""Resolve the single manager reviewer from trusted configuration."""
from .models import ApproverType, EmployeeStatus


def manager_for(configuration, requester_id, policy):
    employee = configuration.employee(requester_id)
    if employee is None or policy.approver_type != ApproverType.MANAGER:
        return None
    manager = configuration.employee(employee.manager_slack_id)
    if (manager is None or manager.status != EmployeeStatus.ACTIVE
            or manager.slack_user_id == requester_id):
        return None
    return manager.slack_user_id
