"""UI-independent orchestration for permanent Engineering GitHub Read/Write access."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from .audit import event_for
from .approvals import manager_for
from .config import APPLICATION_ACCESS, Configuration
from .database import Database
from .integrations.mock_okta import AccessProvider, GrantResult
from .models import AccessRequest, AuditEvent, ApproverType, Decision, EmployeeStatus, RequestStatus
from .notifications import granted, pending, stopped
from .policy_engine import match_policy


class IntakeError(ValueError):
    """A fixed, employee-safe validation message."""


class Workflow:
    def __init__(self, configuration: Configuration, database: Database, provider: AccessProvider):
        self.configuration = configuration
        self.database = database
        self.provider = provider

    def _validate(self, employee_id, application, access_level, business_reason, duration):
        employee = self.configuration.employee(employee_id)
        if employee is None or employee.status != EmployeeStatus.ACTIVE:
            raise IntakeError("An active employee account is required. Contact IT; no access was granted.")
        if any(not isinstance(value, str) or not value.strip()
               for value in (application, access_level, business_reason, duration)):
            raise IntakeError("Provide application, access level, business reason, and duration. No request was processed.")
        if access_level not in APPLICATION_ACCESS.get(application, set()):
            raise IntakeError("Choose a supported application and access level. No request was processed.")
        policy = match_policy(self.configuration, employee_id, application, access_level)
        if policy is None or policy.decision not in (Decision.AUTO_APPROVE, Decision.APPROVAL_REQUIRED):
            raise IntakeError("This request cannot use automatic provisioning. Contact IT; no access was granted.")
        # Phase gate only: eligibility and approval decisions still come from CSV.
        if (application != "GitHub" or access_level not in ("Read", "Write")
                or employee.department != "Engineering"):
            raise IntakeError("This phase supports Engineering GitHub Read/Write only. Contact IT for other access.")
        if ((access_level == "Read" and policy.decision != Decision.AUTO_APPROVE)
                or (access_level == "Write" and (policy.decision != Decision.APPROVAL_REQUIRED
                    or policy.approver_type != ApproverType.MANAGER))):
            raise IntakeError("The configured approval path is unsupported. Contact IT; no access was granted.")
        if duration != "Permanent" or not policy.permanent_allowed:
            raise IntakeError("This workflow requires policy-permitted Permanent access. Contact IT for other durations.")
        return policy

    def submit(self, employee_id, application, access_level, business_reason, duration):
        try:
            policy = self._validate(employee_id, application, access_level, business_reason, duration)
            reviewer = None
            if policy.decision == Decision.APPROVAL_REQUIRED:
                reviewer = manager_for(self.configuration, employee_id, policy)
                if reviewer is None:
                    raise IntakeError("A valid manager could not be resolved. Contact IT; no access was granted.")
            now = datetime.now(timezone.utc)
            request = AccessRequest(
                request_id=f"REQ-{uuid4().hex}", requester_slack_id=employee_id,
                application=application, access_level=access_level, business_reason=business_reason,
                temporary=False, expires_at=None, created_at=now, updated_at=now,
                status=RequestStatus.PENDING_APPROVAL if reviewer else RequestStatus.APPROVED,
                assigned_approver_id=reviewer,
            )
            self.database.create(request, policy, event_for(
                request, policy, "REQUEST_SUBMITTED" if reviewer else "REQUEST_AUTO_APPROVED", None,
                "Request created pending manager approval." if reviewer else "Request created and automatically approved."
            ))
        except IntakeError as error:
            return stopped(str(error))
        except Exception:
            return stopped("The request could not be recorded safely. Contact IT; no access was granted.")
        return pending(request) if reviewer else self.process(request.request_id)

    def _record(self, request, event_type, details, actor="access_ops", status=None):
        updated = replace(request, status=status or request.status, updated_at=datetime.now(timezone.utc))
        policy_id, version = self.database.policy_reference(request.request_id)
        self.database.transition(updated, AuditEvent(
            request_id=request.request_id, event_type=event_type, actor=actor,
            previous_status=request.status, new_status=updated.status,
            timestamp=updated.updated_at, policy_version=version,
            details=f"Policy {policy_id}: {details}",
        ))
        return updated

    def approve(self, request_id, reviewer_id):
        """Reviewer identity is supplied by trusted local demo code, like intake identity."""
        try:
            request = self.database.get(request_id)
            if request is None:
                return stopped("Request not found. Check the request ID or contact IT.")
            request = self._record(request, "APPROVAL_ATTEMPTED", "Approval attempted.", reviewer_id)
            reviewer = self.configuration.employee(reviewer_id)
            if (request.status != RequestStatus.PENDING_APPROVAL
                    or reviewer_id == request.requester_slack_id
                    or not request.assigned_approver_id
                    or reviewer_id != request.assigned_approver_id
                    or reviewer is None or reviewer.status != EmployeeStatus.ACTIVE):
                self._record(request, "APPROVAL_REJECTED", "Reviewer or request state is not authorized.", reviewer_id)
                return stopped("Approval rejected. Only the assigned manager may approve a pending request; "
                               "self-approval is prohibited. No access was granted by this attempt.", request_id)
            self._record(request, "REQUEST_APPROVED", "Assigned manager approved the request.",
                         reviewer_id, RequestStatus.APPROVED)
        except Exception:
            return stopped("Approval stopped safely. Contact IT to check the request state.", request_id)
        return self.process(request_id)

    def process(self, request_id):
        """Internal entry point: load persisted state, never accept caller approval."""
        try:
            request = self.database.get(request_id)
            if request is None:
                return stopped("Request not found. Check the request ID or contact IT.")
            if request.status == RequestStatus.ACTIVE:
                return granted(request)
            if request.status == RequestStatus.PENDING_APPROVAL:
                return pending(request)
            if request.status != RequestStatus.APPROVED:
                return stopped("Processing is stopped. Contact IT to check the access state.", request_id)
            human = request.access_level == "Write"
            try:
                policy = self._validate(
                    request.requester_slack_id, request.application, request.access_level,
                    request.business_reason, "Permanent",
                )
                if self.database.policy_reference(request_id) != (policy.policy_id, policy.policy_version):
                    raise IntakeError("Policy changed. Contact IT; no provisioning was attempted.")
                if human:
                    reviewer = manager_for(self.configuration, request.requester_slack_id, policy)
                    if (reviewer is None or reviewer != request.assigned_approver_id
                            or not any(e.event_type == "REQUEST_APPROVED" and e.actor == reviewer
                                       for e in self.database.events(request_id))):
                        raise IntakeError("Manager approval is no longer valid. Contact IT; no access was granted.")
            except Exception:
                if human:
                    self._record(request, "REVALIDATION_FAILED", "Current employee, policy, or approval is invalid.",
                                 status=RequestStatus.REJECTED)
                raise
            if human:
                request = self._record(request, "REVALIDATION_SUCCEEDED", "Current employee, policy, and approval validated.")
            provisioning = replace(request, status=RequestStatus.PROVISIONING,
                                   updated_at=datetime.now(timezone.utc))
            # This transaction MUST commit before entering the provider boundary.
            self.database.transition(provisioning, event_for(
                provisioning, policy, "PROVISIONING_STARTED", request.status, "Authorized grant attempt."
            ))
            try:
                result = self.provider.grant(provisioning)
            except Exception:
                result = GrantResult.FAILED
            confirmed = isinstance(result, GrantResult) and result in (GrantResult.GRANTED, GrantResult.ALREADY_EXISTS)
            completed = replace(
                provisioning, status=RequestStatus.ACTIVE if confirmed else RequestStatus.PROVISIONING_FAILED,
                provisioning_result=result.value if isinstance(result, GrantResult) else GrantResult.FAILED.value,
                updated_at=datetime.now(timezone.utc),
            )
            self.database.transition(completed, event_for(
                completed, policy, "PROVISIONING_SUCCEEDED" if confirmed else "PROVISIONING_FAILED",
                provisioning.status, "Provider confirmed access." if confirmed else "Provider did not confirm access.",
            ))
            if confirmed:
                return granted(completed)
            return stopped("Access could not be confirmed. Contact IT with this request ID; do not resubmit.", request_id)
        except IntakeError as error:
            return stopped(str(error), request_id)
        except Exception:
            # Provider may have succeeded before a local completion-write failure.
            return stopped("Processing stopped safely. Contact IT to check the access state; do not resubmit.", request_id)
