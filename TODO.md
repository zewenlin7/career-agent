# Career Agent engineering and learning map

## Current milestone

**v0.1a Foundation — implemented; final verification recorded in CHANGELOG.**
No work on v0.1b is authorized by this milestone.

Completed: skeleton/configuration, domain/persistence and migration, typed local API,
revision/event semantics, runtime/version metadata, fake model gateway, privacy baseline,
synthetic tests with real PostgreSQL and documentation. See CHANGELOG for verified details.

## Next milestones: committed roadmap

### v0.1b Resume Compiler (planned)

- [ ] Canonical verified-profile snapshot → structured Resume Variant with fact/requirement references.
- [ ] Versioned template/artifact records referencing input revisions and runtime provenance.
- [ ] Typst canonical renderer; one fixed template, selected language/fonts/paper size.
- [ ] Deterministic low-priority compression/removal; bounded render attempts.
- [ ] One-page, text extraction, bounds/glyph/required-field checks and visual acceptance.
- [ ] Explicit layout failure; no fabricated facts, invisible clipping or arbitrary font shrinkage.
- [ ] Renderer/grounding tests using synthetic data. No unrelated job workflow yet.

### v0.1c Job Preparation Workflow (planned)

- [ ] Thin LangGraph graph with explicit state, structured observations and bounded repair branches.
- [ ] Configured real model adapter with capability/usage/error handling and privacy review.
- [ ] Manual JD extraction, bounded company research with evidence and safe public text access.
- [ ] Fit analysis, greeting draft, interview-preparation generation.
- [ ] Untrusted-content boundary, tool arguments, timeouts/retry caps and per-run limits.
- [ ] Trace concrete workflow/prompt/schema/tool versions; never fabricate missing metadata.

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

- Database: retain historical revisions; consider explicit input-snapshot FKs when artifacts arrive.
- Data lifecycle: retention/backup/restore and private artifact reference resolution when storage is added.
- Company identity: add explicit resolution only when duplicate company records impede use.
- Query efficiency: batch current-job projections if measured list-query overhead warrants it.
- Runtime: add real execution accounting before claiming hard budget enforcement; current policy
  admission only checks output allowance/cost floor and fake calls cost zero.
- Runtime call cost: canonicalize structured usage versus searchable cost projections at execution integration.
- Access control: local-only Foundation; authentication must precede any deliberate public exposure.
- Dependencies: maintain uv.lock and immutable migrations; reevaluate supported Python/DB versions.
- CI: review the first remote run after the user chooses to push; local checks do not claim remote CI success.

## Learning map

- [ ] Explain domain state versus workflow state versus runtime telemetry versus checkpoint.
- [ ] Demonstrate transaction rollback, optimistic revisions, row locks and append-only history.
- [ ] Explain model capability routing versus natural-language intent routing.
- [ ] Explain fact references versus semantic grounding and confidence versus verification.
- [ ] Demonstrate deterministic document compilation and explicit layout failures.
- [ ] Evaluate agent trajectories, idempotent recovery and fault propagation.
- [ ] Explain cost accounting, control hysteresis, dependency-scoped circuits and graceful degradation.

## Future / Optional Extensions (not committed scope)

- URL / BOSS ingestion (revisit login, terms, anti-crawling and privacy constraints).
- pgvector / semantic retrieval.
- Multilingual resumes.
- Letter / multi-page resume templates.
- DOCX export.
- Natural-language intent routing.
- Cross-provider judge.
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
