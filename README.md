# Career Agent

Career Agent is a primarily single-user personal job-search Agent engineering project.
The current milestone is **v0.2a Runtime Core (completed locally)**, built on the completed v0.1 Domain MVP.
Development and demonstrations use synthetic data; this is not a multi-user production service.

## Implemented now

- Versioned personal profile, user-confirmed facts and replacement history.
- Manual JD ingestion, explicit requirements, immutable JD revisions, company records.
- Application tracker with optimistic revision checks, status/correction/note events.
- Interview rounds and manual notes; knowledge-note CRUD basics.
- PostgreSQL persistence for source documents, STAR structures and runtime metadata.
- Run/step/call metadata APIs and two explicitly invoked fixed preparation workflows.
- Model-independent contracts, static policy/capability filtering and an injected fake provider.
- Safe error responses, allowlisted operational logging and private-data configuration.
- Synthetic tests using a real temporary PostgreSQL database, Ruff and strict mypy.
- Hand-authored, versioned ResumeVariants, fact grounding, deterministic content compression,
  trusted zh-CN Typst rendering, one-page PDF validation and exact-revision artifact APIs.
  Chinese resumes with English technical terms are the current canonical product.

OpenAI Responses and Tavily adapters, deterministic target orchestration, versioned prompts,
structured zh-CN tailoring and static budget controls are implemented and tested offline.
**Live extraction/research/fit/tailoring/PDF/greeting have been exercised; Interview Prep passed after a timeout-policy fix, and controlled compression produced an accepted PDF. v0.1c live acceptance is historical; v0.1d acceptance is offline only. Synthetic acceptance does not establish real job-search quality.**
No automatic applications/messages, unrestricted planner, durable worker, mock interview, LLM judge,
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
- v0.2a: bounded Runtime Core; v0.2b: Interview Loop (planned).
- v0.3: Harness / Evaluation / Safety (planned).
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
are operator configuration, not domain logic. The seven prompt versions are repo-owned in
`preparation/prompts.py`; hashes cover instructions, input keys and output schema, never private text.

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

- `input_tokens` / `output_tokens` / `cached_tokens` / `reasoning_tokens` are provider-reported
  usage. `measurement=reported` describes usage, not a paid invoice. Unknown per-call usage is null.
- Existing `estimated_cost` (with `currency=USD`) is the USD estimate, equivalent to
  `estimated_cost_usd`: reported OpenAI usage × the versioned configured price table.
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
