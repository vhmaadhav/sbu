"""LanceDB chunk index: vector search with metadata filters."""
import fcntl
import threading
from contextlib import contextmanager
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import lancedb
import pyarrow as pa

from core.config import LANCEDB_DIR
from core.embed import EMBED_DIM, embed

TABLE = "chunks"
_WRITE_LOCK = threading.RLock()
_LOCK_PATH = LANCEDB_DIR / ".write.lock"

SCHEMA = pa.schema([
    pa.field("chunk_id", pa.int64()),
    pa.field("item_id", pa.int64()),
    pa.field("subject", pa.string()),
    pa.field("source_label", pa.string()),
    pa.field("text", pa.string()),
    pa.field("ts_start", pa.float64()),
    pa.field("page", pa.int64()),
    pa.field("image_path", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
])


@contextmanager
def _write_lock():
    """Serialize LanceDB mutations across API, worker, and Telegram processes."""
    LANCEDB_DIR.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK, Path(_LOCK_PATH).open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@lru_cache(maxsize=1)
def _table():
    # A zero read-consistency interval keeps cached handles current when the API
    # and Telegram bot each run an ingestion worker against the same local DB.
    db = lancedb.connect(
        str(LANCEDB_DIR),
        read_consistency_interval=timedelta(seconds=0),
    )
    # lru_cache can execute this function more than once during a concurrent
    # first call. exist_ok makes table initialization atomic and idempotent.
    with _write_lock():
        return db.create_table(TABLE, schema=SCHEMA, exist_ok=True)


def ensure_ready() -> None:
    """Create or open the index without loading an embedding model."""
    _table()


def _id_filter(chunk_ids: list[int]) -> str:
    ids = sorted({int(chunk_id) for chunk_id in chunk_ids})
    if not ids:
        raise ValueError("at least one chunk id is required")
    return "chunk_id IN (" + ", ".join(map(str, ids)) + ")"


def _mutate(operation) -> None:
    """Run an idempotent mutation, refreshing a stale cross-process handle once.

    LanceDB handles can occasionally surface ``EIO`` after another Study Buddy
    process commits a new manifest. Reopening the table is safe here because all
    callers use idempotent delete/add or deterministic update operations.
    """
    try:
        table = _table()
        with _write_lock():
            operation(table)
    except OSError as error:
        if error.errno != 5:
            raise
        _table.cache_clear()
        table = _table()
        with _write_lock():
            operation(table)


def add_chunks(rows: list[dict]):
    """rows: chunk_id, item_id, subject, source_label, text, ts_start, page, image_path."""
    if not rows:
        return
    vectors = embed([r["text"] for r in rows])
    for r, v in zip(rows, vectors):
        r["vector"] = v
        r.setdefault("ts_start", None)
        r.setdefault("page", None)
        r.setdefault("image_path", None)
    chunk_ids = [int(row["chunk_id"]) for row in rows]
    def write(table):
        # Retrying a completed SQLite write must not duplicate its vectors.
        table.delete(_id_filter(chunk_ids))
        table.add(rows)
    _mutate(write)


def delete_chunks(chunk_ids: list[int]) -> None:
    if not chunk_ids:
        return
    def delete(table):
        table.delete(_id_filter(chunk_ids))
    _mutate(delete)


def update_item_subject(item_id: int, subject: str) -> None:
    def update(table):
        table.update({"subject": subject}, where=f"item_id = {int(item_id)}")
    _mutate(update)


def search(query: str, subject: str | None = None, k: int = 8) -> list[dict]:
    q = _table().search(embed([query])[0])
    if subject:
        q = q.where(f"subject = '{subject.replace(chr(39), chr(39)*2)}'")
    return q.limit(k).to_list()
