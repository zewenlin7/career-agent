# Career Agent work and acceptance map

## Current stage and pre-commit work

**v0.5 Application/Interview closeout; accumulated changes are not yet authorized for submission.**
Profile Workspace has passed user manual acceptance. Application/Interview overall final confirmation
and Internal final manual acceptance remain open. Implemented, offline-verified and user-observed are
separate states; none by itself establishes broad model quality or a release.

- [x] Round-two Job-create request receipts and frontend refresh recovery, including uncertain responses.
- [x] Active-owner archive checks for named Profile/snapshot/Resume; deleted-workspace navigation,
  task reachability and execution/adoption ordering without erasing historical facts.
- [x] Round-two offline closeout report: 955 backend tests; frontend check (56 units), isolated build,
  124 fixture browsers; 63 full real-backend browsers followed by four affected cases after the final
  HTTP-timeout identity correction; static, migration/drift, Typst/PDF and package checks. These are
  prior implementation-round results, not tests rerun for this documentation update.
- [x] Project README layering, matching Chinese entrypoint and current frontend-contract reconciliation.
- [ ] User final confirmation of the accumulated Application/Interview milestone.
- [ ] Internal final manual acceptance; do not infer it from fixture tests.
- [ ] Explicit user authorization for staging/commit/push; after an authorized push, inspect the actual
  remote CI outcome. Neither a local check nor an older stage's CI proves this accumulated change passed remotely.
- [ ] Confirm the target business database revision and separately authorize the necessary full migration
  path. The code includes Review/Notes migration `c205c2102601` followed by Job receipts `c305c2202601`;
  do not apply only the old Review reminder or infer deployment state. Consult the full files in
  `migrations/versions` and [migration procedure](docs/development.md#database-migrations).

No business DB was queried or migrated by the documentation pass. Historical note modification times,
request identities, snapshots and accepted outputs must not be invented or backfilled by documentation.

## Implemented, awaiting final confirmation

### Evidence already confirmed

- **Profile:** user manual acceptance passed for named profiles, shared editing, Resume creation,
  explicit presentation, source validation and PDF workflows.
- **Mock limited real functional checks:** a reasonably complete answer led to a next primary question;
  an explicit gap led to a targeted follow-up. This confirms both choices were observed, not their
  distribution or quality across all modes/answers.
- **Debrief limited real functional checks:** an old failed target retried successfully; a separate
  start on the same interview produced a new complete analysis. This does not validate every finding,
  every failure mode or the whole Review workspace.
- **Historical Resume recovery:** the prior-session handoff reports four outputs restored with original
  frozen Resume provenance. This documentation pass did not query the business DB, reverify records,
  or rerun recovery scripts. Recovery completion does not authorize test-data cleanup.

### Remaining manual acceptance

- [ ] Application Summary, state/notes operations, exact history navigation and final Apply-page interaction.
- [ ] Create-response recovery/new-intent confirmation, closed-Application deletion, subsequent resource
  archival, and explained unavailable old links/notifications.
- [ ] Research never-created/last-removal empty state; Fit/Prep/Research protected removal and selection
  retention. Isolated automation exists; the sole real Prep record was not used for a deletion trial.
- [ ] Resume/Greeting refinement naming, replacement confirmation and cross-page notification wording
  where no reliable individual sign-off exists.
- [ ] Interview intake/history editing and exact return, source selection, continued sessions and
  complete desktop/narrow-screen interaction. Keep completed observations above; do not reset them
  to “no real calls tested” or mark all seven task cards accepted.
- [ ] Review combined selector, multi-group/full-overall scope, frozen evidence navigation, source-change
  hint, per-generation removal and note CRUD beyond the limited successful real flows above.

The implemented question identity is a stable UUID with parent/order relationships; visible numbers
are derived from current order, while a Debrief retains its own frozen numbering. “Stable question
anchors” does not mean immutable display numbers or permission to renumber old snapshots.

### Historical failure attribution and recovery boundaries

| Record / mechanism | Current status | Remaining evidence boundary |
| --- | --- | --- |
| Structured tailoring entries rejected by the old bullet-length guard | Code defect corrected and production-path offline regression documented in [model reliability](docs/model-reliability.md#confirmed-defects-corrected) | The four restored outputs are accepted as reported in the handoff, not newly queried |
| Resume adjustment/regeneration input duplicated and preflight misclassified | Input/diagnostic correction and accepted-output save recovery implemented; see [preflight record](docs/model-reliability.md#resume-adjustmentregeneration-preflight-2026-11-06) | Admission eligibility is not real-provider output quality |
| The earlier reminder naming “two live tailoring failures” without exact identities | No separate known unfixed mechanism can be established from that reminder alone | Do not silently equate the two with either case set above. Exact per-request correlation remains unverified; a renewed investigation needs reliable identities/safe records and appropriate access authorization |
| Debrief invalid overall references | Prompt/mapping/validation corrected; user observed successful retry/new analysis | Historical rejected raw output was not retained, so specific old illegal values remain unknown |

Supported Mock, Draft and Debrief paths can validate and save already durable accepted output without
another provider call. Explicit known-failure retry may call again within budget. Unknown outcomes
must first be queried; lost provider bodies cannot be recovered from metadata alone. Agent checkpoints
resume at committed action boundaries; synchronous Preparation rollback does not imply a generic
model-call replay service. There is no distributed worker, exactly-once guarantee or database/filesystem
global atomicity. These limits do not negate the implemented task-specific recovery.

## Post-commit third round: retired code cleanup

- [ ] Start only after the milestone commit and separate scope confirmation.
- [ ] Identify actually unreachable/retired implementations and tests; do not remove compatibility merely
  because Product no longer exposes a control. Retain old parsers, frozen provenance, Eval replay and
  historical request/output recovery dependencies.
- [ ] Keep regression coverage for active contracts; do not restore Facts approval gates, fixed Mock
  scheduling or input-based Debrief generation reuse while cleaning historical paths.

## Next function stage and Polish

- [ ] After a stable baseline, scope multi-turn discussion around a Debrief and its frozen Q&A as an
  independent feature. It precedes final visual Polish; no design or implementation is authorized here.
- [ ] Later Polish: actual viewport widths, built-in/external-screen half-window use, accessibility and
  video/demo experience. Define scope from real observations, not a new blanket redesign.
- [ ] Test-data cleanup, including restored Resume outputs, needs separate write/delete authorization
  and checks for shared sources and frozen/downstream references.
- [ ] Full physical cleanup/privacy erasure remains undecided future work, not a commitment attached
  to Application soft deletion.

## Evidence gathering and engineering research

These are bounded follow-ups or optional investigation, not all blockers for the current commit.

- [ ] Broader paired Mock quality samples: complete/brief-correct answers, important omissions,
  contradictions, exhausted coverage, continuous probing and finish-with-unused-allowance. Existing
  fixture decisions verify execution, not real preference; no target follow-up rate is prescribed.
- [ ] Broader Prep/Resume/Greeting/Debrief semantic and grounding review, distinct from observed
  successful calls. Paid model/search/Judge checks require explicit scope and call/cost caps.
- [ ] Real Judge calibration and representative labels; deterministic fixture judgments are not truth.
- [ ] Provider invoice reconciliation, operational load/retention and contention characterization.
  Reported usage, estimated cost, unsettled reservation and actual billed cost remain distinct.
- [ ] Backup/restore and orphan artifact reconciliation after process crashes. Normal rollback cleanup
  exists; it is not cross-filesystem transactionality or comprehensive crash cleanup.
- [ ] Query batching only if measured overhead warrants it; explicit Company identity resolution only
  when actual duplicates require it. No fuzzy identity merge as an idempotency shortcut.
- [ ] Targeted Resume engineering research: concurrency at revision boundaries, empty-required-section
  policy, stronger short-expression hard-claim checks, direct-SQL JSON and dirfd race hardening.
- [ ] Explicit persisted-policy migration and distributed quota coordination only as separately scoped work;
  never reset an incompatible durable controller to healthy or automatically replay unknown spend.
- [ ] Public deployment requires a deliberate authentication/security project first. Internal Ops UI
  already exists; this is not a reminder to implement the whole frontend again.
- [ ] Keep dependency/lockfile and immutable-migration maintenance separate from business changes.

## Optional future extensions

Not promised scope: URL/BOSS ingestion (subject to login/terms/privacy), pgvector/semantic retrieval,
English/bilingual/multi-locale or Letter/multi-page Resume templates, DOCX export, PDF import/OCR,
additional result naming, broader planner routing, cross-provider Judge, optional built-in web search,
prompt A/B infrastructure, tool-version rollout, email/calendar integration, browser automation,
analytics/reapplication cycles, voice Mock, multi-agent research, advanced human approval,
distributed runtime/rate limiting and advanced PII/DLP. Current Chinese Resume support is not pending.

## Learning goals

- [ ] Explain domain state, workflow state, runtime telemetry and checkpoint differences.
- [ ] Demonstrate rollback, CAS, row locks, request identity and append-only history.
- [ ] Explain capability routing versus natural-language intent routing.
- [ ] Explain source references versus semantic grounding, confidence versus verification.
- [x] Demonstrate deterministic document compilation and explicit layout failure with synthetic fixtures.
- [ ] Evaluate trajectories, evidence-based recovery and fault propagation.
- [ ] Explain cost accounting, control hysteresis, dependency-scoped circuits and degradation boundaries.

## Historical implementation roadmap

This is implementation lineage, not a release list or current acceptance checklist. Original test
counts, live budgets and commit/CI statements retain their stage-specific context in [CHANGELOG](CHANGELOG.md).

| Stage | Implemented contribution / later boundary |
| --- | --- |
| v0.1a | Domain, PostgreSQL/API, revisions/events, metadata and privacy baseline |
| v0.1b | Canonical Chinese Resume compiler, grounded exact sources, Typst/PDF checks; automatic selection later replaced by explicit presentation |
| v0.1c / v0.1d | Governed preparation/provider contracts, bounded historical live smoke; deterministic Python target execution replaced the original LangGraph wrapper |
| v0.2a | Bounded typed planner/executor, shared budget, committed-action checkpoint and explicit resume |
| v0.2b | Actual/Mock/Debrief sources, snapshots, group analysis and operation provenance; fixed question scheduling later replaced by model decisions |
| v0.3 | Frozen Eval replay, sampling/Judge, annotation/calibration/capture and priority-tier comparison |
| v0.4 | Approved routing, capacity/circuits, durable journal/reconciliation/Ops, bounded controls, exact observation/artifact reuse; later Debrief request identity replaces cross-intent input reuse |
| v0.5 | Product/Internal Web, named Profile/Resume workspace, Application bindings/Summary/materials/submissions, interview lifecycle, Review/Notes and closeout fixes |

The old “v0.5 Real Usage Loop planned” label described an earlier roadmap; the current v0.5 is the
implemented Web product. Broader real outcomes, representative bad-case regression and selection-bias
analysis remain evidence work, not a claim that fit labels predict hiring probability. Earlier manual
Facts surfaces are retired; internal evidence/history remains for validation and compatibility.
