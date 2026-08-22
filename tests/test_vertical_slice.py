from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from revisionledger import (
    IngestionError,
    as_of,
    connect,
    ingest_fixture,
    ingest_manifest,
    load_manifest,
)


def write_fixture(tmp_path: Path, vintage: str, value: str = "22672.859") -> Path:
    name = f"gdpc1_{vintage}.csv"
    raw = f"observation_date,GDPC1_{vintage.replace('-', '')}\n2023-10-01,{value}\n".encode()
    (tmp_path / name).write_bytes(raw)
    manifest = {
        "schema_version": 1,
        "fixtures": [
            {
                "path": name,
                "series_id": "GDPC1",
                "vintage_date": vintage,
                "source_url": f"https://alfred.stlouisfed.org/example?vintage_date={vintage}",
                "retrieved_at": "2026-08-22T00:00:00Z",
                "byte_size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ],
    }
    path = tmp_path / f"manifest-{vintage}.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def ingest_pair(tmp_path: Path) -> sqlite3.Connection:
    connection = connect()
    ingest_manifest(connection, write_fixture(tmp_path, "2024-02-28", "22668.986"))
    ingest_manifest(connection, write_fixture(tmp_path, "2024-01-25", "22672.859"))
    return connection


def test_manifest_requires_schema_version_one(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version": 2, "fixtures": []}', encoding="utf-8")
    with pytest.raises(IngestionError, match="schema_version 1"):
        load_manifest(path)


def test_checksum_mismatch_fails_before_database_write(tmp_path: Path) -> None:
    fixture = load_manifest(write_fixture(tmp_path, "2024-01-25"))[0]
    fixture.path.write_text("tampered", encoding="utf-8")
    connection = connect()
    with pytest.raises(IngestionError, match="checksum mismatch"):
        ingest_fixture(connection, fixture)
    assert connection.execute("SELECT count(*) FROM fixture_registry").fetchone()[0] == 0


def test_byte_size_mismatch_fails(tmp_path: Path) -> None:
    fixture = load_manifest(write_fixture(tmp_path, "2024-01-25"))[0]
    with pytest.raises(IngestionError, match="byte-size mismatch"):
        ingest_fixture(connect(), replace(fixture, byte_size=fixture.byte_size + 1))


def test_vintage_stamped_header_is_required(tmp_path: Path) -> None:
    fixture = load_manifest(write_fixture(tmp_path, "2024-01-25"))[0]
    raw = fixture.path.read_bytes().replace(b"GDPC1_20240125", b"GDPC1")
    fixture.path.write_bytes(raw)
    fixture = replace(fixture, sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw))
    with pytest.raises(IngestionError, match="expected header"):
        ingest_fixture(connect(), fixture)


def test_decimal_is_preserved_as_canonical_text(tmp_path: Path) -> None:
    connection = connect()
    ingest_manifest(connection, write_fixture(tmp_path, "2024-01-25", "22672.8590"))
    row = connection.execute("SELECT value_text FROM observations").fetchone()
    assert row["value_text"] == "22672.8590"
    assert as_of(connection, "GDPC1", "2023-10-01", "2024-02-01").value == Decimal("22672.8590")


@pytest.mark.parametrize("missing", [".", ""])
def test_missing_values_become_null_not_zero(tmp_path: Path, missing: str) -> None:
    connection = connect()
    ingest_manifest(connection, write_fixture(tmp_path, "2024-01-25", missing))
    result = as_of(connection, "GDPC1", "2023-10-01", "2024-02-01")
    assert result is not None and result.value is None


def test_idempotent_reingestion_is_no_op(tmp_path: Path) -> None:
    connection = connect()
    path = write_fixture(tmp_path, "2024-01-25")
    assert ingest_manifest(connection, path) == 1
    assert ingest_manifest(connection, path) == 0
    assert connection.execute("SELECT count(*) FROM observations").fetchone()[0] == 1


def test_same_vintage_different_checksum_is_hard_failure(tmp_path: Path) -> None:
    connection = connect()
    fixture = load_manifest(write_fixture(tmp_path, "2024-01-25"))[0]
    ingest_fixture(connection, fixture)
    connection.execute(
        "UPDATE fixture_registry SET sha256 = ? WHERE series_id = ? AND vintage_date = ?",
        ("0" * 64, "GDPC1", "2024-01-25"),
    )
    with pytest.raises(IngestionError, match="different checksum"):
        ingest_fixture(connection, fixture)


def test_as_of_before_revision_returns_first_value(tmp_path: Path) -> None:
    result = as_of(ingest_pair(tmp_path), "GDPC1", "2023-10-01", "2024-02-27")
    assert result is not None
    assert result.value == Decimal("22672.859")
    assert result.source_vintage_date == "2024-01-25"
    assert result.system_to == "2024-02-28"


def test_as_of_revision_boundary_returns_second_value(tmp_path: Path) -> None:
    result = as_of(ingest_pair(tmp_path), "GDPC1", "2023-10-01", "2024-02-28")
    assert result is not None
    assert result.value == Decimal("22668.986")
    assert result.source_vintage_date == "2024-02-28"
    assert result.system_to is None


def test_before_first_vintage_returns_none(tmp_path: Path) -> None:
    assert as_of(ingest_pair(tmp_path), "GDPC1", "2023-10-01", "2024-01-24") is None


def test_exactly_one_open_system_interval(tmp_path: Path) -> None:
    connection = ingest_pair(tmp_path)
    open_count = connection.execute(
        """SELECT count(*) FROM observations
           WHERE series_id = 'GDPC1' AND observation_date = '2023-10-01' AND system_to IS NULL"""
    ).fetchone()[0]
    assert open_count == 1


def test_system_intervals_do_not_overlap(tmp_path: Path) -> None:
    connection = ingest_pair(tmp_path)
    overlaps = connection.execute(
        """SELECT count(*) FROM observations a JOIN observations b
           ON a.series_id = b.series_id AND a.observation_date = b.observation_date
          AND a.source_vintage_date < b.source_vintage_date
          AND (a.system_to IS NULL OR a.system_to > b.system_from)"""
    ).fetchone()[0]
    assert overlaps == 0


def test_as_of_index_exists() -> None:
    indexes = {row["name"] for row in connect().execute("PRAGMA index_list(observations)")}
    assert "idx_observations_as_of" in indexes


def test_committed_official_vertical_slice() -> None:
    manifest = Path(__file__).parents[1] / "data" / "raw" / "manifest.json"
    connection = connect()
    assert ingest_manifest(connection, manifest) == 2
    first = as_of(connection, "GDPC1", "2023-10-01", "2024-02-27")
    second = as_of(connection, "GDPC1", "2023-10-01", "2024-02-28")
    assert first is not None and first.value == Decimal("22672.859")
    assert second is not None and second.value == Decimal("22668.986")
    assert first.fixture_sha256 != second.fixture_sha256
