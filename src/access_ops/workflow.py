"""UI-independent orchestration for permanent Engineering GitHub Read access."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from .audit import event_for
from .config import APPLICATION_ACCESS, Configuration
from .database import Database
from .integrations.mock_okta import AccessProvider, GrantResult
from .models import AccessRequest, Decision, EmployeeStatus, RequestStatus
from .notifications import granted, stopped
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
        if policy is None or policy.decision != Decision.AUTO_APPROVE:
            raise IntakeError("This request cannot use automatic provisioning. Contact IT; no access was granted.")
        # Phase gate only: eligibility and approval decisions still come from CSV.
        if (application, access_level) != ("GitHub", "Read") or employee.department != "Engineering":
            raise IntakeError("This phase supports Engineering GitHub Read only. Contact IT for other access.")
        if duration != "Permanent" or not policy.permanent_allowed:
            raise IntakeError("This workflow requires policy-permitted Permanent access. Contact IT for other durations.")
        return policy

    def submit(self, employee_id, application, access_level, business_reason, duration):
        try:
            policy = self._validate(employee_id, application, access_level, business_reason, duration)
            now = datetime.now(timezone.utc)
            request = AccessRequest(
                request_id=f"REQ-{uuid4().hex}", requester_slack_id=employee_id,
                application=application, access_level=access_level, business_reason=business_reason,
                temporary=False, expires_at=None, created_at=now, updated_at=now,
                status=RequestStatus.APPROVED,
            )
            self.database.create(request, policy, event_for(
                request, policy, "REQUEST_AUTO_APPROVED", None, "Request created and automatically approved."
            ))
        except IntakeError as error:
            return stopped(str(error))
        except Exception:
            return stopped("The request could not be recorded safely. Contact IT; no access was granted.")
        return self.process(request.request_id)

    def process(self, request_id):
        """Internal entry point: load persisted state, never accept caller approval."""
        try:
            request = self.database.get(request_id)
            if request is None:
                return stopped("Request not found. Check the request ID or contact IT.")
            if request.status == RequestStatus.ACTIVE:
                return granted(request)
            if request.status != RequestStatus.APPROVED:
                return stopped("Processing is stopped. Contact IT to check the access state.", request_id)
            policy = self._validate(
                request.requester_slack_id, request.application, request.access_level,
                request.business_reason, "Permanent",
            )
            if self.database.policy_reference(request_id) != (policy.policy_id, policy.policy_version):
                return stopped("Policy changed. Contact IT; no provisioning was attempted.", request_id)
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
