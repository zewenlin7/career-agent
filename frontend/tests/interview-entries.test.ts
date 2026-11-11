import test from "node:test";
import assert from "node:assert/strict";
import { moveEntry, projectEntries } from "../src/features/workspace/interview-entries.ts";
import type { Entry } from "../src/features/workspace/contracts.ts";
const items: Entry[] = [
  {
    entry_id: "a",
    order: 1,
    kind: "primary",
    primary_entry_id: null,
    question: "A",
    answer: "answer",
    main_question_number: 8,
  },
  {
    entry_id: "b",
    order: 2,
    kind: "follow_up",
    primary_entry_id: "a",
    question: "B",
    answer: null,
  },
  { entry_id: "c", order: 3, kind: "primary", primary_entry_id: null, question: "C", answer: null },
];
test("current numbering is contiguous without mutating frozen source", () => {
  assert.deepEqual(
    projectEntries(items).map((e) => [e.main_question_number, e.followup_index]),
    [
      [1, null],
      [1, 1],
      [2, null],
    ],
  );
  assert.equal(items[0].main_question_number, 8);
});
test("moving a primary moves its complete group and retains identity and answers", () => {
  const moved = moveEntry(items, "a", 1);
  assert.deepEqual(
    moved.map((e) => e.entry_id),
    ["c", "a", "b"],
  );
  assert.equal(moved[1].answer, "answer");
  assert.equal(moved[2].main_question_number, 2);
});
