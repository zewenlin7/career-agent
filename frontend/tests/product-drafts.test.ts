import test from "node:test";
import assert from "node:assert/strict";
import { canonical, draftFromProfile } from "../src/features/onboarding/drafts.ts";
import { blankProfile, type Fact, type Profile } from "../src/features/onboarding/contracts.ts";
import { productRule, validateBody } from "../src/features/workspace/transport-policy.ts";
import { id } from "./fixtures/product-api.ts";

test("no-op equality sorts object keys but preserves meaningful entry order", () => {
  assert.equal(canonical({ b: 2, a: [1, 2] }), canonical({ a: [1, 2], b: 2 }));
  assert.notEqual(canonical({ a: [1, 2] }), canonical({ a: [2, 1] }));
});
test("Profile draft maps known structure and refs without inventing evidence", () => {
  const profile: Profile = {
    id: id(1),
    revision: 3,
    created_at: "2026-01-01T00:00:00Z",
    data: {
      ...blankProfile(),
      display_name: "合成用户",
      projects: [
        {
          organization: "合成项目",
          role: "开发",
          description: "实现 Python 测试",
          fact_ids: [id(2)],
        },
      ],
      skills: ["Python", "Rust"],
    },
  };
  const fact = { id: id(2), status: "verified", statement: "实现 Python 测试" } as Fact;
  let sequence = 10;
  const draft = draftFromProfile(profile, [fact], () => id(sequence++));
  assert.equal(draft.profile_id, profile.id);
  assert.equal(draft.profile_revision, 3);
  assert.deepEqual(
    draft.sections.map((section) => section.name),
    ["projects", "skills"],
  );
  assert.deepEqual(draft.sections[0].items[0].fact_refs, [fact.id]);
  assert.deepEqual(draft.sections[1].items[0].fact_refs, [fact.id]);
  assert.deepEqual(draft.sections[1].items[1].fact_refs, []);
  const proposed = draftFromProfile(profile, [{ ...fact, status: "proposed" }], () =>
    id(sequence++),
  );
  assert.deepEqual(proposed.sections[1].items[0].fact_refs, []);
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
