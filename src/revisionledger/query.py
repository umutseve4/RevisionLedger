"""Point-in-time queries over both valid time and knowledge time."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import sqlite3


@dataclass(frozen=True)
class Observation:
    series_id: str
    observation_date: str
    value: Decimal | None
    source_vintage_date: str
    valid_to: str | None
    system_to: str | None
    fixture_sha256: str


def as_of(
    connection: sqlite3.Connection,
    series_id: str,
    economic_date: str,
    knowledge_date: str,
) -> Observation | None:
    """Return what the ledger says was known at the two requested dates."""
    row = connection.execute(
        """SELECT series_id, observation_date, value_text, source_vintage_date,
                  valid_to, system_to, fixture_sha256
           FROM observations
           WHERE series_id = ?
             AND valid_from <= ?
             AND (valid_to > ? OR valid_to IS NULL)
             AND system_from <= ?
             AND (system_to > ? OR system_to IS NULL)
           ORDER BY valid_from DESC
           LIMIT 1""",
        (series_id, economic_date, economic_date, knowledge_date, knowledge_date),
    ).fetchone()
    if row is None:
        return None
    return Observation(
        series_id=row["series_id"],
        observation_date=row["observation_date"],
        value=Decimal(row["value_text"]) if row["value_text"] is not None else None,
        source_vintage_date=row["source_vintage_date"],
        valid_to=row["valid_to"],
        system_to=row["system_to"],
        fixture_sha256=row["fixture_sha256"],
    )
