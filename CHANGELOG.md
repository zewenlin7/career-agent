# Changelog

## Unreleased

### Added — v0.4 Phase 1 Runtime Control Core

- Task-approved prioritized routes, immutable attempt selections and metadata-only control decisions;
  unknown tasks and unqualified extra routes fail closed. No hidden Gateway retry loop.
- Process-shared provider/route capacity admission, configurable headroom and static traffic protection;
  independent capacity estimates and conservative financial reservations, idempotent settlement/debt.
- Rolling attempt-level circuit health, bounded half-open probes, typed conservative rate feedback,
  shared operation deadlines and bounded retry/fallback amplification including schema repair.
- Versioned output reservations/hard ceilings and complete-only truncation diagnostics. Partial/degraded
  metadata extension points do not enable incomplete canonical business results.
- Isolated frozen offline Eval controllers, frozen policy manifests, provider-specific dispatch and
  exact-origin routing checks; explicitly live Eval composition shares the injected quota controller.
- Interview preflight checks feasibility without selecting an attempt route; explicit generation retry
  preserves accumulated execution time while excluding time waiting for user input.

### Fixed — v0.4 Phase 1 audit

- Unified attempt outcome classification: provider timeout affects health; operation deadlines and
  external cancellation remain neutral. Interview/Runtime no longer relabel a settled cancellation
  as provider timeout. Interview cancellation cleanup persists ledger/trace/state before propagating.
- Typed trusted quota/bucket feedback defaults to route-local; configured provider/shared-group
  buckets share reservations without cross-bucket counter replenishment. Control identities advance
  to v2; unavailable older origin implementations fail closed while historical reads remain available.
- Judge late admission denial retains ordered metadata-only decisions and removes the undispatched
  ModelCall without charging the financial budget.

### Verified — v0.4 Phase 1 offline acceptance

- 499 tests passed, including real PostgreSQL migration/drift/history upgrades and real Typst paths.
- Ruff/formatter and strict mypy passed; offline locked install, wheel/sdist build/import and controlled
  font hash/Typst 0.15.1 preflight verified. Tests ran on Python 3.13.13 (project supports Python 3.12+).
- No paid provider/Tavily calls. Single-process quota coordination only; no restart reconstruction,
  distributed limiter, automatic tuning, Ops dashboard or new degraded business features.

### Added — v0.3 offline evaluation foundation

- Executable shared prompt input block/type/size/trust/privacy contracts, with feature-local definitions.
- Versioned current-execution artifact compatibility; legacy results remain historically readable.
- Explicit Debrief regeneration against immutable frozen sources, with selected-result/history retrieval.
- Versioned cases/suites/candidates/runs/trials and private operation provenance; disposable PostgreSQL
  and temporary artifact stores for workflow/Agent replay, frozen external observations and clock.
- Deterministic validator/trajectory checks and adapter fault plans, bounded shared budgets/concurrency,
  candidate drift rejection and priority-tier regression comparison with multi-trial distributions.
- Stable sampled/not-sampled decisions, independent pending Judge records and explicit offline drain;
  separate feedback, blind human annotation, confusion/Kappa/F1/confidence calibration reports.
- Private immutable bad-case payloads with append-only triggers, explicit triage/sanitization/promotion,
  repo-safe export and local evaluation CLI/API. Forty synthetic foundation cases cover all existing
  business model tasks plus deterministic, workflow, runtime, privacy and failure paths.
- Nullable Debrief history links and new evaluation tables; database payload immutability constraints.

### Verified — v0.3 offline acceptance

- 444 tests passed; Ruff/formatter, strict mypy, empty PostgreSQL migration/drift/history upgrades,
  offline locked install/build/import, Typst/font preflight and repository hygiene passed.
- Offline acceptance used no paid calls. Fixture Judge output validates plumbing, not real quality.

### Verified — v0.3 minimal live smoke

- Six synthetic OpenAI calls verified component and workflow replay, pending Judge drain, blind
  annotation linkage, comparison and exact-model origin re-execution. Estimated usage cost was
  USD 0.017976; no Tavily, retries or schema repairs. Actual billed cost remains unknown.
- Added explicit, default-off Gateway injection for paid replay; CandidateConfig records the injected
  registry/policy/prompts. Isolated PostgreSQL, frozen research and shared budgets remain enforced.
- Judge returned pass/high for three criteria on this tiny sample; this is not quality calibration.

### Fixed — v0.3 verification

- Tier 0 regressions always block; ordinal Judge severities and unavailable requested judgments
  retain their comparison meaning. Incomplete evaluation evidence is excluded from pass-rate denominators.
- Origin re-execution binds the original available model, prompt/schema/policy and generation
  parameters instead of using current routing; unavailable contracts fail closed.
- Versioned private capture/replay closures preserve authoritative inputs and reusable dependencies.
  Subject/call/operation identity is validated and promotion cannot overwrite origin provenance.
- Model/search/Judge deadlines bound admission and in-flight calls while retaining unknown usage
  reservations on cancellation; repeated annotation/Judge pairs no longer overweight a subject.
- Replaced eight redundant malformed-output cases with grounding, cross-group evidence, runtime
  duplicate/cycle/no-progress, search failure, CAS recovery and legacy capture compatibility risks.
  Added concurrent multi-trial workflow/agent capture-to-promotion-to-replay regression coverage.
- Exact UUID references remain intact when digit segments resemble phone numbers in PII filtering.
- Standalone installed Eval imports no longer depend on API import order.
- Immutable result guards distinguish JSONB null from SQL NULL, allowing first completion while
  rejecting later payload replacement. Operational traces retain only metadata and references.

### Fixed — Architecture audit boundaries

- Shared copy-only provider view closes Preparation base/selected Resume, metadata/label, and
  requirements PII bypasses; preserves domain content, business references and technical context.
  Preparation and Interview input/prompt identities now include the versioned privacy-view contract.
- Interview logical operation IDs link transport/schema/explicit-generation retry attempts. New
  Mock turns and Debrief group/overall artifacts store their accepted ModelCall FK; persistence
  validates successful status, owner run and operation before publishing a result.
- Backwards-compatible nullable migration preserves historical content without inventing unknown
  associations; concurrent accepted results and retry provenance have PostgreSQL regression tests.

### Verified — v0.2b bounded synthetic live smoke

- Real `gpt-6.1-sol`: Mock Quick completed 3 primary questions + 1 follow-up; single QuestionGroup,
  all three groups + independent Overall, and a synthetic Actual-source group Debrief passed.
- Ten calls, no retry/schema repair, 20,993 input / 7,418 output tokens (420 reasoning),
  2,169 cached-read / 18,794 cache-write tokens. Estimated cost USD 0.1120449; no remaining unknown
  reservations, provider billed cost unknown. No Tavily calls or functional changes needed.
- Observed bounded provider concurrency 3, out-of-order completion and incremental persisted results;
  stable Q1/Q2/Q3/Overall presentation, valid evidence refs, matching ledger/call totals and immutable
  Actual snapshot after a later source edit. No production proxy buffering or quality generalization.
- Post-smoke offline regression: 32 targeted tests passed in 11.40s; full suite 349 passed in
  58.22s. Ruff/formatter, strict mypy and staged/unstaged diff checks passed.


### Added / Changed — v0.2b Interview Loop

- Actual InterviewSession current-state Q&A intake: ordered stable primary/follow-up entries,
  same-session primary references, occurred_at, CAS content_revision, correction/replacement and
  legacy notes through the same mutation boundary. No per-edit immutable history or status changes.
- Separate frozen-context MockInterviewSession/Turn with explicit Resume selection, Quick/Standard/
  Long/Custom exact primary quotas, bounded follow-ups, immutable answers, idempotency receipts,
  explicit generation retry and persistent waiting states. No implicit Interview Prep generation.
- Standalone Debrief source snapshots/hashes from Actual or completed/early-ended Mock; independent
  none/single/all question analysis and overall target. Evidence-validated group/overall artifacts,
  deterministic source joins/display ordering and conservative grounded example answers.
- Bounded concurrent provider calls with isolated DB sessions, shared row-locked budget reservations,
  once-only settlement and metadata-only ModelCall/AgentStep/Observation. Unknown usage stays reserved;
  actual billed cost remains unknown. No duplicated parent/child charging.
- Post-commit incremental SSE delivery and durable event readback, finite transport/schema retries,
  independent partial failures and cancellation that preserves completed artifacts. No worker service.
- Three feature-local versioned PromptSpecs and explicit strong routing in career-model-policy-v3;
  existing preparation/planner contracts preserved. Interview-only live configuration does not require
  a Tavily key or expose research capability. Initial implementation acceptance was offline.
- Migration a841c3d12342 follows f730b2c01231, adds six interview workflow tables and backfills legacy
  InterviewSession revision/entries without losing notes. Downgrade/re-upgrade and drift verified.
- Offline acceptance: **32 new tests passed**; full suite **349 passed in 58.01s**, including real
  PostgreSQL migration/drift and existing real Typst cases. Ruff/format, strict mypy, offline locked
  install, wheel/sdist build and isolated wheel imports, Typst 0.15.1/font hashes and hygiene passed.
- Synthetic fixture acceptance establishes contract/runtime behavior, not real interview assessment
  quality. Live calibration, semantic evaluation and production recovery remain outside this work.


### Added / Changed — shared version governance before v0.2b

- Shared code-managed PromptSpec/Registry for all nine LLM tasks, with feature-local definitions,
  canonical contract hashes and pre-dispatch rejection of unregistered/mismatched metadata/schema.
- Unified prompt name/version/hash/schema/policy/provider/model/workflow ModelCall trace; explicit
  planning/replanning strong routing and safe diagnostics on successful planner responses.
- Action args/result schema versions, pinned action versions in new plans, strict plan/resume/
  dispatch checks; legacy unpinned pending actions remain readable but cannot silently execute.
- Search ToolCall input/output schema columns/API fields; nullable historical values preserved by
  migration `f730b2c01231`. Independent render-wrapper and validation implementation versions.
- Optional OpenAI cache-write usage retained through adapter/Usage/ModelCall, without inventing
  independent cache-write fees. Existing estimated/reserved/billed-cost semantics remain intact.
- Offline regressions cover metadata/schema/instruction mismatch, all task registrations, action
  compatibility, planner diagnostics, persisted tool schema versions and cache-write usage.
- Keep Planner's 8k input ceiling: trace-only metadata is excluded from the model input bound.
- Offline acceptance: **317 passed in 62.06s**, including real PostgreSQL empty-DB migration/drift
  and real Typst checks; targeted runtime/governance **66 passed in 20.14s**. Ruff/format (83 files),
  strict mypy (48 source files), offline locked install/build/wheel imports and package hygiene passed.
- No live calls, Mock Interview, Debrief, typed PlannerContext refactor or pricing snapshots added.

### Fixed — v0.2a resume state atomicity

- Apply resume bindings, scope and Gate approval to a deep candidate state; publish it only after
  validation and pending-plan calculation succeed. Rejected context leaves confirmed authorization
  unchanged and preserves an outstanding Gate decision.
- Regressions cover cross-profile/missing Resume rejection followed by a valid selection, and failed
  Gate approval validation followed by context repair and renewed explicit approval.
- Shared-budget review found no double counting: root/child accounting are separate projections;
  `generate`/`search` do not reserve or settle usage again.
- Offline acceptance: targeted runtime tests **39 passed in 21.36s**; full suite **274 passed in
  59.62s**, including empty PostgreSQL migration/drift. Ruff/format, strict mypy and diff checks passed.

### Added / Changed — v0.2a Runtime Core

- Bounded Goal Planner → deterministic PlanValidator → registered business actions → action
  observations → deterministic Evaluator, above the preserved v0.1d orchestrator.
- Typed versioned plans, exact user bindings, explicit scope/policy validation, finite dependency DAGs,
  no-progress stopping, limited replanning and canonical requested-target outcomes.
- Shared parent budget for planner/replan, child calls, unknown reservations, tools and active time;
  no new budget on resume. Provider-reported usage, estimates, reservations and billed-cost unknowns
  remain distinct. Internal model retry is not a replan or a Typst attempt.
- Root waiting-input/decision/completed/cancelled lifecycle; private goals, append-only plan/checkpoint
  revisions and CAS/idempotent explicit resume. Migration `e620a1b90120` adds control persistence,
  parent run links and action observations while preserving legacy workflow records.
- Agent create/query/plan/observation/resume APIs, committed-action reuse and resume-time fact/context/
  PDF checks. Explicit approval is required after Fit Gate; no automatic resume selection.
- Offline regression for multiple actions, illegal refs/actions/scope/dependencies, shared budgets,
  retry accounting, legal replan, wait/continue/cancel, no-progress, checkpoint conflicts, corrupted PDF,
  verified-fact changes, trace privacy and real Typst overflow → fake compression → real recompile.
- Existing preparation endpoints remain independently usable. No Mock Interview, Debrief, LLM judge,
  arbitrary execution tools, dynamic routing, distributed worker or production recovery was added.

### Verified — v0.2a local offline acceptance

- Full suite: **271 passed in 56.48s**, including 36 new runtime tests, empty PostgreSQL migration,
  Alembic drift and real Typst E2E. Ruff/formatter (78 Python files) and strict mypy (46 source files)
  passed. No external OpenAI/Tavily call was made.
- Clean temporary environment `uv sync --locked --offline`, offline wheel/sdist build, installed-wheel
  imports/template discovery, Typst 0.15.1 and pinned CJK font hash checks passed.
- Candidate-file scan found no keys, private artifacts, database/PDF/font binaries; `git diff --check`
  passed. Synthetic acceptance is not live planner or recruitment-quality verification.
- Action-boundary resume only: no in-flight replay, exactly-once, uncommitted transaction recovery,
  distributed worker or database/filesystem global atomicity. These limitations remain documented.

### Added / Changed — v0.1d Integration / E2E

- Arbitrary Fit/Tailoring/Greeting targets; explicit immutable resume selection and optional
  Tailoring→Greeting output binding. No automatic Fit/research paid prerequisite or latest selection.
- Deterministic Python target orchestration replaces the fixed LangGraph wrapper; unused graph/tracing
  dependencies removed. Compatible provenance-keyed target reuse and independent failures.
- Versioned opt-in must-have Fit Gate, needs-input/decision-required endings and canonical requested-target
  outcome shared by run/package/API. Migration `d4196a2f3011` preserves legacy records.
- Shared context validation, exact base/output revision provenance, PDF availability/hash checks,
  historical package context and Job/Application/Run discovery plus resume-choice hints.
- Offline target combination, gate/reuse/context/retrieval/failure E2E using real PostgreSQL/Typst;
  real overflowing PDF → fixture semantic compression → accepted real PDF. No paid calls or v0.2 work.


### Verified — v0.1d local offline acceptance

- Full suite: **235 passed in 34.46s**; real temporary PostgreSQL empty migration and Alembic drift,
  real pinned Typst compilation, target E2E and privacy/guardrail regression all passed.
- Ruff/formatter (**67 Python files**) and strict mypy (**38 source files**) passed.
- Offline lock/sync, clean temporary environment install, wheel/sdist and installed-package/template
  checks passed. Typst 0.15.1 and controlled Noto CJK font hashes verified; no binary assets packaged.
- Generic fixture smoke completed application and explicit interview workflows. No real OpenAI/Tavily
  call, no new paid acceptance, no commit/push and no v0.2 implementation.
- Public candidate-file hygiene and `git diff --check` passed. Synthetic integration acceptance does
  not establish real job-search quality or durable transaction/crash recovery.

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
- Public candidate-file hygiene and `git diff --check` passed. Remote v0.1c CI later passed (user confirmed).

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
  truth or general compression quality. Human review remains necessary. At that historical acceptance, v0.1d had not started.

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
