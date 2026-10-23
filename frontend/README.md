# Career Agent Web foundation

Next.js App Router, React, strict TypeScript and Tailwind CSS v4. Dependencies are pinned
in `package.json` and `package-lock.json`. No UI component framework or external font service.
Dev/build explicitly use the supported Webpack path (Turbopack worker-port IPC is restricted
in this development environment). The Python application remains a separate service. Applications
and its workspace now make server-side **GET-only** reads; other business features remain placeholders.

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
error/empty/history distinctions, navigation and narrow-screen layout. They never use a real
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
otherwise-placeholder sections. Missing Application gives not-found; failed or mismatched joins
show a sanitized read error. No auto-selection of another Application.
There is no synthetic Application link, fake metric, implied business success, or enabled
backend action. Internal pages are static placeholders, **not** an authentication boundary.

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
unchanged. There are **no BFF HTTP handlers yet**, and no new auth/session system.

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
means one Application. Switching always opens the chosen Application's Summary. All placeholders
inherit its validated header/navigation; they do not generate any materials or analyses.

Summary has independent read/error/empty states for each existing resource. No total counts are
inferred from limited pages, no progress/fit score, no selected/current material inference.
Application events are sorted by their sequence (last five); dates use Asia/Shanghai. Current JD
text is escaped plain text in a disclosure. Historical package JD refs are not rewritten to the
current JD. The latest research history row is not automatically the current compatible report.
Actual Interview's first row is explicitly called first-recorded, never latest interview.
Reconciliation, retry, provider calls and writes are never triggered by these pages.

## Scope still deferred

Research/Fit operations, Resume/Greeting/Submission detail workflows, Interview/Review business
pages, Profile editing and all Internal data integration remain placeholders. No Summary engine,
new backend API, unified interview timeline, material-selection lineage or new control actions.
