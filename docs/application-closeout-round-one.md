# Application closeout — round-one evidence and next scope

**Historical checkpoint:** the missing mechanisms below were the round-one findings. Round two
implements request receipts, active-owner archive filtering/locking, nullable Job navigation and
separate task reachability; see README, architecture and CHANGELOG for the current contracts.
The original matrices remain as evidence, not an active list of unfixed backend tasks.
Chinese README is now present. The four-result recovery TODO is closed using the supplied handoff,
without a business-database recheck. Manual acceptance and authorized business cleanup remain pending.

This is a bounded checkpoint, not a milestone sign-off. No business database, paid provider,
search or Judge was accessed. At the round-one checkpoint, backend changes below were proposals rather than implemented behavior.
The user reports successful failed-target retry and a separate complete Debrief creation;
that observation does not establish overall Application/Internal or live semantic acceptance.

## Direct changes and verification boundary

- `frontend/src/features/workspace/review.tsx`: remove saved-item lists and completed summaries;
  preserve one generating line, exact failed-target reasons/actions and incremental chapters.
  History selection, execution identity, source-change warnings, frozen Q&A and evidence are retained.
- Company Research production behavior is unchanged. Isolated real backend/browser coverage verifies
  never-created, sole visible history without a live current, allowed last deletion and refresh.
  Fixture browser fault injection verifies history-read errors and refusal retaining exact selection.
  Isolated PostgreSQL tests verify expired readable history, sole Prep-referenced refusal, last
  removal, unchanged call counts and retained exact audit reads. A fixture refusal alone is not
  backend deletion evidence. User manual empty-state acceptance remains pending.

## Round-one finding: Job request idempotency was missing

| Boundary | Current evidence | Next change / acceptance |
| --- | --- | --- |
| Frontend | `features/onboarding/jobs.tsx`: in-memory submitted/attempted flags only. 4xx permits another attempt; uncertain errors keep this mounted form blocked until explicit reset. Refresh/re-entry loses flags. | Retain a create-request UUID and original payload across uncertain responses; a deliberate new action gets a new UUID. |
| BFF/API | `transport-policy.ts` POST jobs allowlist has company_id/name/title/jd_text only. `domain/schemas.py:JobCreate` has no request identity; an extra request_id is rejected. | Extend the allowlist, DTO and validation together. Reject same UUID with a different canonical payload. |
| Transaction | `api/dependencies.py:db` wraps service and projection in one transaction. `services.create_job` creates Company (if absent), Job, JD/requirements, Application, binding and initial event together. Diagnostic rollback leaves none. | Keep atomic creation and persist the identity/result in the same transaction. |
| Concurrency | A company-name advisory lock serializes exact trimmed-name reuse. Concurrent identical requests create different Jobs/Applications; a third replay creates a third pair. | Lock/uniquely constrain request identity; concurrency and committed-response-loss must return one result. |
| Separate identities | Company names are not globally unique; ambiguous existing names require explicit selection. No Job title/content dedup. Application.job_id is unique. | Preserve these independent business rules; do not use Company or Job matching as request idempotency. |

A minimal durable request/receipt row (request UUID, canonical payload hash, exact Job/Application
result) needs a new migration unless a suitable existing durable store is deliberately reused.
No existing JobCreate receipt was found. Test independent clicks, sequential/concurrent replays,
conflicting payload, atomic rollback, response loss and re-entry; no historical backfill is needed.
At that checkpoint, `test_application_closeout_audit.py` documented the gaps; round two replaced
those diagnostic assertions with target-behavior, concurrency and migration regressions.

## Application soft deletion: confirmed and bounded findings

| Status | Evidence / consequence | Minimal second-round work |
| --- | --- | --- |
| Implemented | `services.delete_application`: exclusive Application row lock, closed-only eligibility, deleted_at plus revision increment. Repeated delete returns 404. Lists, context and Summary hide/reject deleted owners. | Preserve current logical deletion and concurrent tracking serialization. |
| Unfixed | `profile_area/records.py:delete` (named profiles) and `profile_area/service.py:archive_profile` (snapshots) check direct Profile bindings without joining active Applications. `profile_area/api.py:archive_resume` does the same for Resume bindings. Named Profile, direct snapshot and Resume residual blocks reproduced independently. | Filter these checks to live owners while retaining active-binding protection and compatible locks. Do not erase bindings. |
| Important distinction | Modern Resume bindings store no direct Profile pointer (`product/bindings.py:update`); Profile context is derived from the immutable Resume source. Historical Profile/Resume/PDF references remain readable. | Do not turn all provenance into archive blockers. Preserve active direct Profile bindings, active Resume bindings, archive CAS and new-binding archive checks. |
| Unfixed | `services.job_view` selects application_id by Job without deleted_at. Job GET/list still project a deleted workspace ID; application layout resolves it to not-found. | Define unavailable workspace projection, update JobOut/decoder/link consumers, suppress invalid normal navigation. Keep Job/JD history. |
| Unfixed projection | `product/task_status.py` returns retained task results without owner-deletion state (isolated old-Fit status remains success while its Summary returns 404); `task-tracker.ts:taskDestination` combines the saved href and selection. TaskDetail keeps return/result links. | Reconcile deleted-owner availability with exact task/result links and existing acknowledged notifications; do not globally hide audit results. Browser reproduction of every old-notification variant remains pending. |
| Implemented admission | Preparation checks active_job under a shared row lock; Product operations check before dispatch. Draft dispatch/adoption rebuild context; Mock continue and Debrief create/retry/execute check active owners. Pending operation after deletion was rejected before a ModelCall. | Preserve admission and frozen result reads. Already-dispatched settlement and mid-call deletion across every service were not exhaustively fault-injected this round; add bounded race cases before claiming full lifecycle consistency. |
| Deliberate retention | Existing lifecycle tests keep Company, JD, binding and exact old Fit result after deletion. Existing adopted draft/receipt replay may return an already saved result without creating work. | Do not cascade-delete shared sources, clear bindings, rewrite snapshots or reinterpret historical reads as new execution. |

No migration is required merely to filter archive checks or repair projections. A new deletion policy,
physical erasure or business cleanup is outside the next-round recommendation.

## Documentation inventory for second round (before commit)

| File | Stale or missing material | Suggested update |
| --- | --- | --- |
| `frontend/README.md` | Saved-item execution reports contradicted this UI change. | Updated here; retain concise failures and exact actions. |
| `TODO.md` | Phase-3 ordinary Debrief fingerprint reuse/regenerate description; arbitrary multi-group subsets still pending; historical tailoring recovery assessment still pending. | Mark superseded scope precisely; multi-group is implemented. The four-result completion appears in the supplied handoff, but no matching formal completion record was found. Reconcile records without querying/replaying business recovery. |
| `docs/architecture.md` | The old “Ordinary Debrief create fingerprints…” section still describes cross-intent reuse; newer sections describe request identity v3. “Active Application bindings prevent deletion” omits the current residual-binding defect. | Reconcile old/new generation semantics and document corrected lifecycle only after second-round code. |
| `README.md` | Current Debrief section already describes independent intent; no Chinese README link exists. | Add request-idempotent Job creation and corrected deletion behavior only after implementation; retain final manual-acceptance caveat. |
| `docs/profile-workspace.md` | Current Resume-derived Profile binding is correctly documented; archive/deleted-owner behavior needs explicit closure. | Add the precise active-owner archive contract after the fix. |
| `CHANGELOG.md` | Needs bounded closeout facts, not a whole-milestone completion claim. | Minimal entry added here; reconcile the second-round changes before commit. |
| Chinese README | Only root `README.md` and `frontend/README.md` exist among project README files; no Chinese version or mutual links. | Add `README.zh-CN.md`, preserve English README and link both. Translate the project README only after code stabilizes. |

Five old reminders remain distinct: retired-code cleanup is deferred until after the milestone commit;
Job request idempotency is missing; Application archive/link lifecycle has confirmed gaps; Research
empty/removal has new isolated evidence but still awaits human acceptance; Fit removal has existing
production protection and this round's isolated deletion regression, not a new manual acceptance.
Neither Application nor Internal is marked finally accepted by this checkpoint.

## Executed verification

- Three new Debrief state regressions failed against the prior isolated build, then passed after UI cleanup.
- Frontend check (55 unit tests, lint, typecheck, format) and isolated production build passed.
- Related fixture browser suite: 14 passed; the three state fixtures were rerun after correcting the
  synthetic partial presentation. Real isolated backend/browser suite: 22 passed; two affected
  loading/empty-state cases additionally passed with full-page captures and zero-call assertions.
- Isolated PostgreSQL: 18 passed across closeout diagnostics, generated-result removal and Application
  lifecycle. Known-gap assertions are observations, not evidence of backend fixes. Ruff and formatting
  checks passed for the three affected Python test files. No backend production code changed.
- Full-page screenshots include 1280px and 375px; Debrief also covers 768px. Computed headings remain
  24px/600/32px and normal/failure body 16px/400/26px. No horizontal overflow in these cases.
- The first audit assumed a Resume binding also stored a direct Profile pointer; the corrected
  diagnostic tests distinguish the actual contracts. Browser helper corrections similarly separate
  task completion from input-form validity and preserve legitimate background notifications.
- No full-repository suite, live quality assessment or final Git submission review was performed.
