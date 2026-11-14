"""Unit tests for SQLiteConversationStore (Stage 7)."""

import json
import sqlite3
from pathlib import Path

import pytest

from backend.conversation.store import (
    ConversationNotFoundError,
    ConversationRecord,
    MessageRecord,
    SQLiteConversationStore,
    get_conversation_store,
    set_conversation_store,
)


@pytest.fixture
def store(tmp_path: Path) -> SQLiteConversationStore:
    db_file = tmp_path / "test_conversations.db"
    return SQLiteConversationStore(db_file)


def test_create_and_get_conversation(store: SQLiteConversationStore):
    conv = store.create_conversation("Project Questions")
    assert conv.id is not None
    assert conv.title == "Project Questions"
    assert conv.message_count == 0

    fetched = store.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.id == conv.id
    assert fetched.title == "Project Questions"
    assert fetched.message_count == 0


def test_create_conversation_defaults(store: SQLiteConversationStore):
    conv = store.create_conversation()
    assert conv.title == "New Conversation"

    conv_whitespace = store.create_conversation("   ")
    assert conv_whitespace.title == "New Conversation"

    custom_id = "my-custom-id"
    conv_custom = store.create_conversation(title="Custom ID Conv", conversation_id=custom_id)
    assert conv_custom.id == custom_id


def test_get_nonexistent_conversation_returns_none(store: SQLiteConversationStore):
    assert store.get_conversation("does-not-exist") is None


def test_list_and_count_conversations(store: SQLiteConversationStore):
    assert store.count_conversations() == 0
    assert store.list_conversations() == []

    c1 = store.create_conversation("First")
    c2 = store.create_conversation("Second")

    assert store.count_conversations() == 2
    listed = store.list_conversations(limit=10, offset=0)
    assert len(listed) == 2
    ids = [c.id for c in listed]
    assert c1.id in ids
    assert c2.id in ids

    # Test pagination
    p1 = store.list_conversations(limit=1, offset=0)
    p2 = store.list_conversations(limit=1, offset=1)
    assert len(p1) == 1
    assert len(p2) == 1
    assert p1[0].id != p2[0].id


def test_update_conversation_title(store: SQLiteConversationStore):
    conv = store.create_conversation("Old Title")
    ok = store.update_conversation_title(conv.id, "New Title")
    assert ok is True

    updated = store.get_conversation(conv.id)
    assert updated.title == "New Title"

    # Nonexistent
    assert store.update_conversation_title("nonexistent", "Title") is False


def test_delete_conversation_cascades(store: SQLiteConversationStore):
    conv = store.create_conversation("To Delete")
    store.add_message(conv.id, "user", "Hello")
    store.add_message(conv.id, "assistant", "Hi there")

    assert len(store.get_messages(conv.id)) == 2
    deleted = store.delete_conversation(conv.id)
    assert deleted is True

    assert store.get_conversation(conv.id) is None
    with pytest.raises(ConversationNotFoundError):
        store.get_messages(conv.id)

    # Deleting again returns False
    assert store.delete_conversation(conv.id) is False


def test_add_and_get_messages(store: SQLiteConversationStore):
    conv = store.create_conversation("Q&A")

    sources = [
        {
            "chunk_id": "doc.pdf:1:0",
            "file_name": "doc.pdf",
            "page_number": 1,
            "chunk_index": 0,
            "similarity": 0.85,
            "excerpt": "Sample excerpt",
        }
    ]

    msg1 = store.add_message(
        conv.id,
        role="user",
        content="What is Drone A?",
        standalone_query="What is Drone A?",
    )
    assert msg1.id is not None
    assert msg1.role == "user"
    assert msg1.content == "What is Drone A?"
    assert msg1.standalone_query == "What is Drone A?"
    assert msg1.found is True

    msg2 = store.add_message(
        conv.id,
        role="assistant",
        content="Drone A is a quadcopter [Passage 1].",
        found=True,
        sources=sources,
        message_id="custom-msg-id",
    )
    assert msg2.id == "custom-msg-id"
    assert msg2.role == "assistant"
    assert len(msg2.sources) == 1
    assert msg2.sources[0]["file_name"] == "doc.pdf"

    messages = store.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].content == "What is Drone A?"
    assert messages[1].content == "Drone A is a quadcopter [Passage 1]."

    # Test get_messages with limit
    latest_one = store.get_messages(conv.id, limit=1)
    assert len(latest_one) == 1
    assert latest_one[0].id == "custom-msg-id"


def test_add_message_to_nonexistent_conversation_raises(store: SQLiteConversationStore):
    with pytest.raises(ConversationNotFoundError):
        store.add_message("invalid-id", role="user", content="Hi")


def test_get_messages_from_nonexistent_conversation_raises(store: SQLiteConversationStore):
    with pytest.raises(ConversationNotFoundError):
        store.get_messages("invalid-id")


def test_auto_titling_on_first_user_message(store: SQLiteConversationStore):
    conv = store.create_conversation()
    assert conv.title == "New Conversation"

    # User message shorter than 50 chars
    store.add_message(conv.id, role="user", content="What is the flight time?")
    updated = store.get_conversation(conv.id)
    assert updated.title == "What is the flight time?"

    # Long user message
    conv2 = store.create_conversation()
    long_msg = "This is a very long question asking about the technical specifications of model A-100 and its battery capacity"
    store.add_message(conv2.id, role="user", content=long_msg)
    updated2 = store.get_conversation(conv2.id)
    assert len(updated2.title) <= 50
    assert updated2.title.endswith("...")

    # Assistant message does not auto-title
    conv3 = store.create_conversation()
    store.add_message(conv3.id, role="assistant", content="System announcement")
    updated3 = store.get_conversation(conv3.id)
    assert updated3.title == "New Conversation"


def test_persistence_across_store_reinstantiation(tmp_path: Path):
    db_file = tmp_path / "persistent.db"

    # Session 1: write conversation and messages
    store1 = SQLiteConversationStore(db_file)
    conv = store1.create_conversation("Persistent Conv")
    store1.add_message(conv.id, "user", "Question 1")
    store1.add_message(conv.id, "assistant", "Answer 1")

    # Session 2: re-open DB from disk and verify data
    store2 = SQLiteConversationStore(db_file)
    fetched = store2.get_conversation(conv.id)
    assert fetched is not None
    assert fetched.title == "Persistent Conv"
    assert fetched.message_count == 2

    messages = store2.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].content == "Question 1"
    assert messages[1].content == "Answer 1"


def test_corrupted_sources_json_handling(store: SQLiteConversationStore):
    conv = store.create_conversation("Corrupt Sources Test")
    msg = store.add_message(conv.id, "user", "Hello")

    # Directly inject invalid JSON into DB
    db_file = str(store.db_path)
    conn = sqlite3.connect(db_file)
    conn.execute("UPDATE messages SET sources_json = 'invalid-json{' WHERE id = ?;", (msg.id,))
    conn.commit()
    conn.close()

    messages = store.get_messages(conv.id)
    assert len(messages) == 1
    assert messages[0].sources == []


def test_global_store_singleton(tmp_path: Path, monkeypatch):
    custom_db = tmp_path / "global_test.db"
    monkeypatch.setenv("CONVERSATIONS_DB_PATH", str(custom_db))

    set_conversation_store(None)
    s1 = get_conversation_store()
    s2 = get_conversation_store()
    assert s1 is s2

    custom_store = SQLiteConversationStore(tmp_path / "another.db")
    set_conversation_store(custom_store)
    assert get_conversation_store() is custom_store

    # Test string path initialization
    str_store = SQLiteConversationStore(str(tmp_path / "str_store.db"))
    assert str_store.count_conversations() == 0

    # Test :memory: path initialization
    mem_store = SQLiteConversationStore(":memory:")
    assert mem_store.count_conversations() == 0
    mem_store.close()
    mem_store.close()  # idempotent

    set_conversation_store(None)

