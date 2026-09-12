"""Local mock provider: performs operations, never authorization."""
import sqlite3
from enum import StrEnum
from typing import Protocol

from ..models import AccessRequest


class GrantResult(StrEnum):
    GRANTED = "GRANTED"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    FAILED = "FAILED"


class AccessProvider(Protocol):
    def grant(self, request: AccessRequest) -> GrantResult:
        """Perform an already-authorized operation and confirm the outcome."""
        ...


class MockOkta:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS mock_access (
                employee_id TEXT NOT NULL, application TEXT NOT NULL,
                access_level TEXT NOT NULL, grant_key TEXT UNIQUE NOT NULL,
                PRIMARY KEY (employee_id, application, access_level)
            )
        """)
        self.connection.commit()

    def close(self):
        self.connection.close()

    def grant(self, request: AccessRequest) -> GrantResult:
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO mock_access VALUES (?, ?, ?, ?) "
                "ON CONFLICT (employee_id, application, access_level) DO NOTHING",
                (request.requester_slack_id, request.application, request.access_level,
                 f"{request.request_id}:grant"),
            )
        return GrantResult.GRANTED if cursor.rowcount else GrantResult.ALREADY_EXISTS

    def access_list(self):
        return self.connection.execute(
            "SELECT employee_id, application, access_level FROM mock_access "
            "ORDER BY employee_id, application, access_level"
        ).fetchall()
