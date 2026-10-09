# Career Agent architecture

Status: **v0.1a Foundation implemented**. Every capability below marked **planned** is not
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
Future artifact records will reuse this contract; artifact entities/renderers are **planned**.

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
| v0.1b Resume Compiler | Planned: fact-backed Variant, Typst, one-page PDF, deterministic compression/validation |
| v0.1c Job Preparation Workflow | Planned: bounded research, fit, greeting, prep and minimal graph |
| v0.1d Integration / E2E | Planned: complete job-preparation path, failure cases, acceptance and v0.1.0 release |
| v0.2 Agent Runtime | Planned: bounded planner/executor/evaluator/replan, checkpoints/worker, mock/debrief |
| v0.3 Harness / Evaluation / Safety | Planned: scenarios/golden/regression, replay, fault injection, deterministic + human + LLM evaluation |
| v0.4 Production Engineering | Planned: Ops dashboard, metrics, dynamic routing/budgets, concurrency/rate limits, circuits/fallback/control/cache |
| v0.5 Real Usage Loop | Planned: actual outcomes, feedback, real bad cases, continuous regression |

Resume compilation will separate trusted facts, model-generated structured variants, deterministic
layout and validation. One-page failure must be explicit, never hidden clipping or invented facts.
Typst is planned as canonical renderer; optional DOCX export is not a v0.1a dependency.

Production control will scope action by dependency/tool/workflow, use windows/minimum samples,
cooldowns and recovery probes, and record policy decisions. One error does not pause the service.
Before real use, 1000+ posting tests are synthetic workload tests, not claimed production traffic.

Semantic retrieval may use pgvector if measured retrieval needs justify it; no vector extension
or embedding pipeline is installed now. Optional extensions are listed separately in TODO.md.
