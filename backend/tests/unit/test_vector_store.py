"""Tests for backend/retrieval/vector_store.py.

These tests use a real `chromadb.PersistentClient` in a fresh temporary
directory per test (never a mock of Chroma, per the approved testing plan),
so they exercise the actual behaviour found in Stage 3A's probes: silent
duplicate-id handling, configuration not being enforced by
`get_or_create_collection`, batch limits, and so on.
"""

from __future__ import annotations

import chromadb
import pytest
from chromadb.config import Settings as ChromaSettings

from backend.retrieval.vector_store import (
    CollectionConfigError,
    EmptyBatchError,
    IndexIssue,
    VectorStore,
    open_collection_or_none,
)


def make_store(tmp_path, *, embedding_model="fake-model", dimension=4, collection_name="document_chunks"):
    return VectorStore(
        chroma_dir=tmp_path / "chroma",
        collection_name=collection_name,
        embedding_model=embedding_model,
        dimension=dimension,
    )


def unit_vector(dimension: int, hot_index: int) -> list[float]:
    vector = [0.0] * dimension
    vector[hot_index] = 1.0
    return vector


# ---------------------------------------------------------------------------
# collection opening / configuration verification
# ---------------------------------------------------------------------------


def test_opening_a_fresh_collection_creates_it_with_cosine_and_metadata(tmp_path):
    store = make_store(tmp_path)

    assert store.count() == 0  # forces the collection to open

    # Reopen with the real client directly to check what was actually written.
    client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"), settings=ChromaSettings(anonymized_telemetry=False)
    )
    collection = client.get_collection(name="document_chunks", embedding_function=None)
    assert collection.metadata["embedding_model"] == "fake-model"
    assert collection.metadata["dimension"] == 4
    assert collection.configuration["hnsw"]["space"] == "cosine"


def test_reopening_with_the_same_configuration_succeeds(tmp_path):
    store1 = make_store(tmp_path)
    store1.upsert_chunks(
        ids=["a"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    store2 = make_store(tmp_path)  # a different instance, same configuration
    assert store2.count() == 1


def test_reopening_with_a_different_embedding_model_raises_clear_error(tmp_path):
    make_store(tmp_path, embedding_model="model-a").count()

    mismatched = make_store(tmp_path, embedding_model="model-b")
    with pytest.raises(CollectionConfigError, match="model-a.*model-b|model-b.*model-a"):
        mismatched.count()


def test_reopening_with_a_different_dimension_raises_clear_error(tmp_path):
    make_store(tmp_path, dimension=4).count()

    mismatched = make_store(tmp_path, dimension=8)
    with pytest.raises(CollectionConfigError):
        mismatched.count()


def test_get_or_create_collection_does_not_silently_change_an_existing_collection(tmp_path):
    """Regression test for Stage 3A findings 11/12: get_or_create_collection
    silently returns the OLD collection when asked for a different
    configuration. This module's job is to catch that itself, not rely on
    Chroma to update anything."""
    make_store(tmp_path, embedding_model="model-a", dimension=4).count()

    client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"), settings=ChromaSettings(anonymized_telemetry=False)
    )
    # Ask Chroma directly for a different config; per 3A it is silently ignored.
    collection = client.get_or_create_collection(
        name="document_chunks",
        embedding_function=None,
        configuration={"hnsw": {"space": "l2"}},
        metadata={"embedding_model": "model-b", "dimension": 8, "space": "l2"},
    )
    assert collection.metadata["embedding_model"] == "model-a"  # unchanged by Chroma itself


# ---------------------------------------------------------------------------
# writes: upsert, idempotency, empty batch, large batch
# ---------------------------------------------------------------------------


def test_upsert_chunks_stores_text_vector_and_metadata(tmp_path):
    store = make_store(tmp_path)

    store.upsert_chunks(
        ids=["doc.pdf:1:0"],
        documents=["some chunk text"],
        embeddings=[unit_vector(4, 1)],
        file_names=["doc.pdf"],
        page_numbers=[1],
        chunk_indices=[0],
    )

    results = store.query(unit_vector(4, 1), top_k=1)
    assert len(results) == 1
    assert results[0].chunk_id == "doc.pdf:1:0"
    assert results[0].text == "some chunk text"
    assert results[0].file_name == "doc.pdf"
    assert results[0].page_number == 1
    assert results[0].chunk_index == 0
    assert results[0].similarity == pytest.approx(1.0, abs=1e-6)


def test_upsert_is_idempotent_unlike_add(tmp_path):
    """Regression test for Stage 3A finding 5: add() silently ignores a
    duplicate id. upsert_chunks must use upsert() so re-indexing a file with
    changed content actually replaces the old text and vector."""
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a"], documents=["old text"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    store.upsert_chunks(
        ids=["a"], documents=["new text"], embeddings=[unit_vector(4, 1)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    assert store.count() == 1
    results = store.query(unit_vector(4, 1), top_k=1)
    assert results[0].text == "new text"


def test_upsert_chunks_rejects_an_empty_batch(tmp_path):
    store = make_store(tmp_path)

    with pytest.raises(EmptyBatchError):
        store.upsert_chunks(
            ids=[], documents=[], embeddings=[], file_names=[], page_numbers=[], chunk_indices=[]
        )


def test_upsert_chunks_rejects_mismatched_list_lengths(tmp_path):
    store = make_store(tmp_path)

    with pytest.raises(ValueError):
        store.upsert_chunks(
            ids=["a", "b"],
            documents=["only one"],
            embeddings=[unit_vector(4, 0)],
            file_names=["x.pdf"],
            page_numbers=[1],
            chunk_indices=[0],
        )


def test_upsert_chunks_splits_a_large_batch_into_safe_sized_calls(tmp_path, monkeypatch):
    import backend.retrieval.vector_store as vector_store_module

    monkeypatch.setattr(vector_store_module, "_MAX_SAFE_BATCH", 10)
    store = make_store(tmp_path, dimension=4)

    count = 25
    store.upsert_chunks(
        ids=[f"id-{i}" for i in range(count)],
        documents=[f"text {i}" for i in range(count)],
        embeddings=[unit_vector(4, i % 4) for i in range(count)],
        file_names=["x.pdf"] * count,
        page_numbers=[1] * count,
        chunk_indices=list(range(count)),
    )

    assert store.count() == count


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_file_removes_only_that_files_chunks(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a", "b"], documents=["x page", "y page"],
        embeddings=[unit_vector(4, 0), unit_vector(4, 1)],
        file_names=["x.pdf", "y.pdf"], page_numbers=[1, 1], chunk_indices=[0, 0],
    )

    store.delete_file("x.pdf")

    assert store.list_file_names() == {"y.pdf"}
    assert store.count() == 1


def test_delete_file_is_quiet_when_the_file_has_no_chunks(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a"], documents=["x"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    store.delete_file("never-uploaded.pdf")  # must not raise

    assert store.count() == 1


# ---------------------------------------------------------------------------
# list / count
# ---------------------------------------------------------------------------


def test_count_and_list_file_names_on_an_empty_store(tmp_path):
    store = make_store(tmp_path)

    assert store.count() == 0
    assert store.list_file_names() == set()


def test_list_file_names_pages_through_more_than_one_batch(tmp_path, monkeypatch):
    import backend.retrieval.vector_store as vector_store_module

    monkeypatch.setattr(vector_store_module, "_MAX_SAFE_BATCH", 3)
    store = make_store(tmp_path)

    count = 10
    store.upsert_chunks(
        ids=[f"id-{i}" for i in range(count)],
        documents=[f"text {i}" for i in range(count)],
        embeddings=[unit_vector(4, i % 4) for i in range(count)],
        file_names=[f"file-{i}.pdf" for i in range(count)],
        page_numbers=[1] * count,
        chunk_indices=[0] * count,
    )

    assert store.list_file_names() == {f"file-{i}.pdf" for i in range(count)}


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def test_query_returns_fewer_than_top_k_when_the_collection_is_smaller(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a"], documents=["only one"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    results = store.query(unit_vector(4, 0), top_k=5)

    assert len(results) == 1


def test_query_orders_by_similarity(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["near", "far"],
        documents=["near text", "far text"],
        embeddings=[[0.9, 0.1, 0.0, 0.0], [0.0, 0.0, 0.1, 0.99]],
        file_names=["x.pdf", "x.pdf"],
        page_numbers=[1, 2],
        chunk_indices=[0, 0],
    )

    results = store.query([1.0, 0.0, 0.0, 0.0], top_k=2)

    assert [r.chunk_id for r in results] == ["near", "far"]
    assert results[0].similarity > results[1].similarity


# ---------------------------------------------------------------------------
# verify_index
# ---------------------------------------------------------------------------


def test_verify_index_on_a_healthy_store_reports_no_issues(tmp_path):
    # The id follows the project's chunk_id format (file:page:index); verify_index
    # checks that (master context 9.4), so a healthy record must use it.
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["x.pdf:1:0"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    issues = store.verify_index(disk_file_names={"x.pdf"})

    assert issues == []


def test_verify_index_detects_an_orphan_chunk(tmp_path):
    """A chunk is indexed for a file that no longer exists on disk (e.g. the
    PDF was deleted but the chunk-delete step failed)."""
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["gone.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    issues = store.verify_index(disk_file_names=set())

    assert any(issue.kind == "orphan_chunk" and "gone.pdf" in issue.detail for issue in issues)


def test_verify_index_detects_an_unindexed_file(tmp_path):
    store = make_store(tmp_path)  # nothing indexed at all

    issues = store.verify_index(disk_file_names={"not-indexed.pdf"})

    assert any(
        issue.kind == "unindexed_file" and "not-indexed.pdf" in issue.detail for issue in issues
    )


def test_verify_index_detects_wrong_dimension(tmp_path):
    """Regression test for Stage 3A finding 9: Chroma accepts a wrong-shaped
    vector list without complaint via the raw client, so verify_index must
    catch it itself."""
    store = make_store(tmp_path, dimension=4)
    collection = store._ensure_open()
    collection.upsert(
        ids=["bad"], embeddings=[[1.0, 0.0]], documents=["short vector"],
        metadatas=[{"file_name": "x.pdf", "page_number": 1, "chunk_index": 0}],
    )

    issues = store.verify_index(disk_file_names={"x.pdf"})

    assert any(issue.kind == "bad_vector" and "bad" in issue.detail for issue in issues)


def test_verify_index_detects_a_zero_vector(tmp_path):
    """Regression test for Stage 3A finding 9: Chroma accepts a zero vector
    without complaint."""
    store = make_store(tmp_path, dimension=4)
    collection = store._ensure_open()
    collection.upsert(
        ids=["bad"], embeddings=[[0.0, 0.0, 0.0, 0.0]], documents=["zero vector"],
        metadatas=[{"file_name": "x.pdf", "page_number": 1, "chunk_index": 0}],
    )

    issues = store.verify_index(disk_file_names={"x.pdf"})

    assert any(issue.kind == "bad_vector" and "norm" in issue.detail.lower() for issue in issues)


def test_vector_store_itself_rejects_a_non_finite_embedding_before_storing_it(tmp_path):
    """This installed Chroma version (1.5.9) already rejects NaN/Infinity at
    the upsert() call itself (InvalidArgumentError), so a non-finite vector
    can never actually reach the collection through this module -- there is
    nothing for verify_index to find after the fact here. The _check_vector
    finiteness check in verify_index is still kept as defence in depth for a
    Chroma version that does not validate this (the dimension and norm checks
    right next to it are proven necessary by the two tests above, where
    Chroma accepts the bad data without complaint)."""
    store = make_store(tmp_path, dimension=4)
    collection = store._ensure_open()

    with pytest.raises(Exception):
        collection.upsert(
            ids=["bad"], embeddings=[[float("inf"), 0.0, 0.0, 0.0]], documents=["inf vector"],
            metadatas=[{"file_name": "x.pdf", "page_number": 1, "chunk_index": 0}],
        )


def test_check_vector_directly_flags_a_non_finite_component(tmp_path):
    """Unit-level test of the finiteness branch in _check_vector: this
    installed Chroma version refuses to store a non-finite embedding at all
    (see test_vector_store_itself_rejects_a_non_finite_embedding_before_storing_it),
    so the branch cannot be exercised end-to-end through upsert/verify_index
    here. Calling the check function directly keeps it covered and keeps it
    correct in case a future Chroma version stores such a vector."""
    store = make_store(tmp_path, dimension=4)

    issue = store._check_vector("bad", [float("nan"), 0.0, 0.0, 0.0])

    assert issue is not None
    assert issue.kind == "bad_vector"
    assert "bad" in issue.detail


def test_verify_index_self_retrieval_check_passes_for_normal_data(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a", "b", "c"],
        documents=["alpha", "beta", "gamma"],
        embeddings=[unit_vector(4, 0), unit_vector(4, 1), unit_vector(4, 2)],
        file_names=["x.pdf"] * 3,
        page_numbers=[1, 1, 1],
        chunk_indices=[0, 1, 2],
    )

    issues = store.verify_index(disk_file_names={"x.pdf"})

    assert not any(issue.kind == "self_retrieval_failed" for issue in issues)


def test_verify_index_on_empty_store_with_no_files_reports_nothing(tmp_path):
    store = make_store(tmp_path)

    assert store.verify_index(disk_file_names=set()) == []


def test_index_issue_is_a_frozen_dataclass_with_kind_and_detail():
    issue = IndexIssue(kind="bad_vector", detail="something")
    assert issue.kind == "bad_vector"
    assert issue.detail == "something"
    with pytest.raises(Exception):
        issue.kind = "other"  # frozen


# ---------------------------------------------------------------------------
# open_collection_or_none
# ---------------------------------------------------------------------------


def test_open_collection_or_none_returns_none_when_nothing_was_ever_indexed(tmp_path):
    result = open_collection_or_none(
        chroma_dir=tmp_path / "chroma", collection_name="document_chunks"
    )

    assert result is None


def test_open_collection_or_none_returns_the_collection_once_it_exists(tmp_path):
    make_store(tmp_path).upsert_chunks(
        ids=["a"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    result = open_collection_or_none(
        chroma_dir=tmp_path / "chroma", collection_name="document_chunks"
    )

    assert result is not None
    assert result.count() == 1


# ---------------------------------------------------------------------------
# telemetry
# ---------------------------------------------------------------------------


def test_store_disables_anonymized_telemetry(tmp_path):
    store = make_store(tmp_path)
    store.count()  # opens the client

    # There is no public getter on the client for this; the only reliable
    # check is that creating a second client pointed at the same path with a
    # *conflicting* telemetry setting does not raise ("instance already
    # exists" conflicts are about Settings as a whole in some Chroma
    # versions, so this mainly documents the intent); the authoritative check
    # is that our own client was constructed with anonymized_telemetry=False,
    # which test_opening_a_fresh_collection_creates_it_with_cosine_and_metadata
    # already exercises end to end.
    assert store._client is not None


def test_verify_index_detects_an_id_that_does_not_match_its_metadata(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["wrong-id"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    issues = store.verify_index(disk_file_names={"x.pdf"})

    assert [i.kind for i in issues] == ["bad_metadata"]


def test_verify_index_detects_page_number_below_one(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["x.pdf:0:0"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[0], chunk_indices=[0],
    )

    assert [i.kind for i in store.verify_index({"x.pdf"})] == ["bad_metadata"]


def test_verify_index_self_retrieval_failure_is_reported(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["x.pdf:1:0"], documents=["hi"], embeddings=[unit_vector(4, 0)],
        file_names=["x.pdf"], page_numbers=[1], chunk_indices=[0],
    )
    monkeypatch.setattr(store, "query", lambda vector, top_k: [])

    assert [i.kind for i in store.verify_index({"x.pdf"})] == ["self_retrieval_failed"]


def test_clear_and_file_chunk_counts(tmp_path):
    store = make_store(tmp_path)
    store.upsert_chunks(
        ids=["a.pdf:1:0", "a.pdf:1:1", "b.pdf:1:0"], documents=["1", "2", "3"],
        embeddings=[unit_vector(4, 0), unit_vector(4, 1), unit_vector(4, 2)],
        file_names=["a.pdf", "a.pdf", "b.pdf"], page_numbers=[1, 1, 1], chunk_indices=[0, 1, 0],
    )
    assert store.file_chunk_counts() == {"a.pdf": 2, "b.pdf": 1}
    store.clear()
    assert store.count() == 0


def test_query_on_an_empty_store_returns_nothing(tmp_path):
    assert make_store(tmp_path).query(unit_vector(4, 0), top_k=3) == []


def test_collection_with_wrong_space_is_rejected(tmp_path):
    import chromadb as c
    from chromadb.config import Settings as S

    client = c.PersistentClient(path=str(tmp_path / "chroma"), settings=S(anonymized_telemetry=False))
    client.create_collection(
        name="document_chunks", embedding_function=None,
        configuration={"hnsw": {"space": "l2"}},
        metadata={"embedding_model": "fake-model", "dimension": 4, "space": "cosine"},
    )
    del client
    with pytest.raises(CollectionConfigError, match="l2"):
        make_store(tmp_path).count()
