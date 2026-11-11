import assert from "node:assert/strict";
import { test } from "node:test";
import { applicationRepository, type Reader } from "../src/features/applications/repository.ts";
import {
  decodeApplication,
  decodeJob,
  pageOf,
  decodeCompany,
} from "../src/features/applications/contracts.ts";
import { parseQuery, listHref } from "../src/features/applications/queries.ts";
import { BackendError } from "../src/lib/api/error.ts";
import { fixtureResponse, application, job, id } from "./fixtures/product-api.ts";

function fixtureReader() {
  const requests: string[] = [];
  const read: Reader = async (path, decode, query) => {
    const url = new URL(path, "http://fixture.test");
    url.search = query?.toString() || "";
    requests.push(url.pathname + url.search);
    const result = fixtureResponse(url);
    if (result.status !== 200) throw new BackendError("response", result.status);
    return decode(result.body);
  };
  return { read, requests };
}
test("query validation and pagination retain selected company/status", () => {
  const q = parseQuery({ status: "applied", company_id: id(1001), page: "2", company_q: "晨星" });
  assert.match(listHref(q, { page: 3 }), /page=3/);
  assert.match(listHref(q, { page: 3 }), /status=applied/);
  assert.match(listHref(q, { page: 3 }), new RegExp(id(1001)));
  for (const input of [
    { status: "success" },
    { page: "-1" },
    { page: "1.5" },
    { page: ["1", "2"] },
    { company_id: "../../ops" },
  ])
    assert.throws(() => parseQuery(input));
});
test("decode validates lifecycle and strips unrelated payloads", () => {
  assert.throws(() => decodeApplication({ ...application(1), status: "completed" }));
  assert.throws(() =>
    decodeApplication({
      ...application(1),
      events: [{ ...application(1).events[0], application_id: id(2) }],
    }),
  );
  assert.throws(() => decodeJob({ ...job(1), revision: "2" }));
  assert.throws(() =>
    pageOf(decodeCompany)({ items: [], limit: 20, offset: 0, has_more: "false" }),
  );
  assert.ok(!("secret" in decodeApplication({ ...application(1), secret: "PRIVATE" })));
});
test("list is paginated, filtered before joining; no invented companies or API calls", async () => {
  const f = fixtureReader(),
    repo = applicationRepository(f.read);
  const first = await repo.list(parseQuery({ company_id: id(1001) }));
  assert.equal(first.items.length, 20);
  assert.equal(first.has_more, true);
  const second = await repo.list(parseQuery({ company_id: id(1001), page: "2" }));
  assert.equal(second.items.length, 3);
  assert.equal(second.has_more, false);
  assert.equal(new Set([...first.items, ...second.items].map((x) => x.application.id)).size, 23);
  const applied = await repo.list(parseQuery({ status: "applied", company_id: id(1001) }));
  assert.equal(applied.items.length, 1);
  assert.equal(applied.items[0].job.title, "后端工程师");
  assert.ok(
    f.requests.every((p) => p.startsWith("/api/v1/applications?") || p.startsWith("/api/v1/jobs/")),
  );
});
test("exact Application/Job/Company binding rejects mismatches", async () => {
  const { read } = fixtureReader(),
    repo = applicationRepository(read);
  const ctx = await repo.context(id(1));
  assert.equal(ctx.application.id, ctx.job.application_id);
  assert.equal(ctx.company.id, ctx.job.company_id);
  await assert.rejects(() => repo.context(id(88)), /backend_contract/);
  await assert.rejects(
    () => repo.context(id(999)),
    (e) => e instanceof BackendError && e.status === 404,
  );
  const siblings = await repo.siblings(ctx);
  assert.ok(siblings.items.every((x) => x.job.company_id === ctx.company.id));
  assert.equal(siblings.has_more, false);
  assert.equal(siblings.items.length, 23);
});

test("failed Job join never fabricates a row or returns an empty success", async () => {
  const f = fixtureReader();
  const read: Reader = (path, decode, query) =>
    path.startsWith("/api/v1/jobs/")
      ? Promise.reject(new BackendError("unavailable"))
      : f.read(path, decode, query);
  await assert.rejects(
    () => applicationRepository(read).list(parseQuery({})),
    /backend_unavailable/,
  );
});

test("repeated company IDs are bounded, deduplicated and preserved across pages", async () => {
  const query = parseQuery({ company_ids: [id(1001), id(1002), id(1001)], status: "tracking" });
  assert.deepEqual(query.company_ids, [id(1001), id(1002)]);
  const next = new URL(listHref(query, { page: 2 }), "http://test");
  assert.deepEqual(next.searchParams.getAll("company_ids"), query.company_ids);
  const f = fixtureReader(),
    repo = applicationRepository(f.read);
  const first = await repo.list(query);
  const second = await repo.list({ ...query, page: 2 });
  assert.equal(first.items.length, 20);
  assert.equal(second.items.length, 2);
  assert.equal(first.has_more, true);
  assert.equal(second.has_more, false);
  assert.equal(new Set([...first.items, ...second.items].map((i) => i.application.id)).size, 22);
  assert.ok(f.requests[0].includes("company_ids="));
  assert.throws(() => parseQuery({ company_ids: [id(1001), "invalid"] }));
  assert.throws(() => parseQuery({ company_ids: Array(51).fill(id(1001)) }));
});
