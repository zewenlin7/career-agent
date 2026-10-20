# Career Agent architecture

Status: **v0.1–v0.2 and v0.3 offline foundation complete and locally verified**. Every capability below marked **planned** is not
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
- `models`: canonical request/task/output contracts, model registry entries, static policy, fake and OpenAI Responses adapters.
- `preparation`: target-driven deterministic orchestration, task prompts/schemas, guardrails, research and budgets.
- `runtime`: metadata plus v0.2a bounded control engine, validated plans and action-boundary checkpoints.
  Business rules remain in the v0.1d preparation orchestrator.
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
provenance per revision. v0.1a accepts manual requirements; v0.1c appends validated extracted requirements with exact JD evidence and extraction metadata. Existing referenced rows are never silently rewritten.
Names alone do not establish company identity; no name-based company merge occurs. An optional
existing company_id with matching company_name explicitly reuses a Company across new jobs.

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
persistence; explicit fixed workflow APIs now create runs. There is no generic runtime mutation API.

- Run: workflow/version, requested outputs, status/timestamps, stop code, budget, consumed usage.
- Step: sequence, node/action, status, attempt, latency, structured reason code, versions.
- ModelCall: task, provider/model, attempts, usage/cost, latency, finish reason, schema result,
  safe error code/retryability and versions.
- ToolCall: name/version, input/output schema versions, attempt/status, latency, estimated usage/cost
  and safe error code/retryability.
- Observation: exactly one model/tool call FK, status, opaque UUID data/evidence references,
  warning codes, error code and retryability.

VersionMetadata supports workflow, prompt, input/output schema, tool implementation,
model policy, provider/model, resume template and evaluator versions. Missing versions remain
null for historical/unused fields. Active model calls require the shared code-managed PromptRegistry
contract described below. No hosted prompt service, rollout or A/B system.
Resume artifact records extend this contract with variant-schema, layout-policy and compiler/font
metadata. Unused model/workflow versions remain null; the compiler does not fabricate Agent calls.

Runtime metadata fields reject paths/free-text errors at the ORM boundary. Metadata identifiers
must still be authored by trusted application code; regex validation is not complete PII detection.
There are no prompt/response/JD/resume/reasoning body columns in runtime tables. Version and
usage JSON are validated. Unknown usage/cost is null, never automatically reported as zero.
v0.1c maintains per-attempt and aggregate run usage. Unknown attempts retain separate budget/token reservations; ordinary usage/cost fields remain unknown.

Agent Observation is structured feedback for an executor; Operational Observability is timing,
usage/failure/control telemetry. They share call identifiers but are different responsibilities.
Neither is hidden chain-of-thought. v0.2a action-boundary checkpoints are distinct from traces and domain KB.

## Model boundary

`Domain Task → canonical TaskSpec + Pydantic schema → Gateway → Policy → Adapter`

The caller constructs `ModelRequestContext` with task_type, workflow, complexity, capabilities,
privacy class, remaining budget, output schema and max output tokens. The gateway never reads
an Agent State. `workflow`, `task_type`, and `requested_outputs` are not natural-language
intent classification. v0.2a uses a constrained goal Planner; arbitrary intent/action routing remains excluded.

Registry entries contain tier/capabilities/privacy eligibility and price metadata; adapters are
injected by provider identifier. Static task policy chooses a tier, promotes high-complexity cheap
tasks to strong, filters capability/privacy eligibility and chooses deterministically within a tier.
It never silently upgrades to premium. Missing eligible candidates fail explicitly.

Gateway admission checks capabilities/privacy and the requested output allowance/cost floor.
The v0.1c caller additionally reserves a conservative UTF-8 input bound (including canonical schema
and envelope allowance), max output tokens and configured cost before **every** network attempt.
Input contexts above 80,000 bytes plus schema/envelope are rejected. Actual known usage reconciles
the reservation; unknown usage retains separate `budget_reserved_usd` and reserved token bounds. This is static admission,
not provider billing reconciliation or production control. Configured prices must track selected
models; the API has no price guarantee.
OpenAI Responses uses native Pydantic structured output and `store=False`; no model tools are sent.
SDK retries are disabled so workflow attempt accounting owns transport retries and schema repair.
Fake and HTTP-mocked adapters exercise the same canonical contracts offline. All requested real
API task cases passed bounded synthetic acceptance; this does not establish real job-search quality.

Model-family prompt overrides and additional real providers remain unimplemented. v0.3 adds an explicit
quality Judge runner through the same Gateway, currently verified with offline fixtures only.

## Privacy boundary

Public repository: synthetic/sanitized `tests/fixtures` only. Private resume/JD/notes/artifacts
belong under external `CAREER_AGENT_DATA_DIR`. Optional `.private` is entirely ignored.
The database, Docker volume, backups and checkpoints are private, not just source files.
Secrets belong in ignored `.env`; `.env.example` includes only local-development placeholders.
No external tracing is enabled; CI has no real data or provider secret.

Operational logs use enum events/codes, UUID and numeric latency only. Basic redaction handles
common email/phone/path/credential forms but cannot recognize every name or private fact.
Validation errors omit original inputs; unexpected exceptions are caught before ASGI error logging.
Documented Uvicorn startup disables access logs. SQL echo is off and bound parameters are hidden.
Model task content remains in memory and is not automatically persisted to traces.

JD and research evidence are untrusted external data. The only web adapter calls a fixed Tavily
endpoint with a validated search query. Returned URLs are evidence, never fetched or executed.
No shell, SQL, arbitrary HTTP, browser or filesystem tool is available to a model. Injection fixtures
exercise the structural boundary; this does not certify universal model resistance to injection.

## Planned architecture and roadmap

The long-term modular monolith adds a thin LangGraph workflow layer:
`Goal → Planner/Router → Shared State → Executor → Tool → Observation → Evaluator → continue/replan/finish`.
Domain services remain independent of the orchestrator. No general unbounded loop or multi-agent
system is present in Foundation.

| Milestone | Status / purpose |
| --- | --- |
| v0.1a Foundation | Implemented: domain, persistence, APIs, runtime/model/privacy/testing contracts |
| v0.1b Resume Compiler | Implemented: hand-authored Variant, grounding, Typst, one-page PDF, deterministic compression/validation |
| v0.1c Job Preparation Workflow | Completed locally: two fixed workflows, providers, guardrails, budgets and bounded live acceptance |
| v0.1d Integration / E2E | Completed locally: target-driven deterministic orchestration, context integrity, retrieval closure and offline E2E |
| v0.2a Runtime Core | Bounded planner/validator/executor/evaluator, shared budgets, explicit checkpoint resume |
| v0.2b Interview Loop | Actual intake, text Mock, standalone snapshot Debrief; offline acceptance |
| v0.3 Evaluation Foundation | Current: frozen cases/trials/operations, offline replay, sampling/Judge, calibration/capture and priority comparison |
| v0.4 Production Engineering | Phase 1: approved routing, in-process admission/circuits, attempt bounds and output control. Later: Ops, automatic policies, distributed coordination/cache |
| v0.5 Real Usage Loop | Planned: actual outcomes, feedback, real bad cases, continuous regression |

Resume compilation now separates verified fact references, hand-authored structured variants,
deterministic layout and validation. v0.1c adds structured model generation before the unchanged compiler boundary; bounded synthetic live acceptance passed.
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
All content fixtures are synthetic. The preparation layer generates Variant data without changing this compiler boundary.

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

## v0.1d deterministic preparation layer

Two explicit product workflows remain, with finite Python orchestration in `preparation/orchestrator.py`.
The previous LangGraph wrapper and unused dependencies were removed: no dynamic planner, model-selected
edges, checkpointer or worker is required for this bounded target graph. Task execution/guardrails/budgets
stay in `workflows.py`; shared exact context validation lives in `context.py`. No external tracing SDK runs.

`WorkflowRequest.targets` is any nonempty subset of Fit/Tailoring/Greeting. Exact Profile and JD form
common context. Existing valid Requirements are reused or extracted once. Research is optional fresh
same-company/mode context only; no hidden Tavily or synthesis prerequisite. Fit is independently requested
or explicitly authorized by `fit_gate=gate_downstream`; it is never a default dependency of the other two.
Tailoring consumes an explicit base ResumeVariantRevision ID and appends a revision; Greeting consumes
an explicit chosen revision or the explicit `output_of(resume_tailoring)` edge. Missing bindings stop
before paid work, without any automatic latest/original selection. The deterministic schedule orders
independent nodes consistently, but failure only blocks dependent nodes. Eligible layout failure permits
one semantic compression call and a second compiler invocation; existing deterministic compression stays.

`TargetArtifact` is validated private JSONB in existing PreparationArtifact storage, not a new generic
artifact platform. It records source resume ID, output/render refs and a deterministic compatibility hash
(exact profile/JD/requirements/fact status, mode, prompt hash, resume binding, and actually used research).
Interview keys also hash selected notes/stories. Compatible completed targets are revalidated and reused
without duplicate calls. Legacy Fit can also be reused when exact package context, prompt hash, verified-fact timestamps
and current references prove compatibility; other legacy outputs lacking binding provenance stay readable. Invalid cached PDFs fail explicitly. Concurrent duplicate requests are not an exactly-once guarantee.

`ContextLoader` validates current consumption: exact immutable Profile/JD, owned requirement refs/evidence,
same-company research, Fit refs/coverage, current verified facts against the resume's stored snapshot,
exact Variant→Render linkage and file hash. Explicit selected bases can originate from another Job while
retaining their own valid requirement refs; generated output binds the requested JD. Interview consumes an
explicit existing package and its exact accepted resume, rechecking the same boundaries. Stale historical
research is warned about, not refreshed. Historical GET returns original context even if facts were later
superseded; historical retrieval is deliberately different from new generation eligibility.

`fit_gate_policy_v1` counts only must-have requirements: explicit_gap >= 2 OR >=50% gives low_fit;
otherwise no_evidence >=50% gives insufficient_evidence; otherwise pass (including zero must-haves).
Matched/partial do not contribute a score, and absence of evidence is not inability. On a gate decision,
unexecuted targets stay pending and the run ends `decision_required`; an explicit new request may continue
using existing results. The standalone v0.1d API remains terminal per request; the v0.2a wrapper maps
these outcomes to waiting states and adds action-boundary checkpoints.

`WorkflowOutcome` is the sole terminal calculation, persisted on AgentRun and in the PreparationPackage,
and returned by API. Requested target statuses are completed/failed/blocked/pending; intermediate success
cannot promote failed to partial. Overall completed means all requested targets completed; partial requires
at least one requested completion and at least one failed/blocked; otherwise execution failure is failed.
Needs-input and decision-required are separate terminal states. AgentRun's existing `succeeded` maps to
canonical `completed`; the embedded outcome remains identical. Migration `d4196a2f3011` adds nullable
validated outcome JSONB and the new status/check/width, preserving old runs. Legacy packages may lack outcome.

Discovery endpoints expose Job/Application packages, Run final package, historical package context and
resume choices with hints. Task outputs link through target artifacts; intermediates remain state refs,
not requested outputs. No Application status/event is changed by generating materials. Known limits remain:
synchronous transaction rollback on uncaught exceptions and non-global DB/filesystem atomicity, with no
worker/recovery implementation. Offline E2E uses synthetic API inputs, fake models, fixture research, real
PostgreSQL and real Typst, including missing/corrupt PDFs and real overflow/semantic compression/recompile.

The seven task types are extraction, research synthesis, fit, tailoring, compression, greeting and
interview preparation, using the full identifiers in `TaskType`. Transport retry and schema repair
keep task_type and increment the attempt ordinal. Semantic compression is a new task type, at most
one network attempt (no hidden retry). Typst compilation attempts remain only in render reports.
ModelCall rows represent individual network attempts; `attempts` is an ordinal, not a multiplier
when aggregating usage. `prompt_version`, SHA-256, schema versions and policy version are recorded
per attempt. No private prompt/input/output/reasoning text is stored in runtime tables.

OpenAI is the only live model adapter. Cheap extraction and strong other tasks are configurable
composition-root mappings. Premium is absent from the executable registry even if its reserved
configuration flag is set. Canonical schemas and prompts do not branch by model family. An explicit
capability requirement gates structured outputs. Prompts are Python specs in the repository, not
hosted prompt services, with allowlisted input blocks and schema/version hashes.

The retained research executor/ResearchAdapter normalizes Fixture/Tavily into ResearchEvidence.
The v0.1d target orchestrator only loads existing research; it never calls this search/refresh path. Tavily always uses basic depth,
max five results, no raw-page fetch or built-in generated answer. Each attempt consumes one of
at most two slots. The second query runs only when the first fails or provides less than 60 snippet
characters. This sufficiency threshold is deliberately simple, not semantic evidence scoring.
CompanyResearch stores immutable numbered report/evidence snapshots, source URLs, retrieved time,
expiry, mode, conclusions, unknowns and explicit inference. Freshness defaults to 168 hours.
A company row lock serializes cache refresh/version allocation; no distributed infrastructure.
Different Company IDs never share cache solely because their names match.

PreparationArtifact stores Pydantic-validated private fit/greeting/interview/package/target JSONB. A kind
validator enforces the matching output schema. Its run/profile/exact-JD foreign keys RESTRICT
history deletion; referenced runs cannot be cascade-deleted until artifacts are handled. Report
references inside JSONB are application-validated, not general relational foreign keys. The v0.1c
migration added these two tables, optional extraction metadata and tool usage JSONB. No existing
fact-verification or resume revision/font/template semantics are changed.

Input limits bound JD size, verified fact count (stable first 60), optional selected notes/stories,
context bytes, calls/searches and estimated USD/tokens. Profile contact/preferences are excluded;
common name/email/phone forms are minimized in selected prose. This is a baseline, not complete DLP.
Tailoring receives a fixed layout budget; factual items and short forms pass existing v0.1b grounding
before revision persistence/render. Compression preserves identity, section/item IDs and retained
reference sets, required content, numbers and explicitly protected fields. Greeting checks refs and
numbers; fit requires exact requirement coverage, distinguishes unknown from explicit confirmed
gaps, and has no score/probability field. Interview answers are short outlines with validated refs.
Reference/numeric checks cannot establish complete semantic truth, prevent all undeclared named
entity hallucinations, or detect subtle responsibility inflation; human review remains required.

Each synchronous HTTP request owns its database transaction, including network waits. Normal
budget/provider/validation failure commits available partial results and metadata. A process crash
can lose the uncommitted child run and its billing trace. v0.2a preserves a parent dispatch reservation,
but does not recover in-flight calls or claim durable crash recovery.
PDF/DB commits remain non-atomic globally, with the existing normal rollback cleanup and planned
orphan reconciliation. Live smoke uses an isolated synthetic database, now retained with its generated database_ref
for targeted follow-up; fixture mode still cleans its temporary database. Private reports/PDFs persist; it is a bounded acceptance script, separate from the v0.3 frozen evaluation harness.


Structured-output failure diagnostics use the native SDK raw-response wrapper to read allowlisted
response metadata and usage before invoking the same native Pydantic parser. No free-form JSON
fallback or output schema weakening is introduced. Incomplete/refusal, malformed structured output,
canonical validation and business guardrail failures are separate categories. ModelCall version
metadata contains bounded safe diagnostics alongside prompt/hash/schema versions; business failures
retain their specific stop code with `output_guardrail_failed` in AgentStep version metadata.
Validation locations use schema property names or redacted unknown-field markers. Messages are
fixed whitelist values; validation inputs, custom message interpolation, refusal text and raw bodies
never enter diagnostic persistence. The first failed live response did not retain these diagnostics
or a response ID (`store=False`), so its exact validation cause cannot be recovered retrospectively.


### Model request timeout policy (implemented)

`ModelTimeoutPolicy` is injected at the provider composition boundary. Settings supply the
60-second default and per-task overrides (Interview Prep: 120 seconds); no prompt, model name,
output schema or workflow edge selects the timeout. External content cannot override it.
The adapter passes the effective timeout per request to the SDK/HTTP transport. It is independent
of model-call counts and token/cost admission, and is not a total workflow duration budget.
Timeout diagnostics record only policy version, effective seconds and a whitelisted transport
phase. `provider_timeout` remains stable; missing response/model/usage are not fabricated.


Final v0.1c review retains one general smoke entry using the real workflow implementation.
One-off recovery scripts bound to historical run IDs/budgets and duplicated direct-provider
compression code were removed from the public source tree. Private acceptance records remain
outside git. All requested live tasks passed across separate attempts; final offline checks
passed without new live calls. v0.1d adds offline integration acceptance only; no new live quality claim.


Cost accounting separates provider-reported usage, price-table `estimated_cost` (USD),
`budget_reserved_usd`, and nullable `actual_billed_cost_usd`. ModelCall's searchable cost column
is only the estimated cost projection, null for unknown-usage failures. Run admission includes
estimated + reserved cost and reported + reserved tokens; reserve bounds never masquerade as
provider usage. Tavily dispatch counts are observed, credits/free-credit coverage are unknown;
USD 0.008 is a configured PAYG-equivalent retail estimate. No billing integrations/admin key.
Historical pre-fix private summaries retain their earlier combined semantics; docs label their
cumulative amounts as conservative budget consumption, not expenses or reported usage.


v0.1d local acceptance: 235 offline tests passed, including empty real PostgreSQL migration and
Alembic drift; Ruff/format, strict mypy, offline dependency installation, wheel/sdist inspection,
Typst 0.15.1 and pinned-font hash preflight passed. The generic fixture smoke completed both
explicit workflows. No external model/search call was made for this milestone. These are synthetic
integration checks, not evidence of real job-search quality or production crash recovery.


## v0.2a bounded runtime

The runtime adds orchestration above, rather than replacing, `preparation.Orchestrator`. It owns
user-authorized goals, accepted plan revisions, control checkpoints and cumulative budgets. Domain
artifacts remain the authoritative business results. Existing preparation APIs run independently.

Planner input contains only goal, explicit IDs, compatible-artifact summaries, allowed actions,
progress/previous observation, authorization and remaining budget. No full JD, resume, research or
historical trace is included. Planner discovery conservatively summarizes compatible Fit/Tailoring
artifacts; richer Greeting/Interview reuse stays in the existing business context loader. The prompt is versioned/hashed; a conservative UTF-8 byte bound including
prompt and output schema enforces the 8k input ceiling. Context is intentionally compact (4–6k target,
not padding or a token-count guarantee). `PlanProposal` cannot execute until `validate_plan` produces
`ExecutablePlan`. Validation checks registry names, typed arguments, exact bindings, scope, evidence,
legal output dependencies, unique targets, cycles, max 4 actions and dependency depth 3.

Registry entries declare version, args/result schemas, private-domain-write side effects,
explicit-scope permission, timeout, no action retry, checkpoint/reuse idempotency and shared-budget
class. Only preparation and explicit interview preparation are exposed. Models, search and compiler
remain internal; there is no arbitrary shell/Python/SQL/filesystem/HTTP tool.

`AgentState` / `AgentProgress` contain refs, immutable original scope, current allowed subset, exact
bindings, action/target progress, child package/run/artifact refs, phases, revisions and accumulated
usage. Goal prose is stored in a separate private `AgentGoal`, never copied into operational trace or
checkpoint state. `AgentPlan`, `AgentCheckpoint` and resume receipts are private control persistence,
not business artifact revisions. The migration adds parent run links, action step/transition metadata,
action observations and distinct root waiting/completed/cancelled statuses without changing legacy
workflow outcomes.

An action executes the existing deterministic orchestrator. Model-call success is distinct from
business success: an invalid referenced fact can yield a successful ModelCall and a failed action
observation. Deterministic Evaluator uses target progress, observation, legal remaining dependencies,
waiting conditions, limits and no-progress detection; it never calls a judge. Root steps are planner,
business dispatch and evaluator decisions. Internal child nodes retain their existing separate steps;
model attempts, semantic compression and Typst rounds remain separate counters.

A root ledger controls planner/replan plus all child model/search reservations and usage. Child
limits are scoped to remaining resources; parent and child usage are projections, not additive totals.
Reservations for unknown usage remain distinct from usage-derived estimates and unknown actual billed
cost. Tool invocations count compiler operations and search attempts; individual deterministic Typst
rounds remain in RenderReport. Defaults/hard limits are documented in README and RuntimeLimits.
Waiting time does not count toward active execution time. No adaptive routing/control policy is added.

Plans/checkpoints append revisions. A row lock and expected checkpoint revision serialize explicit
resume; `(run_id, request_id)` receipts prevent duplicate dispatch and reject payload reuse conflicts.
A dispatch checkpoint conservatively reserves the remaining token/cost allocation before starting.
The whole business action, child artifacts, usage, action observation and next checkpoint then commit
in one database transaction. Completed actions are never replayed after normal checkpoint resume.
Unexpected in-flight failure leaves a non-resumable dispatch checkpoint with its conservative
reservation; it does not claim exact consumed usage or actual billing. No automatic recovery is promised.

Resume validates facts, exact context, permissions and completed artifacts including PDF hashes.
Missing binding yields `waiting_input`; Fit Gate yields `waiting_decision`, with no terminal outcome.
Explicit user continuation permits the original gated context to proceed; the planner cannot grant
that approval. User updates can fill missing bindings or select authorized targets within original
scope, never change existing exact bindings, budget or immutable gate policy. A new plan revision
retains completed targets and cumulative budgets. Replan is capped at 2, total business actions at 8;
repeated terminal targets or repeated equivalent plans stop as `no_progress`. Provider retry/schema
repair is internal to a child and consumes the same ledger, not a replan. Compression remains capped.

Checkpoint recovery covers committed action boundaries, waiting input/decision and normal process
restart. It does not cover in-flight paid calls, unknown side effects, exactly-once, uncommitted
transactions, filesystem/database atomicity, distributed workers or production crash recovery.
Synchronous validation/finalization is not preemptively interrupted at a wall-clock deadline.
All acceptance is synthetic/offline; no claim is made about live planner or job-search quality.


## Shared version governance (before v0.2b)

`models/prompts.py` defines shared PromptSpec and a small PromptRegistry. Definitions remain local
in preparation/prompts.py and runtime/prompts.py; future features can register their own specs.
All seven preparation tasks and goal_planning/goal_replanning resolve through this contract. The
latter share name/version/hash, not duplicated instructions. Registry identities reject conflicting
contracts for the same name/version. `prompt-sha256-v1` canonical sorted UTF-8 JSON hashes prompt
name/version, instruction, stable input contract/schema version, and complete output JSON schema/
version. Private request payloads and task routing labels are excluded. Preparation `_v3` and
`goal-planner-v2` explicitly identify the new contract/hash boundary. No typed PlannerContext
refactor is included: its compact input shape remains a versioned descriptor.

TaskSpec and ModelRequestContext both carry prompt name/version/hash and input/output schema
versions. Gateway validates both against the registered spec, checks instruction and canonical
output schema identity, then generates trace metadata including policy/provider/model/workflow.
Unknown task → `unregistered_prompt_task`; inconsistency → `prompt_contract_mismatch`, before
provider dispatch. Both preparation and planning use the same trace builder, including failed
attempt metadata and safe success diagnostics. `career-model-policy-v2` explicitly maps planning
and replanning to strong; current cheap/strong model selection is unchanged.

ActionSpec requires explicit args/result schema versions as well as action version. A PlanAction
pins the registered version before it becomes executable; `agent-plan-v2` records this contract.
Validation, resume of outstanding actions and dispatch require exact version equality. Old plans
and checkpoints can still be read; missing/incompatible action versions are rejected, never
inferred from today's Registry. Completed actions remain provenance. Action semantics/schema
changes require a version bump; no compatibility rollout platform is implemented.

Search ToolCall stores input/output schema versions alongside tool name/version. Migration
`f730b2c01231` follows `e620a1b90120`; new columns are nullable to preserve historical unknowns.
AgentStep records action name/version and args/result schema versions. These are distinct from
underlying tools. RenderReport records explicit render-wrapper and validation implementation
versions independently of template/font/layout/actual Typst versions. Historical reports do not
receive invented implementation versions. No generic Tool/Action/Prompt/Model mega-registry.

OpenAI adapter preserves optional provider `cache_write_tokens` through Usage and ModelCall JSONB.
Absent is null, not zero; cached read, total input/output and reasoning counters remain unchanged.
No independent write surcharge is inferred: current estimation is non-cached input × input rate +
cached input × cached rate + output × output rate. A write-specific tariff/inclusion relationship
would require a reliable provider pricing contract before changing arithmetic. This update does not
claim invoice accuracy, add pricing snapshots, aggregate cache metrics, or automate cache policy.
The existing unknown-usage reservation and actual-billed-cost-null boundaries remain unchanged.

Acceptance uses fake providers, HTTP mocks and real local PostgreSQL/Typst only. It verifies metadata
and execution boundaries, not real model quality. The Interview Loop below adds three registered tasks.


## v0.2b Interview Loop

`interview/actual.py` owns deterministic current-state intake. InterviewSession keeps Application,
round name, occurrence time, legacy notes, ordered validated JSONB QA and positive content_revision.
Row locking + expected_revision CAS applies to every update including notes; there is no selectable
per-edit content history. Full entry replacement supports corrections/deletion and validates unique
IDs/orders plus same-session primary-only parent links. It never marks an application applied.

MockInterviewSession/Turn are separate records. A session freezes existing exact domain context
via v0.1 ContextLoader/grounding (Profile revision/fact revision map/JD/explicit Resume, optional
existing InterviewPreparation). No missing-context generation or automatic Resume selection.
The deterministic scheduler chooses legal next kind and exact target progress; one shared strong
`mock_interview_turn_generation` prompt generates only the question. Immutable answer acceptance,
receipt/idempotency hash and generation admission are committed together after input preflight.
Generation then runs outside that transaction; failure retains answer and ready state. Waiting
state has no time expiry, and only active calls count toward execution time. Retry is explicit and
uses the same cumulative attempt quota. Context/policy JSON is frozen at session creation.

DebriefRun stores immutable SourceSnapshot, source hash, policy and one authoritative ledger.
Snapshot includes ordered actual/mock entries, notes, source schema/revision, exact optional domain
context. DebriefArtifact stores each independent group's/overall's validated output and status;
DebriefEvent is a durable ordered business event log. A QuestionGroup joins primary+follow-ups.
`interview_group_debrief` sees that group; `interview_overall_debrief` sees the authoritative source
without group analyses. Both are strong tasks registered through feature-local PromptSpec and the
shared registry; career-model-policy-v3 explicitly maps all three to strong without premium fallback.
Evidence is validated against answered entries in the correct snapshot/group.
Example answers use only a conservative verbatim verified-fact composition. Unknown semantics and
quality still require human review; this is not an evaluator ground-truth mechanism.

A fixed-size async worker pool is local to the request, not a durable/background worker service.
Each provider attempt uses independent short DB sessions for reservation/settlement; concurrent
workers never share AsyncSession. The owner row lock serializes ledger writes and event sequence.
ModelCall/AgentStep/Observation reuse existing metadata contracts. Every attempt reserves once,
settles once; parent AgentRun usage mirrors owner usage and is never re-added. Unknown costs stay
reserved; billed cost remains null. Cache-write usage is not separately guessed or double-charged.
Time admission reserves maximum call duration, then records elapsed duration; concurrent durations
are summed conservatively, while user waiting time is excluded. Actual and Mock have independent
per-group/overall safety profiles, and all oversized input is rejected without truncation.

SSE execution emits completed only after schema/evidence/privacy validation and the artifact/event
transaction commits. Persistent events support reconnect/readback; reconnect does not restart the
run. Overall has bottom display order even when it finishes first. Transport/schema repair retains
task identity and consumes budget. Exhaustion leaves a failed artifact, never semantic fallback.
Aggregate outcome is derived from artifact success/failure, allowing independent partial results.
Closing the iterator cancels local workers and preserves completed artifacts; no hidden work is
promised. Crash/in-flight request recovery, exactly-once, DB/filesystem atomicity and automated
cleanup/reconciliation remain outside this milestone.

The v0.2a engine, PlanValidator, two business Action Registry entries, v0.1d target orchestrator and
Resume Compiler remain intact. Interview endpoints are explicit standalone workflows; a Planner
cannot invoke them via invented actions. There is no Mock/Actual transcript parser, LLM summary,
judge, scores, automatic knowledge verification, dynamic routing/concurrency or cache controller.


Subsequent bounded synthetic live verification exercised the existing OpenAI path without changing
these contracts: 3-primary/1-follow-up Quick, single group, concurrent all+overall, and Actual group.
Observed peak concurrency was 3; groups completed Q3/Q2/Q1 before Overall, while retrieval retained
source order. Cached-read/write metadata reached trace, and cost/usage projections equalled call
sums without duplicate settlement. All reservations cleared. This verifies a small synthetic path,
not broad semantic quality, live failure recovery or production network/proxy SSE buffering.


### Audit boundary fixes

`security/model_view.py` creates copied provider-facing data, stripping Resume metadata and contact
fields and minimizing known personal identity/contact spans without altering stored domain records.
Preparation applies it centrally before constructing every TaskSpec, including base Resume,
Greeting/Interview Prep variants and requirements. Frozen Interview context shares the same policy.
Prompt input contracts hash `model_view_version`; output schemas and grounding remain unchanged.
The deterministic patterns cannot recognize every possible PII phrase and do not claim complete DLP.

Interview generation allocates a logical operation before its first attempt. Mock retains it after
failed generation and clears it only when a turn is accepted; each Debrief group/overall owns a
separate operation. Owner row locks serialize attempt allocation and budget mutation; the DB uniquely
constrains `(logical_operation_id, attempts)`. Accepted artifact persistence verifies call success,
matching run and operation, then stores its unique RESTRICT FK in the artifact transaction. SSE
completion remains after commit. The calls API exposes operation refs, never prompt/transcript bodies.
Existing rows have nullable provenance: historical unknown links are not guessed. This does not add
in-flight recovery, exactly-once execution or atomic provider/database transactions.


## v0.3 evaluation boundaries

`models/inputs.py` validates code-managed prompt block names/types/size/trust/privacy before dispatch.
Feature-local prompts supply their contracts; unknown or incompatible inputs fail without provider cost.
Compatibility policy distinguishes historical readability from current execution eligibility. Missing
source/schema/validator/grounding/render metadata denies reuse, while pricing and monitoring do not
invalidate artifacts. Frozen Debrief regeneration appends results and updates selection separately.

`evaluation/contracts.py` and private persistence separate Case (problem), CandidateConfig (implementation),
Run, Trial and OperationInvocationSnapshot. Candidate code/content hashes plus prompt/schema/action/model
policy/settings detect drift. Immutable DB payload triggers protect case/suite/candidate/capture identities.
Workflow/Agent replay reconstructs domain state in a newly migrated disposable PostgreSQL DB; component
model replay uses frozen provider-facing input. Frozen clock and exact-query observations replace ambient
external state. Adapter faults affect production retry behavior, with injected-fault provenance separated
from real errors. Authoritative production validators still decide grounding, references and permissions.

Root/trial budget ledgers are projections, not additive expenses. Model/search reservations use a shared
lock and settle once per ledger; provider concurrency never shares a SQLAlchemy Session. Static workers
are in-request coroutines, not durable background processes. Cancellation/crash reconciliation remains
unsupported; committed results survive but in-flight work has no exactly-once guarantee.

SamplingDecision (including not-sampled) is separate from pending/completed/failed JudgeEvaluation.
Stable hashes govern ordinary sampling; forced samples remain a separate population. Evaluation-origin
calls do not recursively sample. Explicit Judge drain uses the existing Gateway and separate budget;
CLI/API currently default to fixture adapters. Criterion labels/confidence/evidence are stored even on
pass; deterministic severity aggregation is not a numeric capability score. Human annotations are blind,
append-only and separate from feedback. Calibration reports separate random and targeted populations.

Private operation/capture tables contain inputs for forensic replay; ordinary ModelCall/step traces do
not. Captures have one frozen payload plus append-only triggers. Promotion requires explicit triage and
review, sanitization, repo-safe validation and invariant expectations; it never writes raw data to Git.
Comparisons retain per-check tiers and trial distributions, report incompatible/insufficient evidence,
and prohibit lower-priority gains from masking blocking regressions. Operation differences provide
attribution context only, not causal proof. Synthetic offline acceptance does not validate real quality.

Verified locally for v0.3: 444 offline tests, real PostgreSQL/Typst, migration/drift/history upgrades,
Ruff/formatter/strict mypy and offline packaging. Real Judge calibration and live quality claims remain
unverified. Temporary replay PDFs are cleaned; exact compiler reports, revision bindings and hashes
are retained in private operation snapshots. Unavailable origin code/model/contracts fail explicitly.

### v0.3 correctness audit corrections

Comparison treats every Tier 0 pass-to-fail transition as blocking, regardless of the optional
materiality annotation. Judge checks retain ordinal category evidence, so minor-to-major changes
are not lost as binary fail-to-fail ties. Requested but pending/running/failed/cancelled judgments
remain explicit coverage gaps; not-sampled is a separate state. Incomplete quality evidence cannot
silently produce a passing quality conclusion; deterministic correctness is reported separately.

Origin re-execution is fail-closed: supported origin prompt/schema identities, policy and generation
parameters must be available, and the gateway is restricted to the exact origin model. The current
candidate router cannot substitute another model. Unsupported historical execution configurations
remain unavailable rather than being approximated.

Private captured sources use `captured-source-v1` and `captured-replay-v1`. Frozen authoritative rows
are restored only inside the disposable replay database, through an explicit domain-table allowlist
and the existing database/JSON contracts. Promotion deterministically converts the source; old
captures missing required inputs are incompatible. Planner captures include validation evidence refs.
Accepted-call captures validate subject/task/operation/artifact identity and derive payload provenance
from the authoritative invocation. Promotion can add notes, not replace origin identity.

The frozen closure includes compatible Research/Fit/Resume dependencies and exact artifact bytes
inside the private capture boundary. Replay restores these only into its temporary store; preserving
the original request mode preserves cache identity, while injected fixture adapters still prohibit
network access. Missing dependencies fail closed. Sanitization removes private PDF bytes, so a
public workflow case that still requires those bytes is incompatible rather than silently rerendered.
Planner continuation captures remain usable for component diagnostics; they cannot be promoted as
a fresh goal replay without the required continuation contract. Initial-goal captures support the
workflow/agent promotion and concurrent replay integration path.

Model and frozen-search admission share an evaluation deadline; in-flight awaits are bounded by its
remaining time. Judge drain honors its configured execution ceiling. Deadline/cancellation retains
unknown usage reservations rather than asserting zero cost, and cannot authorize another attempt.

Calibration uses `latest-pair-per-subject-stratum-v1`: within population/task/JudgeSpec/model/criterion,
select the latest annotation and judgment pair per subject (timestamp then ID as stable tie-break).
All pair details remain available, but repeated annotations/judgments do not multiply a subject's
weight in that stratum. Reports include unique subject count. This selection is not adjudication.

Paid evaluation is opt-in dependency injection, not a consequence of application live mode.
EvalRunner requires an explicit OpenAI Gateway, `allow_paid_models=True` and enabled live settings.
Its frozen CandidateConfig uses the injected registry/policy/prompts; default API/CLI still use fixtures.
The workflow sandbox receives the same explicit permission but retains disposable databases, private
temporary artifacts, frozen search and cleared local credentials. JudgeRunner uses its existing
injected Gateway boundary. Minimal synthetic live acceptance verified six calls; one blind synthetic
annotation only validates linkage and selection, not empirical Judge calibration.

## v0.4 Phase 1 — Runtime Control Core

The existing feature executors still own transport retry and schema repair. Gateway performs one
provider attempt; SDK retries remain disabled. Mock explicit retry and resume semantic compression
keep their existing boundaries. Each registered task now has an approved, versioned candidate set
in the existing ModelPolicy. Unknown tasks fail closed. Priorities are ordered integers (lower first),
not scores. Additional routes require explicit role/qualification configuration; defaults do not
silently add premium/fallback routes.

The shared attempt boundary is:

`Prompt/input validation → candidate eligibility → tentative capacity lease → authoritative financial
reservation → bound attempt trace → adapter dispatch → capacity and financial settlement → canonical
output validation`.

`AttemptSelection` binds the operation/attempt, route, qualification, traffic class, lease, policy
versions, output limits and deadline. Pricing, trace and dispatch consume that selection; trace does
not route again. Candidate pricing is copied at selection. Dispatch rechecks circuit and newly observed capacity debt/feedback
after asynchronous financial reservation; a revoked tentative lease is refunded without a provider attempt.
Admission rejection is a control decision,
not a provider failure. Ordered decisions are retained on step/call or private invocation metadata.
Existing JSON metadata contracts are extended additively; no controller tables or migration are needed.

### Process ownership and capacity

Live composition injects a process-owned Controller per non-secret `quota_scope`; gateways remain
request scoped. Configure the scope to reflect a shared provider project/account. Multiple server
processes and independent CLI processes do **not** coordinate exact quotas. Controller state is
in-memory and is not restored after restart.

A short threading lock checks provider RPM/TPM and route RPM/TPM/concurrency together, then creates a
tentative lease. The lock never spans network I/O, sleeping or a database operation. The default
headroom factor is 0.90. Background/evaluation admission has a static 0.50 fraction ceiling, protecting
capacity for interactive/normal traffic; dispatched work is never preempted. This is not a scheduler.

Capacity and money remain different ledgers. Capacity reserves input upper bound plus the governed
output estimate (default 512), whereas financial budgets reserve the allowed hard output ceiling.
Dispatch consumes RPM once; settlement replaces the token estimate with reported actual usage.
Under-reservation creates capacity debt and an observation, not a task failure. Unknown usage retains
conservative capacity until the rolling window expires and conservative financial reservation under
the existing accounting rules. Provider usage is observed, price-based cost is estimated, invoices
remain unknown. Tentative cancellation releases capacity; post-dispatch cancellation keeps unknown
usage. Settlement is idempotent.

### Health, retries and completion

Availability health observes each real timeout/connection/5xx attempt, with rolling thresholds,
open cooldown and bounded half-open probes. Business/schema/grounding rejection, budget denial and
admission denial do not poison provider health. 401/403/configuration errors disable the route within
this process instead of transient recovery. Typed allowlisted 429 feedback constrains capacity without
retaining raw headers or erasing outstanding reservations; missing quota data is not inferred.

Timeout classification is settled at the attempt boundary. Native provider request timeouts retain
stable error code `provider_timeout` and normalized `attempt_outcome=provider_request_timeout`;
these affect breaker health. In-flight operation/run deadline expiry uses
`operation_deadline_exceeded`, and external cancellation uses `execution_cancelled`; both are neutral.
Interview/Runtime pass their remaining time into the boundary rather than wrapping and relabeling
an already-settled attempt. Cancellation cleanup shields only the final Interview ledger/trace/state
transactions, then propagates cancellation; it does not shield continued model execution.

Normalized feedback carries a trusted quota scope and bucket (`route`, `provider_shared`, or
`shared_group`). Unknown sharing defaults to route-local. Operator `feedback_buckets` maps exact
routes to explicitly shared buckets; headers cannot set this identity. Bucket feedback includes its
own in-flight reservations and subsequent consumption. Provider-wide buckets constrain all provider
routes; a shared group constrains its configured members. One bucket cannot replenish another.
Mismatched quota/bucket identity is ignored; missing raw quota information is never invented.
The control policy/implementation identities are `runtime-control-v2` / `attempt-controller-v2`.

Each retry re-enters admission. Per-route attempts, total operation attempts and route switches are
bounded; schema repair consumes that same total. Admission waits, retry waits and provider execution
share the original operation deadline, capped by the caller’s remaining runtime/Eval/Judge execution budget. Committed Interview retry attempts seed new request gateways,
so explicit retry cannot regain a fresh attempt quota. Restored operation time uses persisted active
execution duration, excluding time waiting for the user. This is not controller crash reconstruction.

Output estimate is independent of the hard generation limit. All current tasks remain complete-only:
hard-limit/incomplete output fails closed, even if some JSON can be parsed. No partial JSON salvage
or new degraded feature is implemented. Service-disposition/output-policy contracts keep future
versioned opt-in partial artifacts and degradation separate; correctness/privacy/grounding are never
negotiable. Routing/health changes do not invalidate historical business artifacts; reuse continues
to use the independent compatibility policy.

### Evaluation isolation

CandidateConfig freezes approved candidates, qualifications, priorities, output limits, headroom,
retry/amplification and breaker/controller identities. Each offline trial receives its own controller,
a controllable frozen clock and a versioned synthetic ControlScenario. Explicit real-model Eval
and Judge composition instead shares the injected live quota controller with evaluation traffic
protection. Real-model Eval rejects synthetic fault/control scenarios so they cannot poison live
health state. Adapter dispatch remains
provider-specific. Observed selections/decisions/outcomes belong to operation provenance, not mutable
candidate configuration. Private invocation snapshots retain the control configuration for origin
analysis; operational metadata contains versions/refs and decisions, never bodies.

Exact origin re-execution is supported for reconstructible first-attempt primary routes. Missing
historical control contracts, unavailable implementations and origins requiring unrecorded prior
fallback/probe state fail with `origin_config_unavailable`; they never silently use current routing.
Original output and trace remain readable. Live controller state is never imported into offline replay.
Paid origin diagnostics additionally require the existing shared control policy and evaluation traffic
classification; they cannot elevate diagnostic traffic priority to reproduce an old user request.

Phase 2 extends this core with the recovery/control backend below. Dashboard/UI, distributed
coordination, durable queues, response caching and generalized partial salvage remain outside this implementation. No paid provider fault probes are part of offline acceptance.


## v0.4 Phase 2: durable control and operational facts

The controller retains its short synchronous admission/settlement lock. `DurableControl` adds an
independent session factory and a separate asynchronous journal serialization boundary. It never
locks a business budget-owner row or creates a journal FK to an uncommitted AgentRun/Step/ModelCall.
No DB I/O, network call or sleep occurs inside the controller's lock.

Live composition obtains one owner per database/quota scope. A dedicated PostgreSQL session advisory
lock rejects a second owner. Requests borrow that process owner; Judge and explicitly live Eval
Gateway wrappers retain it. Offline fixtures and sandbox trials have isolated controllers and never
bootstrap the production owner. Startup is ownership → validated event replay → unsettled-attempt
classification → effective controls → readiness. Failure closes admission.

`ControllerState` is a replaceable projection. `ControlEvent` is append-only and stores version,
input window, ordered reason/decision metadata, before/after revision and a UTC state image. The latest
event can reconstruct a missing/stale projection. `AttemptJournal` fixes attempt/operation/selection,
owner refs and conservative reservation before dispatch; mutable result/link fields are separate from
that immutable identity. `RecoveryIncident` records unresolved evidence and operator decisions.
None of these tables stores model-facing bodies.

Transitions: reserved → dispatch_intent → settled → business_committed; reserved cancellation becomes
not_dispatched. A restart at dispatch_intent becomes unknown, even if the network might not yet have
been reached. This ambiguity is intentional. Successful ModelCall is checked for terminal status,
route/task/operation identity, and committed private invocation or Judge result before linkage.
`business_committed` means outcome evidence was found, not that every enclosing workflow succeeded;
an artifact ref is optional and only taken from committed evidence. Missing evidence stays an incident.
Normal tick linkage does not label a still-running business transaction as a recovery failure.

Unknown/known-but-uncommitted recovered attempts block reuse of their budget owner until evidence is
reconciled. They never create a new full budget. Unknown token/cost estimates remain reservations,
not billed cost. Window expiry releases capacity uncertainty only. Reconciliation is metadata/ledger
work, not checkpoint replay or hidden provider retry. No lost result body is fabricated.

Snapshots persist UTC timestamps/expiries, generation and revision. Restore converts UTC into the new
process monotonic epoch. Backward clock movement cannot prematurely expire quota debt; long downtime
can expire quota windows but cannot forgive financial uncertainty. OPEN/disabled routes are restored;
in-flight HALF_OPEN probes restart OPEN, with bounded probes reacquired normally. Transient semaphore
slots are rebuilt while uncertain token/window debt remains conservative. Kill flags and TTL overrides
are separate state; global control events are durable independently of a route's local projection.

Base policy remains versioned and immutable. `AutomaticPolicy` drives a bounded process-local tick
using a recent observation window and reliable current capacity pressure. Only pressure/concurrency,
output reservation estimate and future-subject Judge rate can change. Hard output/financial bounds,
candidate approvals/priorities and security never change. Active manual overrides suppress automatic
adjustment; safety/kill switches dominate both. Effective state is validated on a copy and published
after CAS/event commit. The API exposes request-ID idempotency, revisions and override expiry.

Sampling inherits the effective rate/revision associated with the producing call. Existing decisions
are returned unchanged by their stable subject/policy key; forced and random populations remain
separate and evaluation-origin calls never recurse into sampling. Pending Judge work still requires
explicit drain; the control tick is not a Judge worker.

Ops projections use attempt journal rows once per attempt. Unknown dispatch intents are separated
from confirmed attempts; unknown cost is never a zero-valued observation. Parent/child run projections
are counted as their own populations, never summed into attempt spend. Events/results returned through
Ops omit snapshots, prompts, private invocations, transcript and raw provider errors. Local operator
access requires an environment token; this is not a multi-user authorization system.

Eval CandidateConfig freezes recovery/control algorithms, bounds and base sampling policy. Each trial
uses a fresh controller, frozen UTC/monotonic scenario, optional persisted initial image, and deterministic
pre-execution restart/operator events. State transitions are invocation provenance; they do not mutate
the candidate manifest. Origin re-execution fails closed for effective-control contracts it cannot
reconstruct exactly. Existing historical artifacts remain readable and their reuse compatibility is
not invalidated by ordinary control-state changes.

Known limits: single owner per quota scope, no distributed reconciliation/exactly-once guarantee,
no provider outcome lookup, no automatic replay or unknown-spend waiver, no production worker/UI.
A changed persisted base-policy identity requires an explicit administrative migration. Event retention
and larger operational-load optimization are deferred; private artifact/DB commits are still not globally atomic.

Phase 2 audit fixes: global control publication and bootstrap serialize across local owners; global
writes additionally require expected_global_revision. Local rollback cannot restore stale global state.
Dispatch rechecks effective RPM/concurrency without preempting dispatched calls. Business transactions
register commit/rollback acknowledgements; rollback immediately schedules independent journal protection,
and subsequent prepare/dispatch waits for that protection before admitting the same budget owner.
Acknowledgement persistence failure closes admission. This is not automatic replay or a durable worker.
Eval uses the candidate automatic policy; legacy explicit scenario policies must match, and persisted
initial state must match the base/automatic policy hash. Ops separates deduplicated admission decisions,
automatic adjustments and lifecycle events, and reports window versus all-time outstanding uncertainty.
Sampling begins at configured base/per-task rates; prior SamplingDecision records remain unchanged.
