import { applicationStatuses, UUID_PATTERN, type ApplicationStatus } from "./contracts.ts";
export type Search = Record<string, string | string[] | undefined>;
export type ListQuery = {
  status?: ApplicationStatus;
  company_id?: string;
  page: number;
  company_q: string;
  company_page: number;
};
export const APPLICATION_PAGE_SIZE = 20;
export const COMPANY_PAGE_SIZE = 10;
export function parseQuery(search: Search): ListQuery {
  function one(key: string) {
    const v = search[key];
    if (Array.isArray(v)) throw new Error("invalid_query");
    return v || undefined;
  }
  function page(key: string) {
    const v = one(key) || "1";
    if (!/^[1-9]\d{0,5}$/.test(v)) throw new Error("invalid_query");
    return Number(v);
  }
  const status = one("status");
  const company = one("company_id");
  const q = one("company_q") || "";
  if (
    (status && !(applicationStatuses as readonly string[]).includes(status)) ||
    (company && !UUID_PATTERN.test(company)) ||
    q.length > 200
  )
    throw new Error("invalid_query");
  return {
    status: status as ApplicationStatus | undefined,
    company_id: company?.toLowerCase(),
    page: page("page"),
    company_q: q,
    company_page: page("company_page"),
  };
}
export function listHref(query: ListQuery, change: Partial<ListQuery> = {}) {
  const q = { ...query, ...change };
  const params = new URLSearchParams();
  if (q.status) params.set("status", q.status);
  if (q.company_id) params.set("company_id", q.company_id);
  if (q.page > 1) params.set("page", String(q.page));
  if (q.company_q) params.set("company_q", q.company_q);
  if (q.company_page > 1) params.set("company_page", String(q.company_page));
  return `/applications${params.size ? `?${params}` : ""}`;
}
