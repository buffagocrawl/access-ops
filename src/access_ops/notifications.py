"""Safe local Slack-style employee feedback."""
from dataclasses import dataclass
from .models import ApproverType


@dataclass(frozen=True)
class EmployeeResponse:
    request_id: str | None
    message: str


def granted(request):
    return EmployeeResponse(
        request.request_id,
        f"Access Ops: {request.application} {request.access_level} access is granted in the mock directory. "
        f"No further action is needed. Request ID: {request.request_id}.",
    )


def stopped(message, request_id=None):
    reference = f" Request ID: {request_id}." if request_id else ""
    return EmployeeResponse(request_id, f"Access Ops: {message}{reference}")


def pending(request, approver_type=ApproverType.MANAGER):
    label = "manager" if approver_type == ApproverType.MANAGER else "reviewer"
    if not request.assigned_approver_id:
        return stopped(
            f"Your request is saved pending {label} approval, but a valid configured {label} could not be resolved. "
            "Review is blocked until the configuration is corrected. Contact IT with this request ID; "
            "no access was granted.", request.request_id,
        )
    return stopped(
        f"{request.application} {request.access_level} request submitted and pending {label} approval "
        f"from <@{request.assigned_approver_id}>. No access has been granted. "
        f"Wait for your {label} to review the request.", request.request_id,
    )


def exception_pending(request):
    if not request.assigned_approver_id:
        return stopped(
            "Your request is outside normal eligibility and is saved for exception review, "
            "but a valid configured reviewer could not be resolved. Review is blocked. "
            "Contact IT with this request ID; no access was granted.", request.request_id,
        )
    return stopped(
        f"{request.application} {request.access_level} is outside the normal eligibility policy, "
        "but your request may be legitimate. It has been routed for exception review "
        f"to <@{request.assigned_approver_id}>. Wait for that reviewer; no access has been granted.",
        request.request_id,
    )


def exception_review(request):
    """Private mock reviewer message, built from the persisted request."""
    return stopped(
        f"<@{request.assigned_approver_id}>: Review the exception for "
        f"<@{request.requester_slack_id}>. Application: {request.application}. "
        f"Access: {request.access_level}. Duration: {request.duration}. "
        f"Business reason: {request.business_reason}. Approve or reject this exception.",
        request.request_id,
    )
