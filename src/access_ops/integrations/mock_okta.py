"""Local mock provider: performs operations, never authorization."""
import sqlite3
from enum import StrEnum
from typing import Protocol

from ..models import AccessRequest


class GrantResult(StrEnum):
    GRANTED = "GRANTED"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    FAILED = "FAILED"


class TransientProviderError(Exception):
    """Explicitly retryable provider timeout or temporary unavailability."""


def operation_id(request: AccessRequest, operation: str) -> str:
    """Stable provider key, never evidence of authorization."""
    return f"{request.request_id}:{operation}"


class AccessProvider(Protocol):
    def revoke(self, request: AccessRequest) -> bool:
        """Use request_id:revoke; True confirms removal, including completed replay.

        Only TransientProviderError is retryable; False/other errors are not.
        """
        ...

    def grant(self, request: AccessRequest) -> GrantResult:
        """Use request_id:grant. Only TransientProviderError is retryable."""
        ...


class MockOkta:
    def __init__(self, path, *, fail_grant=False, fail_revoke=False,
                 transient_grant_failures=0, transient_revoke_failures=0):
        for count in (transient_grant_failures, transient_revoke_failures):
            if type(count) is not int or count < 0:
                raise ValueError("Transient failure counts must be nonnegative integers")
        # Explicit demo/test failures occur before any directory mutation.
        self.fail_grant = fail_grant
        self.fail_revoke = fail_revoke
        self.transient_failures = {"grant": transient_grant_failures, "revoke": transient_revoke_failures}
        self.attempts = {}
        self.connection = sqlite3.connect(path)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS mock_access (
                employee_id TEXT NOT NULL, application TEXT NOT NULL,
                access_level TEXT NOT NULL, grant_key TEXT UNIQUE NOT NULL,
                PRIMARY KEY (employee_id, application, access_level)
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS mock_operations (
                operation_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL,
                application TEXT NOT NULL, access_level TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def close(self):
        self.connection.close()

    def _completed(self, request, operation):
        row = self.connection.execute(
            "SELECT employee_id, application, access_level FROM mock_operations WHERE operation_id = ?",
            (operation_id(request, operation),),
        ).fetchone()
        if row is not None and row != (request.requester_slack_id, request.application, request.access_level):
            raise ValueError("Operation key was already used for different access")
        return row is not None

    def _remember(self, request, operation):
        # Called in the same transaction as the access mutation.
        self.connection.execute("INSERT INTO mock_operations VALUES (?, ?, ?, ?)",
                                (operation_id(request, operation), request.requester_slack_id,
                                 request.application, request.access_level))

    def _simulate_transient(self, request, operation):
        key = operation_id(request, operation)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if self.attempts[key] <= self.transient_failures[operation]:
            raise TransientProviderError("Simulated temporary provider unavailability")

    def grant(self, request: AccessRequest) -> GrantResult:
        if self._completed(request, "grant"):
            # A completed grant must never recreate access after revocation.
            exists = self.connection.execute(
                "SELECT 1 FROM mock_access WHERE employee_id = ? AND application = ? AND access_level = ?",
                (request.requester_slack_id, request.application, request.access_level),
            ).fetchone()
            return GrantResult.ALREADY_EXISTS if exists else GrantResult.FAILED
        if self.fail_grant:
            return GrantResult.FAILED
        self._simulate_transient(request, "grant")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO mock_access VALUES (?, ?, ?, ?) "
                "ON CONFLICT (employee_id, application, access_level) DO NOTHING",
                (request.requester_slack_id, request.application, request.access_level,
                 operation_id(request, "grant")),
            )
            self._remember(request, "grant")
        return GrantResult.GRANTED if cursor.rowcount else GrantResult.ALREADY_EXISTS

    def access_list(self):
        return self.connection.execute(
            "SELECT employee_id, application, access_level FROM mock_access "
            "ORDER BY employee_id, application, access_level"
        ).fetchall()

    def current_grants(self):
        """Read the actual SQLite grant owner, not duplicate approval history."""
        return [dict(zip(("employee_id", "application", "access_level", "grant_key"), row))
                for row in self.connection.execute(
                    "SELECT employee_id, application, access_level, grant_key FROM mock_access "
                    "ORDER BY employee_id, application, access_level")]

    def revoke(self, request: AccessRequest) -> bool:
        if self._completed(request, "revoke"):
            return True
        if self.fail_revoke:
            return False
        self._simulate_transient(request, "revoke")
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM mock_access WHERE employee_id = ? AND application = ? "
                "AND access_level = ? AND grant_key = ?",
                (request.requester_slack_id, request.application, request.access_level,
                 operation_id(request, "grant")),
            )
            if cursor.rowcount:
                self._remember(request, "revoke")
        return cursor.rowcount == 1
