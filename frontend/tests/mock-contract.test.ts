import test from "node:test";
import assert from "node:assert/strict";
import { decodeMock, mockGroups } from "../src/features/workspace/mock-contract.ts";

function record() {
  return {
    id: "session",
    revision: 7,
    status: "waiting_answer",
    pending_question_id: "f2",
    primary_question_count: 2,
    followup_count: 2,
    interviewer_turn_count: 4,
    turns: [
      ["p1", "primary", null, "已回答"],
      ["p2", "primary", null, "已回答"],
      ["f1", "follow_up", "p2", "已回答"],
      ["f2", "follow_up", "p2", null],
    ].map(([id, kind, parent, answer], i) => ({
      id,
      sequence: i + 1,
      question: { kind, primary_entry_id: parent, question: "问题正文" },
      answer,
    })),
  };
}
test("decoder and grouping use persisted kinds and parent identity for delayed consecutive followups", () => {
  const value = decodeMock(record());
  assert.deepEqual(
    value.turns.map((t) => t.question_number),
    ["1", "2", "2.1", "2.2"],
  );
  assert.deepEqual(
    mockGroups(value.turns).map((group) => group.map((t) => t.id)),
    [["p1"], ["p2", "f1", "f2"]],
  );
  assert.equal(
    decodeMock({ ...record(), status: "completed", pending_question_id: null }).turns.length,
    4,
  );
});
test("decoder rejects unknown kinds, foreign parents, fabricated counters and false numbering", () => {
  for (const mutate of [
    (r: ReturnType<typeof record>) => {
      r.turns[3].question.kind = "unknown";
    },
    (r: ReturnType<typeof record>) => {
      r.turns[3].question.primary_entry_id = "other-session";
    },
    (r: ReturnType<typeof record>) => {
      r.primary_question_count = 3;
    },
    (r: ReturnType<typeof record>) => {
      Object.assign(r.turns[3], { question_number: "3" });
    },
  ]) {
    const r = record();
    mutate(r);
    assert.throws(() => decodeMock(r), /invalid_response/);
  }
});
