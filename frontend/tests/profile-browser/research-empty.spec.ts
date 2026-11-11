import { test, expect } from "@playwright/test";
const backend = "http://127.0.0.1:3131";
const api = `${backend}/api/v1`;
test("research never-created, sole history without live current, last deletion and refresh", async ({
  page,
  request,
}, info) => {
  await request.post(`${backend}/__reset`);
  const job = await (
    await request.post(`${api}/jobs`, {
      data: { company_name: "空态合成公司", title: "工程师", jd_text: "Python" },
    })
  ).json();
  const path = `/applications/${job.application_id}/research-fit/company`;
  await page.goto(path);
  const empty = async () => {
    await expect(page.getByText("暂无记录。", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "开始研究", exact: true })).toBeEnabled();
    await expect(page.getByLabel("研究记录", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "删除记录", exact: true })).toHaveCount(0);
    await expect(page.locator("[data-result-destination]")).toHaveCount(0);
  };
  await empty();
  expect((await (await request.get(`${backend}/__provider/status`)).json()).calls).toEqual([]);
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: info.outputPath(`never-created-${width}.png`), fullPage: true });
  }
  const op = await (
    await request.post(`${api}/companies/${job.company_id}/research`, {
      data: {
        request_id: crypto.randomUUID(),
        kind: "company_research",
        request: { job_revision_id: job.job_revision_id, mode: "fixture" },
      },
    })
  ).json();
  const done = await (await request.post(`${api}/operations/${op.id}/execute`)).json();
  expect(done.status).toBe("success");
  const historyPath = `${api}/companies/${job.company_id}/research`;
  expect((await request.get(`${historyPath}/current`)).status()).toBe(404);
  expect((await (await request.get(historyPath)).json()).items).toHaveLength(1);
  await page.reload();
  await expect(page.getByLabel("研究记录", { exact: true })).toHaveValue(done.research_report_id);
  await expect(page.getByRole("heading", { name: "研究结论", exact: true })).toBeVisible();
  const calls = (await (await request.get(`${backend}/__provider/status`)).json()).calls;
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await empty();
  expect((await (await request.get(historyPath)).json()).items).toEqual([]);
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.reload();
    await empty();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: info.outputPath(`last-deleted-${width}.png`), fullPage: true });
  }
  expect((await (await request.get(`${backend}/__provider/status`)).json()).calls).toEqual(calls);
});
