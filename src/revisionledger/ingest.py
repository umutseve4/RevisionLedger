"""Fail-closed ingestion of immutable ALFRED vintage fixtures."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from typing import Any


class IngestionError(RuntimeError):
    """Fixture provenance, format, or temporal invariants are invalid."""


@dataclass(frozen=True)
class Fixture:
    path: Path
    series_id: str
    vintage_date: str
    source_url: str
    retrieved_at: str
    byte_size: int
    sha256: str


def load_manifest(path: str | Path) -> list[Fixture]:
    manifest_path = Path(path)
    payload: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("fixtures"), list):
        raise IngestionError("manifest must use schema_version 1 and contain fixtures")
    fixtures = []
    for item in payload["fixtures"]:
        fixtures.append(
            Fixture(
                path=manifest_path.parent / item["path"],
                series_id=item["series_id"],
                vintage_date=item["vintage_date"],
                source_url=item["source_url"],
                retrieved_at=item["retrieved_at"],
                byte_size=item["byte_size"],
                sha256=item["sha256"],
            )
        )
    return fixtures


def _parse(fixture: Fixture, raw: bytes) -> list[tuple[str, str | None, str | None]]:
    try:
        text = raw.decode("utf-8-sig", "strict")
    except UnicodeDecodeError as exc:
        raise IngestionError(f"fixture is not UTF-8: {fixture.path}") from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise IngestionError("fixture is empty") from exc
    expected = ["observation_date", f"{fixture.series_id}_{fixture.vintage_date.replace('-', '')}"]
    if header != expected:
        raise IngestionError(f"expected header {expected!r}, got {header!r}")

    parsed: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for line_number, row in enumerate(reader, start=2):
        if len(row) != 2:
            raise IngestionError(f"row {line_number} must have exactly 2 columns")
        try:
            observation_date = date.fromisoformat(row[0]).isoformat()
        except ValueError as exc:
            raise IngestionError(f"row {line_number} has invalid observation date") from exc
        if observation_date in seen:
            raise IngestionError(f"duplicate observation date: {observation_date}")
        seen.add(observation_date)
        cell = row[1].strip()
        if cell in {"", "."}:
            value_text = None
        else:
            try:
                value_text = format(Decimal(cell), "f")
            except InvalidOperation as exc:
                raise IngestionError(f"row {line_number} has invalid decimal value") from exc
        parsed.append((observation_date, value_text))
    if not parsed:
        raise IngestionError("fixture has no observations")
    if [row[0] for row in parsed] != sorted(row[0] for row in parsed):
        raise IngestionError("observation dates must be strictly increasing")
    return [
        (observation_date, value_text, parsed[index + 1][0] if index + 1 < len(parsed) else None)
        for index, (observation_date, value_text) in enumerate(parsed)
    ]


def ingest_fixture(connection: sqlite3.Connection, fixture: Fixture) -> int:
    """Ingest one fixture atomically; return inserted observations (0 means no-op)."""
    raw = fixture.path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != fixture.sha256:
        raise IngestionError(f"checksum mismatch for {fixture.path.name}")
    if len(raw) != fixture.byte_size:
        raise IngestionError(f"byte-size mismatch for {fixture.path.name}")
    rows = _parse(fixture, raw)

    with connection:
        registered = connection.execute(
            "SELECT sha256 FROM fixture_registry WHERE series_id = ? AND vintage_date = ?",
            (fixture.series_id, fixture.vintage_date),
        ).fetchone()
        if registered:
            if registered["sha256"] != fixture.sha256:
                raise IngestionError("same series/vintage has a different checksum")
            return 0
        connection.execute(
            """INSERT INTO fixture_registry
               (series_id, vintage_date, sha256, source_url, retrieved_at, byte_size)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                fixture.series_id,
                fixture.vintage_date,
                fixture.sha256,
                fixture.source_url,
                fixture.retrieved_at,
                fixture.byte_size,
            ),
        )
        for observation_date, value_text, valid_to in rows:
            connection.execute(
                """INSERT INTO observations
                   (series_id, observation_date, source_vintage_date, value_text,
                    valid_from, valid_to, system_from, system_to, ingested_at, fixture_sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (
                    fixture.series_id,
                    observation_date,
                    fixture.vintage_date,
                    value_text,
                    observation_date,
                    valid_to,
                    fixture.vintage_date,
                    fixture.retrieved_at,
                    fixture.sha256,
                ),
            )
        _rebuild_system_intervals(connection, fixture.series_id)
    return len(rows)


def _rebuild_system_intervals(connection: sqlite3.Connection, series_id: str) -> None:
    observation_dates = connection.execute(
        "SELECT DISTINCT observation_date FROM observations WHERE series_id = ?",
        (series_id,),
    ).fetchall()
    for item in observation_dates:
        observation_date = item["observation_date"]
        vintages = connection.execute(
            """SELECT source_vintage_date FROM observations
               WHERE series_id = ? AND observation_date = ?
               ORDER BY source_vintage_date""",
            (series_id, observation_date),
        ).fetchall()
        for index, vintage in enumerate(vintages):
            next_vintage = (
                vintages[index + 1]["source_vintage_date"]
                if index + 1 < len(vintages)
                else None
            )
            connection.execute(
                """UPDATE observations SET system_to = ?
                   WHERE series_id = ? AND observation_date = ? AND source_vintage_date = ?""",
                (next_vintage, series_id, observation_date, vintage["source_vintage_date"]),
            )


def ingest_manifest(connection: sqlite3.Connection, path: str | Path) -> int:
    """Ingest all fixtures in chronological order and return inserted row count."""
    fixtures = sorted(load_manifest(path), key=lambda item: (item.series_id, item.vintage_date))
    return sum(ingest_fixture(connection, fixture) for fixture in fixtures)
