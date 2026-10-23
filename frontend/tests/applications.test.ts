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
  assert.equal(siblings.has_more, true);
});
test("summary keeps historical bindings, categories and independent failures", async () => {
  const { read } = fixtureReader(),
    repo = applicationRepository(read);
  const ctx = await repo.context(id(1)),
    summary = await repo.summary(ctx);
  assert.equal(summary.packages.state, "ready");
  if (summary.packages.state === "ready")
    assert.notEqual(summary.packages.value[0].job_revision_id, ctx.job.job_revision_id);
  if (summary.research.state === "ready")
    assert.equal(summary.research.value.items[0].reusable_for_current_execution, false);
  if (summary.debrief.state === "ready")
    assert.equal(summary.debrief.value.items[0].is_selected, false);
  assert.ok(!JSON.stringify(summary).includes("PRIVATE_PAYLOAD_NOT_RENDERED"));
  const empty = await repo.summary(await repo.context(id(2)));
  assert.deepEqual(empty.actual, { state: "ready", value: [] });
  const partial = await repo.summary(await repo.context(id(24)));
  assert.equal(partial.research.state, "unavailable");
  assert.equal(partial.submissions.state, "ready");
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
