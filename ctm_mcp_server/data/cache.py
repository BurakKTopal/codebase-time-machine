"""
SQLite caching layer for CTM.

Provides persistent caching for expensive operations like
GitHub API calls and commit analysis results.
"""

import hashlib
import json
import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class CacheError(Exception):
    """Base exception for cache errors."""

    pass


class Cache:
    """SQLite-based cache for CTM data."""

    DEFAULT_TTL = 3600  # 1 hour
    SCHEMA_VERSION = 1

    def __init__(
        self,
        db_path: str | Path | None = None,
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        """Initialize cache.

        Args:
            db_path: Path to SQLite database. If None, uses in-memory database.
            default_ttl: Default time-to-live in seconds.
        """
        self.db_path = Path(db_path) if db_path else None
        self.default_ttl = default_ttl

        # Initialize database
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection."""
        if self.db_path:
            conn = sqlite3.connect(self.db_path)
        else:
            conn = sqlite3.connect(":memory:")

        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    hit_count INTEGER DEFAULT 0
                )
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cache_namespace
                ON cache_entries(namespace)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cache_expires
                ON cache_entries(expires_at)
            """
            )

            # Store schema version
            cursor.execute(
                """
                INSERT OR REPLACE INTO cache_meta (key, value)
                VALUES ('schema_version', ?)
            """,
                (str(self.SCHEMA_VERSION),),
            )

            conn.commit()

    @staticmethod
    def _make_key(namespace: str, *args: Any) -> str:
        """Create a cache key from namespace and arguments."""
        # Create deterministic key from arguments
        key_data = json.dumps(args, sort_keys=True, default=str)
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        return f"{namespace}:{key_hash}"

    def get(
        self,
        namespace: str,
        *args: Any,
    ) -> Any | None:
        """Get value from cache.

        Args:
            namespace: Cache namespace (e.g., 'commit', 'pr', 'blame').
            *args: Cache key arguments.

        Returns:
            Cached value or None if not found/expired.
        """
        key = self._make_key(namespace, *args)
        now = time.time()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT value, expires_at
                    FROM cache_entries
                    WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)
                """,
                    (key, now),
                )

                row = cursor.fetchone()
                if row:
                    # Update hit count
                    cursor.execute(
                        """
                        UPDATE cache_entries
                        SET hit_count = hit_count + 1
                        WHERE key = ?
                    """,
                        (key,),
                    )
                    conn.commit()

                    return json.loads(row["value"])
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                # Table doesn't exist - try to recreate schema
                self._init_db()
                # Return None for this call, subsequent calls will work
            else:
                raise

        return None

    def set(
        self,
        namespace: str,
        *args: Any,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Set value in cache.

        Args:
            namespace: Cache namespace.
            *args: Cache key arguments.
            value: Value to cache (must be JSON-serializable).
            ttl: Time-to-live in seconds. If None, uses default_ttl.
                 If 0, entry never expires.
        """
        key = self._make_key(namespace, *args)
        now = time.time()

        if ttl is None:
            ttl = self.default_ttl

        expires_at = now + ttl if ttl > 0 else None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries
                    (key, value, namespace, created_at, expires_at, hit_count)
                    VALUES (?, ?, ?, ?, ?, 0)
                """,
                    (key, json.dumps(value, default=str), namespace, now, expires_at),
                )

                conn.commit()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                # Table doesn't exist - try to recreate schema and retry
                self._init_db()
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO cache_entries
                        (key, value, namespace, created_at, expires_at, hit_count)
                        VALUES (?, ?, ?, ?, ?, 0)
                    """,
                        (key, json.dumps(value, default=str), namespace, now, expires_at),
                    )
                    conn.commit()
            else:
                raise

    def delete(self, namespace: str, *args: Any) -> bool:
        """Delete entry from cache.

        Args:
            namespace: Cache namespace.
            *args: Cache key arguments.

        Returns:
            True if entry was deleted, False if not found.
        """
        key = self._make_key(namespace, *args)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            conn.commit()

            return cursor.rowcount > 0

    def clear_namespace(self, namespace: str) -> int:
        """Clear all entries in a namespace.

        Args:
            namespace: Cache namespace to clear.

        Returns:
            Number of entries deleted.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM cache_entries WHERE namespace = ?", (namespace,))
            conn.commit()

            return cursor.rowcount

    def clear_all(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries deleted.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM cache_entries")
            conn.commit()

            return cursor.rowcount

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed.
        """
        now = time.time()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at < ?", (now,)
            )
            conn.commit()

            return cursor.rowcount

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total entries
            cursor.execute("SELECT COUNT(*) as count FROM cache_entries")
            total = cursor.fetchone()["count"]

            # Entries by namespace
            cursor.execute(
                """
                SELECT namespace, COUNT(*) as count
                FROM cache_entries
                GROUP BY namespace
            """
            )
            by_namespace = {row["namespace"]: row["count"] for row in cursor.fetchall()}

            # Total hits
            cursor.execute("SELECT SUM(hit_count) as hits FROM cache_entries")
            total_hits = cursor.fetchone()["hits"] or 0

            # Expired entries (not yet cleaned up)
            now = time.time()
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM cache_entries
                WHERE expires_at IS NOT NULL AND expires_at < ?
            """,
                (now,),
            )
            expired = cursor.fetchone()["count"]

            return {
                "total_entries": total,
                "by_namespace": by_namespace,
                "total_hits": total_hits,
                "expired_entries": expired,
                "db_path": str(self.db_path) if self.db_path else ":memory:",
            }


# Global cache instance (lazy initialization)
_global_cache: Cache | None = None


def get_cache(db_path: str | Path | None = None) -> Cache:
    """Get or create global cache instance.

    Args:
        db_path: Path to database. Only used on first call.

    Returns:
        Cache instance.
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = Cache(db_path)

    return _global_cache
