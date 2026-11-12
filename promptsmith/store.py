"""SQLite persistence: users (API keys), profiles, and daily usage counters.

API keys are stored as SHA-256 hashes, so a leaked database does not leak working keys.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

PLAN_LIMITS = {"free": 20, "pro": 1000}  # enhancements per UTC day

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    key_hash   TEXT UNIQUE NOT NULL,
    plan       TEXT NOT NULL DEFAULT 'free',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id    TEXT PRIMARY KEY REFERENCES users(id),
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    user_id TEXT NOT NULL REFERENCES users(id),
    day     TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
"""


@dataclass
class User:
    id: str
    plan: str


class QuotaExceeded(Exception):
    def __init__(self, limit: int):
        super().__init__(f"Daily limit of {limit} enhancements reached. It resets at 00:00 UTC.")
        self.limit = limit


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str = "promptsmith.db"):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def create_user(self, plan: str = "free") -> tuple[User, str]:
        """Create a user and return it with its plaintext API key (shown once, never stored)."""
        key = "ps_" + secrets.token_urlsafe(24)
        user = User(id=str(uuid.uuid4()), plan=plan)
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO users (id, key_hash, plan, created_at) VALUES (?, ?, ?, ?)",
                (user.id, _hash(key), plan, _now()),
            )
        return user, key

    def user_for_key(self, key: str) -> User | None:
        row = self._db.execute("SELECT id, plan FROM users WHERE key_hash = ?", (_hash(key),)).fetchone()
        return User(*row) if row else None

    def set_plan(self, user_id: str, plan: str) -> None:
        """Hook for a future Stripe webhook: flip a user between free and pro."""
        if plan not in PLAN_LIMITS:
            raise ValueError(f"unknown plan {plan!r}")
        with self._lock, self._db:
            self._db.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))

    def save_profile(self, user_id: str, profile: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO profiles (user_id, data, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                (user_id, json.dumps(profile), _now()),
            )

    def get_profile(self, user_id: str) -> dict | None:
        row = self._db.execute("SELECT data FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def consume(self, user: User) -> int:
        """Count one enhancement against today's quota. Returns how many remain; raises QuotaExceeded."""
        limit = PLAN_LIMITS[user.plan]
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT count FROM usage WHERE user_id = ? AND day = ?", (user.id, day)
            ).fetchone()
            used = row[0] if row else 0
            if used >= limit:
                raise QuotaExceeded(limit)
            self._db.execute(
                "INSERT INTO usage (user_id, day, count) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1",
                (user.id, day),
            )
        return limit - used - 1
