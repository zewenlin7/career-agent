import { test, expect } from "@playwright/test";
import { taskMessage } from "../../src/features/workspace/task-feedback";
const backend = "http://127.0.0.1:3131";
for (const feature of ["company", "fit"] as const) {
  test(`real delayed ${feature} execution permits navigation and resumes exact operation`, async ({
    page,
    request,
  }) => {
    const executions: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && /operations\/[^/]+\/execute$/.test(r.url()))
        executions.push(r.url());
    });
    await request.post(`${backend}/__reset`);
    await page.goto("/profile");
    await page.getByRole("button", { name: "新建", exact: true }).click();
    await page.getByLabel("姓名", { exact: true }).fill("离线求职者");
    await page.getByRole("textbox", { name: "技能", exact: true }).fill("Python、API 开发");
    await page.getByRole("button", { name: "保存", exact: true }).last().click();
    await expect(page.getByRole("button", { name: "编辑", exact: true }).first()).toBeVisible();
    const profiles = await (await request.get(`${backend}/api/v1/profile-library`)).json();
    const job = await (
      await request.post(`${backend}/api/v1/jobs`, {
        data: { company_name: "离线公司", title: "后端工程师", jd_text: "熟悉 Python API 开发。" },
      })
    ).json();
    const root = `/applications/${job.application_id}`;
    await page.goto(`${root}/research-fit/${feature}`);
    if (feature === "fit")
      await page.getByLabel("个人资料", { exact: true }).selectOption(profiles.items[0].profile_id);
    await request.post(`${backend}/__provider/hold`);
    try {
      await page
        .getByRole("button", { name: feature === "company" ? "开始研究" : "开始匹配", exact: true })
        .click();
      await expect
        .poll(
          async () => (await (await request.get(`${backend}/__provider/status`)).json()).entered,
        )
        .toBe(true);
      const ops = await (await request.get(`${backend}/api/v1/operations`)).json();
      expect(ops.items).toHaveLength(1);
      const operationId = ops.items[0].id;
      await page.getByRole("button", { name: "研究与匹配" }).click();
      await page.getByRole("menuitem", { name: "职位描述", exact: true }).click();
      await expect(page.getByRole("heading", { name: "职位描述", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "研究与匹配" }).click();
      await page
        .getByRole("menuitem", {
          name: feature === "company" ? "公司研究" : "岗位匹配",
          exact: true,
        })
        .click();
      await expect(page.getByRole("button", { name: "正在生成…" })).toBeDisabled();
      await page.getByRole("link", { name: "概览", exact: true }).click();
      await expect(page.getByRole("heading", { name: "最新准备结果", exact: true })).toBeVisible();
      await request.post(`${backend}/__provider/release`);
      await expect
        .poll(
          async () =>
            (await (await request.get(`${backend}/api/v1/operations/${operationId}`)).json())
              .status,
          { timeout: 20000 },
        )
        .toBe("success");
      await expect(page).toHaveURL(new RegExp("/summary$"));
      const notification = page.getByRole("complementary", { name: "任务通知" });
      await expect(notification).toContainText("已完成");
      await page.screenshot({
        path: `/private/tmp/reliability-${feature}-notification-desktop.png`,
      });
      await page.setViewportSize({ width: 375, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await expect(notification).toBeVisible();
      await page.screenshot({
        path: `/private/tmp/reliability-${feature}-notification-narrow.png`,
      });
      await page.setViewportSize({ width: 1280, height: 720 });
      const resultLink = notification.getByRole("link", { name: "查看结果" });
      const href = await resultLink.getAttribute("href");
      expect(href).toContain(feature === "company" ? "research=" : "result=");
      await page.reload();
      await expect(page.getByLabel("新通知", { exact: true })).toHaveCount(0);
      await notification.getByRole("button", { name: /未处理通知/ }).click();
      await expect(notification.getByRole("link", { name: "查看结果" })).toHaveAttribute(
        "href",
        href!,
      );
      await notification.getByRole("button", { name: /关闭.*通知/ }).click();
      await page.reload();
      await expect(notification).toHaveCount(0);
      await page.getByRole("button", { name: "研究与匹配" }).click();
      await page
        .getByRole("menuitem", {
          name: feature === "company" ? "公司研究" : "岗位匹配",
          exact: true,
        })
        .click();
      await expect(page.getByLabel(feature === "company" ? "研究记录" : "匹配记录")).toBeVisible();
      await expect(page.getByRole("button", { name: "正在生成…" })).toHaveCount(0);
      await page.reload();
      await expect(page.getByLabel(feature === "company" ? "研究记录" : "匹配记录")).toBeVisible();
      const after = await (await request.get(`${backend}/api/v1/operations`)).json();
      expect(after.items).toHaveLength(1);
      expect(after.items[0].id).toBe(operationId);
      expect(executions).toHaveLength(1);
      expect(
        await page.evaluate(() =>
          Object.keys(sessionStorage).filter((key) => key.startsWith("career-operation:")),
        ),
      ).toEqual([]);
      const calls = (await (await request.get(`${backend}/__provider/status`)).json()).calls;
      expect(calls).toEqual(
        feature === "company"
          ? ["company_research_synthesis"]
          : ["job_requirement_extraction", "fit_analysis"],
      );
    } finally {
      await request.post(`${backend}/__provider/release`);
    }
  });
}

test("Fit repeats are new operations with explicit reuse feedback and unchanged artifact history", async ({
  page,
  request,
}) => {
  await request.post(`${backend}/__reset`);
  await page.goto("/profile");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await page.getByLabel("姓名", { exact: true }).fill("离线背景");
  await page.getByRole("textbox", { name: "技能", exact: true }).fill("Python API 开发");
  await page.getByRole("button", { name: "保存", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "编辑", exact: true }).first()).toBeVisible();
  const profiles = await (await request.get(`${backend}/api/v1/profile-library`)).json();
  const profileId = profiles.items[0].profile_id;
  const job = await (
    await request.post(`${backend}/api/v1/jobs`, {
      data: { company_name: "复用公司", title: "研发", jd_text: "熟悉 Python API 开发" },
    })
  ).json();
  await page.goto(`/applications/${job.application_id}/research-fit/fit`);
  await page.getByLabel("个人资料", { exact: true }).selectOption(profileId);
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByLabel("匹配记录")).toBeVisible();
  await expect(page.getByRole("button", { name: "开始匹配", exact: true })).toBeEnabled();
  await expect(page.getByLabel("个人资料", { exact: true })).toHaveValue(profileId);
  const first = await page.getByLabel("匹配记录").inputValue();
  const statusBefore = await (await request.get(`${backend}/__provider/status`)).json();
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(
    page.getByText(
      "已找到匹配分析。此前已使用相同的职位描述和求职材料完成分析，本次直接展示已有结果，未重新生成。",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByLabel("匹配记录")).toHaveValue(first);
  await expect(page.getByLabel("匹配记录").locator("option")).toHaveCount(1);
  const ops = await (await request.get(`${backend}/api/v1/operations`)).json();
  expect(ops.items).toHaveLength(2);
  expect(new Set(ops.items.map((o: { request_id: string }) => o.request_id)).size).toBe(2);
  const calls = await (await request.get(`${backend}/__provider/status`)).json();
  expect(calls.calls).toEqual(statusBefore.calls);
  await page.getByRole("button", { name: /未处理通知/ }).click();
  await expect(page.getByRole("complementary", { name: "任务通知" })).toContainText(
    "已使用已有结果",
  );
  const summary = await (
    await request.get(`${backend}/api/v1/applications/${job.application_id}/summary`)
  ).json();
  expect(JSON.stringify(summary)).toContain(first);
  const reuse = page.getByText(
    "已找到匹配分析。此前已使用相同的职位描述和求职材料完成分析，本次直接展示已有结果，未重新生成。",
    { exact: true },
  );
  const noticeBox = await reuse.boundingBox();
  const selectorBox = await page.getByLabel("匹配记录").boundingBox();
  expect(noticeBox!.y).toBeGreaterThan(selectorBox!.y);
  await page.getByRole("button", { name: "关闭复用提示" }).click();
  await expect(reuse).toHaveCount(0);
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(reuse).toBeVisible();
  const shownAt = Date.now();
  await expect(reuse).toHaveCount(0, { timeout: 8000 });
  expect(Date.now() - shownAt).toBeGreaterThan(4500);
  await expect(page.getByLabel("匹配记录")).toHaveValue(first);
  const record = profiles.items[0];
  const updated = await (
    await request.patch(`${backend}/api/v1/profile-library/${record.id}/sections/skills`, {
      data: { expected_revision: record.section_revisions.skills, value: "Python API 开发、SQL" },
    })
  ).json();
  await page.reload();
  await page.getByLabel("个人资料", { exact: true }).selectOption(updated.profile_id);
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByLabel("匹配记录").locator("option")).toHaveCount(2);
  const second = await page.getByLabel("匹配记录").inputValue();
  expect(second).not.toBe(first);
  const invalidSource = await (
    await request.patch(`${backend}/api/v1/profile-library/${record.id}/sections/skills`, {
      data: {
        expected_revision: updated.section_revisions.skills,
        value: "Python API 开发、SQL、Docker",
      },
    })
  ).json();
  await request.post(`${backend}/__provider/invalid-fit`);
  await page.reload();
  await page.getByLabel("个人资料", { exact: true }).selectOption(invalidSource.profile_id);
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: /岗位匹配.*(失败|未完成)/ }),
  ).toBeVisible();
  await expect(page.getByLabel("匹配记录")).toHaveValue(second);
  await expect(page.getByLabel("匹配记录").locator("option")).toHaveCount(2);
  await expect(page.getByLabel("个人资料", { exact: true })).toHaveValue(invalidSource.profile_id);
  const failures = (await (await request.get(`${backend}/api/v1/operations`)).json()).items;
  const failed = failures.find((op: { status: string }) => op.status === "failure");
  expect(failed).toBeTruthy();
  const beforeNavigation = (await (await request.get(`${backend}/__provider/status`)).json()).calls;
  await page.getByRole("link", { name: "概览", exact: true }).click();
  const notification = page.getByRole("complementary", { name: "任务通知" });
  await notification.getByRole("button", { name: /未处理通知/ }).click();
  const failureText = taskMessage("岗位匹配", { state: "failure", reason: failed.reason });
  await expect(notification).toContainText(failureText);
  await expect(notification.getByRole("link", { name: "查看任务", exact: true })).toHaveCount(0);
  await page.evaluate(() => sessionStorage.clear());
  await page.reload();
  await notification.getByRole("button", { name: /未处理通知/ }).click();
  await expect(notification).toContainText(failureText);
  expect((await (await request.get(`${backend}/__provider/status`)).json()).calls).toEqual(
    beforeNavigation,
  );

  await expect(
    page.getByText(
      "已找到匹配分析。此前已使用相同的职位描述和求职材料完成分析，本次直接展示已有结果，未重新生成。",
      { exact: true },
    ),
  ).toHaveCount(0);
});
