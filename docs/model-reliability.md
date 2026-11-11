# Model execution reliability

This audit describes code and offline verification. It is not live-provider quality acceptance.
Application and Internal remain pending final manual acceptance. Historical operation bodies and
provider invoices are private; this document contains no customer input or response.

## Boundaries and inventory

The executable inventory is `models.prompts.application_prompts()` (19 tasks), checked against
`preparation.providers.POLICY`. Retired fact extraction is not executable. Workflow APIs,
Product operation handles, Product drafts, explicit Interview actions, bounded Agent actions,
and Eval/Judge can reach this registry; a page read cannot dispatch a task.

All rows use `models/gateway.py`, the process controller, attempt journal, provider adapter and
canonical Pydantic parser. Shared contracts do not imply each task has identical retry policy.
Preparation owns its bounded retry/repair loop; Draft and Interview use `interview/calls.py`;
Agent uses its action-boundary budget and checkpoint; Eval uses isolated frozen candidate settings.

| Task | Input producer → output/validation → persistence and consumers | Version and offline evidence |
| --- | --- | --- |
| job_requirement_extraction | Preparation workflow exact raw JD → RequirementsOutput + source-span validation → JobRequirement on that JD; Fit/material consumers | preparation/prompts.py; test_research_fit_pipeline, test_preparation |
| company_research_synthesis | Company + SearchObservation evidence → ResearchOutput + evidence/scope guards → CompanyResearch; Research, Greeting, Prep | company scope v8 prompt; TTL and execution compatibility independent of historical reads; test_research_fit_pipeline, test_reuse_phase3 |
| fit_analysis | Exact selected Profile/Resume evidence + JD requirements → FitGenerationOutput → canonical FitOutput and target wrapper; Tailoring/Greeting/Prep | v2 single-explanation generation, historical dual-field reader; test_research_fit_contract, test_application_bindings |
| resume_tailoring | Exact selected Resume + frozen facts/requirements → ResumeDocument + grounding/locale/layout → immutable revision, PDF, library entry and target wrapper | structured-entry layout v2; test_product_api structured_entry, test_preparation, test_resume_compiler |
| resume_compression | Existing canonical Resume, protected fields and render report → ResumeDocument + identity/number/required-content guards → canonical revision/PDF | separate bounded preparation compression task, not library short-text task; test_preparation, test_resume |
| greeting_generation | Exact Resume + requirements/facts + optional company research → GreetingOutput/reference/numeric guards → PreparationArtifact → Product/Submission | generation prompt participates in reuse; test_product_api, test_preparation |
| interview_preparation | Exact Resume, requirements/facts, optional research/story/note context → InterviewOutput/reference guards → PreparationArtifact → Prep history/refinement (not a new Mock attachment) | generation prompt participates in reuse; test_interview_loop, test_preparation |
| base_resume_drafting | Deterministic Profile-derived source items → ResumeExpressions/source-item/number validation → ProductDraft → editable Resume workspace | product-draft input v3; test_profile_records, test_product_drafts |
| resume_library_compression | Exact visible Resume items missing short text, not regenerated Profile → ResumeExpressions → validated recoverable editing proposal | compression output v4; test_resume_lifecycle, test_profile_records |
| resume_claim_refinement | Selected exact source items → ResumeExpressions/source checks → editable proposal | product/prompts.py + product/drafts.validate_output; test_profile_records |
| resume_refinement | Exact Resume + user feedback + optional Application context → ResumeDocument + grounding → independent library edition/lineage; binding separately confirmed | product prompt v4 / input v3; test_product_drafts, test_resume_lifecycle |
| greeting_refinement | Exact original artifact/context + feedback → GreetingOutput + production guards → automatically adopted independent target | execute preserves output if adoption fails; test_product_drafts, real Profile browser |
| interview_preparation_refinement | Exact original Prep/context + feedback → InterviewOutput + production guards → automatically saved independent target | auto-adoption with retained accepted-output recovery; test_product_drafts |
| mock_interview_turn_generation | Frozen visible context + current-group Q&A + legal actions/quotas → ask/finish decision + parent/evidence validation → durable turn or finish receipt/session | Mock prompt v8 / input v6 / output v3; test_interview_loop, test_control_traces |
| interview_group_debrief | Frozen transcript and exact question group → CompactGroup → deterministic question-number resolution + canonical validation → DebriefArtifact | compact output v2; test_product_compact, test_interview_loop |
| interview_overall_debrief | Full frozen interview, independent of selected group scope → CompactOverall → exact answered-reference conversion → DebriefArtifact/Knowledge consumers | overall prompt v6 / input v5 / output v3; legacy accepted v2/input v4 recovery; test_product_compact, test_interview_loop |
| goal_planning | Frozen AgentState, approved action/evidence catalog → PlanProposal + registry/identity validation → plan/checkpoint → bounded executor | planner-context v3/agent-plan v2; test_agent_runtime, test_agent_runtime_contracts |
| goal_replanning | Existing checkpoint + structured observations → same pinned plan schema/validator → new plan revision | preserves unknown outcome and action bindings; test_agent_runtime, test_recovery_ops |
| quality_judgement | Explicit rubric/evidence + accepted subject → JudgeOutput → private judge result/metadata metrics | judge-input/output v1; test_evaluation_integration; no automatic paid quality claim |

The registry-wide governance tests cover every active prompt's executable input, output-schema/hash
and routing registration. They do not substitute for feature-level persistence and guardrail tests.

## Confirmed defects corrected

* Tailoring's legacy 180-character bullet check also applied to whole structured `entry` items.
  The check now applies only to bullets. Total document/project limits, schema, grounding and actual
  PDF validation remain enforced. A production-path regression uses a grounded multiline entry,
  then verifies accepted output, library persistence and idempotent execute. It failed before the fix.
* Material reuse now includes its actual generation prompt hash. Historical records missing the
  new compatibility key remain readable but are not silently reused for a new execution.
* Model invocation provenance previously assigned the Resume-tailoring compatibility map to all
  tasks. New invocations freeze the actual task metadata; existing invocation records are not rewritten.
* Eval's `validate_task` did not run Product draft/refinement guardrails. All six Product task schemas
  now dispatch to the production `validate_output`, including deterministic expression conversion.
  An invalid-reference refinement regression failed before this fix.
* Product operation restoration previously covered Research/Fit only. Material/Prep operation
  identities now use the same restoration path. Leaving Debrief no longer implicitly aborts its stream.

## Diagnostics and recovery

A successful ModelCall means provider completion and schema parsing, not business-artifact acceptance.
Later guardrails are recorded on AgentStep/run/operation. Estimated model cost is not an invoice.
Known usage settles reservations; unknown usage/outcome retains conservative recovery constraints.
`business_committed` on an attempt journal also covers a committed failure record: it does not mean
a Resume was created. Provider output may exist in the private invocation with no output_ref.

The real failure investigation used read-only transactions and projected metadata plus SQL length
aggregates only. Four observed failures all had completed/valid tailoring calls, settled usage and
`layout_budget_exceeded` at the post-model node. Their persisted invocation outputs have no bound
artifact. No customer output was read into diagnostics or changed. Safe recovery would still require
running current source/grounding and persistence checks against the frozen output; existence alone
does not prove that later guards will pass. No business recovery mutation was performed in that diagnostic pass. The subsequent user handoff
reports the four outputs restored with original frozen Resume provenance; this documentation update
did not query the business DB or rerun recovery. The earlier unspecific “two failures” reminder cannot
be equated to these exact records without further evidence; see [the attribution boundary](../TODO.md#historical-failure-attribution-and-recovery-boundaries).

## Product task status

`GET /task-status/{family}/{id}` is an explicit, body-free read surface for operations, drafts,
Mock and Debrief. It does not execute/adopt/retry. Mock reads pin the exact request receipt,
so a later successful turn cannot replace an earlier failure. Migration `be05c1702601` adds nullable
metadata-only receipt outcomes; legacy receipts remain readable as unknown rather than borrowing
the current session state. Mixed Debrief failures are not misreported as complete cancellation. A running operation whose execution lock is gone
is projected as unknown without changing the database record. Exact result parameters are derived
from persisted results. Provider acceptance is never completion.

The Product shell retains started task handles in browser local storage, polls existing state across
route changes and reloads, and offers dismissible exact links. Dismissal is per observed state so
closing an unknown-state message does not suppress a later definitive completion. This is browser-local
recovery, not cross-device synchronization or an operating-system push service. Clearing browser
storage removes those local handles; backend operations and results remain available.

## Verification limitations

Offline adapters exercise the production parser, validators, services and isolated PostgreSQL.
They cannot establish real-provider semantic quality, external quota behavior or actual billed cost.
Historical task readability is separate from eligibility to replay it with a changed generation schema.
No frozen input, evidence or old result is silently rebound to current data.

A read-only `/tasks/{family}/{id}` route opens failed/unknown/unadopted tasks without relying on
the originating component or sessionStorage. It polls only the status GET and offers an exact result
link when available. It never executes, adopts or retries. Browser regressions clear sessionStorage
before opening a failed task, then reload the route and verify no additional provider call.

## Resume adjustment/regeneration preflight (2026-11-06)

Read-only diagnostic metadata identified three November 5 requests: two adjustments and one
regeneration. All stopped before provider
admission with the misclassified `debrief_input_too_large` reason. They have no
ModelCall, attempt journal, accepted output or adopted Resume. No historical rows
were rewritten or requests replayed during this repair.

The provider input repeated the selected Resume in both `original` and frozen
context, alongside the full Profile. Input v3 sends the authoritative original
once, retaining frozen evidence, JD requirements and identity constraints. Full
context remains persisted and is still used by the production validator/adopter.
Safe size-only recalculation of those exact inputs gives 26,268 / 27,191 / 27,206
instead of 34,320 / 36,136 / 36,151 against the unchanged 30,000 input bound.
This proves admission eligibility, not live provider output quality.

Input and budget preflight rejections produce metadata AgentSteps without fabricated
provider attempts. Product drafts retain specific failure reasons through read-only
task status. Accepted output is committed before auto-adoption; a database adoption
failure is reread to detect a committed result, otherwise retained for an explicit
save-only retry. Unknown outcomes remain distinct from confirmed rejection.

Execution areas and local notices use the shared frontend task-feedback descriptions.
Notices are created only for explicitly tracked logical tasks, not historical failure
queries. Shown and handled states persist independently; collapse is not acknowledgement.

The safe Product projection retains `reason` rather than flattening every failure into
an invalid-request message. Both the execution area and notification use the same
`taskMessage` presentation:

| Persisted reason/state | Safe meaning |
| --- | --- |
| `product_input_too_large` | Rejected before provider admission |
| `budget_exhausted`, `call_budget_exhausted` | Generation budget unavailable; no invented provider quota diagnosis |
| `operation_attempt_limit` | Logical task attempt limit reached |
| `provider_429` | Provider throttling |
| `provider_timeout`, `operation_deadline_exceeded` | Timeout; do not infer an unconfirmed save outcome |
| `output_validation_failed`, `structured_output_invalid`, grounding/reference guardrails | Generated content rejected |
| `resume_library_save_failed`, `artifact_save_failed` | Accepted output retained for save-only recovery |
| `cancelled`, `reused`, `unknown` | Stopped, existing exact result, or unconfirmed outcome respectively |

Offline regressions mutate provider output to exercise real schema/grounding validators,
inject an isolated database trigger failure at canonical Resume insertion, and verify
persisted task-status reasons. A preflight rejection asserts an AgentStep but no ModelCall
or reservation. Browser checks cover delayed adjustment/regeneration navigation, exact
result recovery, unread/shown persistence, queue timing, focus/hover pauses and simulated
visibility events. These checks do not establish live provider quality or OS background
scheduling behavior. Mock failure/cancellation receipts do not require a session revision
increase to become a notification; the revision guard applies only to preceding success.


## Mock decision-quality contrasts

The separate [Mock decision-quality suite](../tests/fixtures/evaluation/mock_decision_quality.json)
(`mock-decision-quality` v1) contains nine synthetic cases in three contrast groups. Within each group,
only the latest accepted answer changes; materials, questions, history and quotas stay fixed.
Inputs are reconstructed by the production Mock builder. Private evaluation annotations record the
preferred/acceptable decisions, concrete gap and rationale; none is passed to the model.

| Contrast group | Cases and annotated decisions |
| --- | --- |
| First answer, identical question and 5/3 policy | Complete → primary; brief but accurate → primary; required boundary missing → follow-up; technical contradiction → follow-up; explicitly conditional judgment → primary preferred, targeted follow-up also acceptable. |
| After a follow-up, identical current group | Sufficiently explored → primary; newly exposed contradiction → another follow-up. |
| All primaries answered, three follow-ups unused | Resolved final group → finish; unresolved contradiction → follow-up. |

The existing Eval runner/parser/production validator reports Tier 0 execution legality separately
from Tier 1 decision acceptability. Single-answer cases also record Tier 2 preference; multi-answer
preference remains advisory so an acceptable alternative does not fail. Labels are local judgments
for these frozen examples, not universal action rules. Generated question relevance, gap targeting
and absence of repetition still require content review; action labels alone cannot grade them.
The unchanged default fixture chooses follow-up whenever legal: all nine execute legally, but four
fail the quality labels. This expected result verifies the scoring boundary, not a real model's bias
or improvement. The suite uses the existing `evaluation run <suite-file>` entry point; it requires no
Judge. Live paired comparisons need separate bounded authorization and were not part of the offline suite. The user later reported limited real functional choices;
those observations do not constitute a controlled paired quality evaluation.
