from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union


class SQLiteUrlFrontier:
    """SQLite-backed URL frontier with priority and retry tracking."""

    def __init__(self, db_path: Union[str, Path] = ":memory:", max_retry: int = 3) -> None:
        """Open the frontier database and create the schema if needed."""
        if max_retry < 0:
            raise ValueError("max_retry must be non-negative")

        self.max_retry = max_retry
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def add_url(self, url: str, priority: int = 0) -> bool:
        """Add a URL to the pending queue and report whether it was new."""
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO url_frontier (url, priority)
            VALUES (?, ?)
            """,
            (url, priority),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def get_next(self) -> Optional[str]:
        """Return the next pending URL by priority, or None when empty."""
        row = self._conn.execute(
            """
            SELECT url
            FROM url_frontier
            WHERE status = 'pending'
            ORDER BY priority DESC, id ASC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return None

        return str(row["url"])

    def mark_done(self, url: str) -> bool:
        """Mark a queued URL as successfully processed."""
        cursor = self._conn.execute(
            """
            UPDATE url_frontier
            SET status = 'done',
                error_type = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE url = ?
            """,
            (url,),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def mark_failed(self, url: str, error_type: str) -> bool:
        """Record a failure and retry until the retry budget is exceeded."""
        with self._conn:
            row = self._conn.execute(
                """
                SELECT retry_count
                FROM url_frontier
                WHERE url = ?
                """,
                (url,),
            ).fetchone()

            if row is None:
                return False

            retry_count = int(row["retry_count"]) + 1
            status = "failed" if retry_count > self.max_retry else "pending"
            self._conn.execute(
                """
                UPDATE url_frontier
                SET status = ?,
                    retry_count = ?,
                    error_type = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE url = ?
                """,
                (status, retry_count, error_type, url),
            )

        return True

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _initialize_schema(self) -> None:
        """Create tables and indexes required by the frontier."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS url_frontier (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'done', 'failed')),
                priority INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_type TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_url_frontier_pending_priority
            ON url_frontier (status, priority DESC, id ASC)
            """
        )
        self._conn.commit()
