# Career Agent

[简体中文](README.zh-CN.md)

## Purpose and current stage

Career Agent is a single-user, privately deployed workspace for managing a job search and building
source-grounded application materials. It combines a Web product with explicit, bounded model workflows;
it does not apply for jobs or send messages on your behalf.

The current stage is **v0.5 Application/Interview closeout**. Profile Workspace has passed user manual
acceptance. Application/Interview overall confirmation and Internal final manual acceptance remain
pending. Users have exercised both Mock next-question/follow-up choices and successful Debrief retry/new
analysis with real calls; these are limited functional observations, not broad model-quality evidence.
See [current work and acceptance boundaries](TODO.md) and [historical changes](CHANGELOG.md).

## Features and use flow

**Personal profile → Resume → Application → Research / Fit → Submission record → Interview → Debrief**

This is a navigation guide, not a mandatory dependency chain. Research, Fit, optimization and Mock are
optional; each generation action checks its own required inputs. Generating material is separate from
recording an actual submission.

- **Profile and Resume:** named profiles, shared editing sessions, manual/AI Resume creation,
  source validation, saved versions, explicit short expressions and Chinese PDF rendering.
- **Applications:** raw JD entry and revision, six tracking states, notes, exact Resume bindings,
  company research and requirement-level matching with explanations.
- **Apply:** Resume optimization, greeting generation and actual submission records with frozen
  Resume/PDF/greeting references; history and reference-protected removal remain available.
- **Interview:** preparation from visible Resume material, resumable text Mock sessions, atomic
  actual-interview recording/editing, and read-only history. Mock can skip, delay or chain follow-ups
  within server-enforced quotas.
- **Review:** selected question-group analysis and/or full-interview Debrief, exact evidence links,
  frozen Q&A, failed-target retry, independent history and editable job-search notes.
- **Internal:** Operations and Evaluation pages for safe metadata, bounded controls, recovery
  inspection, offline replay, comparisons and explicitly requested quality work.

## Engineering and architecture

- **Grounded structured output:** schemas and source/reference checks reject invalid output before
  formal adoption. References help trace claims; they do not prove semantic truth.
- **Reliable intent and history:** request receipts prevent duplicate work on retransmission;
  revisions/CAS and immutable snapshots keep edits and historical inputs separate.
- **Bounded execution and recovery:** the shared Gateway records attempts, budgets and outcomes.
  Durable accepted output can be recovered where supported; unknown outcomes are not blindly replayed.
- **Evaluation:** frozen inputs, offline providers and production validators separate execution
  correctness from quality evidence. Judge output is not human ground truth.

```text
Next.js Product / Internal → allowlisted server BFFs → FastAPI business services
    → model Gateway / policies / budgets / execution journal
    → PostgreSQL + private artifacts → results / history / PDF / Eval
```

Python >=3.12 (the repository selects 3.12), FastAPI, Pydantic, async SQLAlchemy/Alembic and PostgreSQL;
Next.js, React, strict TypeScript and Tailwind CSS v4. PDF uses pinned Typst and CJK fonts.
Dependencies are defined by `pyproject.toml`, `uv.lock`, `frontend/package.json` and its lockfile.
Detailed boundaries live in [architecture](docs/architecture.md), not in a separate frontend model client.

## Quick start

Prerequisites: uv, Python 3.12, Node >=22.13/npm, Docker Compose (the supplied service uses PostgreSQL
17.6), and **Typst 0.15.1**. Install the compiler yourself; the application does not install/upgrade it.
Use a local/private environment. Configure the target database before migration; do not point this
sequence at an existing business database without authorization and a migration plan.

```sh
uv sync --locked
npm ci --prefix frontend
cp .env.example .env
cp frontend/.env.example frontend/.env.local
# Review database, private storage, compiler and server-only configuration before continuing.
uv run python scripts/setup_resume_fonts.py
./cgstart --check
./cgstart
```

The font setup downloads and verifies Noto Sans CJK SC 2.004 Regular/Bold and its license into an
external cache. `cgstart --check` is an offline dependency preflight. **`cgstart` is not read-only:**
it starts PostgreSQL, applies Alembic migrations to the configured database, installs missing pinned
fonts if needed, and starts FastAPI/Next dev servers. It never downloads Typst. Avoid running it over
an already running development session. Ctrl+C stops its application processes and retains PostgreSQL data.

Product: `http://127.0.0.1:3000`; API docs: `http://127.0.0.1:8000/docs`.
Keep backend credentials only in the root server environment; frontend `.env.local` uses
`CAREER_AGENT_API_ORIGIN` and, for Internal only, a server-side Ops token. The BFF is not login/authentication.

`CAREER_AGENT_LIVE_ENABLED=false` in the example configuration. Product generation requests use live
mode and require explicit provider configuration/authorization; disabled live mode does not turn the
UI into a fixture demo. Reads and ordinary PDF rendering do not start paid calls. See
[development setup, separate service commands and configuration](docs/development.md).

## Tests and quality checks

Common entry points, from the repository root:

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
npm --prefix frontend run check
npm --prefix frontend run build
git diff --check
```

Full backend tests require real PostgreSQL, Typst and pinned fonts. The harness creates random test
databases and uses synthetic inputs/offline providers; it does not reset the business database.
Browser suites require Chromium and a production frontend build. Never run dev/build against the same
`.next` directory concurrently. See [isolated tests, browser suites and packaging](docs/development.md#verification)
for environment details. These commands are instructions, not a claim that checks ran during a documentation edit.

## Limits and safety boundaries

- Single-user local/private deployment; no multi-user login, public SaaS authorization or billing system.
  BFF allowlists and the Ops token do not secure an otherwise publicly exposed backend.
- No automatic application/message sending, unrestricted planning, vector retrieval, voice interview,
  or multi-turn discussion of a Debrief. See [future scope](TODO.md#next-function-stage-and-polish).
- Private sources, database backups, generated artifacts and Eval captures stay outside published
  material. Ordinary logs/Ops contain safe metadata; basic redaction is not comprehensive DLP.
- No distributed exactly-once execution, generic durable worker, provider outcome lookup or global
  database/filesystem atomicity. Recovery depends on the task and evidence actually persisted.
- Soft deletion retains shared sources and audit history; it is not physical erasure. Migration and
  data cleanup require separate decisions. Code migration files do not establish a business DB's version.
- Grounding, synthetic regression and a few real functional observations do not establish hiring
  outcomes, broad model quality, actual billed costs or production load capacity.

## Documentation

| Need | Read |
| --- | --- |
| Setup, configuration, fonts, migrations, tests, Eval CLI | [Development guide](docs/development.md) |
| API use, payload examples and historical compatibility | [Backend API guide](docs/backend-api.md) and local OpenAPI |
| Layering, execution, budgets, recovery and version governance | [Architecture](docs/architecture.md) |
| Profile/Resume editing, rendering and lifecycle | [Profile workspace](docs/profile-workspace.md) |
| Web routes, interaction, BFF, typography and Internal contracts | [Frontend README](frontend/README.md) |
| Task diagnostics, recovery evidence and quality boundaries | [Model reliability](docs/model-reliability.md) |
| Current acceptance, deferred work and historical changes | [TODO](TODO.md), [CHANGELOG](CHANGELOG.md) |
