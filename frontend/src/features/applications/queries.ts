import { applicationStatuses, UUID_PATTERN, type ApplicationStatus } from "./contracts.ts";
export type Search = Record<string, string | string[] | undefined>;
export type ListQuery = {
  status?: ApplicationStatus;
  company_ids: string[];
  page: number;
};
export const APPLICATION_PAGE_SIZE = 20;
export function parseQuery(search: Search): ListQuery {
  function one(key: string) {
    const v = search[key];
    if (Array.isArray(v)) throw new Error("invalid_query");
    return v || undefined;
  }
  const page = one("page") || "1";
  const rawStatus = one("status");
  const status =
    rawStatus === "preparing" ? "tracking" : rawStatus === "withdrawn" ? "closed" : rawStatus;
  const legacy = one("company_id");
  const values = search.company_ids;
  const companies = [
    ...(Array.isArray(values) ? values : values ? [values] : []),
    ...(legacy ? [legacy] : []),
  ];
  if (
    !/^[1-9]\d{0,5}$/.test(page) ||
    (status && !(applicationStatuses as readonly string[]).includes(status)) ||
    companies.length > 50 ||
    companies.some((id) => !UUID_PATTERN.test(id))
  )
    throw new Error("invalid_query");
  return {
    status: status as ApplicationStatus | undefined,
    company_ids: [...new Set(companies.map((id) => id.toLowerCase()))],
    page: Number(page),
  };
}
export function listHref(query: ListQuery, change: Partial<ListQuery> = {}) {
  const q = { ...query, ...change };
  const params = new URLSearchParams();
  if (q.status) params.set("status", q.status);
  for (const id of q.company_ids) params.append("company_ids", id);
  if (q.page > 1) params.set("page", String(q.page));
  return `/applications${params.size ? `?${params}` : ""}`;
}
