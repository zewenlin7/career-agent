# Development, configuration and verification

This guide holds the operational detail formerly embedded in the root README. Commands below are
instructions, not evidence that they ran during the documentation update. Historical test counts,
paid smoke results and stage-specific CI reports belong in [CHANGELOG](../CHANGELOG.md).

## Prerequisites and configuration

- Python 3.12 is selected by [`.python-version`](../.python-version); the package supports >=3.12.
  Use uv and the committed `uv.lock` for the backend environment.
- Node >=22.13 and npm; frontend dependencies use `frontend/package-lock.json`.
- Docker Compose for the supplied PostgreSQL 17.6 service, or a separately configured PostgreSQL
  instance. Integration tests require PostgreSQL, not SQLite, and a test role with CREATEDB.
- Typst **0.15.1**, installed by the operator; Noto Sans CJK SC **2.004** static Regular/Bold fonts.
- Browser tests need the Playwright Chromium version associated with the installed frontend dependencies.

Start from [root `.env.example`](../.env.example) and [frontend `.env.example`](../frontend/.env.example).
Do not copy backend secrets to frontend public variables. Examples contain local placeholders,
not a production deployment or authentication configuration.

| Setting | Purpose / boundary |
| --- | --- |
| `CAREER_AGENT_DATABASE_URL` | Application PostgreSQL database; confirm the target before migration or any CLI that writes metadata |
| `CAREER_AGENT_DATA_DIR` | Private sources/artifacts; defaults outside the repository |
| `CAREER_AGENT_TYPST_BIN`, `CAREER_AGENT_FONT_DIR` | Trusted compiler and pinned font cache; never supplied by Resume API input |
| `CAREER_AGENT_LIVE_ENABLED`, `OPENAI_API_KEY`, `TAVILY_API_KEY` | Explicit live execution gate and server-only provider credentials |
| `CAREER_AGENT_MODEL_TIMEOUT_SECONDS`, `CAREER_AGENT_MODEL_TASK_TIMEOUT_SECONDS` | Global/per-task HTTP phase limits; independent of workflow budgets |
| `CAREER_AGENT_MODEL_RETRY_LIMIT`, `CAREER_AGENT_SCHEMA_REPAIR_LIMIT` | Existing bounded application retry policy; no hidden SDK retries |
| `CAREER_AGENT_MAX_RUN_COST` | Estimated-plus-reserved budget, not a provider invoice guarantee |
| `CAREER_AGENT_COMPANY_RESEARCH_TTL_HOURS`, `CAREER_AGENT_REUSE_CLAIM_WAIT_SECONDS` | Research freshness and bounded transaction-claim wait |
| `CAREER_AGENT_RUNTIME_CONTROL`, `CAREER_AGENT_TASK_MODEL_POLICIES` | Trusted routing/capacity policy, not discovered account entitlements |
| `CAREER_AGENT_AUTOMATIC_CONTROL` | Bounded process-local controls; not a durable scheduler |
| `CAREER_AGENT_INTERVIEW_POLICY` | Interview concurrency, per-call and cumulative safety ceilings |
| `CAREER_AGENT_OPS_TOKEN`, `CAREER_AGENT_OPS_ENABLED` | Private Ops access/bootstrap; not Product login |
| `CAREER_AGENT_API_ORIGIN` | Next server's backend origin, configured only in the frontend server environment |
| `CAREER_AGENT_TEST_DATABASE_URL` | Test server override in the shell; pytest does not load it from `.env` |

Model names, configured prices and defaults are operator settings in [config.py](../src/career_agent/config.py),
not domain logic or current market-price claims. Review capabilities and pricing together when changing
models. See [timeout and accounting contracts](architecture.md#model-request-timeout-policy-implemented)
and [runtime controls](architecture.md#v04-phase-1--runtime-control-core).

## Local setup and separate service commands

Review `.env` before running a migration. The following sequence creates an environment and starts
services; it is not a read-only diagnostic command. On an existing installation, do not overwrite
local configuration or start competing services.

```sh
uv sync --locked
npm ci --prefix frontend
cp .env.example .env
cp frontend/.env.example frontend/.env.local
# Edit server configuration and confirm the intended database.
uv run python scripts/setup_resume_fonts.py
docker compose up -d --wait
uv run alembic upgrade head
uv run uvicorn career_agent.api.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal:

```sh
cd frontend
# Set CAREER_AGENT_API_ORIGIN=http://127.0.0.1:8000 in .env.local.
npm run dev
```

Product is on port 3000; API docs are at `http://127.0.0.1:8000/docs`.
`GET /api/v1/health` is a process-liveness check, not a reliable project-stage or migration inventory.
The Compose database binds to `127.0.0.1:55432` and keeps data in a named volume. `docker compose stop`
stops it; normal `down` retains the volume. Do not use `down -v` as routine shutdown or cleanup.
Access logs are disabled above to avoid recording user-supplied URLs.

### Local Web development shortcut

After dependency installation and configuration:

```sh
./cgstart --check
./cgstart
```

The check path validates installed dependencies/fonts with no service startup or migration. The normal
path runs the existing [launcher](../scripts/start_dev.py): starts PostgreSQL, waits for readiness,
applies migrations to the configured database, installs missing pinned fonts, then starts FastAPI
and Next dev. It does not install Typst or npm/Python dependencies. A missing-font download uses the
network; corrupt fonts fail closed. `start-dev.sh` is the underlying supported entrypoint.
Ctrl+C stops the application's child processes while retaining PostgreSQL data. An existing or ephemeral
Ops token is passed only to server processes, not printed. This is a private local convenience, not
login/authentication or a production supervisor.

## Typst and fonts

Install the exact Typst 0.15.1 platform binary, then verify it. A generic package-manager install may
supply a different version. The application never upgrades the system compiler.

```sh
typst --version
uv run python scripts/setup_resume_fonts.py
uv run python scripts/setup_resume_fonts.py --check
```

The setup command downloads immutable official font files and the SIL OFL 1.1 license, checks SHA-256,
and publishes into the configured external font cache. `--check` verifies hashes and real CLI preflight
offline. Default cache: `~/.cache/career-agent/fonts/noto-sans-cjk-sc-2.004`; this is not system-font
installation. No fallback font is used. Exact hashes, upstream revision and URLs are maintained in
[the font manifest](../src/career_agent/resume/fonts.py). See [render dependencies and layout](profile-workspace.md#compiler-dependencies-and-layout)
for template parameters and retained render provenance.

The compiler rejects missing/wrong versions or corrupt fonts with safe errors. API clients cannot
supply font paths; each render uses a snapshot of verified font bytes, ignoring system/embedded fonts.
No font or PDF binaries belong in the source distribution.

### Synthetic rendering examples

With dependencies/fonts prepared:

```sh
uv run python scripts/render_synthetic_resumes.py
```

The script accepts `--output-dir` for an operator-selected output directory; otherwise it uses
`$CAREER_AGENT_DATA_DIR/synthetic-examples`. It writes PDFs/validation reports from repository fixtures,
without a database or model call. Normal and mixed-script fixtures exercise accepted output; overflow
fixtures exercise explicit failure. It does not automatically substitute short text or delete optional
content. The old v0.1b three-attempt automatic-compression observation is historical, not current behavior.
Automatic checks do not establish perfect visual quality.

## Database migrations

Inspect the code chain and an authorized database separately:

```sh
uv run alembic heads
uv run alembic history
# The following commands access the configured database.
uv run alembic current
# Apply only to an explicitly authorized target after backup/review.
uv run alembic upgrade head
```

Use the files in [migrations/versions](../migrations/versions), not a copied README head value, as the
code-chain inventory. A code head does not establish the business DB's installed revision. Preserve
all intervening migrations; do not rewrite published revisions. Some downgrades deliberately reject
loss of retained receipts/history. Recent note/debrief and Job-request migrations add nullable legacy
fields/new tables without inventing historical note modification times or request identities.
The current authorization/verification status belongs in [TODO](../TODO.md#current-stage-and-pre-commit-work).

## Verification

From the root, after preparing the test server and compiler/font dependencies:

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
git diff --check
```

Pytest blocks external provider sockets. It creates/migrates `career_test_<random UUID>` on the test
server and drops only that temporary database; it must not use business data. A test role needs CREATEDB.
Compiler tests use real Typst and fail on missing/wrong dependencies rather than substituting SQLite
or skipping integration. `uv run pytest tests/unit -q` is the smaller unit entrypoint. Concurrent runs
need distinct `--basetemp` paths. These are execution commands, not passive inspection.

Frontend, from `frontend/`:

```sh
npm run check
npm run build
npm run test:browser
npm run test:profile-browser
```

`check` includes ESLint, Next type generation/strict tsc, Node unit tests and Prettier. Install the
matching Chromium beforehand with `npx playwright install chromium` when installation is authorized.
Fixture browsers use ports 3100/3111. Real backend browsers use 3130/3131, random PostgreSQL, real
FastAPI/Typst and offline adapters. See the [frontend guide](../frontend/README.md#run-and-verify).
Use an isolated build directory/copy when dev is running; never build concurrently into its `.next`.
Production serving uses `npm run start` after build and needs the same server-only configuration.

Packaging uses `uv build`. Inspect wheel/sdist contents and test imports from unpacked artifacts;
exclude credentials, private data, local-only guidance and generated files. Review changed/untracked
files before staging. CI configuration is in [`.github/workflows`](../.github/workflows); the commands
here do not assert that a remote run has occurred or passed.

### Explicit smoke and live boundaries

```sh
uv run python scripts/smoke_preparation.py
```

The default is fixture mode. This command creates a random `career_smoke_*` DB on the configured
server, writes private reports/PDFs, and drops its fixture DB afterward. It is not a read-only check.
The live variant adds `--live`, requires both provider keys plus `CAREER_AGENT_LIVE_ENABLED=true`,
and retains its random DB (including failures) for diagnosis. It requires separate explicit paid
scope/budget authorization; it is not part of Quick Start or ordinary documentation validation.
Current smoke uses synthetic personal/JD input, does not dispatch Tavily search, and has independent
application/interview estimate caps of USD 0.60/0.20. It stops on failure/partial, with transport/schema
retries disabled. Reports stay in private data storage; do not publish source bodies or local diagnostics.
Historical acceptance/budget accounting is in CHANGELOG, not a standing allowance for another call.

### Evaluation CLI

```sh
uv run python -m career_agent.evaluation run tests/fixtures/evaluation/foundation.json
uv run python -m career_agent.evaluation inspect runs RUN_UUID
uv run python -m career_agent.evaluation compare BASELINE_UUID CANDIDATE_UUID
uv run python -m career_agent.evaluation drain-judge --limit 20 --concurrency 2
uv run python -m career_agent.evaluation calibration
```

The CLI defaults to offline fixture adapters, including Judge. **Offline does not mean read-only:**
`run`, `compare` and `drain-judge` write Eval metadata in the configured database. Use an isolated
configuration for validation. Workflow/Agent replay creates disposable domain DBs/private artifacts;
that does not make the parent Eval store disposable. `inspect`/`calibration` read existing data.
Origin re-execution requires `--mode origin_reexecution --explicit-diagnostic`; missing original
execution contracts fail closed. `--trials 3` retains separate results. Paid Eval requires explicit
trusted gateway injection and authorization; enabling application live mode alone does not enable it.
See [Eval boundaries](architecture.md#v03-evaluation-boundaries) and
[Mock decision-quality contrasts](model-reliability.md#mock-decision-quality-contrasts).

## Private data handling

`CAREER_AGENT_DATA_DIR` defaults to `~/.local/share/career-agent`; accepted PDFs use opaque UUID names
under `artifacts/`. Database backups, private Eval inputs/outputs/captures and artifacts remain private.
Ignored files are not encrypted. Ordinary runtime/Ops logging is metadata-only, while dedicated private
invocation/capture and accepted-output stores may contain bodies for validation/recovery. Do not enable
SQL echo, body logging, raw traceback responses or external tracing with real data. Direct SQL and
configuration are trusted operator boundaries, not Product authorization mechanisms.
