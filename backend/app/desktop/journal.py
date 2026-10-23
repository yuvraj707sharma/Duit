"""Write-Ahead Journal in SQLite (WAL mode with fsync, state machine & startup reconciliation)."""
import os
import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional

from contextlib import contextmanager

logger = logging.getLogger(__name__)

# State Transitions
VALID_STATES = {
    "received",
    "decided",
    "confirmed",
    "started",
    "completed",
    "failed",
    "interrupted",
    "expired"
}

VOICE_COMMAND_TTL_SECONDS = 30.0
CONFIRMATION_TTL_SECONDS = 300.0  # 5 minutes


class WriteAheadJournal:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.path.expanduser("~"), ".fastagent", "desktop_journal.db")
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            # Enable Write-Ahead Logging (WAL) and synchronous=FULL for strict fsync on commits
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=FULL;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    action_id TEXT PRIMARY KEY,
                    idempotency_key TEXT,
                    user_id TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    is_read_only INTEGER NOT NULL,
                    is_voice_command INTEGER NOT NULL DEFAULT 0,
                    arguments_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    error_message TEXT,
                    result_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_state ON journal_entries(state);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_idempotency ON journal_entries(idempotency_key);")
            conn.commit()

    def record_received(
        self,
        action_id: str,
        user_id: str,
        intent: str,
        arguments: Dict[str, Any],
        is_read_only: bool,
        is_voice_command: bool = False,
        idempotency_key: Optional[str] = None,
        created_at: Optional[float] = None
    ) -> None:
        now = created_at if created_at is not None else time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO journal_entries (
                    action_id, idempotency_key, user_id, intent, is_read_only,
                    is_voice_command, arguments_json, state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'received', ?)
            """, (
                action_id,
                idempotency_key or action_id,
                user_id,
                intent,
                1 if is_read_only else 0,
                1 if is_voice_command else 0,
                json.dumps(arguments),
                now
            ))
            conn.commit()

    def transition_state(
        self,
        action_id: str,
        new_state: str,
        error_message: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None
    ) -> None:
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid journal state: {new_state}")

        now = time.time()
        with self._get_connection() as conn:
            if new_state == "started":
                conn.execute("""
                    UPDATE journal_entries
                    SET state = ?, started_at = ?
                    WHERE action_id = ?
                """, (new_state, now, action_id))
            elif new_state in ("completed", "failed", "interrupted", "expired"):
                conn.execute("""
                    UPDATE journal_entries
                    SET state = ?, completed_at = ?, error_message = ?, result_json = ?
                    WHERE action_id = ?
                """, (
                    new_state,
                    now,
                    error_message,
                    json.dumps(result_data) if result_data else None,
                    action_id
                ))
            else:
                conn.execute("""
                    UPDATE journal_entries
                    SET state = ?
                    WHERE action_id = ?
                """, (new_state, action_id))
            conn.commit()

    def check_ttl_expired(self, action_id: str) -> bool:
        """Evaluates whether an uncompleted action exceeded TTL (30s for voice, 5m for confirmation)."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM journal_entries WHERE action_id = ?", (action_id,))
            row = cursor.fetchone()
            if not row:
                return False

            created_at = row["created_at"]
            is_voice = bool(row["is_voice_command"])
            elapsed = time.time() - created_at

            if is_voice and elapsed > VOICE_COMMAND_TTL_SECONDS:
                self.transition_state(action_id, "expired", error_message=f"Voice command expired after {elapsed:.1f}s (>30s TTL)")
                return True

            if row["state"] in ("received", "decided", "confirmed") and elapsed > CONFIRMATION_TTL_SECONDS:
                self.transition_state(action_id, "expired", error_message=f"Confirmation expired after {elapsed:.1f}s (>5m TTL)")
                return True

            return False

    def reconcile_on_startup(self) -> List[Dict[str, Any]]:
        """
        Reconciles pending entries upon system startup.
        - Idempotent read-only actions may re-run.
        - Side-effecting actions in non-terminal states ('started', 'confirmed', 'decided', 'received')
          become 'interrupted' and are surfaced to the user.
        """
        reconciled = []
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM journal_entries
                WHERE state IN ('started', 'confirmed', 'decided', 'received')
            """)
            rows = cursor.fetchall()
            for r in rows:
                action_id = r["action_id"]
                is_read_only = bool(r["is_read_only"])
                intent = r["intent"]
                args = json.loads(r["arguments_json"])

                if is_read_only:
                    # Idempotent read-only actions can re-run
                    status_note = "re_run_allowed"
                else:
                    # Side-effecting actions become 'interrupted' and surfaced to user
                    conn.execute("""
                        UPDATE journal_entries
                        SET state = 'interrupted',
                            error_message = 'Interrupted by process termination or crash between states'
                        WHERE action_id = ?
                    """, (action_id,))
                    status_note = "interrupted_surfaced"

                reconciled.append({
                    "action_id": action_id,
                    "intent": intent,
                    "arguments": args,
                    "is_read_only": is_read_only,
                    "reconciliation_status": status_note,
                    "created_at": r["created_at"]
                })
            conn.commit()
        return reconciled

    def get_entry(self, action_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM journal_entries WHERE action_id = ?", (action_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["arguments"] = json.loads(d["arguments_json"])
                return d
            return None


journal = WriteAheadJournal()
