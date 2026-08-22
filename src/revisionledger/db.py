"""SQLite schema and connection helpers for RevisionLedger."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fixture_registry (
    series_id TEXT NOT NULL,
    vintage_date TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    PRIMARY KEY (series_id, vintage_date)
);

CREATE TABLE IF NOT EXISTS observations (
    series_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    source_vintage_date TEXT NOT NULL,
    value_text TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    system_from TEXT NOT NULL,
    system_to TEXT,
    ingested_at TEXT NOT NULL,
    fixture_sha256 TEXT NOT NULL,
    PRIMARY KEY (series_id, observation_date, source_vintage_date),
    FOREIGN KEY (series_id, source_vintage_date)
        REFERENCES fixture_registry(series_id, vintage_date),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (system_to IS NULL OR system_to > system_from)
);

CREATE INDEX IF NOT EXISTS idx_observations_as_of
ON observations(series_id, valid_from, valid_to, system_from, system_to);
"""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a connection with integrity checks enabled and install the schema."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection
