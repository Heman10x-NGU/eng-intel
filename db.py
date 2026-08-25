"""SQLite schema, FTS5, and helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ingest_runs (
  id INTEGER PRIMARY KEY,
  company TEXT,
  source_type TEXT,
  method TEXT,
  fetched_at TEXT,
  n_rows INTEGER,
  coverage_start TEXT,
  coverage_end TEXT,
  truncated INTEGER DEFAULT 0,
  degraded INTEGER DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  company TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT,
  url TEXT UNIQUE,
  published_at TEXT,
  body_text TEXT,
  extra_json TEXT,
  ingest_run_id INTEGER REFERENCES ingest_runs(id),
  department TEXT GENERATED ALWAYS AS (json_extract(extra_json, '$.department')) VIRTUAL,
  is_remote INTEGER GENERATED ALWAYS AS (json_extract(extra_json, '$.is_remote')) VIRTUAL
);

CREATE INDEX IF NOT EXISTS idx_doc_scope ON documents(company, source_type, published_at);
CREATE INDEX IF NOT EXISTS idx_doc_remote ON documents(source_type, is_remote, department);
"""

FTS5_AVAILABLE = True


def _create_fts(conn: sqlite3.Connection) -> None:
    global FTS5_AVAILABLE
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                doc_id UNINDEXED,
                company UNINDEXED,
                source_type UNINDEXED,
                title,
                body_text
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
              INSERT INTO documents_fts(doc_id, company, source_type, title, body_text)
              VALUES (new.id, new.company, new.source_type, new.title, new.body_text);
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
              INSERT INTO documents_fts(documents_fts, rowid, doc_id, company, source_type, title, body_text)
              VALUES ('delete', old.id, old.id, old.company, old.source_type, old.title, old.body_text);
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
              INSERT INTO documents_fts(documents_fts, rowid, doc_id, company, source_type, title, body_text)
              VALUES ('delete', old.id, old.id, old.company, old.source_type, old.title, old.body_text);
              INSERT INTO documents_fts(doc_id, company, source_type, title, body_text)
              VALUES (new.id, new.company, new.source_type, new.title, new.body_text);
            END
            """
        )
    except sqlite3.OperationalError:
        FTS5_AVAILABLE = False


def init_db(path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    try:
        conn.execute("ALTER TABLE ingest_runs ADD COLUMN degraded INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    _create_fts(conn)
    conn.commit()
    return conn


@contextmanager
def get_conn(path: str | Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = init_db(path)
    try:
        yield conn
    finally:
        conn.close()


def rebuild_fts(conn: sqlite3.Connection) -> None:
    if not FTS5_AVAILABLE:
        return
    conn.execute("DELETE FROM documents_fts")
    conn.execute(
        """
        INSERT INTO documents_fts(doc_id, company, source_type, title, body_text)
        SELECT id, company, source_type, title, body_text FROM documents
        """
    )
    conn.commit()
