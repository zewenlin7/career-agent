import test from "node:test";
import assert from "node:assert/strict";
import { internalRule, internalBody, internalProjection } from "../src/features/internal/policy.ts";
import { internalResponse, resetInternal, ids } from "./fixtures/internal-api.ts";
const q = new URLSearchParams();
test("Internal allowlist denies arbitrary proxy, unsupported controls endpoints, duplicate query and payload keys", () => {
  for (const p of [
    "https://evil",
    "ops/routing",
    "ops/circuit/open",
    "evaluation/captures/raw",
    "../ops/controller",
    "profile/revisions",
  ])
    assert.throws(() => internalRule(p, "GET", q));
  assert.throws(() => internalRule("ops/controller", "DELETE", q));
  assert.throws(() => internalRule("ops/metrics", "GET", new URLSearchParams("url=http://evil")));
  assert.throws(() =>
    internalRule("ops/metrics", "GET", new URLSearchParams("window_seconds=1&window_seconds=2")),
  );
  assert.throws(() =>
    internalRule(
      `evaluation/operations/${ids.invocation}`,
      "GET",
      new URLSearchParams("private=true"),
    ),
  );
  const rule = internalRule("ops/controls", "POST", q);
  assert.doesNotThrow(() =>
    internalBody(
      {
        request_id: ids.operation,
        expected_revision: 3,
        action: "override",
        route: "fixture:strong",
        ttl_seconds: 300,
        values: { pressure: 0.8 },
      },
      rule.body,
    ),
  );
  assert.throws(() => internalBody({ api_key: "secret" }, rule.body));
  assert.throws(() => internalBody([], rule.body));
});
test("Run/trial/invocation read projections exclude private payload but preserve exact call provenance", () => {
  const op = {
    id: ids.invocation,
    input_snapshot: { secret: "private" },
    output: { body: "private" },
    accepted_model_call_id: ids.call,
    input_hash: "hash",
    provenance: { prompt_version: "v1" },
  };
  const output = internalProjection(`evaluation/trials/${ids.trial}`, {
    id: ids.trial,
    result: { checks: [], output: { secret: "private" }, usage: { cached_tokens: null } },
    operations: [op],
  }) as { result: object; operations: object[] };
  assert.equal(JSON.stringify(output).includes("private"), false);
  assert.equal(JSON.stringify(output).includes(ids.call), true);
  assert.equal(JSON.stringify(output).includes('"cached_tokens":null'), true);
  assert.deepEqual(internalProjection(`evaluation/operations/${ids.invocation}`, op, true), op);
  const run = internalProjection(`evaluation/runs/${ids.evalrun}/execute`, {
    trials: [{ result: { status: "completed", output: { secret: "private" } } }],
  });
  assert.equal(JSON.stringify(run).includes("private"), false);
});
test("Origin reconstruction and blind view require explicit private access; captures never expose raw payload", () => {
  const origin = {
    model_calls: 0,
    original_output: { secret: "private" },
    frozen_source: { secret: "private" },
    frozen_input: {},
    external_observations: {},
    origin_provenance: { model: "fixture" },
  };
  assert.equal(
    JSON.stringify(internalProjection(`evaluation/cases/${ids.case}/origin`, origin)).includes(
      "private",
    ),
    false,
  );
  assert.deepEqual(internalProjection(`evaluation/cases/${ids.case}/origin`, origin, true), origin);
  const blind = {
    blind: true,
    subject_id: ids.subject,
    input: { private: "yes" },
    output: { private: "yes" },
  };
  assert.deepEqual(internalProjection(`evaluation/annotations/queue/${ids.queue}`, blind), {
    blind: true,
    subject_id: ids.subject,
  });
  assert.deepEqual(
    internalProjection(`evaluation/annotations/queue/${ids.queue}`, blind, true),
    blind,
  );
  const capture = {
    id: ids.capture,
    payload: {
      source_snapshot: { secret: "private" },
      model_input: {},
      output: {},
      external_observations: {},
      content_hash: "hash",
    },
    events: [],
  };
  assert.deepEqual(internalProjection(`evaluation/captures/${ids.capture}`, capture, true), {
    id: ids.capture,
    events: [],
    payload_metadata: { content_hash: "hash" },
  });
});
test("Fixture control writes enforce CAS, request idempotency, global revision and exact reconciliation", () => {
  resetInternal();
  const call = (path: string, body: Record<string, unknown>) =>
    internalResponse(new URL(`http://fixture/api/v1/${path}`), "POST", body, true)!;
  const body = {
    request_id: ids.operation,
    expected_revision: 3,
    expected_global_revision: 2,
    action: "global_kill",
    enabled: true,
  };
  assert.equal(call("ops/controls", body).status, 200);
  assert.deepEqual(call("ops/controls", body), call("ops/controls", body));
  assert.equal(call("ops/controls", { ...body, request_id: ids.call }).status, 409);
  assert.equal(
    call(`ops/attempts/${ids.attempt}/reconcile`, {
      expected_revision: 1,
      resolution: "manual_acknowledge",
    }).status,
    200,
  );
  assert.equal(
    call(`ops/attempts/${ids.attempt}/reconcile`, {
      expected_revision: 1,
      resolution: "manual_acknowledge",
    }).status,
    409,
  );
});
