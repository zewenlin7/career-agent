import test from "node:test";
import assert from "node:assert/strict";
import { canonical } from "../src/features/onboarding/drafts.ts";
import { productRule, validateBody } from "../src/features/workspace/transport-policy.ts";
import { id } from "./fixtures/product-api.ts";

test("no-op equality sorts object keys but preserves meaningful entry order", () => {
  assert.equal(canonical({ b: 2, a: [1, 2] }), canonical({ a: [1, 2], b: 2 }));
  assert.notEqual(canonical({ a: [1, 2] }), canonical({ a: [2, 1] }));
});
test("new Product contracts are narrow; no fixture configuration or authority escalation", () => {
  const cases: [string, string, Record<string, unknown>][] = [
    [
      `applications/${id(1)}/context`,
      "PUT",
      { expected_revision: 1, profile_id: id(2), resume_revision_id: null, job_revision_id: id(3) },
    ],
    [
      "product-drafts",
      "POST",
      {
        request_id: id(4),
        task: "greeting_refinement",
        source_artifact_id: id(5),
        feedback: "简洁一些。",
        mode: "fixture",
      },
    ],
    [`knowledge-notes/${id(6)}`, "PATCH", { expected_revision: 1, title: "合成", content: "内容" }],
    [
      "evaluation/feedback",
      "POST",
      { subject: { subject_id: id(7), task_type: "greeting_generation" }, vote: "thumbs_up" },
    ],
  ];
  for (const [path, method, body] of cases)
    assert.doesNotThrow(() =>
      validateBody(body, productRule(path, method, new URLSearchParams()).body),
    );
  assert.throws(() =>
    validateBody(
      { verified: true },
      productRule("product-drafts", "POST", new URLSearchParams()).body,
    ),
  );
  assert.throws(() => productRule("ops/control", "POST", new URLSearchParams()));
});
