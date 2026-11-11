import type { Mock } from "./contracts";

const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const count = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 0;

/** Decode saved identities, never predict a model decision from mode or array position. */
export function decodeMock(value: unknown): Mock {
  const fail = (): never => {
    throw new Error("invalid_response");
  };
  if (
    !object(value) ||
    typeof value.id !== "string" ||
    !count(value.revision) ||
    !["ready_to_generate", "waiting_answer", "completed"].includes(String(value.status)) ||
    !Array.isArray(value.turns)
  )
    return fail();
  const ids = new Set<string>(),
    sequences = new Set<number>();
  const primaries = new Map<string, number>(),
    follows = new Map<string, number>();
  const turns = [...value.turns]
    .sort((a, b) => Number(a?.sequence) - Number(b?.sequence))
    .map((raw): Mock["turns"][number] => {
      if (
        !object(raw) ||
        typeof raw.id !== "string" ||
        ids.has(raw.id) ||
        !count(raw.sequence) ||
        raw.sequence < 1 ||
        sequences.has(raw.sequence) ||
        !object(raw.question) ||
        typeof raw.question.question !== "string" ||
        !raw.question.question.trim() ||
        (raw.answer !== null && typeof raw.answer !== "string")
      )
        return fail();
      ids.add(raw.id);
      sequences.add(raw.sequence);
      const q = raw.question;
      let main: number,
        follow: number | null = null;
      if (q.kind === "primary" && q.primary_entry_id === null) {
        main = primaries.size + 1;
        primaries.set(raw.id, main);
      } else if (
        q.kind === "follow_up" &&
        typeof q.primary_entry_id === "string" &&
        primaries.has(q.primary_entry_id)
      ) {
        main = primaries.get(q.primary_entry_id)!;
        follow = (follows.get(q.primary_entry_id) || 0) + 1;
        follows.set(q.primary_entry_id, follow);
      } else return fail();
      const number = follow === null ? String(main) : `${main}.${follow}`;
      if (
        (raw.question_number !== undefined && raw.question_number !== number) ||
        (raw.main_question_number !== undefined && raw.main_question_number !== main) ||
        (raw.followup_index !== undefined && raw.followup_index !== follow)
      )
        return fail();
      return {
        ...raw,
        question_number: number,
        main_question_number: main,
        followup_index: follow,
      } as Mock["turns"][number];
    });
  if (
    value.primary_question_count !== primaries.size ||
    value.followup_count !== turns.length - primaries.size ||
    value.interviewer_turn_count !== turns.length
  )
    return fail();
  if (
    value.pending_question_id !== null &&
    !turns.some((t) => t.id === value.pending_question_id && t.answer === null)
  )
    return fail();
  if (value.status === "completed" && value.pending_question_id !== null) return fail();
  return { ...value, turns } as Mock;
}

export function mockGroups(turns: Mock["turns"]): Mock["turns"][] {
  return turns
    .filter((t) => t.question.kind === "primary")
    .map((primary) => [
      primary,
      ...turns.filter(
        (t) => t.question.kind === "follow_up" && t.question.primary_entry_id === primary.id,
      ),
    ]);
}
