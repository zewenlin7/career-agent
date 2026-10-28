/** Narrow Product BFF surface, derived from api/{product,interview,resumes,app,preparation}.py. */
const id = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
type Rule = { path: RegExp; methods: string[]; query: string[]; body?: string[] };
const rule = (path: string, methods: string[], query: string[] = [], body?: string[]): Rule => ({
  path: new RegExp(`^${path}$`),
  methods,
  query,
  body,
});
const paging = ["limit", "offset"];
export const rules: Rule[] = [
  rule(`resume-library/subjects/${id}`, ["GET"]),
  rule("profile-library", ["GET", "POST"], [], ["request_id"]),
  rule(`profile-library/${id}`, ["GET", "PATCH", "DELETE"], [], ["expected_revision", "name"]),
  rule(`profile-library/${id}/history`, ["GET"]),
  rule(
    `profile-library/${id}/editing`,
    ["POST", "PUT"],
    [],
    ["expected_revision", "edit_id", "data"],
  ),
  rule(
    `profile-library/${id}/editing/(?:commit|cancel)`,
    ["POST"],
    [],
    ["expected_revision", "edit_id"],
  ),
  rule(
    `profile-library/${id}/sections/(?:personal|education|experiences|projects|skills|preferences)`,
    ["PATCH"],
    [],
    ["expected_revision", "value", "record_name", "expected_record_revision"],
  ),
  rule("profile-workspace", ["GET"]),
  rule(
    "profile-workspace/sections/(?:personal|education|experiences|projects|skills|preferences)",
    ["PATCH"],
    [],
    ["expected_revision", "value", "record_name", "expected_record_revision"],
  ),
  rule("profile-workspace/publish", ["POST"], [], ["expected_revision"]),
  rule("profile-workspace/restore", ["POST"], [], ["expected_revision", "profile_id"]),
  rule(`profile/revisions/${id}`, ["DELETE"]),
  rule("profile-photos", ["POST"]),
  rule(`profile-photos/${id}`, ["GET"]),
  rule("fact-library", ["GET"], paging),
  rule("fact-library/actions", ["POST"], [], ["ids", "action"]),
  rule(`fact-library/${id}`, ["PATCH"], [], ["expected_revision", "statement", "category"]),
  rule(
    `resume-workspaces/${id}/presentation`,
    ["PUT"],
    [],
    [
      "expected_revision",
      "hidden_sections",
      "hidden_item_ids",
      "compact_item_ids",
      "item_order",
      "experience_order",
    ],
  ),
  rule(
    `resume-library/versions/${id}/presentation`,
    ["PUT"],
    [],
    [
      "expected_revision",
      "hidden_sections",
      "hidden_item_ids",
      "compact_item_ids",
      "item_order",
      "experience_order",
    ],
  ),
  rule("resume-workspaces", ["GET", "POST"], ["limit", "offset"], ["request_id", "profile_id"]),
  rule(
    `resume-workspaces/${id}/editions`,
    ["POST"],
    [],
    [
      "request_id",
      "expected_revision",
      "name",
      "document",
      "presentation",
      "expected_metadata_revision",
    ],
  ),
  rule(`resume-workspaces/${id}/render`, ["POST"], [], ["expected_revision", "confirmed_item_ids"]),
  rule(
    `resume-workspaces/${id}`,
    ["GET", "PATCH", "DELETE"],
    [],
    ["expected_revision", "name", "document"],
  ),
  rule(`resume-workspaces/${id}/(?:review|publish|resolve)`, ["POST"], [], ["expected_revision"]),
  rule(
    `resume-library/versions/${id}/expression`,
    ["POST"],
    [],
    [
      "request_id",
      "generation_id",
      "expected_revision",
      "name",
      "document",
      "presentation",
      "expected_metadata_revision",
    ],
  ),
  rule(`resume-library/versions/${id}/edit`, ["POST"], [], ["expected_revision", "document"]),
  rule("resume-library/versions", ["GET"], paging),
  rule(`resume-library/versions/${id}`, ["PATCH", "DELETE"], [], ["expected_revision", "name"]),
  rule(
    "evaluation/feedback",
    ["POST"],
    [],
    ["subject", "vote", "reason", "comment", "application_id"],
  ),
  rule("resume-library", ["GET"], paging),
  rule(
    "product-drafts",
    ["POST"],
    [],
    [
      "request_id",
      "task",
      "profile_id",
      "source_artifact_id",
      "source_resume_revision_id",
      "source_workspace_id",
      "selected_item_ids",
      "feedback",
      "feedback_id",
      "application_id",
      "intent",
      "mode",
    ],
  ),
  rule(`product-drafts/${id}`, ["GET"]),
  rule(`product-drafts/${id}/execute`, ["POST"]),
  rule(`product-drafts/${id}/cancel`, ["POST"]),
  rule(
    `product-drafts/${id}/adopt`,
    ["POST"],
    [],
    ["expected_profile_revision", "selected_indices"],
  ),
  rule(`resume-revisions/${id}/save`, ["POST"]),
  rule(`resume-revisions/${id}/renders`, ["GET"]),
  rule(`knowledge-notes/${id}`, ["PATCH"], [], ["expected_revision", "title", "content"]),
  rule(`knowledge-notes/${id}`, ["DELETE"], ["expected_revision"]),
  rule(
    `applications/${id}/context`,
    ["GET", "PUT"],
    [],
    ["expected_revision", "profile_id", "resume_revision_id", "job_revision_id"],
  ),
  rule(`applications/${id}/results`, ["GET"], [...paging, "target"]),
  rule("profile", ["GET", "PUT"], [], ["expected_revision", "data"]),
  rule(`profile/revisions/${id}`, ["GET"]),
  rule("facts", ["GET", "POST"], paging, ["statement", "category"]),
  rule(`facts/${id}/(?:verify|reject)`, ["POST"]),
  rule(`facts/${id}/supersede`, ["POST"], [], ["expected_revision", "statement", "category"]),
  rule("companies", ["GET"], [...paging, "q"]),
  rule("jobs", ["POST"], [], ["company_id", "company_name", "title", "jd_text", "requirements"]),
  rule(
    "resume-variants",
    ["POST"],
    [],
    [
      "locale",
      "metadata",
      "schema_version",
      "template",
      "target_page_count",
      "profile_id",
      "profile_revision",
      "job_revision_id",
      "sections",
    ],
  ),
  rule(`resume-variants/${id}/revisions`, ["POST"], [], ["expected_revision", "document"]),
  rule(
    `applications/${id}`,
    ["PATCH"],
    [],
    ["expected_revision", "status", "correction", "reason"],
  ),
  rule(`applications/${id}/notes`, ["POST"], [], ["text"]),
  rule("profile/revisions", ["GET"], paging),
  rule(`job-revisions/${id}`, ["GET"]),
  rule(`applications/${id}`, ["GET"]),
  rule(`applications/${id}/preparation-packages`, ["GET"], paging),
  rule(`applications/${id}/knowledge-notes`, ["GET"], paging),
  rule(`applications/${id}/submissions`, ["GET", "POST"], paging, [
    "request_id",
    "expected_revision",
    "resume_revision_id",
    "render_artifact_id",
    "greeting_id",
    "package_id",
    "note",
  ]),
  rule(`companies/${id}/research(?:/current)?`, ["GET"], [...paging, "mode"]),
  rule(
    `companies/${id}/research`,
    ["POST"],
    [],
    ["request_id", "kind", "request", "application_binding"],
  ),
  rule(`company-research/${id}`, ["GET"]),
  rule(
    "operations",
    ["GET", "POST"],
    [...paging, "job_revision_id", "status"],
    ["request_id", "kind", "request", "application_binding"],
  ),
  rule(`operations/${id}`, ["GET"]),
  rule(`operations/${id}/execute`, ["POST"]),
  rule(`operations/${id}/result`, ["GET"]),
  rule(`preparation-artifacts/${id}/product-view`, ["GET"]),
  rule("resume-revisions", ["GET"], [...paging, "profile_id", "job_revision_id", "variant_id"]),
  rule(`resume-variants/${id}`, ["GET"], ["revision"]),
  rule(`resume-variants/${id}/render`, ["POST"], [], ["revision"]),
  rule(`artifacts/${id}`, ["GET"]),
  rule(`artifacts/${id}/download`, ["GET"], ["inline"]),
  rule(
    "mock-interviews",
    ["GET", "POST"],
    [...paging, "application_id", "job_id"],
    ["context", "focus", "policy", "mode", "application_binding"],
  ),
  rule(`mock-interviews/${id}`, ["GET"]),
  rule(
    `mock-interviews/${id}/answers`,
    ["POST"],
    [],
    ["expected_revision", "request_id", "pending_question_id", "answer", "end_early"],
  ),
  rule(`mock-interviews/${id}/(?:generate|end)`, ["POST"], [], ["expected_revision", "request_id"]),
  rule(
    "interviews",
    ["GET", "POST"],
    [...paging, "application_id", "status"],
    [
      "expected_revision",
      "application_id",
      "round_name",
      "occurred_at",
      "round_number",
      "interview_type",
      "status",
    ],
  ),
  rule(
    `interviews/${id}`,
    ["GET", "PATCH"],
    [],
    [
      "expected_revision",
      "round_name",
      "occurred_at",
      "entries",
      "round_number",
      "interview_type",
      "status",
      "notes_text",
    ],
  ),
  rule(`interviews/${id}/entries`, ["POST"], [], ["expected_revision", "entry"]),
  rule(`interviews/${id}/notes`, ["POST"], [], ["expected_revision", "text"]),
  rule(
    "interview-debriefs",
    ["GET", "POST"],
    [...paging, "application_id", "job_id", "source_kind", "source_id"],
    [
      "source_kind",
      "interview_id",
      "expected_source_revision",
      "question_analysis",
      "overall_analysis",
      "primary_entry_id",
      "context",
      "mode",
    ],
  ),
  rule(`interview-debriefs/${id}`, ["GET"], ["historical"]),
  rule(`interview-debriefs/${id}/events`, ["GET"], ["after"]),
  rule(`interview-debriefs/${id}/execute`, ["POST"]),
  rule(
    `interview-debriefs/${id}/regenerate`,
    ["POST"],
    [],
    ["question_analysis", "overall_analysis", "primary_entry_id"],
  ),
  rule(
    "knowledge-notes",
    ["POST"],
    [],
    ["application_id", "title", "content", "interview_id", "source_document_id"],
  ),
];
export function productRule(path: string, method: string, query: URLSearchParams) {
  const found = rules.find((r) => r.path.test(path) && r.methods.includes(method));
  if (
    !found ||
    [...query.keys()].some((k) => !found.query.includes(k) || query.getAll(k).length !== 1)
  )
    throw new Error("unsupported_product_request");
  return found;
}
export function validateBody(body: unknown, allowed: string[] = []) {
  if (
    !body ||
    typeof body !== "object" ||
    Array.isArray(body) ||
    Object.keys(body).some((k) => !allowed.includes(k))
  )
    throw new Error("invalid_request");
  return body;
}
/** Strip private frozen context bodies; keep business transcript and explicit provenance. */
export function projectResponse(path: string, data: unknown): unknown {
  if (!data || typeof data !== "object" || Array.isArray(data)) return data;
  const value = data as Record<string, unknown>;
  const context = (raw: unknown) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return raw;
    const { data: _private, ...refs } = raw as Record<string, unknown>;
    void _private;
    return refs;
  };
  if (path.startsWith("mock-interviews/") || path === "mock-interviews")
    return { ...value, context: context(value.context) };
  if (path.startsWith("interview-debriefs/") || path === "interview-debriefs") {
    const snapshot = value.snapshot as Record<string, unknown> | undefined;
    return snapshot
      ? { ...value, snapshot: { ...snapshot, context: context(snapshot.context) } }
      : value;
  }
  return value;
}

/** Next's internal URL hostname may differ from the browser Host. Never trust forwarded-host. */
export function sameOriginWrite(request: Request) {
  try {
    const origin = new URL(request.headers.get("origin") || "");
    const internal = new URL(request.url);
    return (
      origin.host === (request.headers.get("host") || internal.host) &&
      origin.protocol === internal.protocol
    );
  } catch {
    return false;
  }
}
