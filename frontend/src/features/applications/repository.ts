import * as c from "./contracts.ts";
import { APPLICATION_PAGE_SIZE, COMPANY_PAGE_SIZE, type ListQuery } from "./queries.ts";
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
    const job = await jobFor(application);
    const company = await related(() =>
      read(`/api/v1/companies/${job.company_id}`, c.decodeCompany),
    );
    match(company.id === job.company_id && company.name === job.company_name);
    return { application, job, company };
  }
  async function list(query: ListQuery) {
    const page = await read(
      "/api/v1/applications",
      c.pageOf(c.decodeApplication),
      params({
        status: query.status,
        company_id: query.company_id,
        limit: APPLICATION_PAGE_SIZE,
        offset: (query.page - 1) * APPLICATION_PAGE_SIZE,
      }),
    );
    match(
      page.limit === APPLICATION_PAGE_SIZE &&
        page.offset === (query.page - 1) * APPLICATION_PAGE_SIZE,
    );
    match(!query.status || page.items.every((a) => a.status === query.status));
    return { ...page, items: await joinApps(page.items, query.company_id) };
  }
  async function companies(query: ListQuery) {
    return read(
      "/api/v1/companies",
      c.pageOf(c.decodeCompany),
      params({
        q: query.company_q || undefined,
        limit: COMPANY_PAGE_SIZE,
        offset: (query.company_page - 1) * COMPANY_PAGE_SIZE,
      }),
    );
  }
  async function company(id: string) {
    const row = await read(`/api/v1/companies/${c.uuid(id)}`, c.decodeCompany);
    match(row.id === id);
    return row;
  }
  async function siblings(ctx: c.ApplicationContext) {
    const page = await read(
      "/api/v1/applications",
      c.pageOf(c.decodeApplication),
      params({ company_id: ctx.company.id, limit: 8, offset: 0 }),
    );
    return { ...page, items: await joinApps(page.items, ctx.company.id) };
  }
  async function summary(ctx: c.ApplicationContext) {
    const id = ctx.application.id;
    const takeOne = params({ limit: 1, offset: 0 });
    const [research, packages, submissions, mock, actual, debrief] = await Promise.all([
      optionalRead(async () => {
        const p = await read(
          `/api/v1/companies/${ctx.company.id}/research`,
          c.pageOf(c.decodeResearch),
          takeOne,
        );
        match(p.items.every((r) => r.company_id === ctx.company.id));
        return p;
      }),
      optionalRead(() =>
        read(
          `/api/v1/applications/${id}/preparation-packages`,
          (v) => c.array(v, c.decodePackage),
          params({ limit: 3, offset: 0 }),
        ),
      ),
      optionalRead(async () => {
        const p = await read(
          `/api/v1/applications/${id}/submissions`,
          c.pageOf(c.decodeSubmission),
          takeOne,
        );
        match(p.items.every((r) => r.application_id === id));
        return p;
      }),
      optionalRead(async () => {
        const p = await read(
          "/api/v1/mock-interviews",
          c.pageOf(c.decodeMock),
          params({ application_id: id, limit: 1, offset: 0 }),
        );
        match(p.items.every((r) => r.job_id === ctx.job.id));
        return p;
      }),
      optionalRead(async () => {
        const p = await read(
          "/api/v1/interviews",
          (v) => c.array(v, c.decodeActual),
          params({ application_id: id, limit: 1, offset: 0 }),
        );
        match(p.every((r) => r.application_id === id));
        return p;
      }),
      optionalRead(() =>
        read(
          "/api/v1/interview-debriefs",
          c.pageOf(c.decodeDebrief),
          params({ application_id: id, limit: 1, offset: 0 }),
        ),
      ),
    ]);
    return { research, packages, submissions, mock, actual, debrief };
  }
  return { context, list, companies, company, siblings, summary };
}
export type Summary = Awaited<ReturnType<ReturnType<typeof applicationRepository>["summary"]>>;
