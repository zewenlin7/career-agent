import test from "node:test";
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";
import {
  entryFields,
  personalFields,
  errorMessage,
} from "../src/features/profile-area/contracts.ts";
import { productRule, validateBody } from "../src/features/workspace/transport-policy.ts";
import { id } from "./fixtures/product-api.ts";

test("education/work/project labels and required fields are distinct and optional roles stay optional", () => {
  assert.deepEqual(
    entryFields.education.filter((f) => f[3]).map((f) => f[0]),
    ["organization"],
  );
  assert.deepEqual(
    entryFields.projects.filter((f) => f[3]).map((f) => f[0]),
    ["organization"],
  );
  assert.equal(entryFields.education.find((f) => f[0] === "major")?.[3], false);
  assert.equal(entryFields.projects.find((f) => f[0] === "role")?.[3], false);
  assert.deepEqual(
    personalFields.filter((f) => f[3]).map((f) => f[0]),
    ["display_name"],
  );
  assert.equal(entryFields.education[0][1], "学校名称");
  assert.equal(entryFields.experiences[0][1], "单位名称");
  assert.equal(entryFields.projects[0][1], "项目名称");
});
test("Profile editing/photo/library BFF is bounded, no arbitrary file or internal authority", () => {
  for (const [path, method, body] of [
    [
      "profile-workspace/sections/skills",
      "PATCH",
      { expected_revision: 1, value: "语言：Python\n\n工程：测试\n" },
    ],
    ["profile-workspace/restore", "POST", { expected_revision: 1, profile_id: id(1) }],
    [`resume-library/versions/${id(1)}`, "PATCH", { expected_revision: 1, name: "求职简历" }],
  ] as const) {
    assert.doesNotThrow(() =>
      validateBody(body, productRule(path, method, new URLSearchParams()).body),
    );
  }
  assert.doesNotThrow(() => productRule("profile-photos", "POST", new URLSearchParams()));
  assert.throws(() => productRule("profile-photos/../../etc/passwd", "GET", new URLSearchParams()));
  assert.throws(() =>
    productRule("profile-workspace/sections/fact_ids", "PATCH", new URLSearchParams()),
  );
  assert.throws(() => productRule("ops/controllers", "GET", new URLSearchParams()));
  assert.throws(() =>
    validateBody({ status: "verified" }, productRule("facts", "POST", new URLSearchParams()).body),
  );
});
test("user-facing conflict and review errors are actionable Chinese without internal codes", () => {
  assert.match(errorMessage("profile_in_use"), /申请/);
  assert.match(errorMessage("resume_draft_needs_review"), /确认/);
  assert.match(errorMessage("revision_conflict"), /输入仍保留/);
  assert.doesNotMatch(errorMessage("unexpected_private_error"), /unexpected|private/);
});

test("Profile area keeps publishing/debug vocabulary out of product copy", () => {
  const root = new URL("../src/features/profile-area/", import.meta.url);
  for (const file of readdirSync(root).filter((name) => name.endsWith(".tsx"))) {
    const source = readFileSync(new URL(file, root), "utf8");
    assert.doesNotMatch(
      source,
      /技术详情|查看关联标识|当前资料|设为当前|恢复草稿|保存草稿|正式简历|审核简历|每行一项|归档/,
      file,
    );
  }
});
test("Named profile, saved expression and cancellation requests use explicit BFF paths", () => {
  for (const [path, method, body] of [
    ["profile-library", "POST", {}],
    [`profile-library/${id(1)}`, "PATCH", { expected_revision: 1, name: "上海资料" }],
    [
      `resume-workspaces/${id(1)}/editions`,
      "POST",
      { request_id: id(2), expected_revision: 1, name: "简历", document: { sections: [] } },
    ],
    [`product-drafts/${id(1)}/cancel`, "POST", {}],
  ] as const) {
    assert.doesNotThrow(() =>
      validateBody(body, productRule(path, method, new URLSearchParams()).body),
    );
  }
});

test("Facts navigation is retired and route redirects; feedback accepts comment and Application", () => {
  const nav = readFileSync(
    new URL("../src/features/profile-area/navigation.tsx", import.meta.url),
    "utf8",
  );
  const route = readFileSync(
    new URL("../src/app/(product)/profile/facts/page.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(nav, /profile\/facts|事实库/);
  assert.match(route, /redirect\("\/profile"\)/);
  assert.doesNotThrow(() =>
    validateBody(
      {
        subject: { subject_id: id(1), task_type: "greeting_generation" },
        vote: "thumbs_down",
        comment: "更具体",
        application_id: id(2),
      },
      productRule("evaluation/feedback", "POST", new URLSearchParams()).body,
    ),
  );
});

test("retired Facts and review/publish APIs are absent from the Product BFF", () => {
  for (const [path, method] of [
    ["facts", "GET"],
    ["facts", "POST"],
    [`facts/${id(1)}/verify`, "POST"],
    [`facts/${id(1)}/reject`, "POST"],
    [`facts/${id(1)}/supersede`, "POST"],
    ["fact-library", "GET"],
    ["fact-library/actions", "POST"],
    [`fact-library/${id(1)}`, "PATCH"],
    [`resume-workspaces/${id(1)}/review`, "POST"],
    [`resume-workspaces/${id(1)}/publish`, "POST"],
  ])
    assert.throws(() => productRule(path, method, new URLSearchParams()));
});
