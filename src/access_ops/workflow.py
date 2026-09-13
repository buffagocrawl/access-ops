"""UI-independent orchestration for GitHub access and single-reviewer exceptions."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .audit import event_for
from .approvals import manager_for, exception_reviewer_for
from .config import APPLICATION_ACCESS, Configuration, ConfigurationError
from .database import Database
from .integrations.mock_okta import AccessProvider, GrantResult, TransientProviderError, operation_id
from .models import AccessRequest, AuditEvent, ApproverType, Decision, EmployeeStatus, RequestStatus, RevocationStatus
from .notifications import granted, pending, exception_pending, stopped
from .policy_engine import match_policy


DURATION_DAYS = {"1 day": 1, "7 days": 7, "30 days": 30, "90 days": 90, "Permanent": None}
MAX_PROVIDER_ATTEMPTS = 3


def utc_time(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Current time must be timezone-aware")
    return value.astimezone(timezone.utc)


class IntakeError(ValueError):
    """A fixed, employee-safe validation message and deterministic intake outcome."""

    def __init__(self, message, status=RequestStatus.REJECTED):
        super().__init__(message)
        self.status = status


class Workflow:
    def __init__(self, configuration: Configuration, database: Database, provider: AccessProvider, clock=None):
        self.configuration = configuration
        self.database = database
        self.provider = provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        return utc_time(self.clock())

    def _validate(self, employee_id, application, access_level, business_reason, duration):
        employee = self.configuration.employee(employee_id)
        if employee is None:
            raise IntakeError("Your employee account was not found in the trusted directory. Contact IT to verify your account; no access was granted.")
        if employee.status != EmployeeStatus.ACTIVE:
            raise IntakeError("Your employee account is inactive, so this request cannot be processed automatically. Contact IT; no access was granted.")
        if not isinstance(business_reason, str) or not business_reason.strip():
            raise IntakeError("Provide a business reason and submit the request again. No access was granted.",
                              RequestStatus.NEEDS_INFORMATION)
        if any(not isinstance(value, str) or not value.strip()
               for value in (application, access_level, business_reason, duration)):
            raise IntakeError("Provide application, access level, business reason, and duration, then submit again. No access was granted.", RequestStatus.NEEDS_INFORMATION)
        if application not in APPLICATION_ACCESS:
            raise IntakeError("The requested application is unsupported. Choose an application from the catalog or contact IT; no access was granted.")
        if access_level not in APPLICATION_ACCESS[application]:
            raise IntakeError(f"The requested access level is unsupported for {application}. Choose a listed access level or contact IT; no access was granted.")
        policy = match_policy(self.configuration, employee_id, application, access_level)
        if policy is None:
            raise IntakeError("No enabled policy matches this request. Contact IT for review and configuration correction; no access was granted.")
        if policy.decision not in (Decision.AUTO_APPROVE, Decision.APPROVAL_REQUIRED, Decision.EXCEPTION_REVIEW):
            raise IntakeError("This request cannot use automatic provisioning. Contact IT; no access was granted.")
        exception = policy.decision == Decision.EXCEPTION_REVIEW
        # Phase gate only: eligibility and approval decisions still come from CSV.
        if (application != "GitHub" or access_level not in ("Read", "Write")
                or (not exception and employee.department != "Engineering")):
            raise IntakeError("This phase supports Engineering GitHub Read/Write and configured GitHub Write "
                              "exceptions. Contact IT for other access.")
        if ((exception and (access_level != "Write" or policy.approver_type not in
                            (ApproverType.APPLICATION_OWNER, ApproverType.IT_SECURITY)))
                or (access_level == "Read" and policy.decision != Decision.AUTO_APPROVE)
                or (access_level == "Write" and not exception and (policy.decision != Decision.APPROVAL_REQUIRED
                    or policy.approver_type != ApproverType.MANAGER))):
            raise IntakeError("The configured approval path is unsupported. Contact IT; no access was granted.")
        if duration not in DURATION_DAYS:
            raise IntakeError("Unsupported duration. Choose 1 day, 7 days, 30 days, 90 days, or Permanent; no access was granted.")
        days = DURATION_DAYS[duration]
        if days is None:
            if not policy.permanent_allowed:
                raise IntakeError("Permanent access is not allowed by this policy; no access was granted.")
        elif not policy.temporary_allowed or days > policy.max_duration_days:
            raise IntakeError("The requested temporary duration is not allowed by this policy; no access was granted.")
        return policy

    def submit(self, employee_id, application, access_level, business_reason, duration):
        try:
            policy = self._validate(employee_id, application, access_level, business_reason, duration)
            reviewer = None
            if policy.decision == Decision.APPROVAL_REQUIRED:
                reviewer = manager_for(self.configuration, employee_id, policy)
            exception = policy.decision == Decision.EXCEPTION_REVIEW
            if exception:
                reviewer = exception_reviewer_for(self.configuration, employee_id, policy)
            now = self._now()
            request = AccessRequest(
                request_id=f"REQ-{uuid4().hex}", requester_slack_id=employee_id,
                application=application, access_level=access_level, business_reason=business_reason,
                temporary=duration != "Permanent", duration=duration,
                expires_at=None, created_at=now, updated_at=now,
                revocation_status=(RevocationStatus.PENDING if duration != "Permanent"
                                   else RevocationStatus.NOT_APPLICABLE),
                status=(RequestStatus.EXCEPTION_REVIEW if exception else
                        RequestStatus.PENDING_APPROVAL if policy.decision == Decision.APPROVAL_REQUIRED else RequestStatus.APPROVED),
                assigned_approver_id=reviewer,
            )
            self.database.create(request, policy, event_for(
                request, policy, "EXCEPTION_DETECTED" if exception else
                "REQUEST_SUBMITTED" if policy.decision == Decision.APPROVAL_REQUIRED else "REQUEST_AUTO_APPROVED", None,
                "Request is outside normal eligibility; exception review required." if exception else
                "Request created pending manager approval." if policy.decision == Decision.APPROVAL_REQUIRED else "Request created and automatically approved."
            ))
            if exception:
                request = self._record(
                    request, "EXCEPTION_ROUTED" if reviewer else "EXCEPTION_ROUTING_FAILED",
                    f"Assigned exception reviewer {reviewer}." if reviewer else
                    "Configured exception reviewer could not be resolved; review is blocked.",
                )
            elif policy.decision == Decision.APPROVAL_REQUIRED and reviewer is None:
                request = self._record(request, "APPROVAL_ROUTING_FAILED",
                                       "Configured manager could not be resolved; review is blocked.")
        except ConfigurationError:
            return self._intake_stopped("Policy configuration cannot safely resolve this request. Contact IT for configuration correction; no access was granted.", RequestStatus.REJECTED)
        except IntakeError as error:
            return self._intake_stopped(str(error), error.status)
        except Exception:
            return stopped("The request could not be recorded safely. Contact IT; no access was granted.")
        if exception:
            return exception_pending(request)
        return pending(request) if policy.decision == Decision.APPROVAL_REQUIRED else self.process(request.request_id)

    def _intake_stopped(self, message, status):
        # Requests require a matched policy. Preserve pre-policy failures in the
        # existing audit store without inventing employee or policy records.
        request_id = f"REQ-{uuid4().hex}"
        try:
            with self.database.connection:
                self.database.append_event(AuditEvent(
                    request_id=request_id, event_type="INTAKE_STOPPED", actor="access_ops",
                    previous_status=None, new_status=status, timestamp=self._now(),
                    policy_version=None, details=message,
                ))
        except Exception:
            return stopped("The request could not be recorded safely. Contact IT; no access was granted.")
        return stopped(message, request_id)

    def _record(self, request, event_type, details, actor="access_ops", status=None, now=None):
        updated = replace(request, status=status or request.status, updated_at=now if now is not None else self._now())
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
        return self._review(request_id, reviewer_id)

    def reject(self, request_id, reviewer_id):
        """Reject a pending exception using the same reviewer authorization checks."""
        return self._review(request_id, reviewer_id, reject=True)

    def _review(self, request_id, reviewer_id, reject=False):
        try:
            request = self.database.get(request_id)
            if request is None:
                return stopped("Request not found. Check the request ID or contact IT.")
            request = self._record(request, "APPROVAL_ATTEMPTED",
                                   "Rejection attempted." if reject else "Approval attempted.", reviewer_id)
            reviewer = self.configuration.employee(reviewer_id)
            exception = request.status == RequestStatus.EXCEPTION_REVIEW
            current_reviewer = None
            if exception:
                saved_id, _ = self.database.policy_reference(request_id)
                policy = next((p for p in self.configuration.policies
                               if p.policy_id == saved_id and p.enabled), None)
                if policy is not None:
                    current_reviewer = exception_reviewer_for(
                        self.configuration, request.requester_slack_id, policy)
            if (request.status not in (RequestStatus.PENDING_APPROVAL, RequestStatus.EXCEPTION_REVIEW)
                    or (reject and not exception)
                    or (exception and current_reviewer != reviewer_id)
                    or reviewer_id == request.requester_slack_id
                    or not request.assigned_approver_id
                    or reviewer_id != request.assigned_approver_id
                    or reviewer is None or reviewer.status != EmployeeStatus.ACTIVE):
                self._record(request, "APPROVAL_REJECTED", "Reviewer or request state is not authorized.", reviewer_id)
                return stopped("Approval rejected. Only the assigned reviewer may decide a pending request; "
                               "self-approval is prohibited. No access was granted by this attempt.", request_id)
            if reject:
                self._record(request, "EXCEPTION_REJECTED", "Assigned reviewer rejected the exception.",
                             reviewer_id, RequestStatus.REJECTED)
                return stopped("Your exception request was rejected by the assigned reviewer. "
                               "No access was granted. Contact IT for further guidance.", request_id)
            self._record(request, "EXCEPTION_APPROVED" if exception else "REQUEST_APPROVED",
                         "Assigned reviewer approved the exception." if exception else
                         "Assigned manager approved the request.",
                         reviewer_id, RequestStatus.APPROVED)
        except Exception:
            return stopped("Approval stopped safely. Contact IT to check the request state.", request_id)
        return self.process(request_id)

    def _provider_operation(self, request, operation, now=None):
        """Retry only the provider call; authorization and audit errors stay outside."""
        key = operation_id(request, operation)
        failed = GrantResult.FAILED if operation == "grant" else False
        for attempt in range(1, MAX_PROVIDER_ATTEMPTS + 1):
            transient = False
            try:
                result = getattr(self.provider, operation)(request)
            except TransientProviderError:
                result, transient = failed, True
            except Exception:
                result = failed
            confirmed = (isinstance(result, GrantResult) and result in
                         (GrantResult.GRANTED, GrantResult.ALREADY_EXISTS)) if operation == "grant" else result is True
            if confirmed:
                return result, attempt
            request = self._record(
                request, "PROVIDER_ATTEMPT_FAILED",
                f"Operation {key}; {operation} attempt {attempt}; "
                f"{'transient' if transient else 'non-retryable'} failure.", now=now,
            )
            if not transient or attempt == MAX_PROVIDER_ATTEMPTS:
                return failed, attempt
            # Commit retry intent before another consequential provider call.
            request = self._record(request, "PROVIDER_RETRYING",
                                   f"Operation {key}; {operation} attempt {attempt + 1} of "
                                   f"{MAX_PROVIDER_ATTEMPTS}.", now=now)

    def process(self, request_id):
        """Internal entry point: load persisted state, never accept caller approval."""
        try:
            request = self.database.get(request_id)
            if request is None:
                return stopped("Request not found. Check the request ID or contact IT.")
            if request.status == RequestStatus.ACTIVE:
                return granted(request)
            if request.status == RequestStatus.EXCEPTION_REVIEW:
                return exception_pending(request)
            if request.status == RequestStatus.PENDING_APPROVAL:
                return pending(request)
            if request.status != RequestStatus.APPROVED:
                return stopped("Processing is stopped. Contact IT to check the access state.", request_id)
            human = request.access_level == "Write"
            try:
                policy = self._validate(
                    request.requester_slack_id, request.application, request.access_level,
                    request.business_reason, request.duration,
                )
                if request.temporary != (request.duration != "Permanent"):
                    raise IntakeError("Stored duration is inconsistent; no access was granted.")
                if self.database.policy_reference(request_id) != (policy.policy_id, policy.policy_version):
                    raise IntakeError("Policy changed. Contact IT; no provisioning was attempted.")
                if human:
                    exception = policy.decision == Decision.EXCEPTION_REVIEW
                    resolver = exception_reviewer_for if exception else manager_for
                    reviewer = resolver(self.configuration, request.requester_slack_id, policy)
                    approval_event = "EXCEPTION_APPROVED" if exception else "REQUEST_APPROVED"
                    if (reviewer is None or reviewer != request.assigned_approver_id
                            or not any(e.event_type == approval_event and e.actor == reviewer
                                       for e in self.database.events(request_id))):
                        raise IntakeError("Reviewer approval is no longer valid. Contact IT; no access was granted.")
            except Exception:
                self._record(request, "REVALIDATION_FAILED", "Current employee, policy, or approval is invalid.",
                             status=RequestStatus.REJECTED)
                raise
            if human:
                request = self._record(request, "REVALIDATION_SUCCEEDED", "Current employee, policy, and approval validated.")
            provisioning = replace(request, status=RequestStatus.PROVISIONING,
                                   updated_at=self._now())
            # This transaction MUST commit before entering the provider boundary.
            self.database.transition(provisioning, event_for(
                provisioning, policy, "PROVISIONING_STARTED", request.status,
                f"Authorized grant attempt 1; operation {operation_id(request, 'grant')}."
            ))
            result, attempt = self._provider_operation(provisioning, "grant")
            confirmed = isinstance(result, GrantResult) and result in (GrantResult.GRANTED, GrantResult.ALREADY_EXISTS)
            # Existing access cannot establish a new temporary grant or expiry.
            if request.temporary and result == GrantResult.ALREADY_EXISTS:
                confirmed = False
            started = self._now() if confirmed and result == GrantResult.GRANTED else None
            completed = replace(
                provisioning, status=RequestStatus.ACTIVE if confirmed else RequestStatus.PROVISIONING_FAILED,
                starts_at=started,
                expires_at=(started + timedelta(days=DURATION_DAYS[request.duration])
                            if started is not None and request.temporary else None),
                provisioning_result=result.value if isinstance(result, GrantResult) else GrantResult.FAILED.value,
                updated_at=self._now(),
            )
            self.database.transition(completed, event_for(
                completed, policy, "PROVISIONING_SUCCEEDED" if confirmed else "PROVISIONING_FAILED",
                provisioning.status, ("Provider confirmed access." if confirmed else "Provider did not confirm access.")
                + f" Operation {operation_id(request, 'grant')}; grant attempt {attempt}.",
            ))
            if confirmed:
                return granted(completed)
            return stopped("Approval succeeded, but provisioning failed. Access could not be confirmed. "
                           "Contact IT with this request ID; do not resubmit.", request_id)
        except IntakeError as error:
            return stopped(str(error), request_id)
        except Exception:
            # Provider may have succeeded before a local completion-write failure.
            return stopped("Processing stopped safely. Contact IT to check the access state; do not resubmit.", request_id)

    def process_expired_access(self, now=None):
        """Manually expire stored grants with bounded transient provider retries."""
        now = utc_time(now) if now is not None else self._now()
        responses = []
        for request in self.database.active_temporary_requests():
            try:
                if request.expires_at > now:
                    continue
                days = DURATION_DAYS.get(request.duration)
                if (days is None or request.starts_at is None
                        or request.expires_at != request.starts_at + timedelta(days=days)
                        or request.provisioning_result != GrantResult.GRANTED
                        or not any(e.event_type == "PROVISIONING_SUCCEEDED"
                                   and e.new_status == RequestStatus.ACTIVE
                                   for e in self.database.events(request.request_id))):
                    self._record(request, "REVOCATION_BLOCKED", "Stored grant lifecycle is inconsistent.", now=now)
                    responses.append(stopped("Expiration stopped safely. Contact IT to check the stored grant.", request.request_id))
                    continue
                request = self._record(request, "ACCESS_EXPIRED", "Temporary access reached its expiration.",
                                       status=RequestStatus.EXPIRED, now=now)
                request = self._record(request, "REVOCATION_STARTED",
                                       f"Removing the stored request grant; revoke attempt 1; "
                                       f"operation {operation_id(request, 'revoke')}.", now=now)
                removed, attempt = self._provider_operation(request, "revoke", now=now)
                outcome = f" Operation {operation_id(request, 'revoke')}; revoke attempt {attempt}."
                if removed is not True:
                    self._record(request, "REVOCATION_FAILED", "Provider did not confirm removal of the stored grant." + outcome,
                                 status=RequestStatus.REVOCATION_FAILED, now=now)
                    responses.append(stopped("Temporary access expired, but removal was not confirmed. "
                                             "Access may remain. Contact IT with this request ID to verify and "
                                             "remove the stored grant; no automatic retry will occur.", request.request_id))
                    continue
                request = replace(request, revocation_status=RevocationStatus.REVOKED)
                self._record(request, "REVOCATION_SUCCEEDED", "Provider confirmed removal of the stored grant." + outcome,
                             status=RequestStatus.REVOKED, now=now)
                responses.append(stopped("Temporary access expired and was removed from the mock directory. "
                                         "No further action is needed.", request.request_id))
            except Exception:
                responses.append(stopped("Expiration stopped safely. Contact IT to check the access state.", request.request_id))
        return responses
