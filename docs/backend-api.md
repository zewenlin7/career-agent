# Backend API usage and compatibility

This guide retains caller-facing endpoint semantics and examples moved out of the project README.
It is not a second schema registry: FastAPI OpenAPI and the linked request/response schemas define
exact fields. All endpoints below use `/api/v1`; the Web BFF permits only its explicit subset.
Local/private deployment is required. Historical readability does not authorize new execution.

## Core resources and request identity

| Endpoints | Caller contract |
| --- | --- |
| `GET /health` | Process liveness; its legacy milestone label is not the current project stage |
| `GET/PUT /profile` | Low-level exact Profile snapshots; Product uses named Profile editing instead |
| `POST/GET /jobs`, `GET /jobs/{id}` | Job/JD resources and nullable active Application projection |
| `GET /job-create-requests/{id}` | Original Job/Application identity and current workspace availability |
| `POST /jobs/{id}/revisions` | Legacy revision writer; Product uses Application-scoped JD editing |
| `GET/PATCH/DELETE /applications/{id}` | Read/update current state; closed-only logical deletion |
| `PUT /applications/{id}/jd` | Atomic JD revision and default binding CAS |
| `POST /applications/{id}/notes`, `PATCH/DELETE /applications/{id}/entries/{id}` | User note/event overlays with request identity and revision checks |
| `GET/POST/PATCH/DELETE /knowledge-notes[/{id}]` | Explicit note CRUD; scope and CAS remain server-enforced |
| `GET /runs/{id}`, `/steps`, `/calls` | Existing metadata; no execution |

The Job request UUID identifies intent, not content deduplication. Same UUID/payload returns the
original Job; different payload conflicts. Modern Product requires it, legacy direct callers may
omit it and retain non-idempotent creation. Company selection/reuse is separate: explicit ID/name
must match; otherwise only a unique exact trimmed-name match is reused, with ambiguity rejected.
Application status changes do not imply a material Submission. Compatibility aliases map preparing
to tracking and withdrawn to closed; closed Applications may reopen before deletion.

Detailed transaction/lock, receipt retention, deleted-result replay and archive semantics have one
implementation reference in [Application lifecycle](architecture.md#application-closeout-create-identity-and-deleted-owner-reachability).
Browser persistence/recovery is in [the frontend contract](../frontend/README.md#application-closeout-request-and-reachability-contracts).

Errors use `{"error":{"code":"..."}}`: 422 validation, 404 absent object, 409 revision/identity/state
conflict, 500 internal failure; deleted Debrief exact targets use 410. Values/private paths/provider
bodies are not reflected. A 201 creates a resource; it is not proof of successful generated content.
Many collections use limit/offset (limit 1–100); consult each schema instead of assuming one universal
page shape. Modern discovery returns items/limit/offset/has_more; offset pages can shift on inserts.
Legacy direct Profile initial payload example:

```json
{"expected_revision":0,"data":{"display_name":"Synthetic Candidate","skills":["Python"]}}
```

The old standalone Fact-create example is retired: Product does not expose Fact review/create as a
prerequisite. Internal historical evidence and canonical source checks remain; use the source-aware
Profile/Resume workspace APIs for new Product content.

## Canonical Resume and artifact API

- `POST /api/v1/resume-variants`: store a structured draft, not a model generation request.
- `GET /api/v1/resume-variants/{id}?revision=N`: retrieve an exact revision; defaults to latest.
- `POST /api/v1/resume-variants/{id}/revisions`: `{expected_revision, document}`; old revision immutable.
- `POST /api/v1/resume-variants/{id}/render`: `{revision: N}`; exact revision is mandatory.
- `GET /api/v1/artifacts/{id}`: status, findings, selection decisions, attempts and versions.
- `GET /api/v1/artifacts/{id}/download`: accepted artifacts only, verified SHA-256, `no-store`.

These low-level canonical endpoints retain factual-reference validation. Product uses the source-aware workspace resolve/save path instead of asking users to maintain Fact links. For direct canonical API clients, use the synthetic fixture `document` as a payload shape, but replace its fixture IDs with actual
existing exact Profile/evidence IDs. New Product content should use the workspace source-resolution path, not construct or confirm Facts through HTTP. Supply `profile_id` and `profile_revision` for low-level historical canonical inputs.
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

The compiler renders the explicitly selected presentation once and returns no accepted PDF on
failure. It does not substitute short expressions or delete optional items on overflow. Product
compression requires an explicit action, returns an editing proposal and requires user save.
The low-level preparation workflow retains its separately bounded semantic-compression branch;
it is not an implicit model call from the Product PDF button.

The current contract is `locale=zh-CN`, schema `resume-v2`, template
`resume_zh_cn_a4_single_v1`, layout policy `content-v3`, and font policy
`noto-sans-cjk-sc-2.004-regular-bold-v1`. Reports retain these versions, actual font family,
verified font-file hashes, compiler version and template hash; never local absolute font paths.
Retained text uses ordered, non-overlapping ranges in immutable normalized extraction, so matching
cannot manufacture text by deleting headings. Accepted status requires validated PDF bytes and
computed SHA-256; subsequent storage failure clears success/file metadata and persists a failed report.
The PDF hash checks file integrity; byte-identical PDFs are not the regression criterion.
Matching selections, decisions, page count and validation results are the determinism contract.

## Preparation workflow APIs

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

`POST /api/v1/workflows/prepare_interview` remains separate and explicit. Supply exact profile/JD and the explicitly selected `resume_revision_id`; the legacy
`application_package_id` branch still consumes its accepted exact Resume/PDF. Product defaults to no
research and sends that choice explicitly; lower-level input defaults differ. Optional selected
STAR stories/knowledge notes remain bounded compatibility inputs. It never runs implicitly or refreshes research.

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

## Bounded Agent API

`Goal → Planner → deterministic PlanValidator → business action → Observation → deterministic Evaluator`

The planner proposes typed targets, exact bindings and dependency edges. It cannot authorize new
refs, change scope/budgets, bypass Fit Gate, verify facts or execute arbitrary code. Registered actions
are only `prepare_application` and `prepare_interview`; they delegate to the existing v0.1d
orchestrator. Its explicit resume selection, reuse, grounding, compiler and target outcomes remain intact.
The fixture planner is a small deterministic router for offline testing, not a quality claim about
natural-language understanding. Live mode uses the existing gateway. Historical validation scope is recorded in CHANGELOG.

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

Default limits, shared parent/child accounting, checkpoint compatibility and action-boundary
resume are specified in [bounded runtime](architecture.md#v02a-bounded-runtime). This Agent action
checkpoint is not a general mechanism for replaying an unknown in-flight provider request. Mock,
Draft and Debrief accepted-output recovery have their own evidence-based contracts.

## Interview and Debrief APIs

| Capability | Entry points and durable identity |
| --- | --- |
| Actual intake | `POST interviews`, `GET/PATCH interviews/{id}`, entries/notes; atomic create identity, content revision CAS, stable entry UUID and parent |
| Mock | `POST mock-interviews`, `GET .../{id}`, `POST .../{answers,generate,end,recover}`; create identity, expected_revision, request_id, pending_question_id for answers |
| Debrief | `POST interview-debriefs`, `GET .../{id}?historical=true`, `DELETE .../{id}`, `POST .../{id}/{execute,retry}`, `GET .../{id}/events?after=N` |

Mock creation freezes exact context; Product also sends Application ownership. Legacy missing ownership
is resolved only from reliable frozen relationships, never by a display name or Job guess. All modes
use the same model ask/finish decision and hard quota/parent checks. Accepted answers are immutable;
a failed next decision does not erase an answer or consume a persisted-turn slot. Retry and unknown
recovery differ. Full rules, versions and old-output compatibility are in
[Interview input/lifecycle](architecture.md#interview-workspace-input-and-lifecycle-update).

Quick/Standard/Long fix `primary_target`/`followup_max` to 3/1, 5/3 and 8/5 respectively.
Custom accepts 1–8 primaries and 0–5 follow-ups, with follow-ups no greater than the primary target.
These are persisted question caps, distinct from the cumulative call-attempt budget; failures do not
consume a question slot but do consume applicable execution budget. A generated final primary must
still be answered before normal completion. Waiting for an answer has no execution-time deadline.

Debrief request fields include `source_kind=actual|mock`, `interview_id`, `expected_source_revision`,
`question_analysis=none|single|selected|all`, `primary_entry_ids` (selected), legacy `primary_entry_id`
(single), `overall_analysis`, and `request_id`. Only primary IDs of the exact source are accepted;
a nonempty distinct set is normalized to snapshot order. Groups include their follow-ups; overall
always receives the complete snapshot. With no retry/reuse, G groups cost G calls, K selected groups
cost K, and overall adds one; overall alone costs one. Selecting neither is rejected before calls.

Each explicit new intent creates an independent generation even for identical input; retransmission
of its UUID returns that generation. Create freezes/preflights but does not call a model. Execute uses
POST SSE of persisted business events, not token streaming or a worker. Retry uses the original
execution revision/identity and frozen scope, retains successful targets, restores compatible accepted
outputs first, and redispatches only confirmed retryable failures within the same cumulative budget.
Unknown queries never authorize paid replay. Legacy frozen-source regenerate remains API-only.

Results retain generation/root/selected identities and immutable snapshots. Discovery provides
`generation_id`, `selected_run_id`, `is_selected`, `detail_url` and `historical_detail_url`; choose the
historical URL for the listed exact generation. Deletion hides one generation, retains outputs/audit,
and rejects execution/downstream references. Current selection, evidence, content-change and retry UI
are defined in [Review workspace contracts](../frontend/README.md#review-workspace-contracts).

`CAREER_AGENT_INTERVIEW_POLICY` configures concurrency (default 3, maximum 8), call profiles
`mock_generation`, `mock_group`, `actual_group`, `mock_overall`, `actual_overall` and cumulative
`mock_session`, `mock_debrief`, `actual_debrief` limits. Profiles contain max_input_tokens,
max_output_tokens, max_estimated_cost and max_seconds; these are safety ceilings, not calibrated
prices. Transport/schema retries retain their separate configured limits. See
[Interview policy](../src/career_agent/interview/policy.py) and [budget implementation](../src/career_agent/interview/calls.py).

## Product operations, materials and discovery

- `GET companies[/{id}]`, `GET companies/{id}/research[/current]`: history is independent of freshness
  and execution compatibility. `POST companies/{id}/research` explicitly creates a research operation;
  modern Product requests force fresh search/synthesis. Company/JD identity is required, personal
  Profile/Facts are not consumed. No missing-history read implicitly authorizes research.
- `POST operations` durably creates a request handle for prepare_application, prepare_interview or
  company_research. Save the ID before `POST operations/{id}/execute`. Execution is synchronous;
  GET operation/result/task-status recovers facts, not background continuation. Orphaned execution
  is recovery_required/unknown, never an automatic replay.
- `GET preparation-artifacts/{id}/product-view` and exact result/context routes expose frozen task
  results, source/output Resume distinction, PDF, allowed actions and feedback subjects.
  `source_resume_revision_id` is input provenance; `resume_revision_id` may be a generated output.
- Application collections include preparation packages, task results, greetings, submissions and
  knowledge notes. Mock/Debrief discovery accepts Application/source filters and loads all pages in
  Product history. Exact Profile/JD revisions remain available independently of current bindings.
- `POST applications/{id}/submissions` takes request_id, expected_revision, exact Resume/PDF,
  optional greeting/package/note. It records real use atomically with an Application event; it never
  sends anything. PATCH/DELETE require Submission revision and request identity, append overlays,
  retain frozen materials/events, and do not themselves change status after the last removal.
- Greeting, Research, Fit/Prep and Debrief each have scoped visibility-removal routes and their own
  reference checks. Do not use one tombstone table for unrelated result types. Removed Submission
  references still protect Greetings; current selection and rejection behavior are in the frontend contract.
- Successful tailoring/Resume refinement and Greeting/Prep refinement auto-save; Application binding
  replacement is a separate CAS-confirmed choice. Accepted output can support save-only recovery.

See [Web product layer](architecture.md#web-product-contract-layer),
[task status/recovery](model-reliability.md#product-task-status) and
[material/source contracts](../frontend/README.md#generation-source-labels).

## Ops and Evaluation

Ops requires server-side `CAREER_AGENT_OPS_TOKEN` / `X-Ops-Token`; unset denies access.
GET controller/metrics/events/recovery-incidents and POST controls/attempt reconcile are the bounded
interfaces. Controls use request identity, revision CAS and applicable route/TTL/global revision;
reconcile distinguishes inspect/manual acknowledgement and never reconstructs a lost model body.
Current Internal UI and exact endpoint/action tables are in
[Internal Dashboard contracts](../frontend/README.md#internal-dashboard-contracts).

Evaluation APIs live under `/evaluation`: cases/suites/runs/trials/operations, comparisons, explicit
Judge drain, blind annotation/calibration and captures. Capture triage → sanitization → explicit
promotion/export is not an automatic publication path. Private origin/invocation payloads are separate
from ordinary metadata. REST/CLI fixture defaults do not imply read-only execution or permission to
write business data. See [Eval CLI](development.md#evaluation-cli) and
[Eval architecture](architecture.md#v03-evaluation-boundaries).

## Versions, budgets and recovery boundaries

Prompt/action/schema identity is feature-owned and registered through the existing Gateway. Consult
[the task inventory](model-reliability.md#boundaries-and-inventory) and
[version governance](architecture.md#shared-version-governance-before-v02b) rather than copying one
historical version suffix to every task. Historical result readability and new-execution compatibility
are different checks. Resume wrapper/font/layout versions remain distinct from model prompt versions.

Provider-reported tokens are usage, not an invoice. Estimated cost and unknown-attempt reservations
are separate, actual billed cost remains unknown, and parent/child usage must not be summed twice.
[Accounting](architecture.md#usage-cost-estimates-and-budget-reservations) retains the field semantics.
Known accepted output can be restored by supported task paths after validation; missing/unknown
output cannot be reconstructed from metadata or automatically replayed. No generic durable worker,
distributed exactly-once or database/filesystem global atomicity is promised.
