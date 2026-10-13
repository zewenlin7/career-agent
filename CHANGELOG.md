# Changelog

## Unreleased

### Cost-accounting clarification — offline only

- Separated unknown-attempt token/cost reservations from provider-reported usage and estimated cost.
  Existing USD `estimated_cost` now excludes reservations; nullable billed cost and unknown billing
  tier explicitly avoid invoice claims. ModelCall cost projection stays null for unknown-cost failures.
- Budget admission still uses estimates + reservations, preserving conservative limits. Successful
  responses and invalid outputs with reported usage release the reservation and retain price estimates.
- Tavily trace records dispatch counts, unknown consumed credits, and PAYG-equivalent retail estimate
  on success; failed searches retain reservations. USD 0.008 is not claimed as actual cash expense.
- Affected offline checks: 62 unit/contract tests and 31 PostgreSQL integration tests passed;
  Ruff/formatter/strict mypy and git diff checks passed. Full suite was not rerun for this scoped fix.
- Historical smoke budget USD 0.3350816 = estimates USD 0.1576516 + reservations USD 0.1774300;
  actual billed cost unknown. No external calls, billing API/admin key, table migration or scope expansion.

### Added — v0.1c Job Preparation Workflow

- Explicit `prepare_application` and `prepare_interview` fixed LangGraph workflows; no dynamic
  planner, worker, automatic application or message delivery. Interview preparation runs separately.
- OpenAI Responses native Pydantic outputs, configurable cheap/strong routing, capability checks
  and disabled automatic premium use. Seven repository-owned prompt specs with version/hash.
- JD requirements with source evidence, company-level Tavily/fixture research and a 168-hour cache,
  per-requirement fit, grounded zh-CN tailoring, existing Resume Compiler integration, greeting
  and interview outlines. One bounded semantic compression call after eligible layout failure.
- Static per-attempt model/search/token/cost admission; failed/unknown usage conservatively reserved.
  Transport retry/schema repair keep task identity; semantic compression and Typst attempts are distinct.
- Private validated JSONB preparation/research artifacts, exact JD/Variant references, runtime
  model/tool/prompt/schema/policy/usage metadata; migration `c38190f12a01` after `ade973186357`.
- Explicit existing Company identity reuse without name-based merging; exposed JD revision IDs.
- Bounded context selection, contact minimization, untrusted-content boundaries and deterministic
  reference/numeric/grounding guards. No prompt/body/hidden reasoning in runtime traces.
- Safe structured-output diagnostics for incomplete/refusal/schema/validation/guardrail failures.
  Validation inputs, raw provider errors, local paths and credentials are excluded.
- Configurable per-task HTTP timeout policy: default 60 seconds, Interview Prep 120 seconds,
  independent of token/cost budgets; stable `provider_timeout` and allowlisted diagnostics.
- Offline test network boundary, fixture adapters and a general isolated dual-workflow smoke entry.
  Live mode requires explicit opt-in; smoke disables retries and retains live databases for diagnosis.

### Verified — v0.1c final local acceptance

- Full offline suite: **195 passed in 30.75s**, including empty real PostgreSQL migration to head,
  Alembic drift, workflow/guardrail/budget/privacy tests and actual Typst/PDF compilation.
- Ruff and formatter (**63 Python files**); strict mypy (**36 source files**) passed.
- Offline lock verification, fresh temporary environment installation, wheel/sdist build and package
  inspection passed; trusted Typst template included, no PDF/font/DB/private binaries packaged.
- Typst 0.15.1 and hash-pinned Noto Sans CJK SC dependencies verified locally.
- Cleaned generic smoke completed both workflows in fixture mode; installed wheel imports and
  trusted template resources verified outside the source checkout. No real provider calls in final checks.
- Final review removed four one-off recovery scripts with historical database IDs/budget baselines,
  cross-script imports and duplicated direct-model compression code from the public candidate tree.
  The retained generic smoke entry uses the actual workflows; no new workflow or harness was added.
- Public candidate-file hygiene and `git diff --check` passed. No commit/push; remote v0.1c CI is pending.

### Verified — v0.1c bounded live acceptance (2026-10-12)

- Real cheap JD extraction, one Tavily basic search, strong research synthesis and Fit Analysis passed.
  The first tailoring attempt failed before safe diagnostics existed; its discarded upstream database
  could not be recovered. Its exact failure cause is not claimed. User-authorized later cases rebuilt
  canonical synthetic upstream context and reused it without repeating upstream paid tasks.
- Targeted tailoring: actual `gpt-6.1-sol`, 2,740 input / 2,933 output / 0 cached / 122 reasoning,
  47,082 ms, USD 0.03481; guardrails passed and first compile accepted one-page zh-CN PDF.
- Greeting: actual `gpt-6.1-sol`, 1,983 input / 282 output / 0 cached / 0 reasoning,
  15,249 ms, USD 0.006786; zh-CN/reference/number checks passed; no message sent.
- Interview: a 60,828 ms local timeout stopped that attempt. After the configurable timeout fix,
  one explicitly authorized call passed: actual `gpt-6.1-sol`, 5,002 input / 3,885 output /
  4,999 cached / 143 reasoning, 78,393 ms, USD 0.0393559; structured output and refs passed.
- Controlled compression: two deterministic preflights reproduced eligible two-page `layout_failed`.
  One real call passed: actual `gpt-6.1-sol`, 5,964 input / 2,497 output / 0 cached / 62 reasoning,
  35,518 ms, USD 0.036898. Repeated summary content shrank from 3,951 to 467 total characters;
  10 required items, 10 fact refs and 9 explicit hard claims preserved; first recompile accepted one page.
- Reasoning tokens are included in output usage. No automatic live retries/schema repair. Cumulative
  conservative accounting **USD 0.3350816**, remaining **USD 0.6649184** of the original USD 1 cap;
  failed-call unknown usage stays reserved, so this is not a confirmed invoice total.
- All requested live task cases passed across bounded attempts, not one uninterrupted production run.
  Synthetic smoke verifies contracts/connectivity; it does not prove real job-search quality, semantic
  truth or general compression quality. Human review remains necessary. v0.1d is not started.

### Added — v0.1b Resume Compiler

- Versioned hand-authored ResumeVariant documents and immutable revision persistence,
  exact Profile/JD references, captured fact revisions and duplicate/invalid input validation.
- Render-time verified-fact/snapshot/requirement checks, numeric token consistency and
  explicitly declared hard-field checks. No semantic truth or LLM tailoring claim.
- Deterministic full/short/optional content selection, stable priority tie-breakers,
  required-content preservation, decision records and an eight-compilation hard cap.
- Canonical zh-CN A4 single-column template with Chinese headings and mixed-script content,
  pinned Typst 0.15.1 and official Noto Sans CJK SC 2.004 Regular/Bold fonts.
- External font dependency setup with immutable URLs, SHA-256 verification, offline preflight,
  render-local snapshots and identical local/CI preparation; no system/embedded font fallback.
- Locale/schema/template/font-policy versions, actual font family and verified file hashes
  in artifact metadata; no font paths, font binaries or PDFs in git/wheel.
- Fixed 10.5 pt body, margins/spacing, compiler timeout and safe structured errors.
- Actual PDF inspection for page count, A4 dimensions, extractable/retained text,
  character bounds, font/minimum size and known glyph failures.
- RenderArtifact persistence with exact Variant revision FK, SHA-256, private opaque file
  references, findings, attempts and schema/template/layout/compiler/font version metadata.
- Create/get/revise/render Variant APIs and artifact metadata/download APIs; failed render
  reports are persisted without a misleading successful/downloadable file.
- Private artifact storage, traversal/symlink defenses, download integrity validation,
  request rollback file cleanup and template-injection regression tests.
- Three Chinese acceptance fixtures plus a mixed-script/font regression fixture and local
  example-generation script; English data remains auxiliary regression input. No LLM calls.
- CI configuration for pinned Typst 0.15.1; README/TODO/architecture updated to actual scope.

### Fixed — v0.1b review

- Retained-text validation now matches ordered, non-overlapping ranges in immutable normalized
  extraction. Deleting headings can no longer manufacture body text; duplicate/missing/overlapping
  text, Chinese/English and Unicode normalization have regression coverage.
- Accepted status is assigned only after byte read and SHA-256 calculation. Read/hash/storage
  failures clear success/file metadata, persist failed reports and cannot be downloaded.
- CJK punctuation uses a fixed content gutter, and vector bullets avoid ambiguous text-glyph
  mappings without relaxing page/font/retained-text validation or shrinking content.

### Verified locally — v0.1b

- Real CLI: `typst 0.15.1 (unknown commit)`; official font dependency setup completed from an
  empty external cache. Regular/Bold hashes match the pinned manifest; offline preflight passes.
- `normal_one_page_zh_cn`: accepted, one page, one attempt.
- `compressible_overflow_zh_cn`: 5 → 3 → 1 pages; short-form replacement then optional item
  removal in three attempts, preserving every required item.
- `impossible_one_page_zh_cn`: required content remains four pages; `layout_failed`, no accepted PDF.
- `mixed_script_font_regression`: accepted, one page; Chinese/Latin/numbers/punctuation extracted.
- Both successful Chinese acceptance PDFs were rendered to images and visually inspected:
  readable Chinese and technical terms, aligned bullet markers, no obvious tofu/overlap/clipping.
  This is an agent visual inspection, not a claim of user sign-off or perfect typography.
- Unit tests: **74 passed**. Integration tests: **50 passed**, real PostgreSQL and Typst.
- Final full suite: **124 passed in 13.36s**; includes empty-DB upgrade to head and Alembic
  drift check, failed read/hash report persistence and download refusal.
- Ruff check passes; formatter: **45 files already formatted**; strict mypy: **25 source files**.
- Wheel builds offline, includes the trusted Chinese `.typ` template and no font/PDF binaries.
- Tracked/untracked hygiene and whitespace checks pass. No system fonts were installed.

### Added — v0.1a Foundation

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

### Verified locally — v0.1a Foundation

- Docker Compose PostgreSQL starts healthy; initial Alembic upgrade succeeds from empty.
- Locked dependency installation succeeds in a new virtual environment.
- Full suite: **57 passed**, no warnings; includes real temporary PostgreSQL databases.
- Ruff check and format check pass; strict mypy passes for all 14 source modules.
- FastAPI starts under Uvicorn; live HTTP health and OpenAPI (21 operations) verified.
- Alembic reports no schema drift; tracked and untracked files pass whitespace checks.

The user confirmed v0.1a was committed/pushed and its remote CI passed.
The v0.1b changes have not been committed/pushed; their updated remote CI has not run.
No final v0.1.0 release has been made.
