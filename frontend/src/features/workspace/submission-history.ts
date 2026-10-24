import type { Page, Submission } from "./contracts.ts";
/** Read all ordinary backend pages before making an actual-use assertion. No latest pointer. */
export async function collectSubmissionHistory(
  read: (offset: number) => Promise<Page<Submission>>,
): Promise<Submission[]> {
  const records = new Map<string, Submission>();
  let offset = 0;
  while (true) {
    const page = await read(offset);
    if (page.offset !== offset || page.limit < 1 || (page.has_more && !page.items.length))
      throw new Error("invalid_pagination");
    for (const item of page.items) records.set(item.id, item);
    if (!page.has_more) return [...records.values()];
    offset += page.limit;
  }
}
