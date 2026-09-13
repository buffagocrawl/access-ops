"""Typed records; these models do not authorize access."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Decision(StrEnum):
    AUTO_APPROVE = "AUTO_APPROVE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    EXCEPTION_REVIEW = "EXCEPTION_REVIEW"
    REJECT = "REJECT"


class ApproverType(StrEnum):
    NONE = "NONE"
    MANAGER = "MANAGER"
    APPLICATION_OWNER = "APPLICATION_OWNER"
    IT_SECURITY = "IT_SECURITY"


class RequestStatus(StrEnum):
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    EXCEPTION_REVIEW = "EXCEPTION_REVIEW"
    APPROVED = "APPROVED"
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    PROVISIONING_FAILED = "PROVISIONING_FAILED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    REVOCATION_FAILED = "REVOCATION_FAILED"


class RevocationStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class Employee:
    slack_user_id: str
    name: str
    email: str
    department: str
    title: str
    manager_slack_id: str | None
    status: EmployeeStatus


@dataclass(frozen=True)
class AccessPolicy:
    policy_id: str
    application: str
    access_level: str
    eligible_departments: frozenset[str]
    eligible_titles: frozenset[str]
    decision: Decision
    approver_type: ApproverType
    approver_id: str | None
    temporary_allowed: bool
    max_duration_days: int
    permanent_allowed: bool
    enabled: bool
    policy_version: int


@dataclass(frozen=True)
class AccessRequest:
    request_id: str
    requester_slack_id: str
    application: str
    access_level: str
    business_reason: str
    temporary: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    status: RequestStatus = RequestStatus.NEEDS_INFORMATION
    assigned_approver_id: str | None = None
    provisioning_result: str | None = None
    duration: str = "Permanent"
    starts_at: datetime | None = None
    revocation_status: RevocationStatus = RevocationStatus.NOT_APPLICABLE


@dataclass(frozen=True)
class AuditEvent:
    request_id: str
    event_type: str
    actor: str
    previous_status: RequestStatus | None
    new_status: RequestStatus | None
    timestamp: datetime
    policy_version: int | None
    details: str
