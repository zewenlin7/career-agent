# Career Agent engineering and learning map

## Current milestone

**v0.1c Job Preparation Workflow — completed; live and final offline acceptance passed.**
Next: v0.1d Integration / E2E (not started).

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

- [x] Two fixed LangGraph workflows; ref-only state and one semantic compression branch.
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

### v0.1d Integration / E2E (planned)

- [ ] End-to-end job preparation and resume artifact delivery.
- [ ] Partial failure, malformed provider output, cost/timeout and layout failure acceptance.
- [ ] Local private-data smoke verification without publishing data/artifacts/logs.
- [ ] Accurate README, acceptance report and final v0.1.0 release notes.

### v0.2 Agent Runtime (planned)

- [ ] Planner/executor/evaluator and bounded replan; shared state and stopping criteria.
- [ ] Persistent checkpoints, recovery, worker and idempotent side effects.
- [ ] Tool registry and structured observations; timeout/retry/budget enforcement.
- [ ] Runtime events and usage aggregation, unknown/estimated accounting.
- [ ] Mock interview and assisted interview debrief; candidate knowledge requires confirmation.

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
- Natural-language intent routing.
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
