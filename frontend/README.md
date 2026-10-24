# Career Agent Web foundation

Next.js App Router, React, strict TypeScript and Tailwind CSS v4. Dependencies are pinned
in `package.json` and `package-lock.json`. No UI component framework or external font service.
Dev/build explicitly use the supported Webpack path (Turbopack worker-port IPC is restricted
in this development environment). The Python application remains a separate service. Applications
and Summary retain server-side reads. Application business pages now use an allowlisted Product BFF for explicit operations and history; Profile/Internal integration remains deferred.

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
There is no synthetic Application link, fake metric or implied business success. Generation requires an explicit action and mode selection. Internal pages are static placeholders, **not** an authentication boundary.

## Visual basis

[`docs/ui-design-system.md`](../docs/ui-design-system.md) overrides generic style advice.
Its RAG-specific structure is not copied. The original reference names files from another
application; those are not assumed to exist here.

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
module or allowlisted BFF handler, not a catch-all proxy. A future Ops reader must be separate
from this Product reader and inject credentials server-side; never pass headers/config/credentials
to a Client Component. Product code does not read the Ops token. Existing Ops controls and CAS remain
unchanged. `app/api/product/[...path]/route.ts` is an explicit path/method/query/body-key allowlist, not arbitrary forwarding. It checks Origin against the browser Host for JSON writes, never copies browser credentials or Ops headers upstream, sanitizes error bodies, and streams only accepted PDF responses and the existing Debrief POST SSE. No new auth/session system is introduced.

Before deployment, the BFF itself must be local/private or behind deployment access protection;
an unauthenticated public proxy would lend its server credential to anyone. Private evaluation
snapshots are not ordinary logs. See [the backend boundary](../docs/web-backend-discovery.md).

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

| Area             | Existing endpoints / behavior                                                                                                                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Company Research | `GET companies/{id}/research[/current]`, `POST companies/{id}/research`; company-level current/history, mode, freshness/compatibility and source evidence. Force refresh is explicit.                                                                         |
| Preparation      | `POST operations`, `POST operations/{id}/execute`, `GET operations[/{id}]`; stable identity is committed before execution. Separate target requests for Fit, Tailoring, Greeting, and explicit `prepare_interview`.                                           |
| Results/history  | `GET applications/{id}/preparation-packages`, `GET preparation-artifacts/{id}/product-view`, `GET job-revisions/{id}`; exact historical context, Fit requirement text, source Resume and reuse. No Greeting revision lineage or selected material pointer.    |
| Resume           | `GET profile/revisions`, `GET resume-revisions`, `GET resume-variants/{id}?revision=...`, `POST resume-variants/{id}/render`, `GET artifacts/{id}/download`; explicit Profile/base Resume choice, structured revision view and accepted PDF preview/download. |
| Submissions      | `GET/POST applications/{id}/submissions`; explicit actual-use confirmation, expected Application revision, stable request UUID, exact Resume/PDF and optional Greeting/package. Only this action records applied according to backend lifecycle rules.        |
| Mock             | `POST mock-interviews`, `GET mock-interviews[/{id}]`, `POST .../{answers,generate,end}`; frozen context, policy quotas, immutable accepted answers, generation-only retry and early end.                                                                      |
| Actual           | `GET/POST interviews`, `GET/PATCH interviews/{id}`, `POST .../{entries,notes}`; current-state CAS, ordered primary/follow-up, question/answer corrections, append-only legacy notes.                                                                          |
| Debrief          | `GET/POST interview-debriefs`, `GET .../{id}?historical=true`, `POST .../{id}/{execute,regenerate}`, `GET .../{id}/events`; frozen source, exact generation response, selected/history, independent group/overall.                                            |
| Knowledge        | `GET applications/{id}/knowledge-notes`, `POST knowledge-notes`; Application scope, creation and paginated read only.                                                                                                                                         |

Forms never implicitly choose a Resume. Modes default to visibly labeled fixture execution; live is
an explicit selection and may incur provider costs. This implementation's acceptance uses only
synthetic HTTP fixtures, not paid providers or claims about generated job-search quality.

Preparation creates an operation before a separate Execute click. Refresh/re-entry can discover
committed operations for the current JD; historical packages remain readable across JD changes.
Execution is synchronous, not a durable background task. Interrupted requests must be queried;
needs_input/decision_required/recovery_required remain distinct. No automatic mutation retry.
A repeated unchanged form uses the same request UUID; starting another explicit request creates a
new identity. Mock continuation uses revision + pending question ID + request UUID.

Previous Interviews has separate Mock and Actual list/detail views with their backend ordering and
pagination, not a merged timeline. Actual note edits/deletion are unavailable in the backend and are
not offered. CAS conflicts keep drafts and require an explicit reread; there is no automatic overwrite.

Debrief streams persisted business events via POST fetch, not EventSource/token streaming. Completed
artifacts are reread after notifications, displayed by group order with Overall last, independent of
completion order. Disconnect has no promise of background continuation; query persisted results/events.
Regenerate binds the exact frozen generation and returns a new run, not negative feedback.

Material-use badges scan ordinary Submission pages rather than treating the first page as the entire
history. Resume revision detail also exposes paginated exact usage checks. Package history has no
creation timestamp or typed-result filter: pages are shown in backend order and expanded on selection.
A manually rendered PDF has no general render-history discovery endpoint; its returned exact report
ID is displayed, while generated package PDFs and submitted PDFs can be rediscovered via those records.

Existing verified Profile/base Resume data is a prerequisite. This scope does not add Profile editing,
manual Resume authoring, an Internal control UI, automatic sends/submissions, a Summary engine, a new
backend API, a unified interview timeline, or new material-selection/revision semantics.
