/** Synthetic only. Mirrors metadata contracts, never used by production pages. */
export const ids = Object.fromEntries(
  [
    "run",
    "agent",
    "step",
    "call",
    "tool",
    "attempt",
    "incident",
    "operation",
    "suite",
    "evalrun",
    "trial",
    "invocation",
    "case",
    "comparison",
    "sampling",
    "subject",
    "judge",
    "queue",
    "capture",
    "annotation",
  ].map((k, i) => [k, `90000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`]),
) as Record<string, string>;
const date = "2026-10-24T08:00:00Z";
let revision = 3,
  globalRevision = 2,
  kill = false,
  globalKill = false,
  incidentRevision = 1,
  incidentStatus = "open",
  evalStatus = "pending",
  annotated = false,
  triage = "captured";
const receipts = new Map<string, unknown>();
export function resetInternal() {
  revision = 3;
  globalRevision = 2;
  kill = false;
  globalKill = false;
  incidentRevision = 1;
  incidentStatus = "open";
  evalStatus = "pending";
  annotated = false;
  triage = "captured";
  receipts.clear();
}
type D = Record<string, unknown>;
const ok = (body: unknown, status = 200) => ({ status, body });
const error = (code: string, status = 409) => ok({ error: { code } }, status);
const subject = {
  subject_id: ids.subject,
  task_type: "greeting_generation",
  accepted_model_call_id: ids.call,
  operation_id: ids.invocation,
  origin: "business",
};
const usage = {
  input_tokens: 120,
  output_tokens: 30,
  cached_tokens: 0,
  cache_write_tokens: null,
  estimated_cost: "0.0001",
  actual_billed_cost_usd: null,
  budget_reserved_usd: "0",
  measurement: "reported",
};
const invocation = {
  id: ids.invocation,
  operation_id: ids.invocation,
  kind: "model_task",
  name: "greeting_generation",
  version: "v1",
  input_snapshot: { private_marker: "PRIVATE_INPUT_SYNTHETIC" },
  input_hash: "synthetic-hash",
  output: { private_marker: "PRIVATE_OUTPUT_SYNTHETIC" },
  output_ref: ids.subject,
  parent_run_id: ids.evalrun,
  parent_step_id: ids.step,
  accepted_model_call_id: ids.call,
  logical_operation_id: ids.operation,
  provenance: {
    prompt_version: "greeting_generation_v1",
    prompt_hash: "synthetic",
    provider: "fixture",
    model: "fixture-strong",
  },
  reason_codes: [],
  injected_fault: null,
};
const trial = {
  status: "completed",
  checks: [
    {
      check_id: "grounding",
      check_version: "v1",
      category: "correctness",
      status: "pass",
      reason_code: "validated",
      evidence_refs: [],
      metadata: {},
      tier: 0,
      material: true,
    },
  ],
  output: { private_marker: "PRIVATE_TRIAL_SYNTHETIC" },
  usage,
  latency_ms: 4,
  reason_code: null,
};
const criteria = [
  {
    criterion: "relevance",
    rating: "minor_issue",
    confidence: "medium",
    uncertainty_reasons: [],
    reason: "Synthetic observation",
    evidence_refs: ["source:1"],
  },
];
const comparison = {
  id: ids.comparison,
  policy: {
    version: "comparison-priority-v2",
    minimum_trials: 1,
    efficiency_threshold: null,
    efficiency_blocking: false,
  },
  configuration_diff: [{ path: "prompts.greeting.hash", baseline: "old", candidate: "new" }],
  cases: [
    {
      case_id: "synthetic-greeting",
      case_version: 1,
      headline: "INCONCLUSIVE",
      gate: "REVIEW_REQUIRED",
      correctness_passed: true,
      reason_code: "judge_evidence_unavailable",
      deltas: [
        {
          check_id: "grounding",
          dimension: "correctness",
          tier: 0,
          delta: "unchanged",
          magnitude: "material",
        },
      ],
      baseline_distribution: { trials: 1 },
      candidate_distribution: { trials: 1 },
    },
  ],
  aggregate: { overall: { INCONCLUSIVE: 1 }, "task_type:greeting_generation": { INCONCLUSIVE: 1 } },
  gate: "REVIEW_REQUIRED",
  operation_deltas_are_attribution_not_causation: true,
};
const page = (url: URL, items: unknown[]) => {
  const offset = Number(url.searchParams.get("offset") || 0),
    limit = Number(url.searchParams.get("limit") || 10);
  return ok({
    items: items.slice(offset, offset + limit),
    offset,
    limit,
    has_more: items.length > offset + limit,
  });
};
export function internalResponse(
  url: URL,
  method: string,
  body: D,
  authorized: boolean,
): { status: number; body: unknown } | null {
  const p = url.pathname.replace("/api/v1/", "");
  if (!authorized) return null;
  if (p === "ops/controller")
    return ok({
      scope: "synthetic-quota",
      base_policy: { version: "capacity-v1", headroom_factor: 0.9 },
      effective: {
        revision,
        global_revision: globalRevision,
        generation: "synthetic-generation",
        ready: true,
        kill,
        global_kill: globalKill,
        overrides: {},
        automatic: { "fixture:strong": { pressure: 0.8, concurrency: 2 } },
      },
      circuits: { "fixture:strong": { phase: "closed", disabled: false, probes: 0 } },
      outstanding_capacity_leases: 0,
    });
  if (p === "ops/metrics")
    return ok({
      scope: "synthetic-quota",
      window_seconds: Number(url.searchParams.get("window_seconds") || 3600),
      window_start: date,
      attempts: 1,
      logical_operations: 1,
      workflow_runs: 1,
      business_actions: 1,
      steps: 1,
      retry_attempts: 0,
      estimated_cost_usd_known: "0.0001",
      actual_billed_cost_usd: null,
      unknown_usage_attempts: 0,
      outstanding_unknown_attempts: 1,
      outstanding_unknown_budget_reserved_usd: "0.02",
      window_unknown_budget_reserved_usd: "0",
      latency_ms: { observations: 1, p50: 40, max: 40 },
      provider_health: { success: 1, failure: 0, neutral: 0 },
      routes: { "fixture:strong": 1 },
      routing_roles: { primary: 1 },
      reservation_accuracy: { known_outputs: 1, under_reserved: 0 },
      provider_token_cache: {
        cached_tokens: { known_sum: 0, reported_attempts: 1, unknown_attempts: 0 },
        cache_write_tokens: { known_sum: null, reported_attempts: 0, unknown_attempts: 1 },
        actual_billed_savings_usd: null,
      },
      reuse_global_population: {
        external_observation: {
          decisions: 2,
          dispositions: { hit: 1, miss: 1 },
          actual_billed_savings_usd: null,
        },
        business_artifact: {
          decisions: 1,
          dispositions: { reused: 1 },
          actual_billed_savings_usd: null,
        },
      },
      quality_global_population: {
        random: {
          subjects: 1,
          decisions: 1,
          sampled: 1,
          not_sampled: 0,
          judge_status: { completed: 1 },
          completed_severity: { minor_issue: 1 },
        },
        targeted: {
          subjects: 0,
          decisions: 0,
          sampled: 0,
          not_sampled: 0,
          judge_status: {},
          completed_severity: {},
        },
      },
    });
  if (p === "ops/events")
    return ok(
      Number(url.searchParams.get("after") || 0) >= 1
        ? []
        : [
            {
              id: ids.operation,
              sequence: 1,
              version: "control-event-v1",
              kind: "tick",
              reason: "pressure",
              policy_version: "automatic-control-v1",
              before_revision: 2,
              after_revision: 3,
              occurred_at: date,
              decisions: [],
            },
          ],
    );
  const incident = {
    id: ids.incident,
    attempt_id: ids.attempt,
    revision: incidentRevision,
    reason: "provider_result_business_unconfirmed",
    status: incidentStatus,
    resolution: incidentStatus === "open" ? null : "manual_acknowledge",
  };
  if (p === "ops/recovery-incidents") return ok([incident]);
  if (p === "ops/attention") {
    const rows = [
      {
        ...incident,
        source: "recovery_incident",
        created_at: date,
        reason_code: incident.reason,
        category: "recovery_incident",
        allowed_actions: incidentStatus === "open" ? ["inspect", "reconcile"] : ["inspect"],
      },
      {
        id: ids.attempt,
        attempt_id: ids.attempt,
        source: "attempt",
        created_at: date,
        status: "unknown",
        reason_code: "execution_cancelled",
        category: "unknown_outcome",
        allowed_actions: ["inspect"],
      },
      {
        id: ids.run,
        run_id: ids.run,
        source: "run",
        created_at: date,
        status: "failed",
        reason_code: "grounding_failed",
        category: "execution_failure",
        allowed_actions: ["inspect"],
      },
    ];
    return page(
      url,
      rows.filter(
        (r) => !url.searchParams.get("source") || r.source === url.searchParams.get("source"),
      ),
    );
  }
  if (p === `ops/attempts/${ids.attempt}`)
    return ok({
      id: ids.attempt,
      attempt_id: ids.attempt,
      operation_id: ids.operation,
      status: "unknown",
      created_at: date,
      model_call_id: ids.call,
      artifact_ref: null,
      budget_owner_refs: [ids.run],
      provider_outcome: "execution_cancelled",
      dispatch_confirmed: true,
      dispatched_at: date,
      settled_at: date,
      financial_reservation: { budget_reserved_usd: "0.02" },
      usage: null,
      latency_ms: 40,
    });
  if (p === "ops/controls" && method === "POST") {
    if (receipts.has(String(body.request_id))) return ok(receipts.get(String(body.request_id)));
    if (body.expected_revision !== revision) return error("revision_conflict");
    if (body.action === "global_kill" && body.expected_global_revision !== globalRevision)
      return error("revision_conflict");
    if (body.action === "kill") kill = body.enabled === true;
    if (body.action === "global_kill") {
      globalKill = body.enabled === true;
      globalRevision++;
    }
    revision++;
    const result = { revision, global_revision: globalRevision, kill, global_kill: globalKill };
    receipts.set(String(body.request_id), result);
    return ok(result);
  }
  if (p === `ops/attempts/${ids.attempt}/reconcile` && method === "POST") {
    if (body.expected_revision !== incidentRevision) return error("revision_conflict");
    if (body.resolution === "manual_acknowledge") {
      incidentStatus = "resolved";
      incidentRevision++;
    }
    return ok({
      attempt_id: ids.attempt,
      status: incidentStatus,
      revision: incidentRevision,
      resolution: body.resolution,
    });
  }
  if (p === "runs")
    return page(
      url,
      [
        {
          id: ids.agent,
          kind: "agent",
          workflow: "goal",
          status: "waiting_input",
          reason: "resume_selection_required",
          created_at: date,
        },
        {
          id: ids.run,
          kind: "workflow",
          workflow: "prepare_application",
          status: "completed",
          reason: null,
          created_at: date,
        },
      ].filter((r) => !url.searchParams.get("kind") || r.kind === url.searchParams.get("kind")),
    );
  if (new RegExp(`^runs/(${ids.agent}|${ids.run})$`).test(p))
    return ok({
      id: p.split("/")[1],
      workflow: "prepare_application",
      workflow_version: "prepare-v1",
      status: "completed",
      requested_outputs: ["greeting_generation"],
      outcome: { status: "completed" },
      budget: { cost_limit: "1" },
      consumed_usage: usage,
    });
  if (/^runs\/[^/]+\/steps$/.test(p))
    return ok([
      {
        id: ids.step,
        run_id: ids.run,
        sequence: 1,
        node: "generate_greeting",
        action: null,
        status: "succeeded",
        attempt: 1,
        latency_ms: 40,
        reason_code: null,
        versions: { workflow_version: "prepare-v1" },
      },
    ]);
  if (/^runs\/[^/]+\/calls$/.test(p))
    return ok({
      model_calls: [
        {
          id: ids.call,
          step_id: ids.step,
          task_type: "greeting_generation",
          logical_operation_id: ids.operation,
          provider: "fixture",
          model: "fixture-strong",
          status: "succeeded",
          versions: {
            prompt_version: "greeting_generation_v1",
            prompt_hash: "synthetic",
            model_policy_version: "policy-v1",
          },
          usage,
          latency_ms: 40,
          attempts: 1,
          estimated_cost: "0.0001",
          error_code: null,
          schema_validation_state: "passed",
        },
      ],
      tool_calls: [],
    });
  if (p === `agent-runs/${ids.agent}`)
    return ok({
      run_id: ids.agent,
      state: {
        revision: 2,
        phase: "waiting_input",
        pending_input: "resume_selection_required",
        goal_id: ids.operation,
        bindings: {},
        progress: { actions: [] },
      },
      outcome: null,
    });
  if (p === `agent-runs/${ids.agent}/plans`)
    return ok([
      {
        id: ids.operation,
        revision: 1,
        plan: { actions: [], missing_inputs: ["resume_revision_id"] },
      },
    ]);
  if (p === `agent-runs/${ids.agent}/observations`)
    return ok([
      {
        id: ids.operation,
        observation: { disposition: "blocked", reason_code: "resume_selection_required" },
      },
    ]);
  if (p === "evaluation/suites" && method === "GET")
    return page(url, [
      { id: ids.suite, created_at: date, suite_key: "synthetic-suite", version: 1 },
    ]);
  if (p === `evaluation/suites/${ids.suite}`)
    return ok({
      id: ids.suite,
      created_at: date,
      suite: {
        suite_id: "synthetic-suite",
        version: 1,
        schema_version: "eval-suite-v1",
        members: [{ case_id: "synthetic-greeting", case_version: 1 }],
      },
    });
  const runView = () => ({
    id: ids.evalrun,
    status: evalStatus,
    candidate: {
      schema_version: "candidate-v1",
      code_revision: "synthetic",
      code_hash: "synthetic",
      prompts: {},
      schemas: {},
      components: {},
      model_policy: {},
      validators: {},
      execution_settings: {},
      config_hash: "synthetic",
    },
    summary: { completed: evalStatus === "completed" ? 1 : 0 },
    reason_code: null,
    trials:
      evalStatus === "completed"
        ? [{ id: ids.trial, case_id: ids.case, trial_index: 1, status: "completed", result: trial }]
        : [],
  });
  if (p === "evaluation/runs" && method === "GET")
    return page(url, [
      {
        id: ids.evalrun,
        created_at: date,
        suite_id: ids.suite,
        status: evalStatus,
        started_at: null,
        finished_at: null,
        reason_code: null,
      },
    ]);
  if (p === "evaluation/runs" && method === "POST") {
    evalStatus = "pending";
    return ok(runView(), 201);
  }
  if (p === `evaluation/runs/${ids.evalrun}`) return ok(runView());
  if (p === `evaluation/runs/${ids.evalrun}/execute`) {
    evalStatus = "completed";
    return ok(runView());
  }
  if (p === `evaluation/runs/${ids.evalrun}/cancel`) {
    evalStatus = "cancelled";
    return ok({ id: ids.evalrun, status: evalStatus });
  }
  if (p === "evaluation/trials")
    return page(url, [
      {
        id: ids.trial,
        created_at: date,
        run_id: ids.evalrun,
        case_id: ids.case,
        trial_index: 1,
        status: "completed",
      },
    ]);
  if (p === `evaluation/trials/${ids.trial}`)
    return ok({ id: ids.trial, result: trial, operations: [invocation] });
  if (p === `evaluation/operations/${ids.invocation}`) return ok(invocation);
  if (p === "evaluation/case-index")
    return page(url, [
      {
        id: ids.case,
        created_at: date,
        case_key: "synthetic-greeting",
        version: 1,
        content_hash: "synthetic-hash",
      },
    ]);
  if (p === `evaluation/cases/${ids.case}/origin`)
    return ok({
      mode: "origin_reconstruction",
      model_calls: 0,
      original_output: { marker: "PRIVATE_ORIGIN_SYNTHETIC" },
      original_trace_refs: [],
      origin_output_available: true,
      origin_provenance: { model: "fixture-strong" },
      frozen_source: { marker: "PRIVATE_SOURCE_SYNTHETIC" },
      frozen_input: {},
      external_observations: {},
    });
  if (p === `evaluation/cases/${ids.case}/export`)
    return ok({ case_id: "synthetic-greeting", case_version: 1, source_type: "synthetic" });
  if (p === "evaluation/cases" && method === "POST") return ok({ id: ids.case, case: body }, 201);
  if (p === "evaluation/suites" && method === "POST")
    return ok({ id: ids.suite, suite: body }, 201);
  if (p === "evaluation/comparisons" && method === "GET")
    return page(url, [
      {
        id: ids.comparison,
        created_at: date,
        baseline_id: ids.evalrun,
        candidate_id: ids.evalrun,
        policy_version: "comparison-priority-v2",
      },
    ]);
  if (
    (p === "evaluation/comparisons" && method === "POST") ||
    p === `evaluation/comparisons/${ids.comparison}`
  )
    return ok(comparison);
  if (p === "evaluation/sampling-records")
    return page(url, [
      {
        id: ids.sampling,
        created_at: date,
        subject_id: ids.subject,
        subject,
        policy_version: "judge-sampling-v1",
        effective_rate: "0.1",
        sampled: true,
        reason: "random_sample",
        decision_key: "synthetic",
        population: "random",
      },
    ]);
  if (p === "evaluation/judges")
    return page(url, [
      {
        id: ids.judge,
        created_at: date,
        sampling_id: ids.sampling,
        subject_id: ids.subject,
        task_type: "greeting_generation",
        population: "random",
        status: "completed",
        severity: "minor_issue",
        model_call_id: ids.call,
        reason_code: null,
      },
    ]);
  if (p === `evaluation/judges/${ids.judge}`)
    return ok({
      id: ids.judge,
      status: "completed",
      spec: {
        name: "task-quality",
        version: "task-quality-v1",
        rubric_version: "quality-rubric-v1",
        target: "greeting_generation",
      },
      result: { criteria },
      severity: "minor_issue",
      model_call_id: ids.call,
      reason_code: null,
    });
  if (p === "evaluation/judges/drain") return ok({ completed: 0, failed: 0 });
  if (p === "evaluation/feedback")
    return page(url, [
      {
        id: ids.subject,
        created_at: date,
        subject_id: ids.subject,
        vote: "thumbs_down",
        reason: "not_specific_enough",
      },
    ]);
  if (p === "evaluation/annotations/queue" && method === "GET")
    return ok([
      {
        id: ids.queue,
        subject_id: ids.subject,
        population: "targeted",
        status: annotated ? "annotated" : "pending",
      },
    ]);
  if (p === `evaluation/annotations/queue/${ids.queue}` && method === "GET")
    return ok({
      id: ids.queue,
      subject_id: ids.subject,
      population: "targeted",
      rubric_version: "quality-rubric-v1",
      input: { marker: "PRIVATE_BLIND_INPUT" },
      output: { marker: "PRIVATE_BLIND_OUTPUT" },
      blind: true,
    });
  if (p === `evaluation/annotations/queue/${ids.queue}` && method === "POST") {
    annotated = true;
    return ok({ id: ids.annotation }, 201);
  }
  if (p === "evaluation/annotations/queue" && method === "POST") return ok({ id: ids.queue }, 201);
  if (p === "evaluation/calibration")
    return ok({
      selection_policy: "latest-pair-per-subject-stratum-v1",
      unique_subject_count: 1,
      selected_pair_count: 1,
      populations: { targeted: { raw_agreement: 1, weighted_kappa: null } },
    });
  if (p === "evaluation/captures")
    return page(url, [
      {
        id: ids.capture,
        created_at: date,
        subject_id: ids.subject,
        status: triage,
        content_hash: "synthetic-hash",
      },
    ]);
  if (p === `evaluation/captures/${ids.capture}`)
    return ok({
      id: ids.capture,
      status: triage,
      payload: {
        subject,
        source_snapshot: { marker: "PRIVATE_CAPTURE_SYNTHETIC" },
        model_input: { marker: "PRIVATE_INPUT_SYNTHETIC" },
        output: {},
        external_observations: {},
        provenance: { code_revision: "synthetic" },
        privacy_class: "private",
        content_hash: "synthetic-hash",
      },
      events: [{ kind: "manual", reference_id: null, reason_code: "manual_capture" }],
    });
  if (p === `evaluation/captures/${ids.capture}/sanitized`)
    return ok({
      payload: {
        subject,
        source_snapshot: { safe: true },
        output: {},
        provenance: { code_revision: "synthetic" },
      },
      requires_explicit_promotion: true,
    });
  if (p === `evaluation/captures/${ids.capture}/triage`) {
    triage = String(body.status);
    return ok({ id: ids.capture, status: triage });
  }
  if (p === `evaluation/captures/${ids.capture}/promote`) {
    if (body.confirmed_repo_safe !== true) return error("explicit_review_required");
    triage = "promoted";
    return ok({ id: ids.case, case: body.case }, 201);
  }
  return null;
}
