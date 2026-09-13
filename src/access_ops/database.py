"""Small SQLite store for access requests and append-style audit."""
import sqlite3
from datetime import datetime

from .models import AccessRequest, AuditEvent, RequestStatus, RevocationStatus


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
        # Additive migration: preceding slices stored only permanent requests.
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(requests)")}
        additions = {
            "assigned_approver_id": "TEXT",
            "duration": "TEXT NOT NULL DEFAULT 'Permanent'",
            "temporary": "INTEGER NOT NULL DEFAULT 0",
            "starts_at": "TEXT",
            "expires_at": "TEXT",
            "revocation_status": "TEXT NOT NULL DEFAULT 'NOT_APPLICABLE'",
        }
        with self.connection:
            for name, definition in additions.items():
                if name not in columns:
                    self.connection.execute(f"ALTER TABLE requests ADD COLUMN {name} {definition}")

    def close(self):
        self.connection.close()

    def create(self, request, policy, event):
        with self.connection:
            self.connection.execute(
                "INSERT INTO requests (request_id, requester_slack_id, application, access_level, "
                "business_reason, created_at, updated_at, status, provisioning_result, policy_id, "
                "policy_version, assigned_approver_id, duration, temporary, starts_at, expires_at, "
                "revocation_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request.request_id, request.requester_slack_id, request.application,
                 request.access_level, request.business_reason, request.created_at.isoformat(),
                 request.updated_at.isoformat(), request.status, request.provisioning_result,
                 policy.policy_id, policy.policy_version, request.assigned_approver_id,
                 request.duration, request.temporary,
                 request.starts_at.isoformat() if request.starts_at else None,
                 request.expires_at.isoformat() if request.expires_at else None,
                 request.revocation_status),
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
            business_reason=row["business_reason"], temporary=bool(row["temporary"]), duration=row["duration"],
            starts_at=datetime.fromisoformat(row["starts_at"]) if row["starts_at"] else None,
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            revocation_status=RevocationStatus(row["revocation_status"]),
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
                "UPDATE requests SET status = ?, updated_at = ?, provisioning_result = ?, "
                "starts_at = ?, expires_at = ?, revocation_status = ? WHERE request_id = ?",
                (request.status, request.updated_at.isoformat(), request.provisioning_result,
                 request.starts_at.isoformat() if request.starts_at else None,
                 request.expires_at.isoformat() if request.expires_at else None,
                 request.revocation_status, request.request_id),
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

    def active_temporary_requests(self):
        rows = self.connection.execute(
            "SELECT request_id FROM requests WHERE status = ? AND temporary = 1 "
            "AND expires_at IS NOT NULL AND revocation_status = ? ORDER BY request_id",
            (RequestStatus.ACTIVE, RevocationStatus.PENDING),
        ).fetchall()
        return [self.get(row["request_id"]) for row in rows]
