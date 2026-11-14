"""Persistent conversation history storage using SQLite (Stage 7).

Provides:
- Thread-safe conversation and message persistence.
- Isolation across independent conversation sessions.
- Safe serialization of message metadata and validated citations.
- Zero external database dependencies (standard library sqlite3).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.config import settings

logger = logging.getLogger(__name__)


class ConversationNotFoundError(Exception):
    """Raised when a conversation_id does not exist in the store."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation '{conversation_id}' not found.")


@dataclass(frozen=True)
class MessageRecord:
    """An individual user or assistant message within a conversation."""

    id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    content: str
    standalone_query: str | None = None
    found: bool = True
    sources: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""


@dataclass(frozen=True)
class ConversationRecord:
    """Metadata summary of a conversation session."""

    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class SQLiteConversationStore:
    """SQLite-backed persistent store for multi-turn conversations."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._mem_conn: sqlite3.Connection | None = None
        if db_path is None:
            self._db_path = settings.conversations_db_path
        elif isinstance(db_path, str) and db_path != ":memory:":
            self._db_path = Path(db_path)
        else:
            self._db_path = db_path

        # If disk path, ensure parent directory exists
        if isinstance(self._db_path, Path):
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()

    @property
    def db_path(self) -> Path | str:
        return self._db_path

    def close(self) -> None:
        """Close persistent in-memory connection if active."""
        if self._mem_conn is not None:
            self._mem_conn.close()
            self._mem_conn = None

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager providing an open SQLite connection with WAL mode."""
        db_file = str(self._db_path) if isinstance(self._db_path, Path) else self._db_path
        if db_file == ":memory:":
            if self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:", timeout=30.0, check_same_thread=False)
                self._mem_conn.row_factory = sqlite3.Row
                self._mem_conn.execute("PRAGMA foreign_keys = ON;")
            yield self._mem_conn
            self._mem_conn.commit()
            return

        conn = sqlite3.connect(db_file, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    standalone_query TEXT,
                    found INTEGER NOT NULL DEFAULT 1,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conv_created
                ON messages(conversation_id, created_at);
                """
            )

    def create_conversation(
        self,
        title: str | None = None,
        conversation_id: str | None = None,
    ) -> ConversationRecord:
        """Create a new conversation session."""
        conv_id = conversation_id or str(uuid.uuid4())
        conv_title = (title or "").strip() or "New Conversation"
        now = _utc_now_iso()

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?);
                """,
                (conv_id, conv_title, now, now),
            )

        logger.info("Created conversation %s ('%s')", conv_id, conv_title)
        return ConversationRecord(
            id=conv_id,
            title=conv_title,
            created_at=now,
            updated_at=now,
            message_count=0,
        )

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        """Retrieve conversation metadata and message count by ID."""
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS msg_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.id = ?
                GROUP BY c.id;
                """,
                (conversation_id,),
            ).fetchone()

        if not row:
            return None

        return ConversationRecord(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=row["msg_count"],
        )

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationRecord]:
        """List conversations ordered by most recently updated."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS msg_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ? OFFSET ?;
                """,
                (max(1, limit), max(0, offset)),
            ).fetchall()

        return [
            ConversationRecord(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                message_count=r["msg_count"],
            )
            for r in rows
        ]

    def count_conversations(self) -> int:
        """Total number of conversations."""
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM conversations;").fetchone()
        return row["total"] if row else 0

    def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update conversation title."""
        now = _utc_now_iso()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?;
                """,
                (title.strip(), now, conversation_id),
            )
            return cursor.rowcount > 0

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its associated messages."""
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ?;",
                (conversation_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info("Deleted conversation %s", conversation_id)
        return deleted

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        standalone_query: str | None = None,
        found: bool = True,
        sources: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> MessageRecord:
        """Append a message to a conversation.
        
        Raises:
            ConversationNotFoundError if conversation_id does not exist.
        """
        msg_id = message_id or str(uuid.uuid4())
        sources_list = sources or []
        sources_json = json.dumps(sources_list)
        now = created_at or _utc_now_iso()

        with self._connection() as conn:
            # Check conversation exists
            conv_row = conn.execute(
                "SELECT title FROM conversations WHERE id = ?;",
                (conversation_id,),
            ).fetchone()
            if not conv_row:
                raise ConversationNotFoundError(conversation_id)

            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, role, content, standalone_query,
                    found, sources_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    msg_id,
                    conversation_id,
                    role,
                    content,
                    standalone_query,
                    1 if found else 0,
                    sources_json,
                    now,
                ),
            )

            # Auto-title on first user message if title is still default
            new_title = None
            if role == "user" and conv_row["title"] == "New Conversation":
                trimmed = content.strip().replace("\n", " ")
                new_title = (trimmed[:47] + "...") if len(trimmed) > 50 else trimmed

            if new_title:
                conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?;",
                    (new_title, now, conversation_id),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                    (now, conversation_id),
                )

        return MessageRecord(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            standalone_query=standalone_query,
            found=found,
            sources=sources_list,
            created_at=now,
        )

    def get_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        """Retrieve chronological messages for a conversation.
        
        Raises:
            ConversationNotFoundError if conversation_id does not exist.
        """
        with self._connection() as conn:
            conv_exists = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?;",
                (conversation_id,),
            ).fetchone()
            if not conv_exists:
                raise ConversationNotFoundError(conversation_id)

            if limit is not None and limit > 0:
                # Fetch the latest N messages, preserved in chronological order
                query = """
                    SELECT id, conversation_id, role, content, standalone_query,
                           found, sources_json, created_at
                    FROM (
                        SELECT rowid, * FROM messages
                        WHERE conversation_id = ?
                        ORDER BY created_at DESC, rowid DESC
                        LIMIT ?
                    )
                    ORDER BY created_at ASC, rowid ASC;
                """
                rows = conn.execute(query, (conversation_id, limit)).fetchall()
            else:
                query = """
                    SELECT id, conversation_id, role, content, standalone_query,
                           found, sources_json, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC, rowid ASC;
                """
                rows = conn.execute(query, (conversation_id,)).fetchall()

        records = []
        for r in rows:
            try:
                sources = json.loads(r["sources_json"])
            except Exception:
                sources = []
            records.append(
                MessageRecord(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    role=r["role"],
                    content=r["content"],
                    standalone_query=r["standalone_query"],
                    found=bool(r["found"]),
                    sources=sources,
                    created_at=r["created_at"],
                )
            )
        return records


_GLOBAL_STORE: SQLiteConversationStore | None = None


def get_conversation_store() -> SQLiteConversationStore:
    """Return the global conversation store instance."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = SQLiteConversationStore()
    return _GLOBAL_STORE


def set_conversation_store(store: SQLiteConversationStore | None) -> None:
    """Set or reset the global conversation store instance (used for testing)."""
    global _GLOBAL_STORE
    _GLOBAL_STORE = store

