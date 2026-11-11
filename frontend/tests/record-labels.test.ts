import assert from "node:assert/strict";
import test from "node:test";
import { researchRecordName, resultRecordName } from "../src/features/workspace/record-labels.ts";

test("record names use known metadata consistently without inventing missing history", () => {
  assert.equal(
    researchRecordName("晨星科技", "2026-10-24T19:42:00Z"),
    "晨星科技 · 2026-10-25 03:42",
  );
  assert.equal(researchRecordName("晨星科技", "invalid"), "晨星科技");
  assert.equal(researchRecordName(undefined, null), "公司研究");
  assert.equal(
    resultRecordName("fit_analysis", "晨星科技", "后端工程师", null),
    "后端工程师 · 晨星科技",
  );
  assert.equal(
    resultRecordName("interview_preparation", "晨星科技", "后端工程师", null),
    "晨星科技 · 后端工程师",
  );
  assert.equal(resultRecordName("interview_preparation", null, null, "invalid"), "准备记录");
  assert.equal(resultRecordName("resume_tailoring", null, null, null, "已命名简历"), "已命名简历");
});
