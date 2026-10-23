# Career Agent

Career Agent is a primarily single-user personal job-search Agent engineering project.
The current work is **Web product backend contract closure**, built on v0.1–v0.4.
Development and demonstrations use synthetic data; this is not a multi-user production service.

## Implemented now

- Versioned personal profile, user-confirmed facts and replacement history.
- Manual JD ingestion, explicit requirements, immutable JD revisions, company records.
- Application tracker with optimistic revision checks, status/correction/note events.
- Actual interview rounds with CAS-protected ordered primary/follow-up Q&A and legacy notes.
- Separate text Mock Interview sessions and snapshot-based standalone Interview Debrief.
- Knowledge-note creation/global discovery and Application-scoped discovery; generated knowledge candidates never auto-promote to facts.
- PostgreSQL persistence for source documents, STAR structures and runtime metadata.
- Run/step/call metadata APIs and two explicitly invoked fixed preparation workflows.
- Model-independent contracts, approved per-task candidate policies and an injected fake provider.
- Safe error responses, allowlisted operational logging and private-data configuration.
- Synthetic tests using a real temporary PostgreSQL database, Ruff and strict mypy.
- Hand-authored, versioned ResumeVariants, fact grounding, deterministic content compression,
  trusted zh-CN Typst rendering, one-page PDF validation and exact-revision artifact APIs.
  Chinese resumes with English technical terms are the current canonical product.

OpenAI Responses and Tavily adapters, deterministic target orchestration, versioned prompts,
structured zh-CN tailoring and static budget controls are implemented and tested offline.
**Live extraction/research/fit/tailoring/PDF/greeting have been exercised; Interview Prep passed after a timeout-policy fix, and controlled compression produced an accepted PDF. v0.1c live acceptance is historical; v0.1d acceptance is offline only. Synthetic acceptance does not establish real job-search quality.**
No automatic applications/messages, unrestricted planner, durable worker,
vector search or frontend are implemented. Interview preparation is an explicit separate request.

## Architecture

`FastAPI → application services → domain rules / async SQLAlchemy → PostgreSQL`

Model calls have a separate `ModelRequestContext → policy → candidate → adapter → ModelResult`
contract. They do not read an Agent State. Domain services contain no provider/model names.
Operational run/step/call records contain metadata. Private goal records and versioned control checkpoints
are separate from business artifacts. The original preparation API remains independently usable.
See [architecture](docs/architecture.md) for boundaries and planned evolution.

```text
src/career_agent/
  api/             typed API inputs/outputs and safe errors
  domain/          lifecycle rules and structured data schemas
  application/     transactional use cases and revision checks
  infrastructure/  async persistence and mapped entities
  models/          contracts, static policy/gateway, fake and OpenAI adapters
  preparation/     task schemas/prompts, research, guardrails, budgets and fixed workflows
  interview/       current-state intake, frozen mock sessions, concurrent snapshot debrief
  runtime/         usage, budget and nullable version metadata
  security/        redaction and allowlisted logging
  resume/          structured variants, grounding, content policy, Typst and PDF checks
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
Accepted PDFs are stored under its `artifacts/` directory using opaque UUID filenames.
Use it for private sources and artifacts. `.private/`, `.env*` (except `.env.example`),
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
uv run python scripts/setup_resume_fonts.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
git diff --check
```

Full tests require PostgreSQL, Typst 0.15.1 and the pinned CJK font setup below; they fail rather than substitute SQLite or silently skip integration.
The suite creates `career_test_<random UUID>` using a role with `CREATEDB`, migrates from empty,
and drops **only that temporary database** afterward. The development database is untouched.
Override `CAREER_AGENT_TEST_DATABASE_URL` in the shell when using another test server;
its default is the Compose server's `postgres` administrative database. Tests do not load this
variable from `.env`. Use a dedicated test server, never a production server.

For unit tests only: `uv run pytest tests/unit -q` (no PostgreSQL or Typst process required).
Compiler tests use real Typst; missing/wrong versions fail rather than silently skip. Pytest
temporary artifact directories are removed at session end.
GitHub Actions runs the same suite with an isolated PostgreSQL service and synthetic credentials.
v0.1a/v0.1b/v0.1c CI passed remotely (user confirmed). v0.1d is locally verified only: **235 offline tests passed**, including empty PostgreSQL migration/drift,
real Typst E2E, static checks and offline installation/build. No commit or push is performed here.

## Roadmap

- v0.1a: Foundation (implemented).
- v0.1b: Resume Compiler, Typst and PDF validation (implemented).
- v0.1c: Job Preparation Workflow (completed and locally verified).
- v0.1d: target-driven deterministic orchestration, context integrity, retrieval closure and offline E2E.
- v0.2a: bounded Runtime Core; v0.2b: deterministic intake, text Mock and standalone Debrief (offline).
- v0.3: Evaluation Harness / Regression / Sampled Quality Monitoring Foundation (current).
- v0.4: Production Engineering; v0.5: Real Usage Loop (planned).

See [TODO](TODO.md) for the full roadmap and optional extensions, and [CHANGELOG](CHANGELOG.md)
for implemented changes. The package version `0.1.0a2` is a development identifier; no final
v0.1.0 release has been made.


## Resume Compiler (v0.1b)

Input is an **already structured, hand-authored ResumeVariant**. The compiler does not choose
job-relevant claims, rewrite text with a model, or call a paid provider.

### Typst and fonts

The supported compiler is **Typst 0.15.1**. Check it before running compiler tests:

```sh
typst --version
typst fonts --ignore-system-fonts
```

On macOS, install it yourself using `brew install typst`, then verify the version. For an exact
version, use the platform binary from the [official 0.15.1 release](https://github.com/typst/typst/releases/tag/v0.15.1).
The application never installs/upgrades a system package. Set `CAREER_AGENT_TYPST_BIN` to an
operator-controlled executable path if needed; macOS Homebrew's standard path is also detected.
Wrong compiler version is a `template_error`; absent executable is `compiler_unavailable`.

The canonical locale is **zh-CN**: Chinese headings/body with natural English technical terms.
Fonts are **Noto Sans CJK SC 2.004, static Regular/Bold**, from the official
[Noto release](https://github.com/notofonts/noto-cjk/releases/tag/Sans2.004), pinned to commit
`523d033d6cb47f4a80c58a35753646f5c3608a78`, under its
[SIL OFL 1.1 license](https://github.com/notofonts/noto-cjk/blob/523d033d6cb47f4a80c58a35753646f5c3608a78/LICENSE).

```sh
uv run python scripts/setup_resume_fonts.py
uv run python scripts/setup_resume_fonts.py --check  # offline hashes + real CLI preflight
```

`CAREER_AGENT_FONT_DIR` defaults to `~/.cache/career-agent/fonts/noto-sans-cjk-sc-2.004`.
This is an external dependency cache, not a system font installation. Setup downloads from
immutable official URLs, verifies SHA-256 before publishing files, and retains the pinned license.
CI uses the same script and manifest. Hash mismatch/download failure aborts; there is no fallback.
Expected SHA-256 values (also enforced in `resume/fonts.py`):

| File | SHA-256 |
| --- | --- |
| NotoSansCJKsc-Regular.otf | `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b` |
| NotoSansCJKsc-Bold.otf | `b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a` |

Each render snapshots hash-verified bytes into its temporary font directory. Typst receives that
explicit `--font-path`, `--ignore-system-fonts`, and `--ignore-embedded-fonts`; template fallback
is disabled. Extra files in the operator cache are not loaded. Missing/corrupt fonts yield safe
`font_dependency_missing` / `font_hash_mismatch` failures. API input cannot supply font paths.
No font/PDF binaries are committed or packaged. English templates and bilingual/multi-locale
support are future extensions; **Chinese support is current scope**.

The template fixes A4, one column, 18 mm horizontal / 16 mm vertical margins, body 10.5 pt,
section headings 12 pt, name 20 pt, and fixed spacing. A fixed 5.25 pt right-side content gutter
keeps CJK punctuation advance boxes within those margins. Bullets use vector circles, avoiding
ambiguous bullet/middle-dot text mappings; continuation lines use a fixed hanging indent.
Compression never changes these values.

### Synthetic examples

After `uv sync --locked`, prepare fonts as above, then generate the four local examples without a database or model:

```sh
uv run python scripts/render_synthetic_resumes.py
# Or choose a temporary output directory:
uv run python scripts/render_synthetic_resumes.py --output-dir /tmp/career-agent-examples
```

Default output is `$CAREER_AGENT_DATA_DIR/synthetic-examples`. Accepted fixtures produce a PDF
and a JSON validation report; the impossible fixture produces **only a failure report**.
This script validates synthetic fact references before invoking the compiler.

| Fixture | Observed result with 0.15.1 |
| --- | --- |
| normal_one_page_zh_cn | Accepted, 1 page, 1 attempt |
| compressible_overflow_zh_cn | 5 pages → short form, 3 pages → optional item removal → accepted 1 page; 3 attempts |
| impossible_one_page_zh_cn | Required content occupies 4 pages; `layout_failed`, no accepted PDF |
| mixed_script_font_regression | Accepted, 1 page; Chinese/English/numbers/punctuation extracted |

The accepted PDFs have been visually inspected locally: no obvious clipping, overlap or missing
glyphs. This does not mean automatic checks can detect every aesthetic/visual defect.

### Variant / artifact API

- `POST /api/v1/resume-variants`: store a structured draft, not a model generation request.
- `GET /api/v1/resume-variants/{id}?revision=N`: retrieve an exact revision; defaults to latest.
- `POST /api/v1/resume-variants/{id}/revisions`: `{expected_revision, document}`; old revision immutable.
- `POST /api/v1/resume-variants/{id}/render`: `{revision: N}`; exact revision is mandatory.
- `GET /api/v1/artifacts/{id}`: status, findings, selection decisions, attempts and versions.
- `GET /api/v1/artifacts/{id}/download`: accepted artifacts only, verified SHA-256, `no-store`.

Use the synthetic fixture `document` as a payload shape, but replace its fixture IDs with actual
Profile/Fact IDs created via your local API. Add each fact ID to an education/experience/project
entry in the Profile before creating the Variant. Supply `profile_id` and `profile_revision`.
The optional `job_revision_id` identifies an exact stored JD revision. Sections are predefined
`summary/experience/projects/education/skills` with Chinese headings; factual items always need `fact_refs`.

Draft storage validates shape and source identity; grounding is rechecked at render time.
Proposed/rejected/superseded facts cannot support accepted output. Requirement references must
belong to the selected JD revision. Numbers in full and short text must occur in supporting
facts. Declared hard claims (organization/title/degree/date/number) are checked against their
fact and full text. Undeclared named entities and semantic exaggeration are **not comprehensively
validated**; references alone do not prove semantic truth. Human review remains necessary.

A render request returns HTTP 201 for a **persisted render result**, including failures. Check
`report.render_status`, not HTTP status alone. Failed results have no downloadable artifact.
`grounding_failed` includes findings such as `missing_verified_fact`, `snapshot_mismatch`,
`hard_field_mismatch`, or `invalid_requirement_reference`. Other stable errors include
`invalid_variant`, `template_error`, `compiler_unavailable`, `compile_timeout`, `compile_failed`,
`pdf_invalid`, `text_validation_failed`, `layout_overflow` (per-attempt finding), `layout_failed`,
and `artifact_write_failed`. Error responses never include Typst raw diagnostics/private paths.

The compiler tries the original content, then supplied short forms, then removes optional bullets
before optional entries using priority/order/UUID tie-breakers. Empty optional sections disappear.
At most **8 compilations**, with the final round testing required content only if necessary.
Every selection decision is recorded; no required item is deleted. Within the compiler, short forms are supplied data. The separate preparation workflow may
perform one explicit semantic compression call after eligible layout failure. Failure never becomes clipping or an unreadable font size.

The current contract is `locale=zh-CN`, schema `resume-v2`, template
`resume_zh_cn_a4_single_v1`, layout policy `content-v1`, and font policy
`noto-sans-cjk-sc-2.004-regular-bold-v1`. Reports retain these versions, actual font family,
verified font-file hashes, compiler version and template hash; never local absolute font paths.
Retained text uses ordered, non-overlapping ranges in immutable normalized extraction, so matching
cannot manufacture text by deleting headings. Accepted status requires validated PDF bytes and
computed SHA-256; subsequent storage failure clears success/file metadata and persists a failed report.
The PDF hash checks file integrity; byte-identical PDFs are not the regression criterion.
Matching selections, decisions, page count and validation results are the determinism contract.

## Job preparation workflows (v0.1d)

`POST /api/v1/workflows/prepare_application` accepts exact `profile_id` (an immutable Profile
revision row), `job_revision_id`, `targets`, `mode` (`fixture` default), `limits` and resume bindings.
Legal targets are any nonempty subset of `fit_analysis`, `resume_tailoring`, `greeting_generation`.
Omitting targets retains the three-target default, but never selects a resume automatically.
Fit is informational by default, not a prerequisite for Tailoring/Greeting. Execution order is
stable; only explicit dependencies block independent targets. Existing compatible results are
reused before spending any model budget. Requirements are reused for the exact JD or extracted
once if absent. Fresh same-company/mode research is optional free context; absent/expired research
is skipped without a search/synthesis call. `force_research_refresh=true` is rejected in this workflow
(`research_refresh_not_a_target`); the research adapter remains available internally, not a hidden target.

Both Tailoring and Greeting need a user-selected immutable `resume_revision_id` (returned by the
ResumeVariant API). A common selection can be supplied at the request top level; per-target
`bindings` override it. Tailoring appends a new revision with the chosen base recorded, never silently
edits that base. Greeting uses the chosen resume, not whichever revision happens to be latest.
Example: tailor a chosen revision, then explicitly use the result for Greeting:

```json
{
  "profile_id": "<exact-profile-revision-uuid>",
  "job_revision_id": "<exact-jd-revision-uuid>",
  "targets": ["resume_tailoring", "greeting_generation"],
  "bindings": {
    "resume_tailoring": {"resume_revision_id": "<chosen-resume-revision-uuid>"},
    "greeting_generation": {"output_of": "resume_tailoring"}
  }
}
```

Missing selection returns `needs_input / resume_selection_required` before model calls.
`GET /api/v1/resume-revisions?profile_id=...&job_revision_id=...` lists paginated choices with
first-revision (`original`), same-JD, same-Job and last-used hints; these never make a selection.
Only `layout_failed` permits one semantic compression call and recompile. Typst attempts are not
model retries. Profile/fact snapshots, requirement ownership, exact variants and PDF hashes are
revalidated at consumption; a missing/corrupt previously accepted PDF causes an explicit failure.

Opt-in `fit_gate: "gate_downstream"` uses `fit_gate_policy_v1` and may generate/reuse an intermediate
Fit even if Fit is not a requested output. Among must-have requirements: at least two explicit gaps
or at least 50% explicit gaps requires a `low_fit` decision; otherwise at least 50% `no_evidence`
requires an `insufficient_evidence` decision. No must-haves passes. Matched/partial receive no scores.
`no_evidence` does not mean inability. The run ends normally with `decision_required` and no later
target calls. A new explicit informational request can reuse existing artifacts; there is no paused process.

`POST /api/v1/workflows/prepare_interview` remains separate and explicit. Supply the same exact
profile/JD and an `application_package_id` containing an accepted exact resume. Optional selected
STAR stories/knowledge notes are bounded context. It never runs implicitly or refreshes research.

HTTP 201 means a run/package resource was created. The single `outcome` is identical in API,
AgentRun and package: `completed`, `partial`, `failed`, `needs_input`, or `decision_required`.
Each **requested** target has `completed/failed/blocked/pending`, an artifact ref or reason.
Only completed requested targets count toward `partial`; successful prerequisites do not.
Node records distinguish `executed/reused/skipped/failed/blocked`. Dependencies remain available in
state refs but are not added to `outcome.targets`. No material generation changes Application status.

Retrieval (all under `/api/v1`):

- `GET /preparation-artifacts/{id}`: package, target provenance or task output. A target record links
  its task result, exact resume revision and render artifact, so every requested output is retrievable.
- `GET /preparation-artifacts/{package_id}/context`: original Profile/JD, requirements and exact
  input/output resumes, even after Profile/JD updates. This is historical retrieval, not re-verification.
- `GET /jobs/{id}/preparation-packages` and `/applications/{id}/preparation-packages`: paginated
  packages across that Job's revisions (Application uses the existing Job relationship).
- `GET /runs/{id}/package`, `/runs/{id}`, `/runs/{id}/calls`: final package, outcome, safe call metadata.
- Existing `GET /company-research/{id}`, resume revision and PDF metadata/download endpoints remain.

These local private-data APIs have no authentication; bind them to loopback.

### Offline versus live

All pytest runs block external sockets, while permitting temporary localhost PostgreSQL.
Fixture model/research adapters are the default. CI installs dependencies/fonts, then tests without
provider keys or paid network calls. Mock HTTP exercises native SDK structured outputs.

```sh
# Isolated synthetic DB, cleaned afterward; retains private smoke PDFs/report.
uv run python scripts/smoke_preparation.py
```

For live smoke, manually fill `OPENAI_API_KEY` and `TAVILY_API_KEY` in ignored `.env` and set
`CAREER_AGENT_LIVE_ENABLED=true`. Never paste keys into chat or enable SDK debug/body logging.
Then explicitly run:

```sh
uv run python scripts/smoke_preparation.py --live
```

This uses only repository synthetic personal facts and a clearly synthetic JD with public OpenAI
company context. The current target smoke does not search Tavily; the adapter was verified in v0.1c. It creates an isolated random `career_smoke_*` PostgreSQL database, never
modifying the configured application DB. Fixture mode drops its database; live mode now retains
it (including failed runs) and records its generated name as `database_ref` for targeted follow-up.
The role needs CREATEDB. It stops on partial/failed outputs and does not automatically retry paid
calls. Independent caps: application USD 0.60 and interview USD 0.20 (estimates, not billing guarantees).
Application compression runs only via the existing eligible-layout-failure workflow branch;
there is no extra direct-model compression probe in this general smoke command.
Reports/PDFs stay under `CAREER_AGENT_DATA_DIR/preparation-smoke/<id>/`; terminal output contains
only safe status and a relative report reference. The report captures model/search usage and latency.
**Live acceptance is complete; rerunning this command incurs new costs and does not reset the recorded cumulative budget below.**

Default routing is extraction → cheap (`gpt-6-luna`), other tasks → strong (`gpt-6.1-sol`).
Premium configuration is reserved and never added to the active registry. Model names and prices
are operator configuration, not domain logic. All thirteen LLM tasks use the shared code-managed `models/prompts.py` contract/registry;
feature definitions remain in preparation, runtime, interview and evaluation prompt modules. Planning and
replanning share one prompt identity. Canonical SHA-256 covers name/version, instructions,
input contract/schema version and output schema/version, never request data. Gateway rejects
unregistered tasks or mismatched request/task metadata before provider dispatch. Every ModelCall
records prompt name/version/hash, schema versions, model policy/provider/model and workflow version.
Preparation specs use `_v6`, planning `goal-planner-v4`, interview `_v4`, and Judge `quality-judge-v2`. Composition ordering is versioned and included in the prompt hash; output schemas remain unchanged.
Changed hashes conservatively invalidate reuse fingerprints; existing artifacts remain readable.

Default run limits: 12 model attempts, 2 basic search calls, 200,000 reserved/consumed input tokens,
40,000 output tokens, USD 1 estimated total, one semantic compression. Every retry/repair consumes
a model slot and reservation. Unknown usage retains a separate budget reservation, never fabricated token usage or cost.
Company cache TTL is 168 hours, keyed by company identity and fixture/live mode. Same-name company
records are not automatically merged; sharing requires the same Company ID. POST /jobs accepts
an optional existing `company_id` with its matching `company_name` for explicit reuse. A search stops after
one response if at least 60 snippet characters are available; this is a bounded heuristic, not a
truth/completeness test. Conclusions/inference require evidence refs. No arbitrary URL fetch tools.

Input context excludes profile contact/preferences and minimizes common name/email/phone forms.
External JD/web/company content is quoted untrusted data; it cannot select tools, models or paths.
Output checks enforce schema, refs, supported numbers, explicit hard fields and compiler grounding.
They **do not prove semantic truth or eliminate all prompt injection/exaggeration**. Review all
real materials manually. USD prices are configurable estimates; changing model names requires
reviewing their pricing/capabilities. References: [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing),
[Tavily search contract](https://docs.tavily.com/documentation/api-reference/endpoint/search).


Live acceptance (2026-10-12) passed each requested task across bounded, explicitly authorized
attempts. Later cases reused canonical synthetic upstream data after the original failed tailoring
run's database was lost. The unknown original failure cause is not inferred. The Interview Prep
120-second timeout case passed, and controlled compression preserved refs/hard fields and produced
an accepted one-page Chinese PDF. This tests controlled deduplication, not general semantic quality.

Cumulative conservative accounting: **USD 0.3350816**, remaining **USD 0.6649184** from the original
USD 1 cap. Unknown failed-call usage remains reserved. One-off recovery scripts tied to local
run IDs and historical budgets were retired; source archives and acceptance artifacts stay outside
the repository. See CHANGELOG for call metrics. No additional live calls were made during final
review. v0.1d offline E2E verifies integration contracts, not real-data or production quality.

Model HTTP timeout policy is configured independently of token/cost budgets: default
`CAREER_AGENT_MODEL_TIMEOUT_SECONDS=60`, with
`CAREER_AGENT_MODEL_TASK_TIMEOUT_SECONDS='{"interview_preparation":120}'` for per-task overrides.
Values must be finite, positive and at most 300 seconds. The adapter passes the selected value
per request to the SDK; these are HTTP phase limits, not a total workflow deadline. SDK retries
remain disabled; live smoke also disables application retries and schema repair.
Safe diagnostics record timeout policy/version/seconds and the transport phase when available,
never exception text or request bodies. A timeout still returns `provider_timeout`; unknown
provider usage retains its conservative budget reservation.


### Usage, cost estimates and budget reservations

- `input_tokens` / `output_tokens` / `cached_tokens` / `cache_write_tokens` / `reasoning_tokens` are provider-reported
  usage. `measurement=reported` describes usage, not a paid invoice. Unknown per-call usage is null.
- Existing `estimated_cost` (with `currency=USD`) is the USD estimate, equivalent to
  `estimated_cost_usd`: reported OpenAI usage × the versioned configured price table.
- `cache_write_tokens` is nullable per-call telemetry. No separate write charge is inferred:
  the estimate still partitions total input into cached reads and other input, plus output.
  Independent cache-write billing is not claimed; no pricing snapshot or billing API is added.
- `budget_reserved_usd` and `reserved_input_tokens` / `reserved_output_tokens` are conservative
  bounds for unsettled/unknown attempts. They are separate from usage and estimated cost.
- `actual_billed_cost_usd=null` and `billing_tier=unknown`: no billing/account integration, Admin
  Costs API or admin key. Run token totals sum known usage; unknown-attempt bounds remain separate.
- Tavily `search_calls` counts locally observed dispatch attempts; `credits_used=null` because
  the current adapter has no reliable consumed-credit/account source. A successful basic search's
  configured USD 0.008 is **PAYG-equivalent retail estimated cost**, not actual cash paid.
  Failed searches retain a reservation. Free allowance coverage is unknown, never assumed free.
- Budget admission uses **estimated_cost + budget_reserved_usd**; `max_estimated_cost` remains
  the existing public limit name for this conservative sum. Timeout/invalid output with reported
  usage still settles normally; only unavailable usage/cost stays reserved.

Historical smoke budget consumption USD 0.3350816 comprises USD 0.1576516 price-derived estimates
(including USD 0.008 Tavily retail equivalent) + USD 0.1774300 unknown-call reservations.
Actual billed cost remains unknown. Earlier private smoke summaries used the old combined fields;
this change does not rewrite those historical records or turn their reservations into expenses.


## Bounded Agent Runtime (v0.2a)

`Goal → Planner → deterministic PlanValidator → business action → Observation → deterministic Evaluator`

The planner proposes typed targets, exact bindings and dependency edges. It cannot authorize new
refs, change scope/budgets, bypass Fit Gate, verify facts or execute arbitrary code. Registered actions
are only `prepare_application` and `prepare_interview`; they delegate to the existing v0.1d
orchestrator. Its explicit resume selection, reuse, grounding, compiler and target outcomes remain intact.
The fixture planner is a small deterministic router for offline testing, not a quality claim about
natural-language understanding. Live mode uses the existing gateway; no v0.2a paid acceptance was run.

- `POST /api/v1/agent-runs`: `goal`, exact `bindings`, `authorized_scope`, optional `limits`,
  `mode` (default `fixture`) and `action_slice` (default 4).
- `GET /api/v1/agent-runs/{id}`: ref-only state, progress, usage and terminal canonical outcome.
- `GET /api/v1/agent-runs/{id}/plans` and `/observations`: accepted plan history and action feedback.
- `POST /api/v1/agent-runs/{id}/resume`: `expected_checkpoint_revision`, UUID `request_id`, optional
  missing resume/package binding, explicit `decision` (`continue`/`cancel`), or `authorized_targets`
  within the original scope. Reusing the same ID/payload returns current state without executing again;
  stale revisions or changed payloads conflict. Existing nonempty bindings cannot be silently replaced.

Example body (replace IDs with synthetic domain records created through the existing APIs):

```json
{
  "goal": "分析岗位匹配，并用我选择的简历生成招呼语。",
  "mode": "fixture",
  "bindings": {
    "profile_id": "00000000-0000-4000-8000-000000000001",
    "job_revision_id": "00000000-0000-4000-8000-000000000002",
    "resume_revision_id": "00000000-0000-4000-8000-000000000003"
  },
  "authorized_scope": {
    "targets": ["fit_analysis", "greeting_generation"],
    "fit_gate": "informational"
  }
}
```

Missing resume selection yields `waiting_input`; gated low fit yields `waiting_decision`.
Neither is terminal and neither automatically resumes. `decision=continue` is an explicit user
approval of the gated, unchanged context. `allow_tailored_greeting=true` authorizes a new-tailored-resume
binding for Greeting; otherwise the selected historical resume remains the input.

Limits default to 32 root steps, 8 business actions, 12 model calls, 16 tool invocations, 2 searches,
2 replans, 200k/40k input/output tokens, USD 1 estimated-plus-reserved budget and 600 active seconds.
A plan has at most 4 actions and dependency depth 3. Planner prompt/context/schema use a conservative
UTF-8 byte token upper bound, hard capped at 8k; oversized goals fail before any model call.
Planner/replan and child calls share one ledger. Unknown usage remains reserved, never billed cost.
Waiting time is excluded; child usage must not be added to the parent total a second time.

Checkpoints are committed at whole-action boundaries. Completed actions are not replayed; facts,
context and completed PDF availability/hash are checked again before resume. `action_slice` can return
at a normal `ready` checkpoint with root status `running`; a later resume continues it. In-flight
requests are deliberately not recoverable or auto-replayed. This is synchronous single-process
execution, not a distributed worker, exactly-once service or production crash recovery system.
Full goal text is private DB content, excluded from checkpoints and operational traces.

Offline runtime acceptance is included in `pytest`; it uses fake models/planner, fixture research,
real temporary PostgreSQL and the pinned real Typst/fonts. Synthetic acceptance does not demonstrate
real recruitment outcomes or planner quality.


### Version governance before v0.2b

Business Action Registry and model/prompt registries remain separate. Actions declare
`version`, `args_schema_version`, `result_schema_version` and existing policy metadata.
New plans pin `action_version`; validation, resume and dispatch require an exact Registry match.
Legacy unpinned pending actions remain readable but cannot resume (`action_version_mismatch`);
completed actions remain historical provenance. No automatic contract upgrade/replay is performed.
Action/schema changes require an action version bump. AgentStep records the bound action and schema
versions. Search ToolCall/API records `company_search` / `company-search-v1` with input/output
schema versions. Migration `f730b2c01231` adds nullable schema columns; old unknown values stay null.
Render reports additionally capture `resume-render-wrapper-v1` and `resume-validation-v1`, separately
from template/font/layout/Typst versions; old reports retain unknown wrapper/validation versions.
Planner success/failure retains safe provider diagnostics. This governance update is offline-only;
Interview Loop adds three feature-local registered prompts; no new live quality claim is made.


## v0.2b Interview Loop

Three explicit API capabilities reuse the existing Model Gateway, PromptRegistry, runtime trace
and budget primitives. They do not replace the v0.2a Planner or add actions to its authorized scope.
Offline acceptance uses synthetic data. A bounded OpenAI synthetic smoke also passed Mock Quick,
single/all-plus-overall Mock Debrief and Actual-source Debrief. This is not real interview assessment
quality validation.

**Actual intake.** `POST /api/v1/interviews` creates a real interview round (free-text `round_name`,
optional `occurred_at`, Application binding). GET one or GET with `application_id` lists rounds.
`POST /interviews/{id}/entries` appends a typed primary/follow-up entry; `PATCH /interviews/{id}`
corrects current fields or replaces the ordered entries list (also supports deletion).
Entries carry stable UUIDs, unique order, question, nullable answer and a same-session primary parent
for follow-ups. Updates and legacy `POST /interviews/{id}/notes` require `expected_revision`.
Successful mutations increment `content_revision`; stale mutations return conflict. Creation starts
at revision 1 (`expected_revision=0`). No per-edit immutable history, transcript parser or Application
status changes. Debrief freezes its own immutable snapshot before later edits.

**Mock.** `POST /api/v1/mock-interviews` requires explicit `context` with `profile_id`,
`job_revision_id`, `resume_revision_id` and optional `interview_preparation_id`.
It freezes verified facts and exact context without generating missing preparation.
Creation returns `ready_to_generate`. POST `/{id}/generate` starts/retries one generation;
POST `/{id}/answers` accepts an immutable answer and attempts the next generation;
POST `/{id}/end` ends early; GET retrieves durable progress/transcript.
All continuations require `expected_revision` and `request_id`; answers additionally require
`pending_question_id`. Identical request IDs return current progress without another call.
Conflicting IDs/stale revisions fail. A generation failure retains an accepted answer and returns
`ready_to_generate` with `stop_reason`; retry needs a new request ID, not a repeated answer.

Quick/Standard/Long have exactly 3/5/8 primary questions and at most 1/3/5 follow-ups.
Custom allows 1–8 primary, 0–5 follow-ups (not above primary target). The fixed policy spends the
follow-up allowance on earliest answered primaries, at most one each. The model cannot stop early
or choose an illegal kind. Waiting for an answer has no deadline and consumes no execution time.
Unknown/failed attempts consume the same session call quota; exhausted resources can prevent
reaching target, leaving a visible stop reason for explicit user action. No auto-paid retry in Mock.
Only the current answer is included in each next-turn request, alongside question-only history.

**Debrief.** `POST /api/v1/interview-debriefs` takes `source_kind=actual|mock`, `interview_id`,
`expected_source_revision`, `question_analysis=none|single|all` and independent `overall_analysis`.
Single requires a primary `primary_entry_id`; arbitrary subsets and empty targets are rejected.
Mock sources must be completed (including early-ended). Optional actual context uses explicit
exact bindings. Identical ordinary create requests reuse the same run (including failed results).
Use `POST /{id}/regenerate` for a new execution over that frozen source; this never switches to
a later edited interview. Creation freezes a source hash/snapshot and preflights all requested input sizes;
it does not call a model. `POST /{id}/execute` drives bounded concurrent work as SSE in the current
request. GET `/{id}` returns status, artifacts and deterministic presentation; GET `/{id}/events?after=N`
replays persisted business events. This is artifact delivery, not token streaming or a worker.

Each group includes its primary and all follow-ups. Overall analyzes the source independently,
not other evaluations. Results can complete out of order; display metadata always orders groups
by source question number and Overall last. Evidence labels/previews join the immutable snapshot;
internal refs are machine fields, not user-facing labels. Missing answers cannot support quality
findings. Retryable/schema failures use finite existing retry limits, with persisted retrying/failed
states. Completed artifacts remain available during other failures; a new single/overall request
can retry that target. Such a request freezes the selected source's then-current revision.

Operator configuration `CAREER_AGENT_INTERVIEW_POLICY` accepts a JSON object with `concurrency`
(default 3, hard maximum 8), `mock_generation`, `mock_group`, `actual_group`, `mock_overall`,
`actual_overall`, plus cumulative `mock_session`, `mock_debrief`, `actual_debrief` limits.
Call profiles contain `max_input_tokens`, `max_output_tokens`, `max_estimated_cost`, `max_seconds`.
These are loose safety ceilings, not calibrated product prices. Actual profiles allow larger
contexts. Transport/schema retry counts inherit `CAREER_AGENT_MODEL_RETRY_LIMIT` and
`CAREER_AGENT_SCHEMA_REPAIR_LIMIT`. Provider timeout settings still apply underneath the per-call
runtime ceiling. Mock quota is primary target + follow-up maximum, including failed attempts.
A row-locked shared ledger reserves before calls, settles once and keeps unknown usage reserved;
AgentRun usage is a projection, not an additional charge. Reported cache/write/reasoning usage is
preserved when available. Estimated/reserved budget is not actual billed cost.

Limits: no bulk import, voice, answer edits in Mock, summary/chunking, scoring, auto-KB writes,
background continuation, exactly-once or production crash recovery. Disconnect cancels active work
and preserves committed results; unknown in-flight cost remains reserved. Process/DB failures can
leave in-progress state requiring operator inspection. Example answers conservatively use only
verbatim supplied verified fact statements. Deterministic guards validate references, basic privacy
and explicit prohibitions, not the complete semantic truth of generated analysis.

Local v0.2b acceptance: 349 tests passed (32 new Interview Loop tests), Ruff/formatter, strict mypy,
empty PostgreSQL migration/drift and legacy backfill, offline locked install/build/import, pinned
Typst/font checks and repository hygiene. Subsequent synthetic live smoke used 10 OpenAI calls,
no Tavily calls or retries, with USD 0.1120449 estimated cost (not provider-billed cash cost).

The live run observed peak provider concurrency 3, out-of-order group completion with stable display
order, and committed artifacts available before the all-mode request ended. One call reported
2,169 cached input tokens; all calls preserved cache-write telemetry without inventing a separate
write surcharge. Run/call accounting matched and all reservations settled. Synthetic source, results
and one-off scripts remain outside the repository. No production network/proxy buffering claim.

### Audit fixes: provider privacy and Interview provenance

Preparation model inputs (including base/selected Resume and requirements) and frozen Interview
context use a shared copy-only minimized view. Resume labels/metadata and contact fields are omitted;
known personal names/contacts and recognizable contact spans are redacted. Domain records remain
unchanged. This is a deterministic privacy baseline, not comprehensive DLP.

New Mock turns and Debrief artifacts expose `logical_operation_id` and `accepted_model_call_id`.
The run's calls endpoint links all attempts for that operation, including explicit Mock retries and
Debrief schema/transport retries. Historical associations remain null when unknown; migration does
not reconstruct provenance from timing or task names.

## v0.3 offline evaluation foundation

Evaluation uses code-managed PromptSpec input contracts before provider dispatch. Cases freeze
inputs, clock and external observations; candidate manifests freeze code/prompt/schema/policy
identity. Legacy artifacts remain readable but are not reused without compatible execution metadata.
Debrief regeneration explicitly reuses a frozen source; it creates a new result and preserves history.

The `evaluation/` package provides component, business-workflow and Agent-goal replay, independent
trials, private operation snapshots, deterministic checks, priority-tier comparison, deterministic
sampling and pending Judge work. Human annotation, user feedback and Judge judgments are separate.
Fixture Judge outputs test plumbing only; they are not evidence of human-level quality or job-search
outcomes. No paid evaluation has been run as part of this milestone.

Run the initial 40-case synthetic suite against local PostgreSQL (the role needs CREATEDB):

```sh
uv run python -m career_agent.evaluation run tests/fixtures/evaluation/foundation.json
uv run python -m career_agent.evaluation inspect runs RUN_UUID
uv run python -m career_agent.evaluation compare BASELINE_UUID CANDIDATE_UUID
uv run python -m career_agent.evaluation drain-judge --limit 20 --concurrency 2
uv run python -m career_agent.evaluation calibration
```

All CLI execution defaults to offline fixture adapters, even if live credentials are configured.
Workflow/Agent trials create a disposable PostgreSQL database and private temporary artifact directory;
model-task replay starts directly from frozen model-facing input. Missing frozen observations fail
closed. Source reconstruction makes zero model calls. Origin re-execution requires
`--mode origin_reexecution --explicit-diagnostic`; unavailable original model/config is reported,
never silently substituted. `--trials 3` preserves separate trial results.

REST endpoints under `/api/v1/evaluation` expose cases/suites/runs/trials/operations, comparisons,
sampling, explicit Judge drain, blind annotation queues/calibration, and private captures.
Explicit `POST /evaluation/judges` can assess a replay artifact without recursive auto-sampling.
Use capture `triage` → `sanitized` → explicit `promote`; `/cases/{id}/export` rejects private/unsafe
payloads. These APIs are local private-data interfaces, not publicly deployable authenticated services.
Operation snapshots and captures deliberately contain private debug inputs in dedicated DB tables;
ordinary runtime traces remain metadata-only. Do not publish database dumps or capture responses.

Static concurrency and root/trial reservations bound execution. Estimated usage cost and unknown
reservations are not provider invoices. Judge draining is explicit, without a worker or scheduler.
The sanitizer is a deterministic baseline plus explicit human review, not proof of complete DLP.
No distributed recovery, production reconciliation, automatic sampling control or dashboard is included.

Local v0.3 acceptance: **444 tests passed**, Ruff/formatter and strict mypy passed; empty PostgreSQL
migration, drift/history upgrades, offline locked install/build/import and Typst/font checks passed.
A separate minimal synthetic OpenAI smoke passed: component/workflow replay, pending Judge drain,
blind annotation linkage, comparison and explicit origin re-execution. Six calls cost an estimated
USD 0.017976 (not billed cost); no Tavily calls. This validates plumbing, not population quality.
Remote CI has not been run for these uncommitted changes.

Evaluation API/CLI remain offline by default. A trusted caller may explicitly inject an OpenAI
Gateway into EvalRunner with `allow_paid_models=True` and `live_enabled=True`; the manifest captures
that actual gateway. Workflow replay still uses temporary PostgreSQL/private storage and frozen
research. Enabling application live mode alone does not enable paid evaluation.

The v0.3 audit corrections retain ordinal Judge ratings in regression comparisons and distinguish
not-sampled from requested-but-unavailable quality evidence. Correctness remains independently
visible, with unconditional Tier 0 blocking. Origin re-execution binds the exact supported origin
model/config instead of using candidate routing. Private versioned capture conversion supports
isolated replay without consulting changed production inputs; insufficient historical captures fail
explicitly. Calibration preserves pair details while selecting one latest pair per subject/stratum.

## Runtime Control Core (v0.4 Phase 1)

Offline acceptance: 499 tests passed, including PostgreSQL and Typst integration; Ruff, formatter,
strict mypy and offline packaging checks passed. This phase has not run paid/live capacity probes.

Model calls use deterministic approved-route priority, shared in-process provider/route capacity,
rolling circuit breakers and bounded attempt/route-switch limits. Request gateways share one
controller per non-secret quota scope. Existing workflows continue to own retries; the gateway does
not introduce hidden provider retries. Defaults retain one approved route per tier/task, with no
automatic premium escalation.

`CAREER_AGENT_RUNTIME_CONTROL` configures the versioned JSON control policy (quota scope, provider and
route limits, `headroom_factor`, `background_fraction`, breaker, `feedback_buckets`). `CAREER_AGENT_TASK_MODEL_POLICIES`
configures approved task candidates, qualifications/roles, output estimates/hard limits and operation
bounds. Configuration is trusted operator input, never model output. The initial default headroom is
10%; background/evaluation traffic has a static protected-capacity ceiling. Set advertised limits to
your actual quota; defaults are development safety ceilings, not discovered account entitlements.

Rate feedback defaults to a route-local bucket. Configure `feedback_buckets` by exact
`provider:model` route with `scope` (`provider_shared` or `shared_group`) and a stable `bucket_id`
only when that sharing is known. Bucket identity comes from configuration, not response headers.
Provider request timeout affects breaker health; operation deadline and user cancellation do not.

Capacity token estimates do not reduce conservative financial budget reservations. Unknown usage
remains reserved; estimated cost is not billed cost. Every real attempt preserves its bound route and
control metadata. Current tasks reject incomplete/truncated outputs and retain full grounding/PII
rules. Offline Eval trials use isolated frozen control scenarios, never the live controller.

Coordination remains limited to one controller-owning process per quota scope. Phase 2 adds a
PostgreSQL ownership guard, durable recovery and bounded controls below. Independent server workers
or Judge CLI processes cannot concurrently own the same scope; this is not distributed quota sharing. This milestone uses offline faults, not paid 429/5xx
probes; synthetic tests do not establish real traffic capacity or job-search quality.


## Recovery, Ops and bounded control (v0.4 Phase 2)

Live API startup and live dependency/CLI lifecycles acquire a PostgreSQL ownership guard, replay
metadata-only control events, classify unsettled attempts, then enable admission. Each attempt has
an independently committed journal before dispatch. The journal contains identities, selection,
financial reservation and usage metadata; it has no FK to uncommitted business rows and no prompt,
response, resume or transcript body. A failed bootstrap/ownership check keeps admission closed.

A dispatch intent without a confirmed result is **unknown**, not a failed or safe-to-retry request.
Its financial reservation remains visible and blocks the same budget owner until reconciliation.
Capacity uncertainty expires according to its quota window; financial uncertainty does not expire
with it. Known results without a committed business outcome also require reconciliation after restart.
Reconciliation can link a committed call/artifact or record a manual acknowledgement; it never replays
an unknown request or forgives unknown spend. Business checkpoint/resume behavior remains separate.

`CAREER_AGENT_AUTOMATIC_CONTROL` is versioned JSON policy for the in-process bounded tick:
minimum observations, hysteresis thresholds, cooldown, pressure/concurrency bounds, output reservation
bounds and Judge sampling bounds. The only actuators are admission pressure/concurrency, capacity
output estimates and rates attached to newly generated subjects. They never change financial hard
limits, candidate priority/qualification, grounding or authorization. Manual overrides have a TTL.
Priority is hard safety/kill switch → active manual override → automatic adjustment → base policy.
The tick is process-local and is not a durable scheduler. No Judge is executed automatically.

Ops routes require an explicitly configured `CAREER_AGENT_OPS_TOKEN` and `X-Ops-Token` header.
Keep that token in the local environment; an unset token denies access. `CAREER_AGENT_OPS_ENABLED=true`
can bootstrap the owner without enabling paid providers (useful for local offline operations).

- `GET /api/v1/ops/controller`: readiness, base/effective state, route counters and circuits.
- `GET /api/v1/ops/metrics?window_seconds=3600`: attempt/operation counts, known estimates,
  unknown reservations, latency, routing/reservation accuracy, and separate random/targeted quality populations.
- `GET /api/v1/ops/events?after=0`: ordered metadata-only events; full snapshots are not returned.
- `GET /api/v1/ops/recovery-incidents`: incident refs and revision/status.
- `POST /api/v1/ops/controls`: `request_id`, `expected_revision`, `action` (`tick`, `override`,
  `clear_override`, `kill`, `global_kill`; global writes require `expected_global_revision`), plus applicable `route`, `values`, `ttl_seconds`, `enabled`.
- `POST /api/v1/ops/attempts/{attempt_id}/reconcile`: idempotency ID, incident expected revision
  (zero if no incident), and `inspect` or `manual_acknowledge` with a safe reason code.

Metrics distinguish confirmed attempts from unknown dispatch intents. Workflow/step/action populations
are separate; parent/child usage is never summed. Estimated USD and unknown budget reservations are
not provider invoices. No actual billed cost is inferred. Ops has no frontend or ordinary access to
private evaluation snapshots.

Offline Eval freezes control algorithms/bounds and can seed UTC snapshots, restart transitions and
operator events in an isolated trial controller. Effective revisions/decisions are execution provenance,
not mutable CandidateConfig. Origin diagnostics that cannot reproduce effective control semantics fail
with `origin_config_unavailable` rather than silently substituting current controls.

Limits: no exactly-once execution, distributed coordination, remote outcome lookup, automatic replay,
durable worker, candidate promotion, UI or response cache. Metadata cannot reconstruct a lost provider
body; ambiguous outcomes require operator review. Incompatible persisted base-policy identities fail
closed and require an explicit state migration, not automatic reset. Synthetic offline tests validate
mechanics, not real traffic capacity or job-search quality.

Phase 2 local offline acceptance: **532 tests passed after the audit fixes**, including real PostgreSQL migration/drift and
historical upgrades. Ruff/format, strict mypy, offline wheel/sdist/import and controlled font checks passed.
Phase 2 is the completed/CI-accepted baseline. This Phase 3 change is verified offline; synthetic
acceptance does not establish real traffic capacity, cache hit rate, or job-search quality.


## Reuse optimization (v0.4 Phase 3)

Provider-facing prompt composition has feature-owned, versioned block order and deterministic
object-key serialization. Semantic array order and fact/evidence/ownership refs remain intact.
Stable context precedes volatile planner/Mock fields. Research synthesis omits retrieval timestamps
and provider bookkeeping from the model view; the original private evidence keeps that provenance.
This is prompt stability, not a local response cache or a guarantee of provider cache hits.

Authorized read-only search first checks PostgreSQL `search_observations`. Its exact identity includes
provider/adapter and tool/schema contracts, whitespace-normalized query, actual search parameters,
company scope and fixture/live mode. Fresh, hash-valid compatible results retain their source refs;
expired/incompatible/missing records require the already-authorized search. Unknown adapter contracts
are not reusable. Successful observations commit independently so later synthesis/business rollback
does not discard them. Preparation targets still never add research on a cache miss. Company report
lookup considers older fresh compatible reports when the newest report is incompatible.
Explicit authorized force refresh bypasses both report and observation reuse.

Transaction-scoped PostgreSQL claims serialize identical prerequisite/target generation before model
spend, holding the claim through commit. `CAREER_AGENT_REUSE_CLAIM_WAIT_SECONDS` defaults to 5 (0–30).
A contender gets `reuse_in_progress` if that wait expires; no model is called. A waiter with no usable
result after a peer fails gets `reuse_result_unavailable`, not an automatic duplicate attempt. This
is request-lifecycle coordination, not a worker or an exactly-once/crash-replay guarantee. Existing
exact fingerprints, grounding, compatibility and artifact integrity validation still decide reuse.
Metadata-only generation intent survives business rollback, so a contending waiter cannot silently
re-spend without an authoritative result. Intent does not imply provider dispatch or actual charges.

Ops metrics expose **separate populations**: `provider_token_cache` (quota-scoped journal attempts,
provider-reported fields only) and `reuse_global_population` (external-observation/business decisions).
Cache-hit rates include their known-data denominators; unreported cache-write/cache-read usage remains
unknown. Reuse is a decision count, not measured financial savings; estimated/billed savings are null.
The new observation JSON is private data, never returned by metadata-only Ops endpoints.

Offline acceptance uses real temporary PostgreSQL, pinned Typst/fonts and synthetic/HTTP-mock
providers. Combined tests check selection→budget→journal→ModelCall→artifact/Ops, overflow without
skipped-route calls, retry/fallback, 429, output-limit rejection, recovery and concurrent reuse.
Existing kill/override/CAS, Eval isolation, frozen clock, PII and historical upgrade checks remain
required. Phase 3 live smoke and independent post-implementation audit are separate later gates.
No Redis, generic/semantic model cache, UI, distributed quota coordination or candidate promotion.

## Web product backend contracts

The backend now exposes browser discovery and exact material-use records; no frontend or
background worker is included. Existing preparation endpoints remain available.

- `GET /api/v1/companies`, `GET /companies/{id}`; company research history and fresh compatible
  current report under `/companies/{id}/research` and `/research/current?mode=live|fixture`.
- `POST /api/v1/companies/{id}/research` creates an explicit research operation. Its body is
  `{request_id, kind: "company_research", request: WorkflowRequest}`. An exact Profile and JD
  context is required by the existing research contract. Set `request.force_research_refresh=true`
  to bypass both report and observation reuse. Missing research is never implicitly authorized.
- `POST /api/v1/operations` durably creates an idempotent handle for `prepare_application`,
  `prepare_interview` or `company_research`. Save its ID before calling `POST /operations/{id}/execute`.
  Execution is synchronous; poll `GET /operations/{id}` and read `/result` after completion.
  Request interruption does not promise background continuation. An abandoned running operation
  becomes `recovery_required`; execute never automatically replays it. Inspect the existing run/recovery
  APIs before explicitly starting new work. The preallocated run ID may have no business row after rollback.
- Operation statuses distinguish `pending`, `running`, `success`, `partial`, `failure`, `needs_input`,
  `decision_required`, and `recovery_required`. Input/decision continuation uses a new explicit request
  and existing compatible artifacts. `201` means handle creation, not model success.
- `GET /preparation-artifacts/{package_id}/product-view` resolves requested targets to exact result,
  Resume revision/PDF, content, context, versions, reuse state, feedback subject and allowed actions.
  Package status preserves the canonical workflow outcome; completed target items use `success`.
  Historical reads never regenerate or silently rebind to latest revisions.
- Paginated collections: `/applications` (Job/Company/status), `/mock-interviews` (Job/Application),
  `/interview-debriefs` (source/Job/Application), `/runs` (kind/workflow/status), `/operations`,
  `/profile/revisions`, `/jobs/{id}/revisions`. Exact history: `/profile/revisions/{id}` and
  `/job-revisions/{id}`. Lists return `items`, `limit`, `offset`, `has_more`, with stable tie-breaks;
  offset pagination is not a frozen snapshot under concurrent insertion.
- `POST /applications/{id}/submissions` records an explicit real submission with `request_id`,
  `expected_revision`, exact `resume_revision_id`, `render_artifact_id`, optional `greeting_id`,
  `package_id`, and `note`. It validates context and PDF integrity and links an Application event
  in the same transaction. First submission explicitly transitions to applied through existing rules;
  another submission while applied appends a note event. Generation/selection alone never does this.
  `GET /applications/{id}/submissions` lists immutable material-use records.

Errors retain sanitized stable codes and HTTP 404/409/422 semantics. An accepted historical render
may later be unavailable on disk; download still verifies the private file/hash. These APIs retain
the single-user/private-service deployment assumption and are not an Internet authentication layer.

Debrief discovery returns each `generation_id`, resolved `selected_run_id`, `is_selected`,
`detail_url` (selected result), and `historical_detail_url` (exact listed generation).
Greeting/InterviewPrep product results include `source_resume_revision_id`; this is distinct from
`resume_revision_id`, which identifies a generated Resume output. Research recovery protection is
reported as `recovery_required`, consistently with Preparation operations.

## Web preflight discovery

Application Knowledge Notes and metadata-only Internal evaluation/attention discovery are documented
in [Web backend contracts](docs/web-backend-discovery.md), including the server-only Next.js/BFF
Ops-token boundary. No frontend or new control-plane actions are added.
