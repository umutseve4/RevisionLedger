# Roadmap

RevisionLedger grows only after the current evidence gate is green.

## M1 — One real revision vertical slice

Acceptance criteria:

- [x] bitemporal SQLite schema and parameterized `AS OF` query;
- [x] fail-closed checksum, byte-size, and vintage-header validation;
- [x] idempotent transactional ingestion and conflict failure;
- [x] automated interval, boundary, missing-value, and provenance tests;
- [x] official fixture bytes committed by the bootstrap workflow;
- [x] every `main` commit is CI-covered, and the change that produced the final
      state has a green run bound to its exact head SHA.

Note on the last criterion: a commit cannot contain the result of its own CI
run, so a hardcoded "final SHA is green" line goes stale on the very next
commit. The verifiable formulation is the one above — the `push: main` trigger
guarantees that no `main` commit escapes the `verify` job, each run pins and
asserts the exact checked-out SHA, and the CI badge in the README reports the
current `main` result. Evidence for a specific change is its pull request's
check runs plus the uploaded `verified-sha.txt` and `pytest.xml` artifacts.

## M2 — Generalize without weakening provenance

Planned:

1. support multiple series and longer observation windows;
2. publish a JSON Schema for the fixture manifest;
3. add schema migrations and a CLI;
4. test late/out-of-order vintages and changed observation calendars;
5. add property-based temporal invariant tests.

Definition of done: at least three series, deterministic offline replay, migration tests, and final-commit CI evidence.

## M3 — Operational durability

Planned:

1. PostgreSQL adapter and transaction-isolation tests;
2. append-only audit events and metrics;
3. backup/restore rehearsal;
4. concurrent-writer and failure-recovery tests;
5. versioned release artifacts and a reproducible demo.

Production-ready will not be claimed before these controls are implemented, tested, and operationally verified.
