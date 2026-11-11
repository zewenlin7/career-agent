import { api } from "./client";
import type { Page } from "./contracts";

/** Read every page; selections remain exact and browsing never executes work. */
export async function readHistory<T>(path: string, signal: AbortSignal): Promise<Page<T>> {
  const items: T[] = [];
  const url = new URL(path, "http://local");
  const size = 100;
  for (let offset = 0; ; offset += size) {
    url.searchParams.set("limit", String(size));
    url.searchParams.set("offset", String(offset));
    const page = await api<Page<T>>(url.pathname.slice(1) + url.search, "GET", undefined, signal);
    items.push(...page.items);
    if (!page.has_more) return { items, has_more: false, limit: items.length, offset: 0 };
    if (!page.items.length) throw new Error("invalid_history_page");
  }
}
