"""One-time, fail-closed retrieval of bounded official ALFRED snapshots."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OBSERVATION_DATE = "2023-10-01"
SERIES_ID = "GDPC1"
EXPECTED = {
    "2024-01-25": "22672.859",
    "2024-02-28": "22668.986",
}


def fetch(url: str) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "RevisionLedger/0.1 (+https://github.com/umutseve4/RevisionLedger)"},
    )
    error: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=45) as response:  # noqa: S310 - fixed HTTPS host
                if response.status != 200:
                    raise RuntimeError(f"unexpected HTTP status {response.status}")
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"ALFRED retrieval failed after 4 attempts: {error}")


def validate(raw: bytes, vintage_date: str) -> None:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig", "strict"))))
    expected_header = ["observation_date", f"{SERIES_ID}_{vintage_date.replace('-', '')}"]
    if not rows or rows[0] != expected_header:
        raise RuntimeError(f"vintage header mismatch: expected {expected_header!r}")
    data_rows = [row for row in rows[1:] if row]
    if data_rows != [[OBSERVATION_DATE, EXPECTED[vintage_date]]]:
        raise RuntimeError(f"official response did not match locked evidence: {data_rows!r}")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    fixtures = []
    for vintage_date in EXPECTED:
        url = (
            "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
            f"?id={SERIES_ID}&cosd={OBSERVATION_DATE}&coed={OBSERVATION_DATE}"
            f"&vintage_date={vintage_date}"
        )
        raw = fetch(url)
        validate(raw, vintage_date)
        name = f"{SERIES_ID.lower()}_{vintage_date}.csv"
        (RAW / name).write_bytes(raw)
        fixtures.append(
            {
                "path": name,
                "series_id": SERIES_ID,
                "vintage_date": vintage_date,
                "observation_date_range": {"start": OBSERVATION_DATE, "end": OBSERVATION_DATE},
                "source_url": url,
                "retrieved_at": retrieved_at,
                "byte_size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    (RAW / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "fixtures": fixtures}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: wrote {len(fixtures)} official fixtures and manifest")


if __name__ == "__main__":
    main()
