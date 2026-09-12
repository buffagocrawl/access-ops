"""Safe local Slack-style employee feedback."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EmployeeResponse:
    request_id: str | None
    message: str


def granted(request):
    return EmployeeResponse(
        request.request_id,
        f"Access Ops: GitHub Read access is granted in the mock directory. "
        f"No further action is needed. Request ID: {request.request_id}.",
    )


def stopped(message, request_id=None):
    reference = f" Request ID: {request_id}." if request_id else ""
    return EmployeeResponse(request_id, f"Access Ops: {message}{reference}")
