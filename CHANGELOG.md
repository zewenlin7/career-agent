# Changelog

## Unreleased

### Added

- v0.1a Foundation modular Python package with uv lockfile, Python 3.12 baseline,
  FastAPI/Pydantic v2, async SQLAlchemy/asyncpg, Alembic and PostgreSQL Compose configuration.
- Initial migration for personal profiles/facts/STAR structures, sources, companies,
  versioned jobs/requirements, application/event history, interview/knowledge records
  and run/step/model-call/tool-call/observation metadata.
- Explicit fact verification/rejection, proposed replacements with lineage/revisions,
  versioned profile/JD writes, application state/correction events and transaction guards.
- Typed `/api/v1` domain APIs and read-only run/step queries, pagination, stable safe errors.
- Model-independent request/task/schema contracts, static tier/capability/privacy policy,
  injected fake provider, validated results and usage/latency/cost/version metadata.
- Nullable provenance fields, validated metadata JSONB and unknown-usage semantics.
- External private-data configuration, ignore rules, allowlisted logs, basic redaction,
  private-path/raw-provider-error protection and synthetic fixtures.
- PostgreSQL integration/API tests including migration drift, FK/unique/delete behavior,
  rollback, revisions, concurrent application writes and privacy metadata rejection.
- Ruff, strict mypy and a synthetic PostgreSQL GitHub Actions workflow.
- README with actual capabilities/setup/API/testing, architecture boundaries and full
  milestone/optional-extension roadmap in TODO.

### Verified locally

- Docker Compose PostgreSQL starts healthy; initial Alembic upgrade succeeds from empty.
- Locked dependency installation succeeds in a new virtual environment.
- Full suite: **57 passed**, no warnings; includes real temporary PostgreSQL databases.
- Ruff check and format check pass; strict mypy passes for all 14 source modules.
- FastAPI starts under Uvicorn; live HTTP health and OpenAPI (21 operations) verified.
- Alembic reports no schema drift; tracked and untracked files pass whitespace checks.

No final v0.1.0 release, commit or push is part of this milestone.
The GitHub Actions configuration has not been run remotely.
