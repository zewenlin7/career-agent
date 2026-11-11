import { test } from "node:test";
import assert from "node:assert/strict";
import { taskMessage } from "../src/features/workspace/task-feedback.ts";
import { pendingNotices } from "../src/features/workspace/task-tracker.ts";
test("page and notification use truthful action-specific failure descriptions", () => {
  assert.equal(
    taskMessage("简历调整", { state: "failure", reason: "product_input_too_large" }),
    "简历调整未开始：输入内容过长，请精简后重试。",
  );
  assert.match(
    taskMessage("简历重新生成", { state: "failure", reason: "grounding_failed" }),
    /^简历重新生成失败：生成内容未通过校验/,
  );
  assert.match(
    taskMessage("简历调整", { state: "unknown", reason: "provider_timeout" }),
    /尚未确认/,
  );
  assert.doesNotMatch(
    taskMessage("简历调整", { state: "failure", reason: "unclassified" }),
    /格式|超时|未保存/,
  );
});
test("shown is not acknowledged and final state changes remain pending", () => {
  const task = {
    key: "x",
    family: "product-drafts",
    id: "x",
    title: "简历调整",
    href: "/",
    shownState: "failure",
    notice: { state: "failure", selection: {} },
  };
  assert.equal(pendingNotices([task]).length, 1);
  assert.equal(pendingNotices([{ ...task, dismissedState: "failure" }]).length, 0);
  assert.equal(pendingNotices([{ ...task, dismissedState: "unknown" }]).length, 1);
});

test("saved generation and binding failure remain separate outcomes", () => {
  assert.equal(
    taskMessage("简历优化", { state: "success", reason: "resume_binding_conflict" }),
    "简历已保存，但申请使用的资料已变化。请重新选择要使用的简历。",
  );
  assert.match(
    taskMessage("简历优化", { state: "success", reason: "resume_binding_unknown" }),
    /简历已保存，替换结果尚未确认/,
  );
});
