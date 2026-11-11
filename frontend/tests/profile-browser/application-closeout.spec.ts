import { test, expect } from "@playwright/test";
const backend = "http://127.0.0.1:3131";
const base = `${backend}/api/v1`;
test.beforeEach(async ({ request }) => {
  await request.post(`${backend}/__reset`);
});
async function fill(page: import("@playwright/test").Page) {
  await page.getByLabel("公司名称", { exact: true }).fill("幂等合成公司");
  await page.getByLabel("职位名称", { exact: true }).fill("工程师");
  await page.getByLabel("职位描述", { exact: true }).fill("合成职位 Python 开发");
}
for (const [committed, transport] of [
  [true, "abort"],
  [false, "abort"],
  [true, "408"],
] as const)
  test(`Job lost response committed=${committed} transport=${transport} survives refresh with one intent`, async ({
    page,
    request,
  }, info) => {
    await page.goto("/applications/new");
    await fill(page);
    const ids: string[] = [];
    let lose = true;
    await page.route("**/api/product/jobs", async (route) => {
      ids.push(route.request().postDataJSON().request_id);
      if (lose) {
        if (committed) await route.fetch();
        if (transport === "408")
          await route.fulfill({ status: 408, json: { error: { code: "request_timeout" } } });
        else await route.abort();
      } else await route.continue();
    });
    await page.getByRole("button", { name: "创建职位", exact: true }).click();
    await expect(
      page.getByText("创建结果尚未确认。再次提交会核对同一次请求，不会另建申请。", { exact: true }),
    ).toBeVisible();
    const stored = await page.evaluate(() =>
      JSON.parse(sessionStorage.getItem("career-job-create-v1")!),
    );
    expect(Object.keys(stored).sort()).toEqual(["fingerprint", "id"]);
    expect(stored.id).toBe(ids[0]);
    lose = false;
    await page.reload();
    if (!committed) {
      await expect(page.getByText(/上次创建结果尚未确认/)).toBeVisible();
      await fill(page);
      await page.getByLabel("职位描述", { exact: true }).fill("不同内容");
      await page.getByRole("button", { name: "创建职位", exact: true }).click();
      await expect(page.getByText(/内容与上次提交不同/)).toBeVisible();
      expect(ids).toHaveLength(1);
      await fill(page);
      await page.getByRole("button", { name: "创建职位", exact: true }).click();
    }
    await expect(page).toHaveURL(/\/summary$/);
    expect(new Set(ids).size).toBe(1);
    let jobs = await (await request.get(`${base}/jobs`)).json();
    expect(jobs).toHaveLength(1);
    await expect(page).toHaveURL(new RegExp(jobs[0].application_id));
    expect(await page.evaluate(() => sessionStorage.getItem("career-job-create-v1"))).toBeNull();
    await page.goto("/applications/new");
    await fill(page);
    for (const width of [1280, 375]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({ path: info.outputPath(`job-${width}.png`), fullPage: true });
    }
    await page.getByRole("button", { name: "创建职位", exact: true }).click();
    await expect(page).toHaveURL(/\/summary$/);
    expect(new Set(ids).size).toBe(2);
    jobs = await (await request.get(`${base}/jobs`)).json();
    expect(jobs).toHaveLength(2);
  });

test("deleted Job receipt and old successful notification explain unavailable workspace", async ({
  page,
  request,
}, info) => {
  await page.goto("/applications/new");
  await fill(page);
  let original: { application_id: string; company_id: string; job_revision_id: string };
  await page.route("**/api/product/jobs", async (route) => {
    const response = await route.fetch();
    original = await response.json();
    await route.abort();
  });
  await page.getByRole("button", { name: "创建职位", exact: true }).click();
  await expect(
    page.getByText("创建结果尚未确认。再次提交会核对同一次请求，不会另建申请。", { exact: true }),
  ).toBeVisible();
  const job = original!;
  const op = await (
    await request.post(`${base}/companies/${job.company_id}/research`, {
      data: {
        request_id: crypto.randomUUID(),
        kind: "company_research",
        request: { job_revision_id: job.job_revision_id, mode: "fixture" },
      },
    })
  ).json();
  const done = await (await request.post(`${base}/operations/${op.id}/execute`)).json();
  expect(done.status).toBe("success");
  const path = `${base}/applications/${job.application_id}`;
  await request.patch(path, {
    data: { expected_revision: 1, status: "closed", correction: true, reason: "结束合成申请" },
  });
  expect((await request.delete(path)).status()).toBe(200);
  await page.reload();
  await expect(
    page.getByText("此前创建的申请已删除，无法打开工作区。", { exact: true }),
  ).toBeVisible();
  expect(await (await request.get(`${base}/jobs`)).json()).toHaveLength(1);
  const href = `/applications/${job.application_id}/research-fit/company`;
  await page.evaluate(
    ({ op, href, result }) =>
      localStorage.setItem(
        "career-task-handles-v1",
        JSON.stringify([
          {
            key: `operations:${op}`,
            family: "operations",
            id: op,
            title: "公司研究",
            href,
            notice: { state: "success", selection: { research: result } },
            shownState: "success",
          },
        ]),
      ),
    { op: op.id, href, result: done.research_report_id },
  );
  await page.goto("/applications");
  await expect(page.getByRole("heading", { name: "申请", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "未处理通知 1 条", exact: true }).click();
  const notice = page.getByRole("complementary", { name: "任务通知" });
  await expect(notice.getByText("该申请已删除，无法打开工作区。", { exact: true })).toBeVisible();
  await expect(notice.getByRole("link", { name: "查看结果", exact: true })).toHaveCount(0);
  await expect(notice).toContainText("已完成");
  await page.screenshot({ path: info.outputPath("deleted-notice.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("deleted-notice-375.png"), fullPage: true });
  await notice.getByRole("button", { name: "关闭公司研究通知" }).click();
  await page.reload();
  await expect(notice).toHaveCount(0);
  await page.goto(`/tasks/operations/${op.id}?return_to=${encodeURIComponent(href)}`);
  await expect(page.getByText("该申请已删除，无法打开工作区。", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看结果", exact: true })).toHaveCount(0);
  await page.goto(href);
  await expect(page.getByRole("heading", { name: "申请不可访问", exact: true })).toBeVisible();
  expect(
    (
      await request.get(`${base}/companies/${job.company_id}/research/${done.research_report_id}`)
    ).status(),
  ).toBe(200);
});
