import { test } from "node:test";
import assert from "node:assert/strict";
import { errorText } from "../src/features/workspace/contracts.ts";
test("material failure copy distinguishes local budget, provider throttling and attempt limits", () => {
  assert.match(errorText("budget_exhausted"), /预算/);
  assert.doesNotMatch(errorText("budget_exhausted"), /稍后重试/);
  assert.match(errorText("provider_429"), /请求过多/);
  assert.match(errorText("operation_attempt_limit"), /尝试次数/);
});

test("post-provider validation failures are not quota failures or instructions to inspect internals", () => {
  assert.match(errorText("layout_budget_exceeded"), /篇幅/);
  assert.doesNotMatch(errorText("layout_budget_exceeded"), /使用限制|稍后|预算/);
  assert.match(errorText("grounding_failed"), /事实核验/);
  assert.doesNotMatch(errorText("unrecognized_failure"), /版本|来源|schema/);
});
