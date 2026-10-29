# Career Agent Web

Next.js App Router, React, strict TypeScript and Tailwind CSS v4. Dependencies are pinned
in `package.json` and `package-lock.json`. No UI component framework or external font service.
Dev/build explicitly use the supported Webpack path (Turbopack worker-port IPC is restricted
in this development environment). The Python application remains a separate service. Applications
and Summary retain server-side reads. Application business pages and Profile use an allowlisted Product BFF; Internal uses its separate server-only token BFF.

## Run and verify

Use Node >=22.13 (Node 22 is the CI baseline) and npm:

```sh
cd frontend
npm ci
# Set CAREER_AGENT_API_ORIGIN in frontend/.env.local (see .env.example).
# Run the existing FastAPI backend separately; do not copy its secret-bearing .env.
npm run dev
# http://127.0.0.1:3000
npm run check
npm run build
npm run start
# Optional browser verification, after build:
npx playwright install chromium
npm run test:browser
# Real backend/Typst tests with an isolated PostgreSQL database:
npm run test:profile-browser
```

`check` runs ESLint, generated Next route types + strict tsc, Node contract tests and Prettier.
Browser tests use the production Next server on 3100 and an isolated synthetic HTTP fixture
server on 3111. They exercise server-rendered API reads, filtering/pagination, context switching,
error/empty/history distinctions, explicit preparation operations, submissions, interview CAS/continuation, Debrief POST SSE and narrow-screen layout. They never use a real
provider or production database. Fixture code lives only in tests, never app/src.
Do not run dev/build concurrently against the same `.next` directory.

## Structure

```text
src/app/
  layout.tsx, globals.css       root document and design tokens
  (product)/                   Product shell: Applications / Profile
    applications/[applicationId]/
      summary, research-fit
      apply/{resume,greeting,submissions}
      interview/{preparation,mock,actual,history}
      review/{debriefs,knowledge-notes}
  (internal)/internal/         Internal shell: Operations / Evaluation
    operations/{overview,runs,incidents,controls}
    evaluation/{production-quality,test-runs,comparisons,calibration-triage}
src/components/
  layout/                      shell, route navigation, placeholder
  ui/                          typography, button/link, surface, input, badge
src/lib/
  navigation.ts                frontend route labels (not backend action enums)
  api/server.ts                Product-only server read transport (no Ops token)
  api/policy.ts                URL validation, no secrets
```

`/` redirects to `/applications`; section roots redirect to their first page. All Application
routes load and validate the explicit Application → current Job/JD → Company context, including
the business sections. Missing Application gives not-found; failed or mismatched joins
show a sanitized read error. No auto-selection of another Application.
There is no synthetic Application link, fake metric or implied business success. Generation requires an explicit user action; test adapters are not Product controls. Internal pages expose existing backend contracts; the BFF is **not** an authentication boundary.

## Visual basis

The checked-in global CSS tokens and shared UI components define the implemented warm neutral palette, serif headings and restrained surfaces. Product information architecture does not copy a chat demo.

- Original palette variables (`--bg`, `--surface`, `--surface-2`, `--primary`, `--primary-h`,
  `--primary-lt`, `--text`, `--text-2`, `--text-3`, `--border`, `--white`) retain exact values.
- `@theme inline` maps them to Tailwind utilities: `bg-canvas`, `bg-surface`, `bg-inset`,
  `bg-paper`, `text-ink`, `text-secondary`, `text-accent-ink`, `border-line`, etc.
- Original radii 14/8px and subtle shadow map to `rounded-panel`, `rounded-control`, `shadow-soft`.
- Body stays 15px/1.65; headings use modest 21px Georgia with explicit Chinese system fallback.
  Code values can use the monospace token. No font binary or runtime download.
- Error literals are named tokens. No invented success/warning palette or backend-status badges.
- Extensions are explicitly new: responsive wrapping navigation, 44px control targets, a 1200px
  shell with 760px reading surfaces, skip link, visible focus and reduced-motion support.
- Pale `--text-3` is decorative only; important small text uses `--text-2`. Small selected labels
  use darker `--accent-ink` (#98472f); filled text buttons use original `--primary-h` for readable
  white text. Accent remains terracotta, not a new theme. Full accessibility audit is later work.

## API / Ops boundary

`.env.example` documents server-only config. Do not copy the backend root `.env` into frontend,
use `NEXT_PUBLIC_*` for secrets, or add secrets to `next.config.env`.

`lib/api/server.ts` imports `server-only`: Next rejects Client Component imports. UI/shell imports
are additionally prohibited by ESLint. The Product transport only reads JSON, requires a caller
provided decoder, uses `no-store`, disallows redirects, has a bounded timeout, never retries, and
returns sanitized errors rather than raw backend bodies. No endpoint/field schema is invented.

Before any feature integration, read the actual FastAPI contract. Add an explicit feature server
module or allowlisted BFF handler, not a catch-all proxy. The Internal BFF is separate
from this Product reader and injects credentials server-side; never pass headers/config/credentials
to a Client Component. Product code does not read the Ops token. Existing Ops controls and CAS remain
unchanged. `app/api/product/[...path]/route.ts` is an explicit path/method/query/body-key allowlist, not arbitrary forwarding. It checks Origin against the browser Host for JSON writes, never copies browser credentials or Ops headers upstream, sanitizes error bodies, and streams only accepted PDF responses and the existing Debrief POST SSE. No new auth/session system is introduced.

Before deployment, the BFF itself must be local/private or behind deployment access protection;
an unauthenticated public proxy would lend its server credential to anyone. Private evaluation
snapshots are not ordinary logs. Lists expose metadata; frozen/private evaluation payload is restricted to explicitly allowlisted detail contracts.

## Applications read-only contract

Feature-local `features/applications/contracts.ts` validates consumed response fields at runtime
and strips unused bodies. `repository.ts` composes reads; `server.ts` provides the only production
reader and request-scoped React cache for shared layout/Summary context. There is no persisted
frontend cache, generic proxy, client-side backend fetch, or new backend aggregate endpoint.

| Existing GET API                                 | Use                                                              |
| ------------------------------------------------ | ---------------------------------------------------------------- |
| `/api/v1/applications`                           | Company/status filters, 20-row pagination; backend `has_more`    |
| `/api/v1/applications/{id}`                      | Exact Application status/revision and events                     |
| `/api/v1/jobs/{id}`                              | Current Job/JD/title/requirements and Company association        |
| `/api/v1/companies`, `/companies/{id}`           | Company-name lookup (10 options/page) and exact context          |
| `/api/v1/companies/{id}/research`                | Latest historical research metadata; mode and backend reuse flag |
| `/api/v1/applications/{id}/preparation-packages` | Up to 3 recent package records, exact historical JD/Profile refs |
| `/api/v1/applications/{id}/submissions`          | Latest actual submission and exact material refs                 |
| `/api/v1/mock-interviews?application_id=...`     | Latest Mock metadata                                             |
| `/api/v1/interviews?application_id=...`          | First recorded Actual Interview (API is oldest-first)            |
| `/api/v1/interview-debriefs?application_id=...`  | Latest generation metadata, separate selected identity           |

Filters live in the URL (`status`, `company_id`, `page`; company lookup uses `company_q`,
`company_page`). Company text search finds choices; a company must then be selected to filter
Applications. Changing a filter resets Application pagination. Unknown status/bad UUID/duplicate
query params fail visibly rather than silently showing all records. No invented title-search API.

List reads join each page with Job details in batches of at most five. Workspace links show the
first eight same-company Applications; a filtered, paginated list exposes the rest. One Job still
means one Application. Switching always opens the chosen Application's Summary. Business pages inherit its validated header/navigation; navigating or reading never starts generation.

Summary has independent read/error/empty states for each existing resource. No total counts are
inferred from limited pages, no progress/fit score, no selected/current material inference.
Application events are sorted by their sequence (last five); dates use Asia/Shanghai. Current JD
text is escaped plain text in a disclosure. Historical package JD refs are not rewritten to the
current JD. The latest research history row is not automatically the current compatible report.
Actual Interview's first row is explicitly called first-recorded, never latest interview.
Reconciliation, retry, provider calls and writes are never triggered by these pages.

## Application business workflows

All paths below are existing `/api/v1` contracts; browser requests use same-origin `/api/product/...`.

| Area             | Existing endpoints / behavior                                                                                                                                                                                                                              |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Company Research | `GET companies/{id}/research[/current]`, `POST companies/{id}/research`; company-level current/history, mode, freshness/compatibility and source evidence. Force refresh is explicit.                                                                      |
| Preparation      | `POST operations`, `POST operations/{id}/execute`, `GET operations[/{id}]`; stable identity is committed before execution. Separate target requests for Fit, Tailoring, Greeting, and explicit `prepare_interview`.                                        |
| Results/history  | `GET applications/{id}/preparation-packages`, `GET preparation-artifacts/{id}/product-view`, `GET job-revisions/{id}`; exact historical context, Fit requirement text, source Resume and reuse. No Greeting revision lineage or selected material pointer. |
| Resume           | `GET resume-workspaces`, `GET resume-library/versions`, workspace/edition/resolve/render endpoints; stable library entries, exact source binding and accepted PDF preview/download.                                                                        |
| Submissions      | `GET/POST applications/{id}/submissions`; explicit actual-use confirmation, expected Application revision, stable request UUID, exact Resume/PDF and optional Greeting/package. Only this action records applied according to backend lifecycle rules.     |
| Mock             | `POST mock-interviews`, `GET mock-interviews[/{id}]`, `POST .../{answers,generate,end}`; frozen context, policy quotas, immutable accepted answers, generation-only retry and early end.                                                                   |
| Actual           | `GET/POST interviews`, `GET/PATCH interviews/{id}` and entry/note APIs; draft/completed records, grouped editing and CAS.                                                                                                                                  |
| Debrief          | `GET/POST interview-debriefs`, `GET .../{id}?historical=true`, `POST .../{id}/{execute,regenerate}`, `GET .../{id}/events`; frozen source, exact generation response, selected/history, independent group/overall.                                         |
| Knowledge        | `GET applications/{id}/knowledge-notes`, `POST knowledge-notes`; Application scope, creation, CAS editing, soft deletion and paginated reads.                                                                                                              |

Forms never implicitly choose a Resume. Previously selected exact Resume bindings may be restored
only when still present in the compatible choices. Product defaults to live execution (which may incur
provider costs); fixture adapters remain test-only. Automated acceptance uses
synthetic HTTP fixtures, not paid providers or claims about generated job-search quality.

Preparation creates and executes a durable operation in one user action. Refresh/re-entry can discover
committed operations for the current JD; historical packages remain readable across JD changes.
Execution is synchronous, not a durable background task. Interrupted requests must be queried;
needs_input/decision_required/recovery_required remain distinct. No automatic mutation retry.
A repeated unchanged form uses the same request UUID; starting another explicit request creates a
new identity. Mock continuation uses revision + pending question ID + request UUID.

Previous Interviews has separate Mock and Actual list/detail views with their backend ordering and
pagination, not a merged timeline. Actual draft editing supports grouped questions and editable notes. CAS conflicts keep drafts and require an explicit reread; there is no automatic overwrite.

Debrief streams persisted business events via POST fetch, not EventSource/token streaming. Completed
artifacts are reread after notifications, displayed by group order with Overall last, independent of
completion order. Disconnect has no promise of background continuation; query persisted results/events.
Regenerate binds the exact frozen generation and returns a new run, not negative feedback.

Material-use badges derive from exact Submission records. Task histories expose successful business
artifacts rather than a mixed preparation-package list. Library saves retain stable user-visible
entry identity while exact historical revisions remain available to bindings and provenance.

Profile/Resume data is selected through the corresponding source/binding contracts. Company research
does not require personal data. There are no automatic sends/submissions or unified interview timeline.
Application and Internal pages are implemented with offline regressions, but await later manual acceptance.

## Internal Dashboard contracts

All browser traffic uses `/api/internal/...` with `X-Internal-Request: 1`. The Next route handler
injects `CAREER_AGENT_OPS_TOKEN` as `X-Ops-Token` on the server only. It rejects missing cross-origin
intent, checks same-origin JSON mutations, validates explicit method/path/query/body-key allowlists,
uses `no-store`, rejects redirects and returns only sanitized error codes. No browser Authorization,
cookie, token or arbitrary upstream URL is forwarded. Missing server configuration fails closed.

This is **not browser authentication**. The single-user Next server and the FastAPI server must remain
local/private or behind deployment access protection. Existing legacy Evaluation detail/write routes
are not all backend-token-protected; adding a BFF does not secure a directly public backend. No new
multi-user authentication system is introduced. Product requests never receive the Ops credential.

| Internal page        | Actual backend resources (all under `/api/v1`)                                                                                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview             | GET `ops/controller`, `ops/metrics?window_seconds=...`, `ops/events?after=...&limit=...`                                                                                                                                |
| Runs                 | GET `runs` (kind/workflow/status + pagination), `runs/{id}`, `/steps`, `/calls`; agent-only `agent-runs/{id}`, `/plans`, `/observations`; exact `ops/attempts/{attempt_id}` lookup                                      |
| Incidents & Recovery | GET `ops/attention` (source/status/include_resolved + pagination), `ops/recovery-incidents`, `operations/{id}`, `runs/{id}`, `ops/attempts/{attempt_id}`; POST attempt `/reconcile`                                     |
| Controls             | GET controller/events; POST `ops/controls` with override/clear_override/kill/global_kill/tick, exact CAS revisions and request UUID                                                                                     |
| Production Quality   | GET `evaluation/sampling-records`, `/judges`, `/judges/{id}`, `/feedback`; Ops global quality population; explicit POST `/judges/drain`                                                                                 |
| Test Runs            | GET `evaluation/case-index`, `/suites`, `/suites/{id}`, `/runs`, `/runs/{id}`, `/trials`, `/trials/{id}`, `/operations/{id}`, `/cases/{id}/origin`, `/cases/{id}/export`; POST cases/suites/runs and run execute/cancel |
| Comparisons          | GET/POST `evaluation/comparisons`, GET `/comparisons/{id}`                                                                                                                                                              |
| Calibration & Triage | GET/POST `evaluation/annotations/queue`, GET/POST queue detail, GET calibration; GET captures/detail/sanitized, POST triage/promote                                                                                     |

### Reading and execution semantics

- Overview shows a current snapshot plus a selected bounded aggregation window, not time series.
  Provider base capacity is visible; the API exposes route effective counters, not a full live
  provider-header quota feed. Three cache/reuse populations are kept separate. Unknown usage and
  actual billed costs remain unknown; parent/child run totals are never summed by the UI.
- Run/step/call/agent views use independent authoritative APIs. No fabricated journal join or unified
  trace is inferred. Per-step schema status/version metadata is shown where returned; unavailable
  detailed guardrail diagnostics are not invented. Events use their sequence cursor.
- Attention rows preserve `source`, `category`, IDs and allowed actions. Related run/attempt/incident
  rows are not summed as unique incidents. Reconcile uses the selected incident revision; unknown
  execution is not automatically replayed. Controls use explicit confirmation and stable request IDs.
- Override exposes only `pressure`, `concurrency`, `output_reservation`, `sampling_rate` and TTL.
  There are no routing, candidate priority, arbitrary RPM/TPM or manual circuit controls.
- Eval create freezes backend CandidateConfig; execution is a separate explicit action. Current HTTP
  EvalRunner and JudgeRunner use fixture providers by default. The UI has no invented paid mode.
  Origin re-execution requires explicit diagnostic intent and preserves unavailable outcomes.
  Advanced case/suite/fault/limit/annotation/promotion contracts use labelled JSON editors; backend
  Pydantic remains authoritative. Invalid JSON does not issue a request.
- EvalRun/trial ordinary views omit output bodies; invocation ordinary views omit input/output;
  origin ordinary views omit frozen source/input/output/external bodies. Explicit private review can
  load an invocation/origin or blind annotation subject, and closing it unmounts the content.
  Captures always return metadata/events through this BFF; only explicit sanitized export returns
  a sanitized payload. Promotion remains explicit and requires backend repo-safe validation.
- Blind annotation does not fetch Judge results. Calibration is hidden/disabled while a blind subject
  is open. The API returns annotation IDs but has no annotation history query. Queue detail does not
  supply complete Subject provenance: the operator must supply exact task/call/operation identity.
- Quality discovery and Ops quality populations are **global**, not guaranteed production-only;
  the backend has no origin filter on Judge discovery. Use task/subject filters and do not describe
  the global population as uncontaminated production traffic. Ratings/severity/confidence remain
  categorical; comparison headlines/gates/dimensions remain unchanged.

### Current limitations

No full attempt journal discovery, unified run/journal detail, complete telemetry time series,
annotation history API, or production-only quality filter is invented. Recovery incident direct list
is limited to 100 recent rows; paginated attention discovery is the broader entrypoint. Array-based
steps/annotation queue queries use explicit next-page probing because those APIs lack `has_more`.
The frontend does not promise background execution after disconnect, automatically retry mutations,
or add missing backend recovery capabilities. Complex frozen cases and promotions require explicit
canonical contract input rather than guessing missing authoritative source data.

Tests use isolated synthetic HTTP fixtures only; no paid provider, real external service or production
state is accessed. Internal browser tests cover token isolation, privacy projections, snapshot/window
metrics, exact run provenance, control CAS, reconciliation, frozen Eval execution, comparison coverage,
blind annotation and capture review, plus desktop/mobile layouts.

## Empty-account Product entrypoints

`/profile` starts without a selection. Users create/select named records, edit the whole document,
save local sections/items into a persisted edit session, then commit or cancel globally. Internal
snapshots are immutable but not user-managed history. Inline renaming is independent of body editing.

`/profile/resumes` uses one selector of stable library entries. Quick/AI creation both save and select
a Resume; ordinary content/presentation/compression saves update the same entry. AI optimization adds
a separate named entry with exact parent lineage. Facts are not a Product prerequisite; the former
Facts route redirects. Source validation remains authoritative for AI claims and PDF rendering.
PDF uses explicit expression/visibility/order settings; overflow never silently shortens or deletes
content. See [workspace contracts](../docs/profile-workspace.md).

Profile workspace manual acceptance has passed. The accumulated Application and Internal surfaces
remain pending subsequent manual acceptance. Offline adapters do not certify live model quality.

Applications has a new-job entry: search/select an exact Company or explicitly create another, enter
title/JD and optional requirements, then make one `POST /jobs`. The returned Application ID opens the
workspace. No name deduplication or automatic retry is performed. Summary exposes legal state changes,
explicit corrections with reason, CAS-conflict refresh and append-only notes. Changing status is not a
material Submission; generating material never changes tracking state.

The empty-state browser fixture starts with no Profile, facts, Resume, Company, Job or Application.
It verifies onboarding into existing preparation/interview/review UI through the actual Product BFF.
Model execution and PDF output remain synthetic fixture results; this is not live model, real database
or Typst quality acceptance. STAR, SourceDocument, JD editing and file imports remain out of scope.

## Checkpoint acceptance

Profile workspace has passed user manual acceptance. Application and Internal implementations are
included, with offline regression coverage, but still await their subsequent manual acceptance.
Use `./cgstart` from the repository root for the checked local supervisor; standalone commands above
remain supported. No UI test here invokes paid providers.

## Retired Facts surface

The unused Facts and legacy Profile onboarding components are removed. The Product BFF no longer
allows manual Facts management or Resume review/publish. The old Facts URL remains a redirect.
Active Resume resolve/render, shared Draft actions and refinement keep their existing contracts.
The actual source/grounding validators are exercised by the real-backend suite, not by HTTP fixtures.
