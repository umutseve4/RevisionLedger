# RevisionLedger

[![CI](https://github.com/umutseve4/RevisionLedger/actions/workflows/ci.yml/badge.svg)](https://github.com/umutseve4/RevisionLedger/actions/workflows/ci.yml)

A small, evidence-first bitemporal ledger for answering:

> What economic value was valid for a period, and what was known about it on a specific decision date?

The first vertical slice stores two official ALFRED vintages of **Real Gross Domestic Product (`GDPC1`)** for observation **2023-10-01**:

| Source vintage | Value | Knowledge interval |
|---|---:|---|
| 2024-01-25 | 22672.859 | `[2024-01-25, 2024-02-28)` |
| 2024-02-28 | 22668.986 | `[2024-02-28, ∞)` |

The values are kept as canonical decimal text, not binary floating point. Each committed source response is bound to its exact URL, retrieval timestamp, byte size, and SHA-256 checksum in `data/raw/manifest.json`.

## Why bitemporal?

A normal time series records when a value applies. A bitemporal table records both:

- **valid time** — the economic observation interval `[valid_from, valid_to)`;
- **system/knowledge time** — the locally captured vintage interval `[system_from, system_to)`.

`system_to IS NULL` means "latest snapshot in this local ledger," not "still current at ALFRED."

## Reproduce

```bash
python -m pip install -e ".[dev]"
pytest
ruff format --check .
ruff check .
```

CI runs from committed fixtures without live-data network access or repository write permission. Pull-request verification uploads JUnit XML plus the exact checked-out Git SHA as a run artifact. Fixture refreshes are explicit, reviewable data changes performed outside the verification workflow; `scripts/fetch_fixtures.py` validates bounded responses before they are proposed for commit.

## Query

```python
from revisionledger import as_of, connect, ingest_manifest

connection = connect("revisionledger.db")
ingest_manifest(connection, "data/raw/manifest.json")

before = as_of(connection, "GDPC1", "2023-10-01", "2024-02-27")
after = as_of(connection, "GDPC1", "2023-10-01", "2024-02-28")
print(before.value, after.value)  # 22672.859 22668.986
```

The query is parameterized and applies both half-open intervals:

```sql
WHERE series_id = ?
  AND valid_from <= ?
  AND (valid_to > ? OR valid_to IS NULL)
  AND system_from <= ?
  AND (system_to > ? OR system_to IS NULL)
```

## Guarantees tested

- exact SHA-256 and byte-size verification before database writes;
- vintage-stamped ALFRED header verification (`GDPC1_YYYYMMDD`);
- transactional ingestion and foreign-key enforcement;
- unique `(series_id, observation_date, source_vintage_date)` rows;
- idempotent replay of the same fixture;
- hard failure for same vintage with a different checksum;
- no overlapping knowledge intervals and exactly one open interval;
- exact boundary behavior before and on the revision date;
- missing `.` or empty cells become `NULL`, never zero;
- an index supporting the point-in-time query.

## Evidence status

| Layer | Status | Evidence |
|---|---|---|
| Problem and temporal model | Implemented | schema, interval semantics, parameterized query |
| Official bounded fixtures | Verified | bootstrap commit `1fe178c02a89399c1de4a8034e34b4105e7da000` and manifest |
| 2024-01-25 fixture | Verified | 53 bytes; SHA-256 `85c7e1895b21a217b73e1fdc8f3a1cc2953afdbe321d27c301ce228466b3414a` |
| 2024-02-28 fixture | Verified | 53 bytes; SHA-256 `6d0598234b9a97d4cef47a1f91cae0d51f2bd87e8d680d2bffd5e6a5feb04753` |
| Automated behavior | Tested | GitHub-hosted JUnit evidence: 16 tests, 0 failures, 0 errors, 0 skipped |
| `main` CI coverage | Verified | `push: main` runs the full matrix on every `main` commit; each job pins and asserts its exact checked-out SHA in `verified-sha.txt`; the badge above reports the current `main` result |
| Deployment | Not applicable | library vertical slice |
| Production-ready | Not claimed | no migrations, backup, monitoring, or multi-writer design |

The two fixture byte lengths and SHA-256 values above were independently recomputed from the committed bytes and matched `data/raw/manifest.json` exactly.

No commit can contain the result of its own CI run, so this table reports the coverage guarantee rather than a hardcoded run id that would go stale on the next push. The per-change evidence is the pull request's check runs together with the `verified-sha.txt` and `pytest.xml` artifacts uploaded by that run.

## Source and limitations

Fixtures come from the [Federal Reserve Bank of St. Louis ALFRED graph endpoint](https://alfred.stlouisfed.org/) with `id`, `cosd`, `coed`, and `vintage_date` fixed in the manifest. ALFRED describes a vintage date as the historical data version available on that date.

This repository proves one real revision path. It does not yet provide a general downloader, migration framework, concurrent-writer protocol, or operational service. See [ROADMAP.md](ROADMAP.md).

## License

MIT — see [LICENSE](LICENSE).
