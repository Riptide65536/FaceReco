from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class AuthSession:
    token: str
    username: str
    expires_at: datetime


class TokenStore:
    def __init__(self, ttl_seconds: int = 8 * 60 * 60) -> None:
        self.ttl_seconds = max(300, int(ttl_seconds))
        self._lock = threading.RLock()
        self._sessions: dict[str, AuthSession] = {}

    def issue(self, username: str) -> AuthSession:
        now = datetime.now(timezone.utc)
        session = AuthSession(
            token=secrets.token_urlsafe(32),
            username=str(username),
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            self._cleanup_locked(now)
            self._sessions[session.token] = session
        return session

    def validate(self, token: str | None) -> AuthSession | None:
        if not token:
            return None
        now = datetime.now(timezone.utc)
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at <= now:
                self._sessions.pop(token, None)
                return None
            return session

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _cleanup_locked(self, now: datetime) -> None:
        expired = [token for token, session in self._sessions.items() if session.expires_at <= now]
        for token in expired:
            self._sessions.pop(token, None)

