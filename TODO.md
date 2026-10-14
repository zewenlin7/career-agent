# Career Agent engineering and learning map

## Current milestone

**v0.2a Runtime Core — completed locally; final offline acceptance passed.**
Next planned milestone: v0.2b Interview Loop (not started).

Completed: skeleton/configuration, domain/persistence and migration, typed local API,
revision/event semantics, runtime/version metadata, fake model gateway, privacy baseline,
synthetic tests with real PostgreSQL and documentation. v0.1b adds structured Variant revisions,
grounding, bounded Typst/PDF compilation, artifact APIs and three Chinese acceptance fixtures plus a mixed-script regression.
See CHANGELOG for verified details.

## Milestones: committed roadmap

### v0.1a Foundation (completed)

- [x] Domain, async persistence/migrations, API contracts, fake gateway, runtime metadata, privacy and tests.
- [x] User confirmed commit, push and remote CI success.

### v0.1b Resume Compiler (completed)

- [x] Canonical verified-profile snapshot → structured Resume Variant with fact/requirement references.
- [x] Versioned template/artifact records referencing input revisions and runtime provenance.
- [x] zh-CN canonical Typst renderer; fixed A4/single-column template and hash-pinned CJK fonts.
- [x] Chinese/mixed-script acceptance, ordered retained-text matching and failed read/hash status.
- [x] Deterministic low-priority compression/removal; bounded render attempts.
- [x] One-page, text extraction, bounds/glyph/required-field checks and visual acceptance.
- [x] Explicit layout failure; no fabricated facts, invisible clipping or arbitrary font shrinkage.
- [x] Renderer/grounding tests using synthetic data. No unrelated job workflow yet.

### v0.1c Job Preparation Workflow (completed locally)

- [x] v0.1c originally introduced two fixed LangGraph workflows (replaced by deterministic Python orchestration in v0.1d); ref-only state and one semantic compression branch.
- [x] OpenAI Responses/Pydantic adapter, cheap/strong policy, no premium auto-escalation.
- [x] Seven versioned/hashed prompts and canonical output schemas.
- [x] JD evidence extraction, Tavily/fixture boundary and company cache with freshness.
- [x] Fit, grounded zh-CN Variant/compiler, greeting and explicit interview preparation.
- [x] Static reservation/accounting, bounded transport/schema repair, private trace metadata.
- [x] Separate reported usage, price estimates and unknown-call reservations; billed cost/tier unknown.
- [x] Offline PostgreSQL/Typst tests and mocked native SDK/research contracts.
- [x] User configured local .env; one bounded live smoke attempted on 2026-10-12.
- [x] Safe failure metadata preserves native response status/usage before Pydantic parsing; no schema bypass.
- [x] Retain future live smoke databases so successful upstream domain results can be reused.
- [x] Original smoke context declared unrecoverable; user authorized fresh canonical synthetic reconstruction.
- [x] Targeted tailoring and one-page zh-CN PDF passed real acceptance on 2026-10-12.
- [x] Live Greeting passed zh-CN and reference guardrails; not automatically sent.
- [x] Local 60-second SDK/HTTP timeout identified; configurable per-task timeout policy added.
- [x] One authorized Interview Prep with 120-second timeout passed in 78,393 ms; refs validated.
- [x] One real controlled compression passed grounding and produced an accepted one-page PDF.
- [x] Preserve cumulative budget: USD 0.3350816 accounted, USD 0.6649184 remaining (includes unknown-usage reservations).
  Historical recovery scripts are retired; any new paid run requires a fresh explicit budget decision.
- [x] Record actual models/tokens/cost/latency/searches, live PDF and compression outcomes.
- [x] Final offline full suite (195 passed), static checks, empty PostgreSQL migration/drift and package checks.
- [x] v0.1c local DoD complete; synthetic acceptance is not real job-search quality verification.

### v0.1d Integration / E2E

- [x] Arbitrary application targets, explicit resume bindings and target-local failure semantics.
- [x] Minimal deterministic execution/reuse; informational Fit and opt-in versioned Fit Gate.
- [x] Single canonical outcome for Run/package/API; required-input and decision terminal states.
- [x] Shared exact-context loader; historical package and Job/Application/Run discovery.
- [x] Fake-model/fixture-research/real-PostgreSQL/real-Typst target E2E, including real overflow repair.
- [x] Final full offline acceptance: 235 passed; Ruff/format, strict mypy, empty PostgreSQL migration,
  Alembic drift, offline install/build/package, pinned Typst/font and git hygiene checks passed.
- Synthetic acceptance is not real job-search quality verification. No new paid smoke required.

### v0.2a Runtime Core

- [x] Bounded structured Planner → PlanValidator → existing deterministic executor.
- [x] Coarse action registry, deterministic evaluator, shared cumulative budgets and action observations.
- [x] Versioned plans/checkpoints, waiting input/decision, explicit CAS/idempotent resume.
- [x] Preserve exact context, explicit bindings, Fit Gate, artifact reuse and canonical target outcomes.
- [x] Offline fake-provider / real PostgreSQL / real Typst runtime regression coverage.
- [x] Final offline DoD: 271 passed; Ruff/format, strict mypy, empty PostgreSQL migration/drift,
  clean offline install, wheel/sdist/package, pinned Typst/font and git hygiene checks passed.

### v0.2b Interview Loop (planned; not implemented)

- [ ] Mock interview and assisted debrief on the bounded runtime.
- [ ] New personal knowledge remains proposed until explicit user verification.
- Distributed workers and production crash recovery are outside v0.2a; no exactly-once claim.

### v0.3 Harness / Evaluation / Safety (planned)

- [ ] Scenario harness, golden labels, regression dataset and trajectory evaluation.
- [ ] Deterministic metrics, human annotation and optional LLM judge (never sole truth).
- [ ] Recorded-observation replay versus live rerun, fault injection and comparisons.
- [ ] Factual grounding, layout evaluation, privacy and injection regression.

### v0.4 Production Engineering (planned)

- [ ] Agent Ops Dashboard and metrics aggregation: runs/steps/tools/retries/errors/latency/tokens/cost.
- [ ] Dynamic model routing and complete token/cost reservation, reconciliation and budget policy.
- [ ] Rate/concurrency limits, scoped circuit breakers, fallback and graceful degradation.
- [ ] Windowed automatic control with cooldowns, recovery probes and control-action audit.
- [ ] Caching with version/privacy-aware keys and invalidation.
- [ ] Synthetic load/failure tests and full E2E acceptance, not invented multi-user traffic.

### v0.5 Real Usage Loop (planned)

- [ ] Real application outcomes, recruiter responses and interview feedback.
- [ ] Actual bad cases become sanitized regressions and product improvements.
- [ ] Track evidence and selection bias; do not equate fit scores with hiring probability.

## Engineering improvement map

- Database: maintain immutable Variant revisions and exact Profile/JD/artifact foreign-key references.
- Data lifecycle: retention/backup/restore and orphan-file reconciliation after process crashes.
  Normal request rollback already removes newly written PDF artifacts.
- Company identity: add explicit resolution only when duplicate company records impede use.
- Query efficiency: batch current-job projections if measured list-query overhead warrants it.
- Runtime: v0.1c reserves input/output/cost before each attempt; unknown usage retains
  conservative reservations. Provider billing reconciliation and durable recovery remain future work.
- Runtime call cost: estimated-cost projection now excludes unknown reservations; retain future provider invoice reconciliation.
- Access control: local-only Foundation; authentication must precede any deliberate public exposure.
- Dependencies: maintain uv.lock and immutable migrations; reevaluate supported Python/DB versions.
- Resume review follow-ups (not v0.1b blockers): simultaneous Variant revision requests,
  empty required-section policy, stronger short-form hard claims, direct-SQL JSON checks,
  and dirfd-based filesystem race hardening. Current documented boundaries remain in force.
- CI: review the first remote run after the user chooses to push; local checks do not claim remote CI success.

## Learning map

- [ ] Explain domain state versus workflow state versus runtime telemetry versus checkpoint.
- [ ] Demonstrate transaction rollback, optimistic revisions, row locks and append-only history.
- [ ] Explain model capability routing versus natural-language intent routing.
- [ ] Explain fact references versus semantic grounding and confidence versus verification.
- [x] Demonstrate deterministic document compilation and explicit layout failures (v0.1b fixtures).
- [ ] Evaluate agent trajectories, idempotent recovery and fault propagation.
- [ ] Explain cost accounting, control hysteresis, dependency-scoped circuits and graceful degradation.

## Future / Optional Extensions (not committed scope)

- URL / BOSS ingestion (revisit login, terms, anti-crawling and privacy constraints).
- pgvector / semantic retrieval.
- English resume template.
- Bilingual / multi-locale resumes.
- Letter / multi-page resume templates.
- DOCX export.
- Multiple resume templates.
- Broader natural-language routing beyond the two registered runtime business actions.
- Cross-provider judge.
- OpenAI built-in web search as an optional future ResearchAdapter.
- Prompt experiments / A-B infrastructure.
- Tool version rollout.
- Email/calendar integration.
- Browser automation.
- Application analytics and reapplication cycles.
- Voice mock interview.
- Multi-agent research.
- Advanced human approval.
- Distributed runtime / rate limiting.
- Advanced PII / DLP.

When completing an item: remove it from active work or mark its milestone complete, record only
implemented/verified changes in CHANGELOG, and update README only to describe actual capability.

### Integration limitations retained

- Uncaught exceptions/transaction crashes roll back the synchronous request; no durable failed-run
  recovery or worker is claimed. v0.2a adds only committed action-boundary checkpoints and explicit resume.
- Database/filesystem writes are not globally atomic. Existing best-effort cleanup cannot replace
  orphan artifact reconciliation after crashes.
- Concurrent identical requests may duplicate model work; artifact reuse is sequential, not a
  distributed idempotency guarantee. Optimistic resume revision checks remain in place.
- Context fingerprints use exact IDs, verified fact status, task prompt hash and mode. They are
  private provenance keys, not cross-version semantic-equivalence judgments or quality scores.
- Pre-v0.1d outputs remain readable. Legacy Fit reuse requires provable package/prompt/fact
  compatibility; other legacy outputs without explicit resume-binding provenance are not auto-reused.
- v0.1d changed orchestration/prompt inputs without new paid acceptance. Historical v0.1c live
  connectivity acceptance does not prove new prompts' real output quality.

### Runtime limitations retained

- In-flight planner/business calls cannot be replayed. A committed dispatch reserves the remaining
  allocation conservatively; unknown cost is not zero and not actual billed cost. Manual inspection
  is required after an unexpected failure during dispatch.
- No model-call-level recovery, unknown-side-effect replay, exactly-once, uncommitted transaction
  recovery, distributed worker or database/filesystem global atomicity. Orphan artifact cleanup remains
  future work. Existing preparation endpoints retain their synchronous transaction limitations.
- Changed/superseded fact context or unavailable completed artifacts blocks resume; immutable context
  is not silently rebound. Restore the artifact or cancel/create a newly bound goal.
- Active-time limits stop new work and bound model/compiler calls; synchronous validation/DB finalization
  can overrun a wall-clock deadline. They are not process-isolation or hard real-time guarantees.
- Planner validation proves authorization/structure, not that a model correctly understood the goal.
  No new live planner quality acceptance, judge, harness, dynamic routing or operational control plane.
