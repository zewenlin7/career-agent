/** Explicit Internal transport surface. No arbitrary upstream paths or browser credentials. */
const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
type Rule = { pattern: RegExp; method: string; query: string[]; body?: string[] };
const rules: Rule[] = [];
function add(path: string, query = "", body?: string[]) {
  rules.push({
    pattern: new RegExp(`^${path}$`),
    method: body ? "POST" : "GET",
    query: query.split(" ").filter(Boolean),
    body,
  });
}
add("ops/controller");
add("ops/metrics", "window_seconds");
add("ops/events", "after limit");
add("ops/recovery-incidents", "limit");
add("ops/attention", "source status include_resolved limit offset");
add(`ops/attempts/${uuid}`);
add("ops/controls", "", [
  "request_id",
  "expected_revision",
  "expected_global_revision",
  "action",
  "route",
  "enabled",
  "values",
  "ttl_seconds",
]);
add(`ops/attempts/${uuid}/reconcile`, "", [
  "request_id",
  "expected_revision",
  "resolution",
  "reason_code",
]);
add("runs", "kind workflow status limit offset");
add(`runs/${uuid}`);
add(`runs/${uuid}/steps`, "limit offset");
add(`runs/${uuid}/calls`);
add(`agent-runs/${uuid}`);
add(`agent-runs/${uuid}/plans`);
add(`agent-runs/${uuid}/observations`);
add(`operations/${uuid}`);
const discoveries: Record<string, string> = {
  "case-index": "tag task_type",
  suites: "suite_key",
  runs: "suite_id status",
  trials: "run_id case_id status",
  comparisons: "baseline_run_id candidate_run_id",
  judges: "subject_id task_type status severity population",
  "sampling-records": "subject_id task_type sampled population",
  feedback: "subject_id",
  captures: "status subject_id task_type",
  "annotations/queue": "status population",
};
for (const [name, query] of Object.entries(discoveries))
  add(`evaluation/${name}`, `${query} limit offset`);
for (const name of [
  "suites",
  "runs",
  "trials",
  "operations",
  "comparisons",
  "judges",
  "captures",
  "annotations/queue",
])
  add(`evaluation/${name}/${uuid}`, "private");
add("evaluation/calibration");
add(`evaluation/cases/${uuid}/origin`, "private");
add(`evaluation/cases/${uuid}/export`);
add(`evaluation/captures/${uuid}/sanitized`);
add("evaluation/cases", "", [
  "schema_version",
  "case_id",
  "case_version",
  "entrypoint",
  "tags",
  "source_type",
  "source_snapshot",
  "model_input",
  "frozen_external_observations",
  "evaluation_clock",
  "expectations",
  "fault_plan",
  "origin_provenance",
  "content_hash",
  "control_scenario",
]);
add("evaluation/suites", "", ["suite_id", "version", "schema_version", "members"]);
add("evaluation/runs", "", [
  "suite_id",
  "suite_version",
  "trials",
  "mode",
  "explicit_diagnostic",
  "max_concurrent_trials",
  "limits",
  "per_trial_limits",
]);
for (const op of ["execute", "cancel"]) add(`evaluation/runs/${uuid}/${op}`, "", []);
add("evaluation/comparisons", "", ["baseline_run_id", "candidate_run_id", "policy"]);
add("evaluation/judges/drain", "", ["limit", "concurrency", "limits"]);
add("evaluation/annotations/queue", "", ["subject", "population"]);
add(`evaluation/annotations/queue/${uuid}`, "", [
  "subject",
  "schema_version",
  "rubric_version",
  "annotator",
  "population",
  "criteria",
  "blind",
  "supersedes_annotation_id",
]);
add(`evaluation/captures/${uuid}/triage`, "", ["status", "reason_code"]);
add(`evaluation/captures/${uuid}/promote`, "", ["case", "confirmed_repo_safe"]);
export function internalRule(path: string, method: string, query: URLSearchParams) {
  const rule = rules.find((r) => r.method === method && r.pattern.test(path));
  if (
    !rule ||
    [...query.keys()].some((k) => !rule.query.includes(k)) ||
    [...query.keys()].some((k) => query.getAll(k).length !== 1)
  )
    throw Error("invalid_request");
  if (query.has("private") && query.get("private") !== "confirmed") throw Error("invalid_request");
  return rule;
}
export function internalBody(value: unknown, keys?: string[]) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    !keys ||
    Object.keys(value).some((k) => !keys.includes(k))
  )
    throw Error("invalid_request");
  return value;
}
type Obj = Record<string, unknown>;
const object = (v: unknown): Obj =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : {};
function omit(v: unknown, keys: string[]) {
  return Object.fromEntries(Object.entries(object(v)).filter(([k]) => !keys.includes(k)));
}
function invocation(v: unknown) {
  return omit(v, ["input_snapshot", "output"]);
}
function trialResult(v: unknown) {
  return v === null ? null : omit(v, ["output"]);
}
/** Private evaluation source/output never rides ordinary discovery or run detail. */
export function internalProjection(path: string, value: unknown, privateReview = false): unknown {
  const data = object(value);
  if (/^evaluation\/captures\/[^/]+$/.test(path))
    return {
      ...omit(data, ["payload"]),
      payload_metadata: omit(data.payload, [
        "source_snapshot",
        "model_input",
        "external_observations",
        "output",
      ]),
    };
  if (/^evaluation\/operations\//.test(path)) return privateReview ? data : invocation(data);
  if (/^evaluation\/trials\//.test(path))
    return {
      ...data,
      result: trialResult(data.result),
      operations: Array.isArray(data.operations) ? data.operations.map(invocation) : [],
    };
  if (/^evaluation\/runs\/[^/]+(?:\/execute)?$/.test(path) && Array.isArray(data.trials))
    return {
      ...data,
      trials: data.trials.map((t) => ({ ...object(t), result: trialResult(object(t).result) })),
    };
  if (/\/origin$/.test(path))
    return privateReview
      ? data
      : omit(data, ["original_output", "frozen_source", "frozen_input", "external_observations"]);
  if (/^evaluation\/annotations\/queue\/[^/]+$/.test(path) && !privateReview)
    return omit(data, ["input", "output"]);
  if (path === "evaluation/cases" && data.case)
    return {
      id: data.id,
      case: omit(data.case, ["source_snapshot", "model_input", "frozen_external_observations"]),
    };
  if (/\/promote$/.test(path) && data.case)
    return {
      id: data.id,
      case: omit(data.case, ["source_snapshot", "model_input", "frozen_external_observations"]),
    };
  return value;
}
