# Contributing

RevisionLedger is an evidence-first bitemporal data project. Keep changes narrow, reviewable, and reproducible.

## Development

```bash
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
pytest
```

Pull requests should explain the temporal or provenance invariant being changed and include tests for behavior changes. Do not replace committed official fixtures or their manifest metadata without documenting the source URL, retrieval timestamp, byte size, and SHA-256 checksum.

## Evidence boundaries

- CI must remain deterministic and must not fetch live economic data.
- Never commit credentials, signed URLs, private data, or local databases.
- Treat fixture refreshes as reviewed data changes, separate from application logic when practical.
- Do not claim production readiness without operational evidence for migrations, backups, monitoring, and concurrent writers.
