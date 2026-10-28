import test from "node:test";
import assert from "node:assert/strict";
import { onboardingResponse, resetOnboarding } from "./fixtures/onboarding-api.ts";
import { productRule, validateBody } from "../src/features/workspace/transport-policy.ts";
import { blankProfile, transitions } from "../src/features/onboarding/contracts.ts";
import { id } from "./fixtures/product-api.ts";
const call = (path: string, method = "GET", body: Record<string, unknown> = {}) =>
  onboardingResponse(new URL(`http://fixture/api/v1/${path}`), method, body)!;
test("Product allowlist supports exact onboarding contracts, not arbitrary writes", () => {
  for (const [path, method, body] of [
    ["profile", "PUT", { expected_revision: 0, data: blankProfile() }],
    ["facts", "POST", { statement: "合成事实", category: "project" }],
    [
      `facts/${id(1)}/supersede`,
      "POST",
      { expected_revision: 1, statement: "替代", category: "project" },
    ],
    [
      "jobs",
      "POST",
      {
        company_id: id(1),
        company_name: "合成公司",
        title: "岗位",
        jd_text: "JD",
        requirements: [],
      },
    ],
    [
      `applications/${id(1)}`,
      "PATCH",
      { expected_revision: 1, status: "preparing", correction: false, reason: null },
    ],
    [`resume-variants/${id(1)}/revisions`, "POST", { expected_revision: 1, document: {} }],
  ] as const)
    assert.doesNotThrow(() =>
      validateBody(body, productRule(path, method, new URLSearchParams()).body),
    );
  assert.throws(() => productRule("companies", "POST", new URLSearchParams()));
  assert.throws(() => productRule(`facts/${id(1)}`, "DELETE", new URLSearchParams()));
  assert.throws(() =>
    validateBody({ status: "verified" }, productRule("facts", "POST", new URLSearchParams()).body),
  );
});
test("empty store enforces Profile CAS and replacement fact lifecycle without rewriting historical refs", () => {
  resetOnboarding(true);
  assert.equal(call("profile").status, 404);
  assert.equal(
    call("profile", "PUT", {
      expected_revision: 0,
      data: { ...blankProfile(), display_name: "合成用户" },
    }).status,
    200,
  );
  assert.equal(call("profile", "PUT", { expected_revision: 0, data: blankProfile() }).status, 409);
  call("facts", "POST", { statement: "实现 Python 服务", category: "project" });
  call(`facts/${id(9010)}/verify`, "POST");
  const data = {
    ...blankProfile(),
    display_name: "合成用户",
    projects: [{ organization: "个人项目", role: "开发者", description: "", fact_ids: [id(9010)] }],
  };
  call("profile", "PUT", { expected_revision: 1, data });
  const history = structuredClone(call(`profile/revisions/${id(9002)}`).body);
  const replacement = call(`facts/${id(9010)}/supersede`, "POST", {
    expected_revision: 1,
    statement: "实现并测试 Python 服务",
    category: "project",
  });
  assert.equal(replacement.status, 201);
  assert.deepEqual(call(`profile/revisions/${id(9002)}`).body, history);
  const facts = call("facts").body as {
    status: string;
    revision: number;
    replaces_id: string | null;
  }[];
  assert.equal(facts[0].status, "superseded");
  assert.equal(facts[1].status, "proposed");
  assert.equal(facts[1].revision, 2);
  assert.equal(facts[1].replaces_id, id(9010));
});
test("existing Company is explicit; Application state CAS/correction and notes remain separate", () => {
  resetOnboarding(true);
  const body = { company_name: "合成公司", title: "工程师", jd_text: "Python", requirements: [] };
  call("jobs", "POST", body);
  assert.equal(
    call("jobs", "POST", { ...body, company_id: id(1001), company_name: "错名" }).status,
    422,
  );
  call("jobs", "POST", { ...body, company_id: id(1001) });
  assert.equal((call("companies").body as { items: unknown[] }).items.length, 1);
  assert.equal(
    call(`applications/${id(1)}`, "PATCH", { expected_revision: 0, status: "applied" }).status,
    409,
  );
  assert.equal(
    call(`applications/${id(1)}`, "PATCH", { expected_revision: 1, status: "offer" }).status,
    409,
  );
  assert.equal(
    call(`applications/${id(1)}`, "PATCH", { expected_revision: 1, status: "preparing" }).status,
    200,
  );
  call(`applications/${id(1)}/notes`, "POST", { text: "尚未投递" });
  assert.equal((call(`applications/${id(1)}`).body as { status: string }).status, "preparing");
  assert.deepEqual(transitions.rejected, []);
  assert.equal(transitions.tracking.includes("offer"), false);
});
