from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db.repository import LabRepository
from app.services.challenge_catalog import blank_circuit
from app.services.lab_service import LabService


SESSION_LIFETIME = timedelta(days=30)


@dataclass(frozen=True)
class AnonymousSession:
    token: str
    lab_id: str
    created: bool


class AnonymousSessionManager:
    """Resolves opaque browser cookies to isolated Lab ownership roots."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        LabRepository(database_path)

    def resolve(self, token: str | None) -> AnonymousSession:
        now = datetime.now(timezone.utc)
        if token:
            lab_id = self._resolve_existing(token, now)
            if lab_id is not None:
                return AnonymousSession(token=token, lab_id=lab_id, created=False)
        return self._create(now)

    def service_for(self, session: AnonymousSession) -> LabService:
        return LabService(LabRepository(self.database_path, session.lab_id, create_schema=False))

    def cleanup_inactive(self, *, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(timezone.utc)) - SESSION_LIFETIME
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT lab_id FROM anonymous_sessions WHERE last_seen_at < ?",
                (cutoff.isoformat(),),
            ).fetchall()
            lab_ids = [str(row[0]) for row in rows]
            connection.executemany("DELETE FROM labs WHERE id = ?", ((lab_id,) for lab_id in lab_ids))
        return len(lab_ids)

    def _resolve_existing(self, token: str, now: datetime) -> str | None:
        if len(token) > 512:
            return None
        token_hash = self._token_hash(token)
        cutoff = now - SESSION_LIFETIME
        with self._connect() as connection:
            row = connection.execute(
                "SELECT lab_id, last_seen_at FROM anonymous_sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if datetime.fromisoformat(str(row[1])) < cutoff:
                connection.execute("DELETE FROM labs WHERE id = ?", (row[0],))
                return None
            connection.execute(
                "UPDATE anonymous_sessions SET last_seen_at = ? WHERE token_hash = ?",
                (now.isoformat(), token_hash),
            )
        return str(row[0])

    def _create(self, now: datetime) -> AnonymousSession:
        for _attempt in range(5):
            token = secrets.token_urlsafe(32)
            lab_id = f"lab_{secrets.token_hex(16)}"
            repository = LabRepository(self.database_path, lab_id, create_schema=False)
            challenge, circuit = blank_circuit()
            try:
                repository.initialize(challenge, circuit)
                with self._connect() as connection:
                    connection.execute(
                        "INSERT INTO anonymous_sessions (token_hash, lab_id, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
                        (self._token_hash(token), lab_id, now.isoformat(), now.isoformat()),
                    )
                return AnonymousSession(token=token, lab_id=lab_id, created=True)
            except sqlite3.IntegrityError:
                with self._connect() as connection:
                    connection.execute("DELETE FROM labs WHERE id = ?", (lab_id,))
        raise RuntimeError("Unable to allocate an anonymous Circuit Bench session.")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
