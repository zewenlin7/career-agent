import test from "node:test";
import assert from "node:assert/strict";
import { invalidShortText, safeResumeFields } from "../src/features/profile-area/short-text.ts";

test("short expressions compare trimmed Unicode code points like backend", () => {
  assert.equal(invalidShortText("正文", "正文"), true);
  assert.equal(invalidShortText("正文", "更长正文"), true);
  assert.equal(invalidShortText(" 正文 ", " 正 "), false);
  assert.equal(invalidShortText("😀文", "😀"), false);
  assert.equal(invalidShortText("正文", null), false);
  assert.equal(invalidShortText("ab", "\ufeffa"), true);
  assert.equal(invalidShortText("ab", "\u0085a"), false);
});
test("only safe short-expression locations cross the BFF", () => {
  assert.deepEqual(
    safeResumeFields([
      {
        section: 0,
        item: 1,
        field: "short_text",
        code: "short_text_not_shorter",
        input: "private",
      },
      { section: -1, item: 0, field: "short_text", code: "short_text_not_shorter" },
      { section: 0, item: 0, field: "password", code: "raw_error" },
    ]),
    [{ section: 0, item: 1, field: "short_text", code: "short_text_not_shorter" }],
  );
});
