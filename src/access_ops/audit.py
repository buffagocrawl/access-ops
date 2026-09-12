"""Audit records exclude employee reasons and raw provider errors."""
from .models import AuditEvent


def event_for(request, policy, event_type, previous_status, details):
    return AuditEvent(
        request_id=request.request_id, event_type=event_type, actor="access_ops",
        previous_status=previous_status, new_status=request.status,
        timestamp=request.updated_at, policy_version=policy.policy_version,
        details=f"Policy {policy.policy_id}: {details}",
    )
