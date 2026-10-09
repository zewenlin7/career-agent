# Career Agent

Career Agent is a primarily single-user personal job-search Agent engineering project.
The current milestone is **v0.1a Foundation**, part of the eventual **v0.1 Domain MVP**.
Development and demonstrations use synthetic data; this is not a multi-user production service.

## Implemented now

- Versioned personal profile, user-confirmed facts and replacement history.
- Manual JD ingestion, explicit requirements, immutable JD revisions, company records.
- Application tracker with optimistic revision checks, status/correction/note events.
- Interview rounds and manual notes; knowledge-note CRUD basics.
- PostgreSQL persistence for source documents, STAR structures and runtime metadata.
- Read-only run/step API; no endpoint executes an Agent workflow.
- Model-independent contracts, static policy/capability filtering and an injected fake provider.
- Safe error responses, allowlisted operational logging and private-data configuration.
- Synthetic tests using a real temporary PostgreSQL database, Ruff and strict mypy.

There is **no LLM job preparation, resume compilation, PDF generation, research, LangGraph,
worker, vector search or frontend yet**. No real model provider or paid API is connected.

## Architecture

`FastAPI → application services → domain rules / async SQLAlchemy → PostgreSQL`

Model calls have a separate `ModelRequestContext → policy → candidate → adapter → ModelResult`
contract. They do not read an Agent State. Domain services contain no provider/model names.
Runtime records are operational metadata, not domain knowledge or checkpoint storage.
See [architecture](docs/architecture.md) for boundaries and planned evolution.

```text
src/career_agent/
  api/             typed API inputs/outputs and safe errors
  domain/          lifecycle rules and structured data schemas
  application/     transactional use cases and revision checks
  infrastructure/  async persistence and mapped entities
  models/          contracts, static policy/gateway, fake provider
  runtime/         usage, budget and nullable version metadata
  security/        redaction and allowlisted logging
  config.py        environment configuration
migrations/        explicit Alembic migration
```

## Local setup

Prerequisites: Docker Compose and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Python 3.12 is selected by `.python-version`; uv can install it. No application container is needed.

```sh
uv sync --locked
cp .env.example .env
docker compose up -d --wait
uv run alembic upgrade head
uv run uvicorn career_agent.api.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open `http://127.0.0.1:8000/docs`; health is `GET /api/v1/health` (process liveness).
The development database binds only `127.0.0.1:55432` and uses an external Docker named volume.
The Compose password is a **public local-development placeholder**, not a production secret.
The app has no authentication and must remain local; do not expose it publicly.
Access logging is disabled in the documented command to avoid logging user-supplied URLs.

Stop PostgreSQL with `docker compose stop`; `docker compose down` retains the named volume.
Do not use `down -v` unless intentionally deleting the local database.

## API contract

All endpoints are under `/api/v1`. Interactive request/response schemas are in OpenAPI.

| Endpoints | Semantics |
| --- | --- |
| `GET /health` | Liveness, current milestone |
| `GET/PUT /profile` | Latest profile; append revision (`expected_revision=0` initially) |
| `GET/POST /facts` | List history; create **proposed** fact |
| `POST /facts/{id}/verify` | Explicit user confirmation, not external certification |
| `POST /facts/{id}/supersede` | Supersede verified fact; replacement starts proposed |
| `POST /facts/{id}/reject` | Explicitly reject proposed/verified fact |
| `POST/GET /jobs`, `GET /jobs/{id}` | Manual JD, requirements and linked tracking application |
| `POST /jobs/{id}/revisions` | New JD revision, old content retained |
| `GET/PATCH /applications/{id}` | Current state and history; explicit user update |
| `POST /applications/{id}/notes` | Append communication event |
| `POST /interviews`, `POST /interviews/{id}/notes` | Round creation and manual notes |
| `GET/POST /knowledge-notes` | Learning notes, never automatically verified facts |
| `GET /runs/{id}`, `GET /runs/{id}/steps` | Existing metadata only; no execution |

Updates to profile/JD/application and fact replacement carry `expected_revision`.
Application notes also increment the revision. Stale writes return `409 revision_conflict`.
Lists support `limit` (1–100) and `offset`; fact listing includes historical revisions.
Initial job creation atomically creates a tracking application and its first event.
Company names alone are not identity keys; ingestion does not automatically merge companies.

Errors use `{"error":{"code":"..."}}`: 422 invalid request, 404 missing object,
409 conflicting revision/transition/integrity, 500 internal error. Payload values, private paths
and provider error bodies are never reflected in error responses.

Example initial profile and fact bodies (synthetic):

```json
{"expected_revision":0,"data":{"display_name":"Synthetic Candidate","skills":["Python"]}}
```

```json
{"statement":"Built a synthetic inventory API","category":"project"}
```

## Data and privacy

`CAREER_AGENT_DATA_DIR` defaults to `~/.local/share/career-agent`, outside this repository.
It is a configuration boundary only: no artifact writer/renderer is implemented yet.
Use it for private sources and future artifacts. `.private/`, `.env*` (except `.env.example`),
artifacts, backups, dumps and volume directories are ignored. Gitignore is not encryption.
The database and its backups are private data too.

`tests/fixtures/` contains only synthetic data. CI never reads the private data directory.
Runtime JSON is validated; metadata identifiers cannot contain paths, emails or free-text errors.
No runtime prompt, response, JD, resume or hidden reasoning fields exist.
Logs accept enumerated events/codes, UUIDs and numeric latency only. The basic redactor is
not a complete DLP system. Do not enable SQL echo, debug traceback responses, body logging or
external tracing with real data. Direct SQL/database administration remains a trusted boundary.

## Tests and quality checks

```sh
docker compose up -d --wait
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
git diff --check
```

Full tests require PostgreSQL; they fail rather than substitute SQLite or silently skip integration.
The suite creates `career_test_<random UUID>` using a role with `CREATEDB`, migrates from empty,
and drops **only that temporary database** afterward. The development database is untouched.
Override `CAREER_AGENT_TEST_DATABASE_URL` in the shell when using another test server;
its default is the Compose server's `postgres` administrative database. Tests do not load this
variable from `.env`. Use a dedicated test server, never a production server.

For unit tests only: `uv run pytest tests/unit -q` (no PostgreSQL connection required).
GitHub Actions runs the same suite with an isolated PostgreSQL service and synthetic credentials.
The CI workflow is supplied; a remote CI run is not implied by local verification.

## Roadmap

- v0.1a: Foundation (current implementation).
- v0.1b: Resume Compiler, Typst and PDF validation (planned).
- v0.1c: Job Preparation Workflow (planned).
- v0.1d: Integration / E2E (planned).
- v0.2: Agent Runtime; v0.3: Harness / Evaluation / Safety (planned).
- v0.4: Production Engineering; v0.5: Real Usage Loop (planned).

See [TODO](TODO.md) for the full roadmap and optional extensions, and [CHANGELOG](CHANGELOG.md)
for implemented changes. The package version `0.1.0a1` is a development identifier; no final
v0.1.0 release has been made.
