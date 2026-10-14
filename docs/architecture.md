# Career Agent architecture

Status: **v0.1a–v0.1d complete and locally verified**. Every capability below marked **planned** is not
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
- ToolCall: name/version, attempt/status, latency, estimated usage/cost and safe error code/retryability.
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
v0.1c maintains per-attempt and aggregate run usage. Unknown attempts retain separate budget/token reservations; ordinary usage/cost fields remain unknown.

Agent Observation is structured feedback for an executor; Operational Observability is timing,
usage/failure/control telemetry. They share call identifiers but are different responsibilities.
Neither is hidden chain-of-thought. Checkpoints are **planned**, distinct from traces and domain KB.

## Model boundary

`Domain Task → canonical TaskSpec + Pydantic schema → Gateway → Policy → Adapter`

The caller constructs `ModelRequestContext` with task_type, workflow, complexity, capabilities,
privacy class, remaining budget, output schema and max output tokens. The gateway never reads
an Agent State. `workflow`, `task_type`, and `requested_outputs` are not natural-language
intent classification. Intent routing is **optional future work**.

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

Model-family prompt overrides, additional real providers and judges are not implemented.

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
| v0.2b Interview Loop | Planned: Mock Interview / assisted Debrief; no distributed worker |
| v0.3 Harness / Evaluation / Safety | Planned: scenarios/golden/regression, replay, fault injection, deterministic + human + LLM evaluation |
| v0.4 Production Engineering | Planned: Ops dashboard, metrics, dynamic routing/budgets, concurrency/rate limits, circuits/fallback/control/cache |
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
for targeted follow-up; fixture mode still cleans its temporary database. Private reports/PDFs persist; it is a bounded acceptance script, not the planned v0.3 general harness.


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
