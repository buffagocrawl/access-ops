"""Safe local Slack-style employee feedback."""
from dataclasses import dataclass


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


def pending(request):
    return stopped(
        f"{request.application} {request.access_level} request submitted and pending manager approval "
        f"from <@{request.assigned_approver_id}>. No access has been granted. "
        "Wait for your manager to review the request.", request.request_id,
    )
