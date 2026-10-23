/** Consumed projections of FastAPI contracts; unknown fields are intentionally not forwarded.
 * Sources: api/schemas.py, api/product.py, api/preparation.py, api/interview.py.
 */
export const applicationStatuses = [
  "tracking",
  "preparing",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
  "closed",
] as const;
export type ApplicationStatus = (typeof applicationStatuses)[number];
export const statusLabels: Record<ApplicationStatus, string> = {
  tracking: "关注中",
  preparing: "准备中",
  applied: "已投递",
  interviewing: "面试中",
  offer: "已获 Offer",
  rejected: "已拒绝",
  withdrawn: "已撤回",
  closed: "已关闭",
};
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("invalid_contract");
  return v as Record<string, unknown>;
}
function text(v: unknown): string {
  if (typeof v !== "string") throw new Error("invalid_contract");
  return v;
}
export function uuid(v: unknown): string {
  const s = text(v);
  if (!UUID_PATTERN.test(s)) throw new Error("invalid_contract");
  return s.toLowerCase();
}
function integer(v: unknown, min = 0): number {
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < min)
    throw new Error("invalid_contract");
  return v;
}
function bool(v: unknown): boolean {
  if (typeof v !== "boolean") throw new Error("invalid_contract");
  return v;
}
function date(v: unknown): string {
  const s = text(v);
  if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(s) || !Number.isFinite(Date.parse(s)))
    throw new Error("invalid_contract");
  return s;
}
function nullable<T>(v: unknown, decode: (v: unknown) => T): T | null {
  return v === null ? null : decode(v);
}
function choice<const T extends readonly string[]>(v: unknown, values: T): T[number] {
  const s = text(v);
  if (!values.includes(s)) throw new Error("invalid_contract");
  return s;
}
export function array<T>(v: unknown, decode: (v: unknown) => T): T[] {
  if (!Array.isArray(v)) throw new Error("invalid_contract");
  return v.map(decode);
}
function row(v: Record<string, unknown>) {
  return { id: uuid(v.id), created_at: date(v.created_at) };
}
export type Page<T> = { items: T[]; limit: number; offset: number; has_more: boolean };
export function pageOf<T>(decode: (v: unknown) => T): (v: unknown) => Page<T> {
  return (value) => {
    const v = object(value);
    const page = {
      items: array(v.items, decode),
      limit: integer(v.limit, 1),
      offset: integer(v.offset),
      has_more: bool(v.has_more),
    };
    if (page.items.length > page.limit) throw new Error("invalid_contract");
    return page;
  };
}
export function decodeCompany(value: unknown) {
  const v = object(value);
  return { ...row(v), name: text(v.name) };
}
export function decodeApplication(value: unknown) {
  const v = object(value);
  const result = {
    ...row(v),
    job_id: uuid(v.job_id),
    status: choice(v.status, applicationStatuses),
    revision: integer(v.revision, 1),
    events: array(v.events, (event) => {
      const e = object(event);
      return {
        ...row(e),
        application_id: uuid(e.application_id),
        sequence: integer(e.sequence, 1),
        kind: text(e.kind),
        from_status: nullable(e.from_status, (x) => choice(x, applicationStatuses)),
        to_status: nullable(e.to_status, (x) => choice(x, applicationStatuses)),
        note: nullable(e.note, text),
      };
    }),
  };
  if (result.events.some((e) => e.application_id !== result.id))
    throw new Error("invalid_contract");
  return result;
}
export function decodeJob(value: unknown) {
  const v = object(value);
  return {
    ...row(v),
    company_id: uuid(v.company_id),
    company_name: text(v.company_name),
    application_id: uuid(v.application_id),
    job_revision_id: uuid(v.job_revision_id),
    revision: integer(v.revision, 1),
    title: text(v.title),
    jd_text: text(v.jd_text),
    requirements: array(v.requirements, (r) => {
      const x = object(r);
      return {
        id: uuid(x.id),
        text: text(x.text),
        category: text(x.category),
        importance: choice(x.importance, ["must", "nice_to_have", "unknown"]),
      };
    }),
  };
}
export function decodeResearch(value: unknown) {
  const v = object(value);
  return {
    id: uuid(v.id),
    company_id: uuid(v.company_id),
    research_version: integer(v.research_version, 1),
    fetched_at: date(v.fetched_at),
    expires_at: date(v.expires_at),
    reusable_for_current_execution: bool(v.reusable_for_current_execution),
    mode: choice(object(v.data).mode, ["fixture", "live"]),
  };
}
export function decodePackage(value: unknown) {
  const v = object(value);
  return {
    id: uuid(v.id),
    run_id: uuid(v.run_id),
    job_revision_id: uuid(v.job_revision_id),
    profile_id: uuid(v.profile_id),
    outcome: nullable(v.outcome, (x) => ({
      status: choice(object(x).status, [
        "completed",
        "partial",
        "failed",
        "needs_input",
        "decision_required",
      ]),
    })),
  };
}
export function decodeSubmission(value: unknown) {
  const v = object(value);
  return {
    ...row(v),
    application_id: uuid(v.application_id),
    event_id: uuid(v.event_id),
    resume_revision_id: uuid(v.resume_revision_id),
    render_artifact_id: uuid(v.render_artifact_id),
    greeting_id: nullable(v.greeting_id, uuid),
    package_id: nullable(v.package_id, uuid),
  };
}
export function decodeMock(value: unknown) {
  const v = object(value);
  return {
    ...row(v),
    job_id: uuid(v.job_id),
    status: choice(v.status, ["ready_to_generate", "waiting_answer", "completed"]),
  };
}
export function decodeActual(value: unknown) {
  const v = object(value);
  return {
    ...row(v),
    application_id: uuid(v.application_id),
    round_name: text(v.round_name),
    occurred_at: nullable(v.occurred_at, date),
    content_revision: integer(v.content_revision, 1),
  };
}
export function decodeDebrief(value: unknown) {
  const v = object(value);
  return {
    ...row(v),
    generation_id: uuid(v.generation_id),
    selected_run_id: uuid(v.selected_run_id),
    is_selected: bool(v.is_selected),
    source_kind: choice(v.source_kind, ["actual", "mock"]),
    status: choice(v.status, ["ready", "running", "completed", "partial", "failed"]),
  };
}
export type Application = ReturnType<typeof decodeApplication>;
export type Job = ReturnType<typeof decodeJob>;
export type Company = ReturnType<typeof decodeCompany>;
export type ApplicationContext = { application: Application; job: Job; company: Company };
