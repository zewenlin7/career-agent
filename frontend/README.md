# Career Agent Web

Next.js App Router, React, strict TypeScript and Tailwind CSS v4. Dependencies are pinned
in `package.json` and `package-lock.json`. No UI component framework or external font service.
Dev/build explicitly use the supported Webpack path (Turbopack worker-port IPC is restricted
in this development environment). The Python application remains a separate service. Applications
retain server-side context reads; Summary uses a read-only aggregate through the Product BFF. Application business pages and Profile use an allowlisted Product BFF; Internal uses its separate server-only token BFF.

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
The fixture browser suite uses the production Next server on 3100 and an isolated synthetic HTTP fixture
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
      summary, research-fit/{description,company,fit}
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
the business sections. A valid but missing/deleted Application gives an explained unavailable-workspace page; invalid UUIDs
remain not-found. Failed or mismatched joins show a sanitized read error. No auto-selection of another Application.
There is no synthetic Application link, fake metric or implied business success. Generation requires an explicit user action; test adapters are not Product controls. Internal pages expose existing backend contracts; the BFF is **not** an authentication boundary.

## Visual basis

The checked-in global CSS tokens and shared UI components define the implemented warm neutral palette, serif headings and restrained surfaces. Product information architecture does not copy a chat demo.

- Original palette variables (`--bg`, `--surface`, `--surface-2`, `--primary`, `--primary-h`,
  `--primary-lt`, `--text`, `--text-2`, `--text-3`, `--border`, `--white`) retain exact values.
- `@theme inline` maps them to Tailwind utilities: `bg-canvas`, `bg-surface`, `bg-inset`,
  `bg-paper`, `text-ink`, `text-secondary`, `text-accent-ink`, `border-line`, etc.
- Original radii 14/8px and subtle shadow map to `rounded-panel`, `rounded-control`, `shadow-soft`.
- Base `body` CSS remains 15px/1.65; the original shared `PageHeading` remains 21px with relaxed
  leading and Georgia/Chinese system fallback. These are defaults, not a universal business-role spec.
- Accepted Research/Fit/Apply/Interview/Review body roles override the base with 16px/400/26px
  (`text-base leading-relaxed`); Interview/Review primary headings use 24px/600/32px. Summary has
  its own 16px body and 20px/700 card-title roles. Reuse the same role/component, not an unrelated
  page's base size. This documentation change does not alter CSS or already accepted pages.
- Code values use the monospace token. No font binary or runtime font download.
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
reader and request-scoped React cache for shared layout context. Summary uses the allowlisted
`GET applications/{id}/summary`; there is no persisted frontend data cache or generic proxy.

| Existing GET API                                | Use                                                              |
| ----------------------------------------------- | ---------------------------------------------------------------- |
| `/api/v1/applications`                          | Company/status filters, 20-row pagination; backend `has_more`    |
| `/api/v1/applications/{id}`                     | Exact Application status/revision and events                     |
| `/api/v1/jobs/{id}`                             | Current Job/JD/title/requirements and Company association        |
| `/api/v1/companies`, `/companies/{id}`          | Company-name lookup (10 options/page) and exact context          |
| `/api/v1/companies/{id}/research`               | Latest historical research metadata; mode and backend reuse flag |
| `/api/v1/applications/{id}/summary`             | Ten-card aggregate with exact results, totals, notes and records |
| `/api/v1/applications/{id}/submissions`         | Latest actual submission and exact material refs                 |
| `/api/v1/mock-interviews?application_id=...`    | Latest Mock metadata                                             |
| `/api/v1/interviews?application_id=...`         | First recorded Actual Interview (API is oldest-first)            |
| `/api/v1/interview-debriefs?application_id=...` | Latest generation metadata, separate selected identity           |

Applied filters live in the URL (`status`, repeated `company_ids`, `page`); legacy `company_id`
links remain accepted. Status changes and company tags stay pending until **筛选** is clicked.
Company lookup is separate, debounced and IME-aware; selecting a candidate clears the input and
adds a deduplicated tag. Company IDs are OR-ed, then AND-ed with status before backend pagination.
**清除筛选** clears pending/applied conditions and returns to page one immediately. Paging uses
only applied filters; single-page results omit pagination controls. UUIDs and the 50-company bound
are validated. No invented title-search API.

List reads join each page with Job details in batches of at most five. Workspace links show the
first eight same-company Applications; a filtered, paginated list exposes the rest. One Job still
means one Application. Switching always opens the chosen Application's Summary. Business pages inherit its validated header/navigation; navigating or reading never starts generation.

Summary uses five rows of two cards, with fixed-height scrolling notes/records. It reads latest
successful saved artifacts by task and expired-but-readable research independently from execution
reuse. Links select exact results, frozen Resume/PDFs, Mock sessions and readable Debrief generations.
Formal Actual records are ordered by creation; Debriefs count independent roots, not generations.
Only JD-dependent results receive a stale-description hint based on exact revision inequality.
Dates use Asia/Shanghai, `YYYY-MM-DD HH:mm`; internal JD numbers are not shown. Returning to Summary
queries persisted state again. Reads never execute models, recovery or retries.

## Application business workflows

All paths below are existing `/api/v1` contracts; browser requests use same-origin `/api/product/...`.

| Area             | Existing endpoints / behavior                                                                                                                                                                                                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Company Research | `GET companies/{id}/research[/current]`, `POST companies/{id}/research`; company-level history and exact reads; explicit generation always forces search and report refresh.                                                                                                                      |
| Preparation      | `POST operations`, `POST operations/{id}/execute`, `GET operations[/{id}]`; stable identity is committed before execution. Separate target requests for Fit, Tailoring, Greeting, and explicit `prepare_interview`.                                                                               |
| Results/history  | `GET applications/{id}/preparation-packages`, `GET preparation-artifacts/{id}/product-view`, `GET job-revisions/{id}`; exact historical context, Fit requirement text, source Resume and reuse. Result names resolve the exact target and its library entry; historical content remains frozen.   |
| Resume           | `GET resume-workspaces`, `GET resume-library/versions`, workspace/edition/resolve/render endpoints; stable library entries, exact source binding and accepted PDF preview/download.                                                                                                               |
| Submissions      | `GET/POST applications/{id}/submissions`, `PATCH/DELETE applications/{id}/submissions/{submission_id}`; recording explicitly confirms actual use, with Application CAS and exact materials. Note/deletion overlays use Submission CAS, stable request IDs and audit history.                      |
| Mock             | `POST mock-interviews`, `GET mock-interviews[/{id}]`, `POST .../{answers,generate,end,recover}`; frozen context, policy quotas, immutable accepted answers, generation-only retry and early end.                                                                                                  |
| Actual           | `GET/POST interviews`, `GET/PATCH interviews/{id}` and entry/note APIs; draft/completed records, grouped editing and CAS.                                                                                                                                                                         |
| Debrief          | `GET/POST interview-debriefs`, exact `GET .../{id}?historical=true`, `DELETE .../{id}`, `POST .../{id}/{execute,retry}`, `GET .../{id}/events`; frozen source, selected primary groups plus independent full-source overall, durable create/retry identities. Legacy regenerate remains API-only. |
| Knowledge        | `GET applications/{id}/knowledge-notes`, `POST knowledge-notes`; Application scope, creation, CAS editing, soft deletion and paginated reads.                                                                                                                                                     |

Forms never implicitly choose a Resume. Previously selected exact Resume bindings may be restored
only when still present in the compatible choices. Product defaults to live execution (which may incur
provider costs); fixture adapters remain test-only. Automated acceptance uses
synthetic HTTP fixtures, not paid providers or claims about generated job-search quality.

### Review workspace contracts

Debrief creation and result reading are independent. The centered typed Interview selector groups
Mock/Actual candidates by stable type+ID, clears source revision/groups on change, and reads all pages.
Review only offers completed Actual and ended non-active Mock sessions; History uses the same picker
without narrowing its readable candidates, preserving exact edit/continue routes. History remains left aligned.

Content defaults to group+overall. Group scope is all or a nonempty multi-selection of primary IDs;
disabling group analysis omits retained selection state from the request. One target per selected group
includes follow-ups, and overall always uses the complete snapshot. A request receipt and execution
revision separate failed-task identity from the current creation form. Retry restores valid accepted
outputs first, otherwise explicitly retries only known retryable failures within original cumulative
budgets. Unknown results only query status. SSE interruption preserves committed results and stops calls.

Completed/partial generations refresh into the independent all-page history selector, auto-select exact
identity, and never backfill creation controls. User history selection wins over late execution responses.
Browsing never calls models. Request-intent and retry behavior is detailed below. Frozen Q&A/notes are collapsed
by default. Findings retain exact entry refs and frozen numbering; links expand and locate that snapshot.
Only unambiguous single-entry redundant refs are hidden; uncertain legacy refs are not inferred. Source
change compares Q&A/order/parents/notes, excluding revision and metadata-only edits.

Delete operates on the selected generation from its first section heading, with the shared danger-outline
button/dialog. Rejection preserves selection/body. Success updates history/Summary/selected fallback;
deleted exact links fail explicitly. Frozen outputs, costs and audit survive; active execution and real
external references block deletion. Root/selected/supersedes relationships alone do not block it.

Knowledge Notes load all pages into a normal-scrolling list, sorted by real modification time (creation
fallback) and stable ID. Persistent EntryMenu opens edit/delete; a single shared editor replaces the list.
Create UUID prevents duplicates after response loss; edit retains ID and revision CAS, unchanged content
does not change revision/time. Dirty cancel and soft-delete use application dialogs. Legacy timestamps
stay unknown rather than receiving fabricated backfill; Application and reliable legacy Actual ownership
remain authoritative. Headings use 24/600/32 and body 16/400/26, with normal-weight selects.

Preparation creates and executes a durable operation in one user action. Refresh/re-entry can discover
committed operations for the current JD; historical packages remain readable across JD changes.
The initiating tab retains the operation identity for read-only re-entry; leaving a client route does
not cancel or replay execution. Application navigation reads do not take the execution admission/write
locks. Execution is synchronous, not a durable background task. Interrupted requests must be queried;
needs_input/decision_required/recovery_required remain distinct. No automatic mutation retry.
A repeated unchanged form uses the same request UUID; starting another explicit request creates a
new identity. Mock continuation uses revision + pending question ID + request UUID.

Interview history uses the shared read-only `InterviewChoiceSelect`: one record selector grouped by
Mock/Actual, identified by type+ID. It loads all backend pages and preserves exact
links; editing an Actual record opens the intake page and returns to that record on save/cancel.
Intake creates a complete record atomically using a request UUID, or updates the same record with
content-revision CAS. No-op writes retain the saved time and legacy note structure. Legacy drafts remain
readable/editable. Current question numbering follows display order; existing Debrief snapshots do not change.
Mock lists use explicit ownership or the [verified legacy resolver](#legacy-interview-ownership).
Missing reliable evidence never permits guessing ownership from a Job or display name.

Debrief streams persisted business events via POST fetch, not EventSource/token streaming. Completed
artifacts are reread after notifications, displayed by group order with Overall last, independent of
completion order. Disconnect has no promise of background continuation; query persisted results/events.
The legacy regenerate API binds the exact frozen generation; Product has no regeneration control.
Each acknowledged “开始复盘” intent creates a new generation; only an uncertain create response retains
its request identity for retransmission. History selection is read-only and never substitutes input reuse
for a new analysis. The current execution area offers explicit failed-only retry over its frozen input.
Feedback belongs to the exact generation: generic navigation has no stored failure restoration; selecting
a partial/failed history shows its actions beside that record. Clearing/changing selection detaches old
feedback, without cancelling execution. Exact task/result URLs support refresh. Late responses cannot
replace a later history selection or newer intent. Terminal discovery refreshes history independently
of visible selection, including an exact task completing after the user cleared or left its result.
Confirmed invalid evidence is retryable only by that explicit action; successful targets are retained.
Accepted output is recovered before redispatch, unknown calls are read-only, and budget blocks are not
labelled unknown. One exact execution area shows lightweight loading or concise actionable failure
reasons, never saved-item lists or a persistent completion summary. Saved chapters remain visible as
they arrive; missing result sections use short status text. “检查状态” reports an update or unchanged state and never generates.

Selected-group scope uses a collapsed multi-select (primary group identities in frozen order), two-line
question excerpts, follow-up counts and optional full-group expansion. No valid source means no picker.
Its trigger and expanded options share one continuous border. Note titles and persistent inline menus
span the full entry width, with the menu at the right edge. Source changes clear selection;
all-group or overall-only requests omit hidden selections. No new backend selection contract.

Exact foreground/background acknowledgement is shared with [cross-page task feedback](#cross-page-task-feedback).

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

Applications has a new-job entry with one Company name autocomplete and title/raw JD. Selecting a candidate binds its ID; editing the name clears that ID. `POST /jobs`
validates an explicit ID/name, otherwise reuses only a unique exact trimmed-name match, rejects
ambiguous matches, or creates a new Company. Similar names are not merged. The returned Application
ID opens the workspace. Submission is guarded against repeated clicks and is never automatically
retried automatically after an uncertain response. Durable UUID/hash identity and refresh recovery are
defined in [creation and reachability](#application-closeout-request-and-reachability-contracts).
Summary exposes six directly selectable states and optional comments, with CAS conflicts retaining
input. Notes and status comments use append-only audit overlays for user-visible edits/removals. Changing status is not a
material Submission; generating material never changes tracking state.

The empty-state browser fixture starts with no Profile, facts, Resume, Company, Job or Application.
It verifies onboarding into existing preparation/interview/review UI through the actual Product BFF.
Model execution and PDF output remain synthetic fixture results; this is not live model, real database
or Typst quality acceptance. STAR, SourceDocument and file imports remain out of scope.

## Checkpoint acceptance

Profile workspace has passed user manual acceptance. Application and Internal implementations are
included, with offline regression coverage, but still await final manual acceptance. Limited real Mock
next-main/targeted-follow-up and Debrief retry/new-analysis success were user-confirmed; they do not
complete broader model-quality or whole-workspace acceptance.
Use `./cgstart` from the repository root for the checked local supervisor; standalone commands above
remain supported. No UI test here invokes paid providers.

## Retired Facts surface

The unused Facts and legacy Profile onboarding components are removed. The Product BFF no longer
allows manual Facts management or Resume review/publish. The old Facts URL remains a redirect.
Active Resume resolve/render, shared Draft actions and refinement keep their existing contracts.
The actual source/grounding validators are exercised by the real-backend suite, not by HTTP fixtures.

### Application JD and closure

Research & Fit edits the full job description through `PUT applications/{id}/jd`, with both Job and binding revisions.
The new immutable JD and the owning Application default commit atomically; unchanged text is a
no-op and new revisions start without copied requirements. Historical results retain exact inputs.
Creation and JD saving never invoke models; later explicit preparation performs extraction.

Only closed cards offer `DELETE applications/{id}`. The backend locks/rechecks current state and
soft-deletes the Application; shared objects and historical artifacts remain. Deleted workspaces
and new business actions are blocked. There is no Product restore action. Deletion refreshes the
applied filters and redirects empty pages backwards to a valid page.

### Summary entry editing

User notes are explicitly attributed; system Submission notes and unknown legacy notes are not
editable user notes. Status-event removal does not alter current status, and creation is read-only.
The card-local menu supports edit/delete, save/cancel, Enter save, Shift+Enter newline and IME-safe
composition. Blur retains input. All normally visible entries are scrollable without a five-row cap.
New notes and overlay writes carry request identity; no uncertain write is automatically repeated.
Frozen Resume navigation uses `resume-revisions/{id}/snapshot` with an optional exact PDF ID; the
backend validates their association. Result links use `preparation-artifacts/{id}/result` scoped to
Application, and company research detail validates company ownership. BFF routes remain explicit.

### Research & Fit subpages

`research-fit/description`, `research-fit/company`, and `research-fit/fit` are accessed through the
Research & Fit primary navigation menu (hover, click and keyboard). Apply, Interview and Review
reuse this menu with their existing subroutes; no permanent second navigation row.
The former `research-fit` entry redirects to description, or company/Fit when an exact research/result
parameter exists. Summary links directly to the corresponding subpage. Exact selection survives URLs
and browser navigation; reads never execute tasks.

JD uses the existing atomic revision/binding CAS write, equal-width auto-growing editing, and exact
revision creation time. Company research history loads all pages, including expired reports, sorted
like Summary; it does not prefer execution-current over the latest readable report. Explicit reads
retain a failed selection and offer retry. Generation forces both report and observation refresh,
while operation replay remains idempotent. Evidence is retained server-side; Product shows source
links rather than the full search snippets/expiry controls.

Fit inputs precede the action, complete matching-history selector and exact result. New results show
one explanation; historical missing-evidence text remains available in a secondary disclosure instead
of being concatenated into a claimed de-duplicated explanation. The four classifications and source
references are unchanged. Offline regressions do not establish live model quality.

Fit input selections remain mounted when an exact result is selected. Each completed explicit action
advances its request identity; retrying an unresolved request retains its identity. A new operation may
legitimately reuse an exact compatible artifact: the UI selects it and briefly reports reuse without
adding history or changing its original time. Failures preserve input and the previously readable
result. Returning during execution reads the original durable operation without resubmitting it.

### Apply material lifecycle

Resume optimization and Greeting separate the centered new-generation action from the left-aligned
record selector and naturally scrolling result. Source lines appear only at the new-generation action;
see [source labels](#generation-source-labels). Successful tailoring and Application
Resume refinement are automatically saved to the library; the optional centered replacement dialog
only changes the Application binding. Resume history labels use the linked library name, including
later renames. Accepted output with a failed save supports an explicit save retry without generation.
Fit reuse feedback is scoped to the selected exact result, dismissible, and lasts six seconds.

New submissions start with no Resume and no Greeting. Resume choices span available library entries;
Greeting choices include all readable results of this Application, independent of the chosen Resume.
The Record action confirms actual delivery, never sends anything, and clears inputs only after success.
Submission history preserves exact Resume/PDF/Greeting links, stable numbers and original recording
time. Notes can be edited and mistaken records hidden through audited CAS writes. After removing the
last record, a separate confirmation may move an applied Application to tracking; cancellation retains
both the deletion and its current status. Single-page history has no pagination controls.

Application material generation has one centered action with exact links to the materials actually
consumed, as listed in [source labels](#generation-source-labels). Execution
errors belong to the initiating control and never replace the previous readable artifact. Greeting
and Interview Prep refinement/regeneration auto-adopt on the server. The triggering regenerate button alone shows progress; navigation remains available.

`GET/DELETE applications/{application_id}/greetings/{target_id}` checks all historical Submission
references, including removed submissions. Deletion appends a visibility tombstone and returns stable
submission numbers when blocked. Exact historical reads and Eval references remain intact. Available
result lists and reuse exclude hidden Greetings and archived library Resumes before pagination.

### Cross-page task feedback

The Product shell tracks explicitly started operation, draft, Mock and Debrief handles in browser
local storage. Its allowlisted `task-status` reads contain state and exact selection parameters,
not generated bodies. Success, reuse, cancellation, failure, pending adoption and unknown outcome
are distinct. Reads never execute/adopt/retry. Closing a message acknowledges only that observed
state; a later definitive state remains visible. Browser storage clearing and another device do not
share local unread handles. Debrief route unmount is not an implicit cancel action.
Notifications float at the bottom right without changing document layout. One new notice is shown
for eight foreground seconds (paused by hover/keyboard focus), then collapses to an unread-count button.
Each popup reconciles pause state with live DOM targets: removing the previous notice cannot retain
stale focus/hover, and pointer focus on the bell does not freeze a later popup. Manually opened lists
have no automatic collapse timer.
Shown and handled states are separate browser-local values: automatic collapse, opening the inbox
and outside clicks do not acknowledge a notice. Closing it or following a successful exact result
handles it; the Debrief execution-state link also acknowledges the shown notice. Failures contain
the same safe action-specific reason as the originating execution area. Debrief failure/unknown
notices can link to their exact execution state. Other failure notices do not
invent a generic error-only destination. Dialogs remain above the notification layer.

Mock task status reads include the exact request identity. On the originating page, execution
failures stay in the existing operation area; the shell shows their completion notice after navigation,
so the same failure is not duplicated alongside the form. Notification handles contain no task bodies.

Debrief and Mock foreground acknowledgement follows exact rendered task/request state, not merely the
route. Receipt-before-render is deferred until the page catches up or the user leaves. Away/background
completion remains queued once; acknowledged transitions stay acknowledged. Debrief execution revisions
reject stale polls; exact committed success cannot regress to a delayed unknown response. A Mock handle
may precede server receipt creation: absence means pending, while an existing outcome-less receipt stays
unknown. This does not dispatch, retry or infer another request's success.

Deleted-owner reachability is orthogonal to task success; see
[creation and reachability](#application-closeout-request-and-reachability-contracts).

### Interview source and removal contracts

New interview inputs project the exact bound Resume through its saved visibility/compact-expression
configuration. Profile/evidence identities remain internal validation inputs; hidden experiences and
unselected long expressions do not enter the model. Prep can use a compatible exact same-company report
or no research; browsing never searches. Its refinements reuse the recorded `interview_context`, not
current bindings. Old results remain readable; an incompatible frozen source cannot silently reexecute.

Mock creation accepts `request_id`. Answers are committed before generation; failures retain accepted
answers and the same next-decision position, without reserving a primary/follow-up kind. Explicit `recover` only adopts an already durable accepted output;
without that evidence it reports unknown and never calls the provider. A generation save failure can be
retried without paying for a second output. Foreground, rendered-question success is suppressed from the
notification inbox; cross-page/background request receipts still produce exact-session notifications.

Mock navigation without `session` always opens the creation home. A collapsed, fully paginated
Application-scoped unfinished-session list provides exact continue links; completed sessions remain
in read-only history. Creation identity survives response loss, and resolution uses that identity,
never the newest session. Creation and first-turn loading stay continuous without premature counters
or recovery controls. Only saved primary/follow-up counts are shown; the answer input has no redundant
empty-answer labels.

Submitting keeps the question and draft visible and disabled until the server confirms persistence.
After confirmation, the saved answer and a single inline spinner (“正在准备下一道问题…”) appear in the
same question container. First generation uses “正在准备第 1 题…”. Monotonic session revisions prevent
an older poll from replacing a newer transcript; new turns do not force a second scroll alignment.
Follow-up number, question, answer/editor and aligned submit/end actions share one indentation.
Runtime decoding validates saved kind, stable parent, sequence, counts and numbering. Primary groups
collect follow-ups by parent, including delayed and continuous follow-ups (2.1, 2.2). Waiting never
predicts a kind. Model `finish` has no new turn; completion removes the session from unfinished
choices and updates the exact request's notification as completion, not “new question”. Foreground
completion is acknowledged only once its completed body mounts; unrelated failures stay intact.

Completed sessions have no extra new-session button. Read-only unfinished history offers an exact
“继续模拟” link at the bottom; answering happens only on the Mock page.

Normal generation polls read-only status. An execution lock distinguishes a live worker from an
orphaned durable flag; unknown outcomes expose an explicit status check, never automatic generation.
Status checks first read the exact receipt and only then may adopt durable accepted output. A turn
published from that exact ModelCall resolves its save-failure notification without rewriting the
original audit receipt or hiding unrelated failures. Recovery checks do not create a second generation
notification, and acknowledged notifications remain acknowledged after resolution.
Submission row separators belong only between adjacent records, including when pagination is visible.

`DELETE applications/{application_id}/results/{target_id}` supports Fit/Prep visibility removal;
`DELETE companies/{company_id}/research/{report_id}` supports company-wide research visibility removal.
Both return `deleted` and readable `used_by` purposes. Frozen business consumers and pending source
references block removal; underlying artifacts and evidence are retained. Legacy target ownership that
cannot be established is rejected, not inferred from a shared Job. Company research tombstones are
excluded from normal history, Summary and automatic reuse; exact archived bodies remain readable.

Fit operations carry `application_id` independently of `application_binding`: the former records
ownership for history/removal, while selected Profile/Resume inputs remain independent of the
Application's current resume. The server validates the exact JD belongs to that Application's Job;
legacy operations without reliable ownership remain readable but cannot be deleted by guessing from
shared Job identity.

### Generation source labels

Source links appear beneath the main new-generation action and describe its current input selection.
JD links open the exact revision; Resume and Profile links retain their immutable revision IDs.
Historical result bodies and expanded adjustment forms do not repeat the source line. Selecting a
historical result never changes the separate new-generation inputs; adjustments/regeneration still
use the selected result's frozen contract. Unknown legacy identities are never replaced with current
selections. The following table describes execution and persisted sources, including those not repeated
in the result display.

| Action                             | Materials actually supplied to the model                                                                   | Selection and persisted-source contract                                                                                                        |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| New Interview Prep                 | Bound Resume's visible expressions, exact JD/requirements, explicitly selected compatible research or none | The generation control defaults to no research and sends `use_company_research=false`; all compatible same-company history remains selectable. |
| Prep adjustment / regeneration     | Original `interview_context`, original Prep content, feedback                                              | Selected result's exact Resume/JD/research and original Prep; old results without the frozen contract remain read-only.                        |
| New Mock / next decision           | Frozen visible Resume, exact JD/requirements, other question history and current-group accepted Q&A        | Session sources stay frozen; company research and Prep attachments are not added.                                                              |
| New Resume optimization            | Exact base Resume, JD requirements, verified facts/project references from its source Profile              | Bound Resume/JD plus the exact source Profile; optional Fit and research are not model inputs.                                                 |
| Resume adjustment / regeneration   | Selected result's Resume body, exact JD requirements, frozen Profile evidence, feedback                    | `refinement_resume_revision_id` selects the displayed result Resume, not its predecessor `source_resume_revision_id`; no Fit/research.         |
| New Greeting                       | Exact Resume, JD title/requirements, its cited facts and available compatible research                     | Bound Resume/JD plus the actual research source when present; optional Fit is explicitly absent.                                               |
| Greeting adjustment / regeneration | Original Greeting, exact Resume/JD, frozen Profile body/evidence, feedback                                 | Selected result's sources and original Greeting, including the exact Profile; research and Fit are not inherited.                              |

The safe Product result projection carries only these source identities and readable Resume names.
It does not expose invocation bodies or turn internal validation IDs into additional source links.
`source_original_target_id` identifies a refinement's predecessor, while prospective
`refinement_resume_revision_id` / `refinement_profile_id` describe the next explicit adjustment.

### Interview acceptance interaction details

Interview pages use the accepted research/Fit title, section and body roles. Mock question numbers use
dark semibold body text; spoken questions and saved answers use normal body text (16/400/26). Internal
legacy topic titles are never displayed. Saved answers have a secondary “我的回答” label; the unanswered
question has only its input. Progress, loading and unfinished-session rows also use readable 16px text;
page headings remain 24/600/32, and shared controls/source links retain their established roles. Prep lists, explanation
paragraphs and answer outlines share ordinary body styling. Research/Fit/Prep removal sits alongside
the first nonempty result heading; result selectors flow into content without an extra boundary rule.
Deletion confirmation and reference refusals use centered, dismissible application dialogs.

Prep research defaults to none; generation settings are centered separately from the left-aligned
history selector. Mock focus and question mode stay on one centered desktop row. History uses the single grouped record selector described in [Review workspace contracts](#review-workspace-contracts),
left aligned and width-bounded; long transcript text wraps naturally.
Actual has one plain `YYYY-MM-DD HH:mm` input and a Chinese date/time picker. Empty values remain
empty. New-form cancellation returns to the mode choice; ordinary edit cancellation returns to record
selection, its top Back returns to mode choice, and history-origin edits preserve their exact return
record. Ordinary edit cancellation clears the exact record from the URL and survives refresh at the
selection page. Dirty exits require confirmation. Question ownership is disclosed on demand; stable entry IDs,
current numbering, no-op/CAS and frozen Debrief snapshots retain their existing semantics. The action
row groups Add follow-up/ownership on the left and compact Up/Down/Delete on the right. Main questions
and their follow-ups form full-width groups; separators occur only between groups, never after the last.

Research/Fit/Prep selector changes read and validate the requested exact result before committing the
selection/URL. A failed read preserves the prior selected body; rejected removal preserves selection
and candidates. Only successful removal refreshes history and selects the latest remaining readable
record. A failed history refresh retains known rows; a confirmed deletion remains removed even if
the subsequent refresh fails, with that read failure reported separately from a refusal. Late selection
reads cannot override a newer URL navigation. Shared display-name helpers use known company/job/time metadata consistently; names never
serve as identity or manufacture missing historical metadata.

Company research history remains readable independently of execution compatibility. The Prep input
selector only offers research compatible with the current research contract; an old prompt fingerprint
cannot be substituted with the current one merely because its historical report is readable.

### Legacy interview ownership

Verified legacy Mock ownership is projected from exact frozen JD/Profile/Resume relationships and
revision checks against the pre-existing unique Application, without backfilling rows. If that evidence
is absent or inconsistent, exact backend history may remain readable but Application discovery omits it.
A shared Job name/ID alone is insufficient. See `interview/ownership.py:mock_owner` for the resolver.
Legacy result removal also verifies the original operation request against the immutable target. Incomplete evidence
still fails closed. Reference refusals report consumer type and saved time; unknown ownership, unknown
references, and temporary read failures have separate messages. Research merely loaded into a package
and Fit/Prep result publication are distinguished from actual frozen model inputs, including exact reuse.

## Application closeout request and reachability contracts

Modern `POST jobs` requires a UUID request_id through the BFF. The creation form stores only that UUID
and a SHA-256 payload fingerprint in sessionStorage (`career-job-create-v1`); no private JD/body copy.
Refresh/remount checks `GET job-create-requests/{id}`. Missing/failed reads retain the same intent;
resubmission requires the original payload hash. Editing cannot silently rotate identity. Success or
confirmed input rejection clears it; timeout (including HTTP 408), rate limiting and uncertain results
keep it. Explicit “另建一条申请” confirms a new
intent. Storage-disabled submission fails closed. Separate tabs are independent; duplicated tabs may
share the copied intent. Tab closure/storage clearing loses the handle, not the backend receipt.

Job decoder accepts application_id=null for retained Jobs without an accessible workspace. The exact
receipt retains the original Application ID plus workspace_available, so replay after deletion never
creates another application. Task state projects workspace availability separately from success or
failure. Old unhandled notices requery before enabling result actions and continue refreshing while
queued. Deleted owners show “该申请已删除，无法打开工作区” without changing outcome/dismissal identity.
Task detail and direct workspace navigation provide an explained unavailable state; they never
redirect to a different Application. Existing independent audit reads remain available.
