import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { id } from "../fixtures/product-api";
import { context } from "../fixtures/workspace-api";
const application = `/applications/${id(1)}`;
const newest = id(27002),
  older = id(27001);
type Kind = "company" | "fit" | "preparation";
const cases = [
  { kind: "company" as const, route: "research-fit/company", label: "研究记录", query: "research" },
  { kind: "fit" as const, route: "research-fit/fit", label: "匹配记录", query: "result" },
  {
    kind: "preparation" as const,
    route: "interview/preparation",
    label: "准备记录",
    query: "result",
  },
];
async function historyFixture(page: Page, request: APIRequestContext, kind: Kind) {
  const raw = await (
    await request.get(`http://127.0.0.1:3111/api/v1/companies/${id(1001)}/research`)
  ).json();
  const target = kind === "fit" ? "fit_analysis" : "interview_preparation";
  const rows = [newest, older].map((key, index) => {
    const marker = index ? "旧记录完整正文" : "新记录完整正文";
    const created = index ? "2026-10-24T19:42:00Z" : "2026-11-01T16:32:00Z";
    if (kind === "company")
      return {
        ...raw.items[0],
        id: key,
        fetched_at: created,
        data: {
          ...raw.items[0].data,
          report: {
            conclusions: [{ text: marker, evidence_refs: [] }],
            inference: [],
            unknowns: [],
          },
        },
      };
    return {
      created_at: created,
      result: {
        available: true,
        kind: target,
        status: "success",
        target_artifact_id: key,
        result_id: key,
        resume_revision_id: null,
        source_resume_revision_id: null,
        resume_variant_id: null,
        revision: null,
        render_artifact_id: null,
        download_url: null,
        context,
        reused: false,
        versions: {},
        reason: null,
        allowed_actions: ["read"],
        content:
          kind === "fit"
            ? { items: [{ requirement_ref: id(7001), status: "no_evidence", explanation: marker }] }
            : {
                likely_topics: [marker],
                knowledge_gaps: [],
                questions_to_ask_interviewer: [],
                technical_questions: [],
                project_deep_dive_questions: [],
                behavioral_questions: [],
                company_specific_questions: [],
              },
      },
    };
  });
  const state = {
    failOld: false,
    failures: 0,
    permitDelete: false,
    failList: false,
    listFailures: 0,
    deleted: new Set<string>(),
    writes: [] as string[],
  };
  await page.route("**/api/product/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname.replace("/api/product/", "");
    const method = route.request().method();
    const isList =
      kind === "company"
        ? p === `companies/${id(1001)}/research`
        : p === `applications/${id(1)}/results` && url.searchParams.get("target") === target;
    const selected =
      kind === "company"
        ? p.match(new RegExp(`^companies/${id(1001)}/research/(${newest}|${older})$`))?.[1]
        : p.match(new RegExp(`^preparation-artifacts/(${newest}|${older})/result$`))?.[1];
    const deleting =
      kind === "company"
        ? selected
        : p.match(new RegExp(`^applications/${id(1)}/results/(${newest}|${older})$`))?.[1];
    if (method === "POST" && (p === "operations" || p === `companies/${id(1001)}/research`)) {
      await route.fulfill({
        json: {
          id: id(27200),
          kind:
            kind === "company"
              ? "company_research"
              : kind === "fit"
                ? "prepare_application"
                : "prepare_interview",
          request_id: id(27201),
          status: "success",
          reason: null,
          research_report_id: kind === "company" ? older : null,
          package_id: kind === "company" ? null : id(27202),
          run_id: id(27203),
          created_at: "2026-11-01T16:32:00Z",
          allowed_actions: ["read"],
        },
      });
    } else if (method === "GET" && p === `preparation-artifacts/${id(27202)}/product-view`) {
      await route.fulfill({ json: { results: [rows[1].result] } });
    } else if (method === "DELETE" && deleting) {
      state.writes.push(deleting);
      if (state.permitDelete) state.deleted.add(deleting);
      await route.fulfill({
        json: {
          deleted: state.permitDelete,
          used_by: state.permitDelete ? [] : ["面试准备（2026-10-26 00:03）"],
        },
      });
    } else if (method === "GET" && isList) {
      if (state.failList) {
        state.listFailures++;
        await route.fulfill({ status: 503, json: { error: { code: "request_failed" } } });
        return;
      }
      await route.fulfill({
        json: {
          items: rows.filter((_, n) => !state.deleted.has(n ? older : newest)),
          limit: 100,
          offset: 0,
          has_more: false,
        },
      });
    } else if (method === "GET" && selected) {
      if (state.failOld && selected === older) {
        state.failures++;
        await route.fulfill({ status: 503, json: { error: { code: "request_failed" } } });
      } else await route.fulfill({ json: rows[selected === newest ? 0 : 1] });
    } else await route.fallback();
  });
  return state;
}
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
for (const item of cases) {
  test(`${item.kind}: refused removal retains exact old selection, contents and history after refresh`, async ({
    page,
    request,
  }) => {
    const state = await historyFixture(page, request, item.kind);
    await page.goto(`${application}/${item.route}?${item.query}=${newest}`);
    const selector = page.getByLabel(item.label, { exact: true });
    await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
    await selector.selectOption(older);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "删除记录", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "无法删除记录", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "知道了", exact: true }).click();
    await expect(selector).toHaveValue(older);
    await expect(selector.locator("option")).toHaveCount(2);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    await selector.selectOption(newest);
    await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
    await selector.selectOption(older);
    await expect(page).toHaveURL(new RegExp(`${item.query}=${older}$`));
    await page.reload();
    await expect(selector).toHaveValue(older);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    expect(state.deleted.size).toBe(0);
    expect(state.writes).toEqual([older]);
  });
  test(`${item.kind}: failed historical switch keeps the previously selected readable result`, async ({
    page,
    request,
  }) => {
    const state = await historyFixture(page, request, item.kind);
    await page.goto(`${application}/${item.route}?${item.query}=${newest}`);
    const selector = page.getByLabel(item.label, { exact: true });
    await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
    state.failOld = true;
    await selector.selectOption(older);
    await expect.poll(() => state.failures).toBeGreaterThan(0);
    await expect(page.getByRole("main").getByRole("alert").first()).toBeVisible();
    await expect(selector).toHaveValue(newest);
    await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
    await expect(page.getByText("旧记录完整正文", { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`${item.query}=${newest}$`));
    state.failOld = false;
    await selector.selectOption(older);
    await expect(selector).toHaveValue(older);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    expect(state.writes).toEqual([]);
  });
  test(`${item.kind}: failed same-path history refresh retains known rows and exact contents`, async ({
    page,
    request,
  }) => {
    const state = await historyFixture(page, request, item.kind);
    await page.goto(`${application}/${item.route}?${item.query}=${older}`);
    const selector = page.getByLabel(item.label, { exact: true });
    await expect(selector.locator("option")).toHaveCount(2);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    if (item.kind === "fit") await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
    state.failList = true;
    await page
      .getByRole("button", {
        name:
          item.kind === "company" ? "重新研究" : item.kind === "fit" ? "开始匹配" : "开始面试准备",
        exact: true,
      })
      .click();
    await expect.poll(() => state.listFailures).toBeGreaterThan(0);
    await expect(page.getByRole("main").getByRole("alert").first()).toBeVisible();
    await expect(selector).toHaveValue(older);
    await expect(selector.locator("option")).toHaveCount(2);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    await expect(page.getByText("新记录完整正文", { exact: true })).toHaveCount(0);
  });
  test(`${item.kind}: confirmed removal survives failed list refresh without a false refusal`, async ({
    page,
    request,
  }) => {
    const state = await historyFixture(page, request, item.kind);
    state.permitDelete = true;
    await page.goto(`${application}/${item.route}?${item.query}=${older}`);
    const selector = page.getByLabel(item.label, { exact: true });
    await expect(selector.locator("option")).toHaveCount(2);
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    state.failList = true;
    await page.getByRole("button", { name: "删除记录", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
    await expect.poll(() => state.deleted.has(older)).toBe(true);
    await expect.poll(() => state.listFailures).toBeGreaterThan(0);
    await expect(page.getByRole("dialog", { name: "无法删除记录", exact: true })).toHaveCount(0);
    await expect(selector).toHaveValue(newest);
    await expect(selector.locator("option")).toHaveCount(1);
    await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
    await expect(page.getByText("旧记录完整正文", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("main").getByRole("alert").first()).toContainText("历史记录");
    state.failList = false;
    await page.reload();
    await expect(selector).toHaveValue(newest);
    await expect(selector.locator("option")).toHaveCount(1);
    expect(state.writes).toEqual([older]);
  });
  test(`${item.kind}: successful removal alone removes the row and selects latest readable result`, async ({
    page,
    request,
  }) => {
    const state = await historyFixture(page, request, item.kind);
    state.permitDelete = true;
    await page.goto(`${application}/${item.route}?${item.query}=${older}`);
    const selector = page.getByLabel(item.label, { exact: true });
    await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "删除记录", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
    await expect(selector).toHaveValue(newest);
    await expect(selector.locator("option")).toHaveCount(1);
    await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
    await expect(page.getByText("旧记录完整正文", { exact: true })).toHaveCount(0);
    await page.reload();
    await expect(selector).toHaveValue(newest);
    expect(state.writes).toEqual([older]);
  });
}

test("completed research receipt restoration cannot override a manually chosen historical record", async ({
  page,
  request,
}) => {
  await historyFixture(page, request, "company");
  const operation = id(27100);
  await page.addInitScript(({ key, operation }) => sessionStorage.setItem(key, operation), {
    key: `career-operation:${id(1)}:company_research:research`,
    operation,
  });
  let release = () => {};
  const responseReady = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/product/operations/${operation}`, async (route) => {
    await responseReady;
    await route.fulfill({
      json: {
        id: operation,
        kind: "company_research",
        status: "success",
        phase: "complete",
        company_id: id(1001),
        research_report_id: newest,
        package_id: null,
        result_links: [],
        reason: null,
        decisions: [],
        requested_targets: [],
        created_at: "2026-11-01T16:32:00Z",
      },
    });
  });
  await page.goto(`${application}/research-fit/company`);
  const selector = page.getByLabel("研究记录", { exact: true });
  await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
  await selector.selectOption(older);
  await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
  release();
  await expect(page.getByRole("button", { name: "重新研究", exact: true })).toBeEnabled();
  await expect(selector).toHaveValue(older);
  await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`research=${older}$`));
});

test("removing the final Prep while history refresh fails cannot resurrect its contents", async ({
  page,
  request,
}) => {
  const state = await historyFixture(page, request, "preparation");
  state.deleted.add(newest);
  state.permitDelete = true;
  await page.goto(`${application}/interview/preparation?result=${older}`);
  await expect(page.getByLabel("准备记录", { exact: true }).locator("option")).toHaveCount(1);
  await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
  state.failList = true;
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect.poll(() => state.listFailures).toBeGreaterThan(0);
  await expect(page.getByRole("dialog", { name: "无法删除记录", exact: true })).toHaveCount(0);
  await expect(page.getByText("旧记录完整正文", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("准备记录", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "删除记录", exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(`${application}/interview/preparation`);
  expect(state.writes).toEqual([older]);
});

test("late historical selection read cannot override browser Back navigation", async ({
  page,
  request,
}) => {
  await historyFixture(page, request, "company");
  const path = `${application}/research-fit/company`;
  await page.goto(path);
  const selector = page.getByLabel("研究记录", { exact: true });
  await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
  await selector.selectOption(older);
  await expect(page.getByText("旧记录完整正文", { exact: true })).toBeVisible();
  let release = () => {};
  const ready = new Promise<void>((resolve) => {
    release = resolve;
  });
  let entered = false;
  await page.route(`**/api/product/companies/${id(1001)}/research/${newest}`, async (route) => {
    entered = true;
    await ready;
    await route.fallback();
  });
  await selector.selectOption(newest);
  await expect.poll(() => entered).toBe(true);
  await page.goBack();
  await expect(page).toHaveURL(path);
  release();
  await expect(page.getByText("新记录完整正文", { exact: true })).toBeVisible();
  await expect(selector).toHaveValue(newest);
  await expect(page).toHaveURL(path);
});
