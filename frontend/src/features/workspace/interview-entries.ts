import type { Entry } from "./contracts.ts";

/** Current editable numbering; frozen Debrief anchors are never passed through this projection. */
export function projectEntries(entries: Entry[]): Entry[] {
  const ordered = [...entries].sort((a, b) => a.order - b.order);
  const result: Entry[] = [];
  let number = 0;
  for (const parent of ordered.filter((e) => e.kind === "primary")) {
    number++;
    result.push({ ...parent, main_question_number: number, followup_index: null });
    ordered
      .filter((e) => e.primary_entry_id === parent.entry_id)
      .forEach((child, index) => {
        result.push({ ...child, main_question_number: number, followup_index: index + 1 });
      });
  }
  // Invalid legacy relationships remain visible instead of disappearing on a read/edit.
  const included = new Set(result.map((entry) => entry.entry_id));
  result.push(
    ...ordered.filter((entry) => !included.has(entry.entry_id)).map((entry) => ({ ...entry })),
  );
  return result.map((e, index) => ({ ...e, order: index + 1 }));
}

export function moveEntry(entries: Entry[], id: string, direction: -1 | 1): Entry[] {
  const ordered = projectEntries(entries);
  const entry = ordered.find((e) => e.entry_id === id);
  if (!entry) return entries;
  const peers = ordered.filter((e) =>
    entry.kind === "primary" ? e.kind === "primary" : e.primary_entry_id === entry.primary_entry_id,
  );
  const index = peers.findIndex((e) => e.entry_id === id);
  const target = peers[index + direction];
  if (!target) return entries;
  [peers[index], peers[index + direction]] = [peers[index + direction], peers[index]];
  const groups =
    entry.kind === "primary"
      ? peers.flatMap((p) => [p, ...ordered.filter((e) => e.primary_entry_id === p.entry_id)])
      : ordered.flatMap((e) =>
          e.entry_id === entry.primary_entry_id
            ? [e, ...peers]
            : e.primary_entry_id === entry.primary_entry_id
              ? []
              : [e],
        );
  return projectEntries(groups.map((e, index) => ({ ...e, order: index + 1 })));
}
