# Profile workspace contracts

Profile workspace has passed user manual acceptance. The checkpoint also contains Application and
Internal implementations that remain pending subsequent manual acceptance.

Product exposes `/profile` and `/profile/resumes`. `/profile/facts` redirects to
Profile; fact storage remains an internal grounding/provenance capability.

## Named Profile and editing

A named `ProfileRecord` owns its current committed data and exact snapshot pointer.
Historical `PersonalProfile` snapshots remain immutable and readable by historical
executions. Product does not expose snapshot management.

- `POST /profile-library/{id}/editing` opens/resumes a persisted editing session.
- `PUT /profile-library/{id}/editing` saves section/item changes into that session.
- `POST /profile-library/{id}/editing/commit` atomically commits the full edit.
- `POST /profile-library/{id}/editing/cancel` discards the edit, including local saves.

Writes require the edit identity and expected edit revision. Commit also compares
the original committed data, preventing a stale edit from overwriting an unrelated
writer. No-op commits do not create snapshots. Renaming is independent of body
editing. Existing bound/historical snapshots never change.

Migration `b505c0802601` adds nullable JSONB `profile_records.editing`; existing rows
require no synthetic editing session and retain their existing snapshots.

## Resume, binding and refinement

Quick and AI creation save a persistent Resume workspace. AI creation is explicit.
The library presents stable user-visible entries in one selector, resolving each to its current
workspace or canonical revision. Ordinary saves replace that projection, not add a duplicate entry.
Exact old revisions remain readable; edits preserve source and enforce head CAS.

`POST /resume-workspaces/{id}/resolve` validates source claims and materializes an
exact canonical revision without rendering a PDF or calling a model. Repeated
resolution returns the same revision. Application binding and Fit use this path
for an unrendered workspace. Unsupported AI claims return claim-specific issues;
user/Profile sourced statements do not require a Product Facts approval step.

New Application Resume bindings persist only the Resume pointer. The execution
Profile is derived from that Resume's immutable source. Legacy Profile-only
bindings remain readable. Fit independently selects Profile, Resume or both;
its optional `fit_input` is frozen in task provenance and reuse identity.

Library and Application adjustments share `resume_refinement`, its canonical
output schema, grounding, Gateway and adoption logic. Library inputs bind a source
workspace/revision; Application inputs additionally bind the source artifact and
original context. Old results are preserved. Feedback is independently persisted
and never starts generation. Metadata discovery supports source workspace and
Resume revision filters through `/evaluation/refinements`.

## Rendering

The Typst template uses a compact contact header, optional proportionally cropped
photo, section rules, aligned experience titles/dates, secondary metadata and body
bullets. Empty contacts/photo reserve no space. Entry layout contains indexes into
validated text and its hash; it introduces no independent factual claims. Edited
or legacy text without matching layout uses the compatible plain-text rendering
path, rather than reconstructing facts heuristically.

Renderer/validator versions are `resume-render-wrapper-v5` and
`resume-validation-v4`. PDF output retains the existing font, one-page, text,
grounding and overflow checks. Rendering never implicitly starts AI compression.

## Presentation and saved time

Migration `b605c0902601` adds persisted presentation settings and nullable saved
timestamps. Historical timestamps are not invented. Section visibility and the
work/project ordering preference are metadata, not destructive content edits.
Presentation writes use CAS; rendering freezes the settings in its report so an
older PDF remains attributable to its original layout. Education precedes work
and projects, and skills follow them; models do not choose top-level ordering.

AI creation and missing-short-expression generation return source-item expressions rather than
asking models to reproduce section IDs, ordering and factual references. Domain
conversion owns these fields and validates the frozen source item set. Previously
completed canonical outputs remain readable. Shared `resume_refinement` continues
to serve library and Application adjustments.

Only confirmed layout overflow exposes compression controls. Content policy v3
renders exactly the selected expressions: it never substitutes short forms or
removes optional items on overflow. Explicit AI compression preserves full text
and stores recoverable short expressions in the generation’s edit proposal, without
creating a Resume workspace. Only short forms are merged by source item ID; the
original private document remains authoritative. The user selects and saves them
as a revision of the same variant before rendering. Cancelling writes no Resume. Manual compression opens the same length controls
without rewriting content. Presentation also stores hidden item IDs, explicit
compact item IDs and item order independently of factual revisions. PDF text validation normalizes the known
Noto CJK bullet extraction equivalence, retaining other text checks.

## Edit sessions and legacy expression compatibility

The Product Resume editor buffers content and presentation together. Editions and
expression writes accept optional presentation metadata in the same transaction;
canonical expression writes additionally require the metadata revision. Cancel
performs no presentation write. Reads normalize legacy empty presentation objects
without rewriting historical documents or PDF reports.

Library creation ordering uses the earliest workspace creation time for a
materialized revision, falling back to the revision's creation timestamp for
standalone versions. SQL pagination uses the same timestamp and stable ID ordering.
AI refinement names use a persisted naming branch, independent of the immutable
parent and source Profile. Renaming creates a new branch; adopted generations
record branch identity/name/ordinal. A variant lock serializes branch numbering.
Legacy generations are resolved using their stored root metadata, never suffix parsing.

Source resolution checks hard-claim membership and values before rebinding both
item references and hard-claim references to the resolved evidence. Rebinding does
not relax numeric or source validation and does not modify historical source rows.

## Independent resume numbering

Only independent roots allocate a library number, using the smallest currently
unused positive integer under a transaction advisory lock. Materializing a workspace
retains its existing number; refinement, compression and manual edits do not allocate
root numbers. Existing identities and names never change when another root is deleted.
Migration `b705c1002601` removes uniqueness from nullable historical display numbers,
allowing reuse after deletion without rewriting archived records. Downgrade fails
closed if reused historical numbers cannot satisfy the old uniqueness constraint.

## In-place compression and naming branches

Migration `b805c1102601` adds library metadata without altering frozen Resume bodies.
Compression requests contain only visible items lacking short text from the exact
selected revision. Existing short expressions and hidden items remain untouched.
Generated expressions are selected in the editor but require explicit user save.
Saving creates an internal immutable revision and replaces the same library entry;
its stable entry ID, name and first-created time are retained. The previous revision
remains readable for exact bindings, PDF snapshots and evaluation provenance.
Cancelling leaves the library unchanged. The Product selector uses entry identity,
while API mutations and model calls continue to use the exact revision identity.

Naming branches persist on revisions and adopted generation facts. A rename affects
only that version's branch; descendants of other versions keep their original branch.
The immutable-record trigger permits only this presentation/library metadata in
addition to the existing metadata fields; body and input snapshots remain protected.
`required` and `priority` remain domain fields for old documents and guardrails; no
Product preservation checkbox is exposed. PDF rendering still uses only explicitly
selected short expressions and never implicitly calls a model.

## Ordinary saves and field errors

Migration `b905c1202601` extends the same library-entry metadata to editing
workspaces. Body edits retain the selected entry ID and original creation time,
replace its list projection, and preserve exact old Workspace/revision reads.
Materialization carries that entry identity into the immutable revision. Pending
older writers cannot fork an already-replaced entry. AI optimization still creates
a separate entry; ordinary editing and compression do not. Existing historical
records are not merged by name or deleted.

Invalid short expressions return allowlisted section/item indices and the
`short_text_not_shorter` code, never the rejected text or raw Pydantic context.
The Product BFF forwards only that bounded contract. Frontend checks compare
trimmed Unicode code-point lengths, show each error alongside its field, retain
input after rejection, and focus the first invalid field after rendering.
