import * as c from "./contracts.ts";
import { APPLICATION_PAGE_SIZE, type ListQuery } from "./queries.ts";
import { BackendError } from "../../lib/api/error.ts";

export type Reader = <T>(
  path: string,
  decode: (v: unknown) => T,
  query?: URLSearchParams,
) => Promise<T>;
export type ReadState<T> = { state: "ready"; value: T } | { state: "unavailable" };
export async function optionalRead<T>(load: () => Promise<T>): Promise<ReadState<T>> {
  try {
    return { state: "ready", value: await load() };
  } catch {
    return { state: "unavailable" };
  }
}
function params(values: Record<string, string | number | undefined>) {
  return new URLSearchParams(
    Object.entries(values)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)]),
  );
}
function match(condition: boolean) {
  if (!condition) throw new BackendError("contract");
}
async function related<T>(load: () => Promise<T>) {
  try {
    return await load();
  } catch (error) {
    if (error instanceof BackendError && error.status === 404) throw new BackendError("contract");
    throw error;
  }
}
export function applicationRepository(read: Reader) {
  async function jobFor(app: c.Application) {
    const job = await related(() => read(`/api/v1/jobs/${app.job_id}`, c.decodeJob));
    match(job.id === app.job_id && job.application_id === app.id);
    return job;
  }
  async function joinApps(apps: c.Application[], companyId?: string) {
    const result: { application: c.Application; job: c.Job }[] = [];
    // Bounded fan-out, not an unbounded whole-company fetch.
    for (let i = 0; i < apps.length; i += 5) {
      const batch = await Promise.all(
        apps.slice(i, i + 5).map(async (application) => {
          const job = await jobFor(application);
          match(!companyId || job.company_id === companyId);
          return { application, job };
        }),
      );
      result.push(...batch);
    }
    return result;
  }
  async function context(id: string): Promise<c.ApplicationContext> {
    const application = await read(`/api/v1/applications/${c.uuid(id)}`, c.decodeApplication);
    match(application.id === id);
    let job = await jobFor(application);
    const bound = await read(`/api/v1/applications/${id}/context`, (value) =>
      c.uuid(c.object(value).job_revision_id),
    );
    if (bound !== job.job_revision_id) {
      const snapshot = await read(`/api/v1/job-revisions/${bound}`, c.object);
      match(snapshot.job_id === job.id && snapshot.job_revision_id === bound);
      // Job-head CAS remains separate from the Application's frozen displayed/input JD.
      job = c.decodeJob({
        ...job,
        title: snapshot.title,
        jd_text: snapshot.jd_text,
        requirements: snapshot.requirements,
        job_revision_id: bound,
      });
    }
    const company = await related(() =>
      read(`/api/v1/companies/${job.company_id}`, c.decodeCompany),
    );
    match(company.id === job.company_id && company.name === job.company_name);
    return { application, job, company };
  }
  async function list(query: ListQuery) {
    const filters = params({
      status: query.status,
      limit: APPLICATION_PAGE_SIZE,
      offset: (query.page - 1) * APPLICATION_PAGE_SIZE,
    });
    for (const id of query.company_ids) filters.append("company_ids", id);
    const page = await read("/api/v1/applications", c.pageOf(c.decodeApplication), filters);
    match(
      page.limit === APPLICATION_PAGE_SIZE &&
        page.offset === (query.page - 1) * APPLICATION_PAGE_SIZE,
    );
    match(!query.status || page.items.every((a) => a.status === query.status));
    const items = await joinApps(page.items);
    match(
      !query.company_ids.length ||
        items.every(({ job }) => query.company_ids.includes(job.company_id)),
    );
    return { ...page, items };
  }
  async function company(id: string) {
    const row = await read(`/api/v1/companies/${c.uuid(id)}`, c.decodeCompany);
    match(row.id === id);
    return row;
  }
  async function siblings(ctx: c.ApplicationContext) {
    const items: c.Application[] = [];
    for (let offset = 0; ; offset += 100) {
      const page = await read(
        "/api/v1/applications",
        c.pageOf(c.decodeApplication),
        params({ company_id: ctx.company.id, limit: 100, offset }),
      );
      items.push(...page.items);
      if (!page.has_more) break;
    }
    return { items: await joinApps(items, ctx.company.id), has_more: false };
  }

  return { context, list, company, siblings };
}
