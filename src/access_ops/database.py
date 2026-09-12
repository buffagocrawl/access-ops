"""Small SQLite store for permanent-access requests and append-style audit."""
import sqlite3
from datetime import datetime

from .models import AccessRequest, AuditEvent, RequestStatus


class Database:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, requester_slack_id TEXT NOT NULL,
                application TEXT NOT NULL, access_level TEXT NOT NULL,
                business_reason TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, status TEXT NOT NULL,
                provisioning_result TEXT, policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY, request_id TEXT NOT NULL,
                event_type TEXT NOT NULL, actor TEXT NOT NULL,
                previous_status TEXT, new_status TEXT,
                timestamp TEXT NOT NULL, policy_version INTEGER, details TEXT NOT NULL
            );
        """)
        # Preserve databases created by the preceding auto-approval slice.
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(requests)")}
        if "assigned_approver_id" not in columns:
            self.connection.execute("ALTER TABLE requests ADD COLUMN assigned_approver_id TEXT")
            self.connection.commit()

    def close(self):
        self.connection.close()

    def create(self, request, policy, event):
        with self.connection:
            self.connection.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request.request_id, request.requester_slack_id, request.application,
                 request.access_level, request.business_reason, request.created_at.isoformat(),
                 request.updated_at.isoformat(), request.status, request.provisioning_result,
                 policy.policy_id, policy.policy_version, request.assigned_approver_id),
            )
            self.append_event(event)

    def get(self, request_id):
        row = self.connection.execute(
            "SELECT * FROM requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        return AccessRequest(
            request_id=row["request_id"], requester_slack_id=row["requester_slack_id"],
            application=row["application"], access_level=row["access_level"],
            business_reason=row["business_reason"], temporary=False, expires_at=None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            status=RequestStatus(row["status"]), provisioning_result=row["provisioning_result"],
            assigned_approver_id=row["assigned_approver_id"],
        )

    def policy_reference(self, request_id):
        row = self.connection.execute(
            "SELECT policy_id, policy_version FROM requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        return tuple(row)

    def transition(self, request, event):
        # State and audit commit together; audit failure rolls both back.
        with self.connection:
            self.append_event(event)
            self.connection.execute(
                "UPDATE requests SET status = ?, updated_at = ?, provisioning_result = ? "
                "WHERE request_id = ?",
                (request.status, request.updated_at.isoformat(), request.provisioning_result,
                 request.request_id),
            )

    def append_event(self, event):
        """Append in the caller's transaction; never swallow write errors."""
        self.connection.execute(
            "INSERT INTO audit_events (request_id, event_type, actor, previous_status, "
            "new_status, timestamp, policy_version, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event.request_id, event.event_type, event.actor, event.previous_status,
             event.new_status, event.timestamp.isoformat(), event.policy_version, event.details),
        )

    def events(self, request_id):
        rows = self.connection.execute(
            "SELECT * FROM audit_events WHERE request_id = ? ORDER BY event_id", (request_id,)
        ).fetchall()
        return [AuditEvent(
            request_id=row["request_id"], event_type=row["event_type"], actor=row["actor"],
            previous_status=RequestStatus(row["previous_status"]) if row["previous_status"] else None,
            new_status=RequestStatus(row["new_status"]) if row["new_status"] else None,
            timestamp=datetime.fromisoformat(row["timestamp"]),
            policy_version=row["policy_version"], details=row["details"],
        ) for row in rows]
