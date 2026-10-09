# Career Agent architecture

Status: **v0.1a Foundation and v0.1b Resume Compiler implemented**. Every capability below marked **planned** is not
present in the executable application. This is an independent project and does not reuse an
unrelated RAG application's data or code.

## Product boundary

Primarily single-user job-search assistance. Before v0.4, real personal data may be used locally
for development, but load/regression demonstrations are synthetic. No claim of real multi-user
production traffic. Generating materials never means an application was sent; generated text
never promotes itself into verified personal knowledge.

Long-term lifecycle (planned beyond manual Foundation operations):

`Job Intake → Tracker → Research → Fit → Resume Tailoring → Greeting → Interview Prep → Mock → Debrief → Knowledge`

No automatic login/application/messaging, browser automation, multi-user SaaS, RBAC/payment,
email/calendar integration or mobile application is included in the committed roadmap.

## Module boundaries

- `domain`: pure lifecycle rules and Pydantic schemas; no database, LLM SDK or orchestration dependency.
- `application`: transactional use cases; calls domain rules and persistence. No model/provider names.
- `api`: explicit user operations, validated request/response models and safe errors.
- `infrastructure`: async SQLAlchemy/asyncpg, PostgreSQL entities, validated JSONB types.
- `models`: canonical request/task/output contracts, model registry entries, static policy, fake adapter.
- `runtime`: metadata contracts. Not a workflow engine, memory store or checkpoint layer.
- `security`: allowlisted events and basic redaction. Not a complete DLP solution.
- `resume`: structured variant schemas, deterministic grounding/content/layout validation, trusted Typst and private PDF storage.

A module can contain one useful file; empty abstractions and speculative services are avoided.
SQLAlchemy is used directly by services rather than wrapped in a generic repository framework.
A request owns one transaction. Mutations flush before responding and commit before response delivery.
HTTP and model errors expose stable codes, never database/provider error bodies.

## Persistence and domain semantics

All entity IDs are UUIDs and timestamps are timezone-aware UTC. Alembic migrations are explicit
and frozen; they do not import current ORM metadata to create/drop tables at execution time.
Database constraints validate enums, positive revisions/counters, foreign keys and uniqueness.
Pydantic validates structured JSONB at ORM write/read boundaries. Direct SQL is trusted
administrative access, not an untrusted API boundary.

### Personal knowledge

`PersonalProfile` is an append-only revision history of structured profile data. The latest
revision is current. A PostgreSQL transaction-scoped advisory lock serializes single-user writes,
including first insertion; clients supply the expected revision. This is not a distributed lock service.

`PersonalFact` starts `proposed`. Only the explicit verify API/service performs user confirmation.
The status means user-confirmed, not third-party certified. Verified content has no edit endpoint.
Replacement locks the original row, marks it `superseded`, and creates a **proposed** fact with
same lineage, next revision and `replaces_id`. The old content and verification time remain.
A unique replacement link prevents multiple direct successors. Rejected/superseded facts cannot
be verified again. Explicit rejection is available for proposed and verified facts.

`SourceDocument` stores opaque private-source references and optional hashes. File ingestion is
not implemented. `StarStory` stores validated situation/task/action/result data with fact IDs;
there is no STAR generation or public edit API yet. Profile/STAR content is not itself a substitute
for verified facts. JSONB fact references are not relational foreign keys; profile writes check
existence, while STAR semantic/reference validation belongs to its future write use case.

### Jobs and applications

`Company → JobPosting → JobRevision → JobRequirement` preserves JD history and requirement
provenance per revision. v0.1a accepts manual requirements; no LLM extraction is performed.
Names alone do not establish company identity; no name-based company merge occurs.

Each created job has one application in Foundation. Reapplication cycles are not exposed.
`ApplicationEvent` records creation, status changes, corrections and communication notes.
Every event increments the application revision and has a unique sequence. Row locks and
expected revisions prevent lost status updates. Notes append under the same lock.

Normal transitions:

- tracking → preparing, applied, withdrawn, closed
- preparing → applied, withdrawn, closed
- applied → interviewing, offer, rejected, withdrawn, closed
- interviewing → offer, rejected, withdrawn, closed
- offer → withdrawn, closed

Direct user-recorded application/offer allows omitted preparatory/interview steps. Terminal
states cannot progress normally. A correction may repair a prior state but requires a nonempty
reason and a distinct event; unchanged-state operations are rejected. No model/material path
can record `applied`. Fact confirmation and application mutations are local user API operations;
there is no authentication/authorization system in v0.1a.

### Interview knowledge

`InterviewSession` stores a round and append-only manual notes (validated JSONB).
`KnowledgeNote` optionally references a session or source. This is learning content, not an
automatically verified assertion about employment or achievements.

### Deletion and transactions

Business history references use `RESTRICT`: deleting a referenced company, job, application,
fact or source cannot silently remove audit history. Requirements are owned by their revision
and use `CASCADE`. Runtime run → step → call → observation ownership uses `CASCADE` to
support future retention cleanup. There are no public delete endpoints in Foundation.
A failed replacement or other multi-row mutation rolls back the entire request transaction.

## Runtime and version traceability

Persisted now: `AgentRun`, `AgentStep`, `ModelCall`, `ToolCall`, `Observation`.
Read API: run metadata and ordered/paginated steps. Calls/observations can be queried through
persistence; no execution or public runtime mutation endpoint exists.

- Run: workflow/version, requested outputs, status/timestamps, stop code, budget, consumed usage.
- Step: sequence, node/action, status, attempt, latency, structured reason code, versions.
- ModelCall: task, provider/model, attempts, usage/cost, latency, finish reason, schema result,
  safe error code/retryability and versions.
- ToolCall: name/version, attempt/status, latency and safe error code/retryability.
- Observation: exactly one model/tool call FK, status, opaque UUID data/evidence references,
  warning codes, error code and retryability.

VersionMetadata supports workflow, prompt, input/output schema, tool implementation,
model policy, provider/model, resume template and evaluator versions. Missing versions remain
null. No fabricated prompt/tool versions are generated. No prompt registry, rollout or A/B system.
Resume artifact records extend this contract with variant-schema, layout-policy and compiler/font
metadata. Unused model/workflow versions remain null; the compiler does not fabricate Agent calls.

Runtime metadata fields reject paths/free-text errors at the ORM boundary. Metadata identifiers
must still be authored by trusted application code; regex validation is not complete PII detection.
There are no prompt/response/JD/resume/reasoning body columns in runtime tables. Version and
usage JSON are validated. Unknown usage/cost is null, never automatically reported as zero.
Run aggregates are a storage contract only; no executing runtime currently maintains them.

Agent Observation is structured feedback for an executor; Operational Observability is timing,
usage/failure/control telemetry. They share call identifiers but are different responsibilities.
Neither is hidden chain-of-thought. Checkpoints are **planned**, distinct from traces and domain KB.

## Model boundary

`Domain Task → canonical TaskSpec + Pydantic schema → Gateway → Policy → Adapter`

The caller constructs `ModelRequestContext` with task_type, workflow, complexity, capabilities,
privacy class, remaining budget, output schema and max output tokens. The gateway never reads
an Agent State. `workflow`, `task_type`, and future `requested_outputs` are not natural-language
intent classification. Intent routing is **optional future work**.

Registry entries contain tier/capabilities/privacy eligibility and price metadata; adapters are
injected by provider identifier. Static task policy chooses a tier, promotes high-complexity cheap
tasks to strong, filters capability/privacy eligibility and chooses deterministically within a tier.
It never silently upgrades to premium. Missing eligible candidates fail explicitly.

Foundation budget admission checks the requested output-token allowance and known output
cost floor. It is **not full tokenization, input-cost reservation or hard runtime budget enforcement**.
Only the injected fake adapter exists, with explicit synthetic output and zero actual billed tokens/cost.
Real adapter token estimation, timeout/retry accounting and reservation are future runtime work.
Fake output is validated against the caller's canonical schema. Raw adapter exceptions become
`provider_error`; validation failures become `invalid_model_output`. Results contain actual selected
provider/model, usage, latency, attempts, finish/schema status, estimated cost and nullable versions.
No workflow/prompt/schema version is invented for fake calls.

Model-family prompt overrides, additional real providers and judges are not implemented.

## Privacy boundary

Public repository: synthetic/sanitized `tests/fixtures` only. Private resume/JD/notes/artifacts
belong under external `CAREER_AGENT_DATA_DIR`. Optional `.private` is entirely ignored.
The database, Docker volume, backups and future checkpoints are private, not just source files.
Secrets belong in ignored `.env`; `.env.example` includes only local-development placeholders.
No external tracing is enabled; CI has no real data or provider secret.

Operational logs use enum events/codes, UUID and numeric latency only. Basic redaction handles
common email/phone/path/credential forms but cannot recognize every name or private fact.
Validation errors omit original inputs; unexpected exceptions are caught before ASGI error logging.
Documented Uvicorn startup disables access logs. SQL echo is off and bound parameters are hidden.
Model task content remains in memory and is not automatically persisted to traces.

Manual JD is stored as data, never interpreted as instructions in Foundation. External web tools,
SSRF protection, prompt injection evaluation and capability enforcement at a tool gateway are
**planned** with their implementing milestones. There is no shell/browser/web execution tool now.

## Planned architecture and roadmap

The long-term modular monolith adds a thin LangGraph workflow layer:
`Goal → Planner/Router → Shared State → Executor → Tool → Observation → Evaluator → continue/replan/finish`.
Domain services remain independent of the orchestrator. No general unbounded loop or multi-agent
system is present in Foundation.

| Milestone | Status / purpose |
| --- | --- |
| v0.1a Foundation | Implemented: domain, persistence, APIs, runtime/model/privacy/testing contracts |
| v0.1b Resume Compiler | Implemented: hand-authored Variant, grounding, Typst, one-page PDF, deterministic compression/validation |
| v0.1c Job Preparation Workflow | Planned: bounded research, fit, greeting, prep and minimal graph |
| v0.1d Integration / E2E | Planned: complete job-preparation path, failure cases, acceptance and v0.1.0 release |
| v0.2 Agent Runtime | Planned: bounded planner/executor/evaluator/replan, checkpoints/worker, mock/debrief |
| v0.3 Harness / Evaluation / Safety | Planned: scenarios/golden/regression, replay, fault injection, deterministic + human + LLM evaluation |
| v0.4 Production Engineering | Planned: Ops dashboard, metrics, dynamic routing/budgets, concurrency/rate limits, circuits/fallback/control/cache |
| v0.5 Real Usage Loop | Planned: actual outcomes, feedback, real bad cases, continuous regression |

Resume compilation now separates verified fact references, hand-authored structured variants,
deterministic layout and validation. Model-based variant generation remains **planned for v0.1c**.
Typst is the canonical renderer; DOCX and other templates remain optional future work.

Production control will scope action by dependency/tool/workflow, use windows/minimum samples,
cooldowns and recovery probes, and record policy decisions. One error does not pause the service.
Before real use, 1000+ posting tests are synthetic workload tests, not claimed production traffic.

Semantic retrieval may use pgvector if measured retrieval needs justify it; no vector extension
or embedding pipeline is installed now. Optional extensions are listed separately in TODO.md.


## Resume Compiler: implemented v0.1b

### Boundary and data flow

`Structured ResumeVariant → Grounding → Content policy → trusted Typst → PDF inspection → RenderArtifact`

The compiler does not decide what a job calls for, extract semantic requirements, generate
prompts, call a model, or perform semantic tailoring. It only validates an already structured
input, selects from its full/short/optional content, renders, validates and persists the outcome.
All content fixtures are synthetic; there is no v0.1c workflow implementation.

### Variant and input snapshots

`ResumeVariant` is a stable ID with a current revision counter. `ResumeVariantRevision` contains
validated JSONB for `ResumeDocument` and `InputSnapshot`, plus profile/JD foreign keys.
The document holds its schema/template/page contract, metadata label, exact profile ID/revision,
optional exact JobRevision ID, section IDs/order/priority/required flags and factual items.
Every bullet/summary/entry needs fact references; predefined structural headings do not.
Duplicate IDs/section names, unsupported types, bad priorities, arbitrary template/output fields,
and empty fact-reference lists are rejected. No arbitrary heading can be used to bypass grounding.

A profile snapshot's eligible fact IDs are the existing `fact_ids` of its education, experience
and project entries. This deliberately reuses Foundation semantics instead of adding a new
ownership/membership model to PersonalFact. Variant creation captures those IDs/revisions and
the profile display name. Standalone skill strings are not independently verified facts: link
supporting facts through a profile entry before referencing them in a resume.

Variant revisions are append-only; expected revisions and row locks serialize edits. A PostgreSQL
trigger also rejects UPDATEs to saved revision rows. Old revisions remain addressable through
`GET ...?revision=N`. Render requires the revision explicitly, never an ambiguous current head.

### Grounding baseline and limits

The render operation reloads current facts and locks them until artifact transaction commit.
All referenced facts must exist, be verified, belong to the exact profile snapshot, and match the
captured fact revision. Proposed, superseded and rejected facts fail, even if they were previously
verified when the Variant was stored. Existing historical artifacts are not retroactively modified.
Requirement references must belong to the document's exact JobRevision. A current JD revision
cannot silently replace a previously selected revision.

Numeric/date-like tokens in both full and short text must occur in supporting fact statements.
Explicit hard-claim declarations (organization/title/degree/date/number) must cite an item fact,
match its statement and occur in the full item text. This is conservative token/substring
consistency, not semantic entailment. Undeclared named entities, contradictory wording,
contribution inflation and subtle distortions remain beyond this baseline. An author-supplied
short form can change meaning even if its references and numbers pass; human review is required.
The name header comes from the exact Profile snapshot, not an invented fact or model output.

### Deterministic policy

Content ordering uses section/item `ordering` with UUID tie-breakers. Original content is tried
first. If the only finding is layout overflow:

1. Switch all provided short forms, recording decisions in ascending priority/order/UUID order.
2. Remove the lowest-priority optional bullet; then optional entries/summaries, with stable
   section priority/order and UUID tie-breakers. Remove an empty optional section.
3. Repeat within an eight-compile hard cap. If still needed, the final round removes all remaining
   optional content in that same order and tests the required-content floor.
4. If required content cannot fit, return `layout_failed`, retaining the actual multi-page count
   and overflow findings but **no accepted/downloadable PDF**.

Required items are never removed, even inside an optional section. A required section heading
is retained; required items may use their explicitly supplied, grounding-checked short forms.
Spacing, margins and font sizes do not change. Eight rounds is a bounded incremental alternative
to the suggested three major rounds; the acceptance fixture fits in three. This policy is not an
optimizer for best visual density. Decisions, selected IDs and canonical selection hashes are
stored per attempt, allowing repeated selections/layout validation to be compared.

### Trusted rendering and fonts

Only the repository-maintained `resume_zh_cn_a4_single_v1.typ` template is executed. The renderer captures its
bytes once per run and records that exact SHA-256; all attempts use that snapshot. Content is
serialized as canonical UTF-8 JSON and inserted through Typst `text`, never eval, source interpolation,
include, import or an executable template supplied by the caller. No API field chooses an output
path, executable, font path or template path. An isolated temporary root contains only the trusted
template, JSON, verified font snapshots and generated PDF. Temporary compilation files are cleaned on success/failure.

Typst 0.15.1 is preflight-checked; actual compiler version is recorded. Every subprocess has a
15-second default timeout (operator-configurable, capped at 60 seconds) and no shell invocation.
The subprocess environment removes user Typst font/package environment settings. The trusted
template imports no packages or network resources. Raw diagnostics are discarded, leaving only
stable codes, so private paths/content do not enter API responses or runtime logs.

The canonical locale is `zh-CN`, using `lang: "zh", region: "CN"` and Chinese headings.
Schema `resume-v2` fixes this single locale/template contract; no dynamic multi-locale system exists.
Font policy `noto-sans-cjk-sc-2.004-regular-bold-v1` pins official Noto Sans CJK SC 2.004
Regular/Bold OTF files to commit `523d033d6cb47f4a80c58a35753646f5c3608a78` and fixed SHA-256
values in `resume/fonts.py`. The official SIL OFL license is fetched and checked by the same setup.
The operator cache is outside the repo, configured through `CAREER_AGENT_FONT_DIR`, never API input.
`setup_resume_fonts.py` downloads and verifies before atomic publication; `--check` is offline.
Local/CI share this mechanism. Missing/hash-mismatched dependencies fail explicitly without fallback.
Each render freezes verified font bytes, copies only those files into its temporary directory,
and passes an explicit font path with both system and embedded font discovery disabled.
The trusted template disables fallback. Font/PDF binaries never enter git or wheel output.
English templates and bilingual/multi-locale support remain future work, not Chinese support.

Fixed layout: A4, exactly one accepted page, one column, 18 mm horizontal / 16 mm vertical margins,
10.5 pt body, 12 pt headings, 20 pt name and fixed line/section spacing. Full page output is compiled;
no page-selection, clipping, hiding or scaling trick is used to manufacture a one-page result.
A fixed 5.25 pt right content gutter accommodates CJK punctuation advance boxes without relaxing
bounds validation. Vector bullets avoid bullet/middle-dot glyph-to-Unicode collisions, and
bullet continuation lines use a fixed hanging indent. Punctuation overhang is disabled.

### PDF inspection and artifact persistence

pdfplumber opens the actual PDF and checks nonempty extractable text, exactly one A4 page,
all retained text occurrences (including required content), character bounds against the content
area, minimum text size, expected font family and known extraction/glyph-failure indicators.
Text matching normalizes Unicode (NFKC) and whitespace once, then searches ordered, non-overlapping
index ranges in that immutable string: name, then each heading and its items in render order.
The cursor only advances; matched text is never deleted or concatenated. Duplicate items require
separate occurrences. Compatibility-equivalent characters/layout whitespace are intentionally
not distinguished; this remains a content-retention check, not a semantic validator.
Chinese/mixed-script fixtures test actual extraction and CJK font names. CID/replacement glyph
checks remain necessary even when Typst exits successfully with no warnings.
A multi-page PDF is inspected in full before content compression, so missing text cannot be
misclassified as harmless overflow. No OCR is used. Automatic checks do not guarantee perfect
visual layout; both successful acceptance PDFs were visually inspected separately.

`RenderArtifact` references `(resume_variant_id, resume_variant_revision)` through a composite
foreign key. It stores an opaque artifact UUID, SHA-256 and validated report JSONB containing
render/validation statuses, actual page count, findings, attempts and version metadata. The report
extends Foundation VersionMetadata with locale, variant schema, layout policy, compiler,
font policy version, actual font family, verified file hashes and template hash. Database checks prevent a successful artifact without a file/hash and passed
one-page validation. No speculative prompt or workflow version is recorded.

The compiler sets accepted only after PDF validation, successful byte read and SHA-256 calculation.
Read/hash/temporary-directory cleanup failures return failed with no content or success hash.
Private-store hashing happens before file creation; a store failure clears accepted/file metadata.
The API exposes accepted only after the file and exact-revision metadata transaction succeed.
A passed PDF validation may coexist with a failed render when later I/O fails; clients use render_status.

Accepted files use UUID-derived paths under `CAREER_AGENT_DATA_DIR/artifacts`, restrictive file
permissions, exclusive creation and symlink checks. The response exposes only an opaque ref, not
an absolute path. Download rechecks SHA-256 and refuses failed or corrupted artifacts. Failed
renders still persist a report and return HTTP 201 (created render result), but have no file ref;
clients must inspect `report.render_status`. Normal request rollback removes newly written files.
Database/filesystem commits are not globally atomic: a process crash could leave an unreferenced
private file; reconciliation is future maintenance work, not a false successful API artifact.

Tests use real temporary PostgreSQL databases and temporary artifact directories, cleaned at
session end. The manual synthetic-example command intentionally retains its three accepted PDFs
and four reports in a caller-selected private directory for review. No PDF/font binary belongs
in the public repository.
