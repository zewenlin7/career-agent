# Career Agent

Career Agent is a primarily single-user personal job-search Agent engineering project.
The current milestone is **v0.1b Resume Compiler**, built on v0.1a Foundation and part of the eventual **v0.1 Domain MVP**.
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
- Hand-authored, versioned ResumeVariants, fact grounding, deterministic content compression,
  trusted zh-CN Typst rendering, one-page PDF validation and exact-revision artifact APIs.
  Chinese resumes with English technical terms are the current canonical product.

There is **no model-based resume tailoring, job preparation, research, LangGraph,
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
Foundation CI previously passed remotely. The v0.1b workflow adds pinned Typst 0.15.1;
its new remote run remains pending until you choose to push.

## Roadmap

- v0.1a: Foundation (implemented).
- v0.1b: Resume Compiler, Typst and PDF validation (implemented).
- v0.1c: Job Preparation Workflow (planned).
- v0.1d: Integration / E2E (planned).
- v0.2: Agent Runtime; v0.3: Harness / Evaluation / Safety (planned).
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
Every selection decision is recorded; no required item is deleted. Short forms are pre-authored,
not automatically rewritten. Failure never becomes clipping or an unreadable font size.

The current contract is `locale=zh-CN`, schema `resume-v2`, template
`resume_zh_cn_a4_single_v1`, layout policy `content-v1`, and font policy
`noto-sans-cjk-sc-2.004-regular-bold-v1`. Reports retain these versions, actual font family,
verified font-file hashes, compiler version and template hash; never local absolute font paths.
Retained text uses ordered, non-overlapping ranges in immutable normalized extraction, so matching
cannot manufacture text by deleting headings. Accepted status requires validated PDF bytes and
computed SHA-256; subsequent storage failure clears success/file metadata and persists a failed report.
The PDF hash checks file integrity; byte-identical PDFs are not the regression criterion.
Matching selections, decisions, page count and validation results are the determinism contract.
