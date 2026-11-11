import { writeFile } from "node:fs/promises";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
const base = "http://127.0.0.1:3131/api/v1";
test.beforeEach(async ({ request, page }) => {
  page.on("pageerror", (error) => console.log("BROWSER_ERROR", error.message, error.stack));
  await request.post("http://127.0.0.1:3131/__reset");
});
async function profile(page: Page) {
  await page.goto("/profile");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  const region = page.getByRole("region", { name: "个人信息", exact: true });
  await region.getByLabel("姓名", { exact: true }).fill("合成求职者");
  await region.getByLabel("所在城市（选填）").fill("上海");
  const projects = page.getByRole("region", { name: "项目经历", exact: true });
  await projects.getByRole("button", { name: "添加项目经历", exact: true }).click();
  await projects.getByLabel("项目名称", { exact: true }).fill("离线项目");
  await projects.getByLabel("项目描述（选填）").fill("实现事务回滚测试。");
  await projects.getByLabel("技术栈（选填）").fill("Python");
  await page.getByRole("button", { name: "保存", exact: true }).last().click();
  await expect(projects.getByText("实现事务回滚测试。", { exact: true })).toBeVisible();
  await expect(projects.getByRole("textbox", { name: "项目名称", exact: true })).toHaveCount(0);
}
async function sources(request: APIRequestContext) {
  return (await (await request.get(base + "/profile-library")).json()).items;
}
async function newResume(page: Page, request: APIRequestContext) {
  const p = (await sources(request))[0];
  await page.goto("/profile/resumes");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await page.getByLabel("个人资料", { exact: true }).selectOption(p.profile_id);
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByText("已创建", { exact: true })).toBeVisible();
}

test("Profile selector, new edit, name, cancellation, no-op and deletion protection", async ({
  page,
  request,
}, info) => {
  await profile(page);
  const first = (await sources(request))[0];
  await page.reload();
  await expect(page.getByRole("region", { name: "个人信息", exact: true })).toHaveCount(0);
  await page.getByRole("combobox", { name: "个人资料", exact: true }).selectOption(first.id);
  const personal = page.getByRole("region", { name: "个人信息", exact: true });
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(personal.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "修改资料名称" }).click();
  await page.getByRole("textbox", { name: "修改资料名称" }).fill("AI 求职资料");
  await page.getByRole("textbox", { name: "修改资料名称" }).press("Enter");
  await expect(page.getByRole("heading", { name: "AI 求职资料", exact: true })).toBeVisible();
  await personal.getByLabel("所在城市（选填）").fill("杭州");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect((await sources(request))[0].data.personal.city).toBe("上海");
  await page.getByRole("button", { name: "修改资料名称" }).click();
  await page.getByRole("textbox", { name: "修改资料名称" }).fill("上海资料");
  await page.getByRole("textbox", { name: "修改资料名称" }).press("Enter");
  await expect(page.getByRole("heading", { name: "上海资料", exact: true })).toBeVisible();
  const job = await (
    await request.post(base + "/jobs", {
      data: { company_name: "合成公司", title: "研发", jd_text: "开发服务" },
    })
  ).json();
  const ctx = await (
    await request.get(base + `/applications/${job.application_id}/context`)
  ).json();
  await request.put(base + `/applications/${job.application_id}/context`, {
    data: {
      expected_revision: ctx.revision,
      profile_id: first.profile_id,
      resume_revision_id: null,
      job_revision_id: job.job_revision_id,
    },
  });
  await page.getByRole("button", { name: "删除", exact: true }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(
    page.getByText("这份资料正被申请使用，请先在申请概览中更换资料。", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("profile-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("profile-mobile.png"), fullPage: true });
});

test("photo persists and optional fields stay optional", async ({ page, request }) => {
  await profile(page);
  const region = page.getByRole("region", { name: "个人信息", exact: true });
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII=",
    "base64",
  );
  await region
    .getByLabel("个人照片（选填）")
    .setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: png });
  await expect(region.getByAltText("个人照片")).toBeVisible();
  await page.getByRole("button", { name: "保存", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  const p = (await sources(request))[0];
  expect((await request.get(base + "/profile-photos/" + p.data.personal.photo_id)).status()).toBe(
    200,
  );
  await page.reload();
  await page.getByRole("combobox", { name: "个人资料", exact: true }).selectOption(p.id);
  await expect(region.getByAltText("个人照片")).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await region.getByRole("button", { name: "移除" }).click();
  await page.getByRole("button", { name: "保存", exact: true }).last().click();
  await expect(region.getByAltText("个人照片")).toHaveCount(0);
});

test("resume creates once, saves without facts, rename and real PDF confirmation in place", async ({
  page,
  request,
}, info) => {
  await profile(page);
  await newResume(page, request);
  const original = (await (await request.get(base + "/resume-workspaces")).json())[0];
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.getByRole("button", { name: "新建", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "修改简历名称" }).click();
  await page.getByRole("textbox", { name: "修改简历名称" }).fill("我的简历");
  await page.getByRole("textbox", { name: "修改简历名称" }).press("Enter");
  await expect(page.getByRole("heading", { name: "我的简历", exact: true })).toBeVisible();
  await page.getByLabel("项目经历内容 1").fill("离线项目\nPython\n实现回滚测试。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: /^我的简历/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  const all = await (await request.get(base + "/resume-workspaces")).json();
  expect(all.length).toBe(1);
  expect(
    (await (await request.get(base + `/resume-workspaces/${original.id}`)).json()).document
      .sections[0].items[0].text,
  ).toContain("事务");
  await page.getByRole("heading", { name: /^我的简历/ }).dblclick();
  await page.getByRole("textbox", { name: "修改简历名称" }).fill("投递简历");
  await page.getByRole("textbox", { name: "修改简历名称" }).press("Enter");
  await expect(page.getByRole("heading", { name: /^投递简历/ })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 600 });
  const renderButton = page.getByRole("button", { name: "生成 PDF", exact: true });
  await renderButton.scrollIntoViewIfNeeded();
  const scrollBefore = await page.evaluate(() => window.scrollY);
  const navigation: string[] = [];
  page.on("request", (r) => {
    if (r.isNavigationRequest()) navigation.push(r.url());
  });
  await renderButton.click();
  await expect(page.getByText("以下内容需要确认", { exact: true })).toHaveCount(0);
  const link = page.getByRole("link", { name: "下载 PDF", exact: true });
  await expect(link).toBeVisible();
  expect(navigation).toEqual([]);
  expect(Math.abs((await page.evaluate(() => window.scrollY)) - scrollBefore)).toBeLessThan(5);
  const pdf = await request.get("http://127.0.0.1:3130" + (await link.getAttribute("href")));
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("resume-mobile.png"), fullPage: true });
  expect(await page.locator("main").innerText()).not.toMatch(
    /草稿|正式简历|审核简历|技术详情|[0-9a-f]{8}-[0-9a-f]{4}/,
  );
});

test("AI resume is explicit and uses selected profile", async ({ page, request }) => {
  await profile(page);
  const p = (await sources(request))[0];
  await page.goto("/profile/resumes");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await page.getByLabel("个人资料", { exact: true }).selectOption(p.profile_id);
  await page.getByLabel("创建方式").selectOption("ai");
  let paid = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/product-drafts") && r.method() === "POST") paid++;
  });
  await expect(page.getByText("此操作会使用 AI。", { exact: true })).toHaveCount(0);
  expect(paid).toBe(0);
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  expect(paid).toBe(1);
  const saved = (await (await request.get(base + "/resume-workspaces")).json())[0];
  await page.reload();
  await page.getByRole("combobox", { name: "简历", exact: true }).selectOption(saved.id);
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByRole("link", { name: "下载 PDF", exact: true })).toBeVisible();
});

test("Facts Product route redirects and no entry remains", async ({ page }) => {
  await page.goto("/profile/facts");
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByRole("link", { name: "事实库", exact: true })).toHaveCount(0);
  await expect(page.getByRole("table", { name: "事实列表" })).toHaveCount(0);
});

for (const [target, path, workflow] of [
  ["resume_tailoring", "apply/resume", "prepare_application"],
  ["greeting_generation", "apply/greeting", "prepare_application"],
  ["interview_preparation", "interview/preparation", "prepare_interview"],
] as const) {
  test(`${target}: feedback is non-generating, refinement saves lineage and preserves source`, async ({
    page,
    request,
  }) => {
    await profile(page);
    await newResume(page, request);
    await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
    await expect(page.getByRole("link", { name: "下载 PDF", exact: true })).toBeVisible();
    const saved = (await (await request.get(base + "/resume-library/versions")).json()).items[0];
    const job = await (
      await request.post(base + "/jobs", {
        data: { company_name: "合成公司", title: "开发工程师", jd_text: "需要 Python 项目经验。" },
      })
    ).json();
    const context = await (
      await request.get(base + `/applications/${job.application_id}/context`)
    ).json();
    await request.put(base + `/applications/${job.application_id}/context`, {
      data: {
        expected_revision: context.revision,
        profile_id: saved.profile_id,
        resume_revision_id: saved.id,
        job_revision_id: job.job_revision_id,
      },
    });
    const generated = await request.post(base + `/workflows/${workflow}`, {
      data: {
        profile_id: saved.profile_id,
        resume_revision_id: saved.id,
        job_revision_id: job.job_revision_id,
        ...(workflow === "prepare_application" ? { targets: [target] } : {}),
      },
    });
    expect(generated.status(), await generated.text()).toBe(201);
    const results = () =>
      request
        .get(base + `/applications/${job.application_id}/results?target=${target}`)
        .then((r) => r.json());
    const initial = (await results()).items[0];
    expect(initial).toBeTruthy();
    await page.goto(`/applications/${job.application_id}/${path}`);
    let generations = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/product-drafts")) generations++;
    });
    const positiveSaved = page.waitForResponse(
      (r) => r.url().endsWith("/evaluation/feedback") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "有帮助", exact: true }).click();
    expect((await positiveSaved).status()).toBe(201);
    await expect(page.getByRole("button", { name: "有帮助", exact: true })).toBeDisabled();
    await page.reload();
    await page.getByRole("button", { name: "不满意", exact: true }).click();
    await page.getByLabel("意见（选填）").fill("请突出事务测试。");
    const negativeSaved = page.waitForResponse(
      (r) => r.url().endsWith("/evaluation/feedback") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "保存", exact: true }).click();
    expect((await negativeSaved).status()).toBe(201);
    await expect(page.getByRole("button", { name: "不满意", exact: true })).toBeDisabled();
    expect(generations).toBe(0);
    await page.getByRole("button", { name: "调整", exact: true }).click();
    await page.getByLabel("告诉 AI 你想怎么调整").fill("请突出事务测试，保持事实不变。");
    await page.getByRole("button", { name: "开始调整", exact: true }).click();
    if (target === "resume_tailoring") {
      await page.getByRole("button", { name: "取消替换", exact: true }).click();
    } else if (target === "interview_preparation") {
      await expect(page.getByRole("button", { name: "保存", exact: true })).toHaveCount(0);
    }
    await expect.poll(async () => (await results()).items.length).toBe(2);
    expect(generations).toBe(1);
    const headers = { "X-Ops-Token": "synthetic-profile-browser-token" };
    const feedback = await (
      await request.get(base + `/evaluation/feedback?application_id=${job.application_id}`, {
        headers,
      })
    ).json();
    expect(feedback.items).toHaveLength(2);
    expect(feedback.items[0].comment).toBe("请突出事务测试。");
    const lineage = await (
      await request.get(base + `/evaluation/refinements?feedback_id=${feedback.items[0].id}`, {
        headers,
      })
    ).json();
    expect(lineage.items).toHaveLength(1);
    expect(lineage.items[0].source_artifact_id).toBe(initial.result.target_artifact_id);
    const newer = (await results()).items.find(
      (i: { result: { target_artifact_id: string } }) =>
        i.result.target_artifact_id !== initial.result.target_artifact_id,
    );
    await page
      .getByLabel(
        target === "resume_tailoring"
          ? "优化记录"
          : target === "greeting_generation"
            ? "招呼语记录"
            : "准备记录",
        { exact: true },
      )
      .selectOption(newer.result.target_artifact_id);
    await expect(page.getByRole("button", { name: "有帮助", exact: true })).toBeEnabled();
    const newFeedback = page.waitForResponse(
      (r) => r.url().endsWith("/evaluation/feedback") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "有帮助", exact: true }).click();
    expect((await newFeedback).status()).toBe(201);
    expect(generations).toBe(1);
    const newerFeedback = await (
      await request.get(
        base + `/evaluation/feedback?subject_id=${newer.result.feedback_target.subject_id}`,
        { headers },
      )
    ).json();
    expect(newerFeedback.items).toHaveLength(1);

    if (target === "resume_tailoring") {
      const library = (await (await request.get(base + "/resume-library/versions")).json()).items;
      const saved = library.find((r: { id: string }) => r.id === newer.result.resume_revision_id);
      const renamed = await request.patch(base + `/resume-library/versions/${saved.id}`, {
        data: { expected_revision: saved.metadata_revision, name: "岗位专用简历" },
      });
      expect(renamed.status()).toBe(200);
      await page.reload();
      await expect(page.getByLabel("优化记录").locator("option:checked")).toHaveText(
        "岗位专用简历",
      );
      const removed = await request.delete(base + `/resume-library/versions/${saved.id}`, {
        data: { expected_revision: (await renamed.json()).metadata_revision },
      });
      expect(removed.status()).toBe(200);
      await page.reload();
      await expect(page.getByLabel("优化记录").locator("option")).toHaveCount(1);
      await expect(page.getByLabel("优化记录")).toHaveValue(initial.result.target_artifact_id);
      expect(generations).toBe(1);
      for (const action of ["调整", "重新生成"]) {
        const previous = (await results()).items.map(
          (item: { result: { target_artifact_id: string } }) => item.result.target_artifact_id,
        );
        await request.post("http://127.0.0.1:3131/__provider/hold");
        try {
          await page.getByRole("button", { name: action, exact: true }).click();
          if (action === "调整") {
            await page.getByPlaceholder("输入调整意见").fill("保留事实，精简表达。");
            await page.getByRole("button", { name: "开始调整", exact: true }).click();
          }
          await expect
            .poll(
              async () =>
                (await (await request.get("http://127.0.0.1:3131/__provider/status")).json())
                  .entered,
            )
            .toBe(true);
          await page.getByRole("button", { name: "投递材料", exact: true }).click();
          await page.getByRole("menuitem", { name: "招呼语", exact: true }).click();
          await expect(page.getByRole("heading", { name: "招呼语", exact: true })).toBeVisible();
          await request.post("http://127.0.0.1:3131/__provider/release");
          await expect.poll(async () => (await results()).items.length).toBe(previous.length + 1);
          await expect(page).toHaveURL(/apply\/greeting$/);
          await expect(page.getByRole("dialog", { name: "替换当前申请简历？" })).toHaveCount(0);
          const fresh = (await results()).items.find(
            (item: { result: { target_artifact_id: string } }) =>
              !previous.includes(item.result.target_artifact_id),
          );
          await page.reload();
          const notice = page.getByRole("complementary", { name: "任务通知" });
          await notice.getByRole("button", { name: /未处理通知/ }).click();
          const link = notice.locator(`a[href$="result=${fresh.result.target_artifact_id}"]`);
          await expect(link).toBeVisible();
          await link.click();
          await expect(page.getByLabel("优化记录", { exact: true })).toHaveValue(
            fresh.result.target_artifact_id,
          );
        } finally {
          await request.post("http://127.0.0.1:3131/__provider/release");
        }
      }
      expect(generations).toBe(3);
    }

    expect(
      (await results()).items.some(
        (i: { result: { target_artifact_id: string } }) =>
          i.result.target_artifact_id === initial.result.target_artifact_id,
      ),
    ).toBe(true);
  });
}

test("inline names commit only on Enter; Profile history is not a Product control", async ({
  page,
  request,
}) => {
  await profile(page);
  const initial = (await sources(request))[0];
  await expect(page.getByText("历史版本", { exact: true })).toHaveCount(0);
  const title = page.getByRole("heading", { name: initial.name, exact: true });
  await title.dblclick();
  let input = page.getByRole("textbox", { name: "修改资料名称" });
  await input.fill("不应保存");
  await input.press("Escape");
  expect((await sources(request))[0].name).toBe(initial.name);
  await title.dblclick();
  input = page.getByRole("textbox", { name: "修改资料名称" });
  await input.fill("失焦不保存");
  await page.getByRole("heading", { name: "个人资料", exact: true }).click();
  await expect(input).toHaveCount(0);
  expect((await sources(request))[0].name).toBe(initial.name);
  await newResume(page, request);
  const before = (await (await request.get(base + "/resume-workspaces")).json())[0];
  await page.getByRole("button", { name: "修改简历名称" }).click();
  const resumeInput = page.getByRole("textbox", { name: "修改简历名称" });
  await resumeInput.fill("取消名称");
  await resumeInput.press("Escape");
  expect((await (await request.get(base + "/resume-workspaces")).json())[0].name).toBe(before.name);
  await page.getByRole("button", { name: "修改简历名称" }).click();
  await resumeInput.fill("保存名称");
  await resumeInput.press("Enter");
  await expect(page.getByRole("heading", { name: "保存名称", exact: true })).toBeVisible();
  const after = await (await request.get(base + "/resume-workspaces")).json();
  expect(after).toHaveLength(1);
  expect(after[0].id).toBe(before.id);
  expect(after[0].document).toEqual(before.document);
});

test("global editing keeps local saves isolated, cancels, adds and deletes entries", async ({
  page,
  request,
}, info) => {
  await profile(page);
  const original = (await sources(request))[0];
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const personal = page.getByRole("region", { name: "个人信息", exact: true });
  const skills = page.getByRole("region", { name: "技能", exact: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("profile-edit-mobile.png"), fullPage: true });
  await personal.getByLabel("所在城市（选填）").fill("杭州");
  await skills.getByRole("textbox").fill("语言：Python\n工程：测试");
  await personal.hover();
  await personal.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("已保存");
  await expect(page.getByRole("status")).toHaveCount(0, { timeout: 3500 });
  expect((await sources(request))[0].data).toEqual(original.data);
  await expect(skills.getByRole("textbox")).toHaveValue("语言：Python\n工程：测试");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect((await sources(request))[0].data).toEqual(original.data);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const education = page.getByRole("region", { name: "教育经历", exact: true });
  await education.getByRole("button", { name: "添加教育经历" }).click();
  await education.getByLabel("学校名称", { exact: true }).fill("合成大学");
  await education.getByLabel("入学时间（选填）").fill("2020-09");
  await expect(education.locator("datalist option").first()).toHaveText("1月");
  await page.getByRole("button", { name: "保存", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  const saved = (await sources(request))[0];
  expect(saved.data.education[0].start_date).toBe("2020-09");
  expect(saved.profile_id).not.toBe(original.profile_id);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await education.hover();
  await education.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(education.getByLabel("学校名称", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect((await sources(request))[0].data.education).toEqual(saved.data.education);
});

for (const mode of ["quick", "ai"]) {
  test(`${mode} Resume supports shared AI optimization and persistent feedback`, async ({
    page,
    request,
  }) => {
    await profile(page);
    const p = (await sources(request))[0];
    await page.goto("/profile/resumes");
    await page.getByRole("button", { name: "新建", exact: true }).click();
    await page.getByLabel("个人资料", { exact: true }).selectOption(p.profile_id);
    await page.getByLabel("创建方式", { exact: true }).selectOption(mode);
    await page.getByRole("button", { name: "创建", exact: true }).click();
    await expect(page.getByText("已创建", { exact: true })).toBeVisible();
    let calls = 0;
    page.on("request", (request) => {
      if (request.method() === "POST" && /product-drafts\/[^/]+\/execute$/.test(request.url()))
        calls++;
    });
    await expect(page.getByRole("button", { name: "有帮助", exact: true })).toHaveCount(0);
    const old = await page.getByLabel("简历", { exact: true }).inputValue();
    await page.getByRole("button", { name: "AI 优化", exact: true }).click();
    await expect(page.getByRole("button", { name: "AI 优化", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "删除", exact: true })).toBeHidden();
    await page.getByRole("button", { name: "取消", exact: true }).click();
    expect(calls).toBe(0);
    await expect(page.getByRole("button", { name: "删除", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "AI 优化", exact: true }).click();
    await page.getByLabel("你希望怎么优化？").fill("突出离线测试，保持事实不变。");
    await page.getByRole("button", { name: "优化", exact: true }).click();
    await expect(page.getByLabel("简历", { exact: true })).not.toHaveValue(old);
    await expect(page.getByRole("button", { name: "有帮助", exact: true })).toHaveCount(0);
    const selected = await page.getByLabel("简历", { exact: true }).inputValue();
    expect(calls).toBe(1);
    await expect(page.getByLabel("简历", { exact: true }).locator("option:checked")).toContainText(
      "AI优化版",
    );
    const subject = await (await request.get(base + `/resume-library/subjects/${selected}`)).json();
    const stored = await request.post(base + "/evaluation/feedback", {
      data: { subject: subject.feedback_target, vote: "thumbs_down", comment: "需要进一步精简" },
    });
    expect(stored.status()).toBe(201);
    expect(calls).toBe(1);
    await expect(page.getByLabel("简历", { exact: true }).locator("option:checked")).toContainText(
      "AI优化版",
    );
    const records = await (
      await request.get(base + `/evaluation/feedback?subject_id=${selected}`, {
        headers: { "X-Ops-Token": "synthetic-profile-browser-token" },
      })
    ).json();
    expect(records.items[0].comment).toBe("需要进一步精简");
    expect(records.items[0].task_type).toBe("resume_refinement");
    await page.reload();
    await page.getByLabel("简历", { exact: true }).selectOption(selected);
    await expect(page.getByRole("button", { name: "AI 优化", exact: true })).toBeVisible();
  });
}

test("unrendered Quick Resume can bind an Application without a PDF or fact review", async ({
  page,
  request,
}) => {
  await profile(page);
  await newResume(page, request);
  const draft = (await (await request.get(base + "/resume-workspaces")).json())[0];
  const job = await (
    await request.post(base + "/jobs", {
      data: { company_name: "合成公司", title: "开发工程师", jd_text: "需要 Python 项目经验。" },
    })
  ).json();
  await page.goto(`/applications/${job.application_id}/summary`);
  const region = page.getByRole("region", { name: "当前使用简历", exact: true });
  await region.getByRole("button", { name: "更换", exact: true }).click();
  await region.getByLabel("简历", { exact: true }).selectOption(draft.id);
  await region.getByRole("button", { name: "保存", exact: true }).click();
  await expect(region.getByRole("button", { name: "更换", exact: true })).toBeVisible();
  const binding = await (
    await request.get(base + `/applications/${job.application_id}/context`)
  ).json();
  expect(binding.resume_revision_id).toBeTruthy();
  expect(
    await (
      await request.get(base + `/resume-revisions/${binding.resume_revision_id}/renders`)
    ).json(),
  ).toEqual([]);
  await page.goto(`/applications/${job.application_id}/research-fit/fit`);
  const fit = page.getByRole("region", { name: "岗位匹配", exact: true });
  await expect(fit.getByRole("button", { name: "开始匹配", exact: true })).toBeDisabled();
  await fit.getByLabel("简历").selectOption(binding.resume_revision_id);
  await expect(fit.getByRole("button", { name: "开始匹配", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "研究与匹配" }).click();
  await page.getByRole("menuitem", { name: "职位描述", exact: true }).click();
  const jd = page.locator("#job-description");
  await jd.getByRole("button", { name: "编辑", exact: true }).click();
  await jd
    .getByLabel("职位描述")
    .fill("完整的新职位描述，包含 Python 服务开发。始终由用户发起匹配分析。");
  await jd.getByRole("button", { name: "保存", exact: true }).click();
  await expect(jd.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "概览", exact: true }).click();
  await expect(page.getByRole("region", { name: "职位描述", exact: true })).toContainText(
    "完整的新职位描述",
  );
  const notes = page.getByRole("region", { name: "申请笔记", exact: true });
  await notes.getByRole("button", { name: "添加申请笔记" }).click();
  await notes.getByLabel("新笔记").fill("真实后端保存的合成笔记");
  await notes.getByLabel("新笔记").press("Enter");
  await expect(notes.getByLabel("新笔记")).toHaveCount(0);
  await expect(notes.getByText("真实后端保存的合成笔记", { exact: true })).toBeVisible();
  const state = page.getByRole("region", { name: "申请状态", exact: true });
  await state.getByRole("button", { name: "更改" }).click();
  await state.getByRole("combobox", { name: "状态", exact: true }).selectOption("offer");
  await state.getByRole("button", { name: "保存", exact: true }).click();
  await expect(state.getByText("已获录用", { exact: true })).toBeVisible();
  await region.getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`revision=${binding.resume_revision_id}`));
  await expect(page.getByRole("link", { name: "← 返回简历库" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "项目经历", exact: true })).toBeVisible();
  await expect(page.getByText("实现事务回滚测试。", { exact: true })).toBeVisible();
});

test("presentation visibility and work/project order persist without another Resume", async ({
  page,
  request,
}) => {
  await profile(page);
  const p = (await sources(request))[0];
  await request.patch(base + `/profile-library/${p.id}/sections/experiences`, {
    data: {
      expected_revision: p.section_revisions.experiences,
      value: [{ organization: "合成公司", role: "研发", description: "完成接口测试。" }],
    },
  });
  await newResume(page, request);
  const id = await page.getByLabel("简历", { exact: true }).inputValue();
  const before = (await (await request.get(base + `/resume-workspaces/${id}`)).json()).document;
  await expect(page.getByRole("button", { name: "有帮助", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const section = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "工作经历", exact: true }) })
    .last();
  await section.getByRole("button", { name: "隐藏", exact: true }).click();
  await expect(section.getByRole("button", { name: "显示", exact: true })).toBeVisible();
  await expect(page.getByText("工作经历内容 1 · 已隐藏", { exact: true })).toBeVisible();
  expect((await (await request.get(base + `/resume-workspaces/${id}`)).json()).document).toEqual(
    before,
  );
  expect((await (await request.get(base + "/resume-workspaces")).json()).length).toBe(1);
  await section.getByRole("button", { name: "显示", exact: true }).click();
  await expect(page.getByText("工作经历内容 1 · 已隐藏", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "交换工作与项目顺序" }).first().click();
  await expect
    .poll(async () => page.getByRole("heading", { level: 3 }).allTextContents())
    .toEqual(["合成求职者", "项目经历", "工作经历"]);
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByRole("link", { name: "下载 PDF", exact: true })).toBeVisible();
  await expect(page.getByText("PDF 已生成", { exact: true })).toHaveCount(0);
});

test("manual overflow recovery opens length settings and retains body", async ({
  page,
  request,
}) => {
  await profile(page);
  const p = (await sources(request))[0];
  const body = "实现离线回归测试。\n".repeat(70);
  await request.patch(base + `/profile-library/${p.id}/sections/projects`, {
    data: {
      expected_revision: p.section_revisions.projects,
      value: [{ organization: "离线项目", description: body }],
    },
  });
  await newResume(page, request);
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByText("内容超出一页，请精简后重试。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "手动精简", exact: true }).click();
  await expect(page.locator("details[open]")).toHaveCount(1);
  await expect(page.getByLabel("项目经历内容 1")).toContainText("");
  expect(await page.getByLabel("项目经历内容 1").inputValue()).toContain(body.trim());
  await page.getByLabel("精简表达（选填）").fill("离线项目\n实现离线回归测试。");
  await page.getByLabel("使用精简版").check();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByRole("link", { name: "下载 PDF", exact: true })).toBeVisible();
});

test("AI compression creates recoverable short forms, then explicit save and PDF", async ({
  page,
  request,
}) => {
  await profile(page);
  const p = (await sources(request))[0];
  await request.patch(base + `/profile-library/${p.id}/sections/projects`, {
    data: {
      expected_revision: p.section_revisions.projects,
      value: [{ organization: "离线项目", description: "实现离线回归测试。\n".repeat(70) }],
    },
  });
  await newResume(page, request);
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByRole("button", { name: "AI 精简", exact: true })).toBeVisible();
  const beforeWorkspaces = (await (await request.get(base + "/resume-workspaces")).json()).length;
  const beforeSelection = await page.getByLabel("简历", { exact: true }).inputValue();
  await page.getByRole("button", { name: "AI 精简", exact: true }).click();
  await expect(page.getByLabel("简历", { exact: true })).toHaveValue(beforeSelection);
  await expect(page.locator("details[open]")).toHaveCount(1);
  expect((await (await request.get(base + "/resume-workspaces")).json()).length).toBe(
    beforeWorkspaces,
  );
  await expect(page.getByLabel("精简表达（选填）")).not.toHaveValue("");
  await expect(page.getByLabel("使用精简版")).toBeChecked();
  const beforeCancel = (await (await request.get(base + "/resume-library/versions")).json()).items;
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect((await (await request.get(base + "/resume-library/versions")).json()).items).toEqual(
    beforeCancel,
  );
  await expect(page.getByLabel("简历", { exact: true })).toHaveValue(beforeSelection);
  await page.getByRole("button", { name: "AI 精简", exact: true }).click();
  await expect(page.locator("details[open]")).toHaveCount(1);
  await page.getByLabel("使用精简版").check();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByRole("link", { name: "下载 PDF", exact: true })).toBeVisible();
  expect((await (await request.get(base + "/resume-workspaces")).json()).length).toBe(
    beforeWorkspaces,
  );
  const versions = (await (await request.get(base + "/resume-library/versions")).json()).items;
  const afterSelection = await page.getByLabel("简历", { exact: true }).inputValue();
  expect(afterSelection).toBe(beforeSelection);
  expect(versions).toHaveLength(beforeCancel.length);
  const savedEntry = versions.find(
    (v: { id: string; entry_id?: string }) => (v.entry_id || v.id) === afterSelection,
  );
  expect(savedEntry.variant_id).toBe(
    beforeCancel.find((v: { id: string }) => v.id === beforeSelection).variant_id,
  );
  await expect(page.getByLabel("简历", { exact: true }).locator("option")).toHaveCount(
    versions.length + 1,
  );
});

test("presentation is an editable draft: cancel restores and save persists without duplicate", async ({
  page,
  request,
}) => {
  await profile(page);
  await newResume(page, request);
  const id = await page.getByLabel("简历", { exact: true }).inputValue();
  const read = async () => await (await request.get(base + `/resume-workspaces/${id}`)).json();
  const before = await read();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByRole("button", { name: "隐藏", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeEnabled();
  expect((await read()).presentation).toEqual(before.presentation);
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect((await read()).presentation).toEqual(before.presentation);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByRole("button", { name: "隐藏", exact: true }).click();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect.poll(async () => (await read()).presentation.hidden_item_ids.length).toBe(1);
  expect((await read()).document).toEqual(before.document);
  expect((await (await request.get(base + "/resume-workspaces")).json()).length).toBe(1);
  await page.reload();
  await page.getByLabel("简历", { exact: true }).selectOption(id);
  await expect(page.getByRole("heading", { name: "项目经历", exact: true })).toHaveCount(0);
});

test("photo drop uses the validated upload path", async ({ page, request }) => {
  await profile(page);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const transfer = await page.evaluateHandle(() => {
    const bytes = Uint8Array.from(
      atob(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII=",
      ),
      (c) => c.charCodeAt(0),
    );
    const data = new DataTransfer();
    data.items.add(new File([bytes], "photo.png", { type: "image/png" }));
    return data;
  });
  await page
    .locator('[aria-label="照片上传区域"]')
    .dispatchEvent("drop", { dataTransfer: transfer });
  await expect(page.getByAltText("个人照片")).toBeVisible();
  await page.getByRole("button", { name: "保存", exact: true }).last().click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  const p = (await sources(request))[0];
  expect((await request.get(base + "/profile-photos/" + p.data.personal.photo_id)).status()).toBe(
    200,
  );
});

test("experience has one title and skills only section visibility controls", async ({
  page,
  request,
}, info) => {
  await profile(page);
  const p = (await sources(request))[0];
  await request.patch(base + `/profile-library/${p.id}/sections/skills`, {
    data: { expected_revision: p.section_revisions.skills, value: "Python、SQL" },
  });
  await newResume(page, request);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.getByText("内容 1", { exact: true })).toHaveCount(0);
  const itemTitle = page.getByText("项目经历内容 1", { exact: true });
  await expect(itemTitle).toHaveCount(1);
  await expect(itemTitle).toHaveCSS("font-weight", "500");
  await expect(page.getByText("优先保留此内容", { exact: true })).toHaveCount(0);
  await page.getByText("篇幅设置", { exact: true }).first().click();
  await expect(page.getByText("精简表达（选填）", { exact: true }).first()).toHaveCSS(
    "font-weight",
    "400",
  );
  await expect(page.getByLabel("精简表达（选填）").first()).toHaveCSS("font-weight", "400");
  const skills = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "技术栈", exact: true }) })
    .last();
  await expect(skills.getByRole("button", { name: "上移", exact: true })).toHaveCount(0);
  await expect(skills.getByRole("button", { name: "下移", exact: true })).toHaveCount(0);
  await expect(skills.getByText("技术栈内容 1", { exact: true })).toHaveCount(0);
  await skills.getByRole("button", { name: "隐藏", exact: true }).click();
  await expect(skills.getByText("· 已隐藏", { exact: true })).toBeVisible();
  await expect(skills.getByRole("button", { name: "显示", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeEnabled();
  await page.screenshot({ path: info.outputPath("editor-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("editor-mobile.png"), fullPage: true });
});

test("ordinary saves keep one selected entry and field validation stays beside input", async ({
  page,
  request,
}) => {
  await profile(page);
  await newResume(page, request);
  const selected = await page.getByLabel("简历", { exact: true }).inputValue();
  let saves = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/editions")) saves++;
  });
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.getByRole("heading", { name: "项目经历", exact: true })).toHaveCSS(
    "font-weight",
    "600",
  );
  const body = page.getByLabel("项目经历内容 1");
  const text = (await body.inputValue()) + "\n补充用户表达。";
  await body.fill(text);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  await expect(page.getByLabel("简历", { exact: true })).toHaveValue(selected);
  await expect(page.getByLabel("简历", { exact: true }).locator("option")).toHaveCount(2);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByRole("button", { name: "隐藏", exact: true }).click();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByText("篇幅设置", { exact: true }).click();
  const short = page.getByLabel("精简表达（选填）");
  await short.fill(text);
  await short.blur();
  await expect(page.getByText("精简表达必须比原文更短", { exact: true })).toBeVisible();
  const before = saves;
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(short).toBeFocused();
  expect(saves).toBe(before);
  await short.fill(text + "更长");
  await short.blur();
  await expect(short).toHaveAttribute("aria-invalid", "true");
  await short.fill("离线项目");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toBeVisible();
  await expect(page.getByLabel("简历", { exact: true })).toHaveValue(selected);
  await expect(page.getByLabel("简历", { exact: true }).locator("option")).toHaveCount(2);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await body.fill("不保存的内容");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.reload();
  await page.getByLabel("简历", { exact: true }).selectOption(selected);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(body).toHaveValue(text);
  await page.getByText("篇幅设置", { exact: true }).click();
  await expect(short).toHaveValue("离线项目");
  expect((await (await request.get(base + "/resume-workspaces")).json()).length).toBe(1);
});

test("server field rejection preserves editor input without generic error", async ({
  page,
  request,
}) => {
  await profile(page);
  await newResume(page, request);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByText("篇幅设置", { exact: true }).click();
  const short = page.getByLabel("精简表达（选填）");
  await short.fill("离线项目");
  await page.route("**/api/product/resume-workspaces/*/editions", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "resume_field_validation",
          fields: [{ section: 0, item: 0, field: "short_text", code: "short_text_not_shorter" }],
        },
      }),
    }),
  );
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(short).toHaveValue("离线项目");
  await expect(short).toBeFocused();
  await expect(page.getByText("精简表达必须比原文更短", { exact: true })).toBeVisible();
  await expect(page.getByText("未能完成操作，请检查输入后重试。", { exact: true })).toHaveCount(0);
});

test("multiple short expression errors map through the real BFF and editor", async ({
  page,
  request,
}) => {
  await profile(page);
  const p = (await sources(request))[0];
  await request.patch(base + `/profile-library/${p.id}/sections/skills`, {
    data: { expected_revision: p.section_revisions.skills, value: "Python、SQL" },
  });
  await newResume(page, request);
  const work = (await (await request.get(base + "/resume-workspaces")).json())[0];
  const document = structuredClone(work.document);
  for (const section of document.sections) section.items[0].short_text = section.items[0].text;
  const rejected = await request.post(
    `http://127.0.0.1:3130/api/product/resume-workspaces/${work.id}/editions`,
    {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: work.revision,
        name: work.name,
        document,
      },
      headers: { Origin: "http://127.0.0.1:3130" },
    },
  );
  expect(rejected.status()).toBe(422);
  const error = (await rejected.json()).error;
  expect(error.code).toBe("resume_field_validation");
  expect(error.fields).toHaveLength(2);
  expect(JSON.stringify(error)).not.toContain("Python");
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  for (const summary of await page.getByText("篇幅设置", { exact: true }).all())
    await summary.click();
  const shorts = page.getByLabel("精简表达（选填）");
  for (let n = 0; n < document.sections.length; n++)
    await shorts.nth(n).fill(document.sections[n].items[0].text);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("精简表达必须比原文更短", { exact: true })).toHaveCount(2);
  await expect(shorts.first()).toBeFocused();
});

test("Application submission uses library choices, own Greetings and audited note/delete with explicit status choice", async ({
  page,
  request,
}, info) => {
  await profile(page);
  await newResume(page, request);
  await page.getByRole("button", { name: "生成 PDF", exact: true }).click();
  await expect(page.getByRole("link", { name: "下载 PDF", exact: true })).toBeVisible();
  const versions = await (await request.get(base + "/resume-library/versions")).json();
  const resume = versions.items[0];
  const jobs = [];
  for (const company of ["投递测试公司", "其他公司"]) {
    const job = await (
      await request.post(base + "/jobs", {
        data: {
          company_name: company,
          title: "研发职位",
          jd_text: "使用 Python 开发 API",
        },
      })
    ).json();
    const generated = await request.post(base + "/workflows/prepare_application", {
      data: {
        job_revision_id: job.job_revision_id,
        profile_id: resume.profile_id,
        resume_revision_id: resume.id,
        targets: ["greeting_generation"],
      },
    });
    expect(generated.status(), await generated.text()).toBe(201);
    expect((await generated.json()).outcome.status).toBe("completed");
    jobs.push(job);
  }
  const applicationId = jobs[0].application_id;
  const path = `/applications/${applicationId}/apply/submissions`;
  await page.goto(path);
  const selector = page.getByLabel("简历", { exact: true });
  await expect(selector).toHaveValue("");
  await expect(page.getByRole("button", { name: "记录投递", exact: true })).toBeDisabled();
  await selector.selectOption(resume.id);
  await expect(selector).toHaveCSS("font-weight", "400");
  const greeting = page.getByLabel("招呼语", { exact: true });
  await expect(greeting.locator("option")).toHaveCount(2);
  await expect(greeting).toHaveValue("");
  await greeting.selectOption({ index: 1 });
  await page.getByPlaceholder("补充投递备注").fill("第一条备注");
  await page.getByRole("button", { name: "预览 PDF", exact: true }).click();
  await expect(page.getByTitle("简历 PDF 预览")).toBeVisible();
  await page.getByRole("button", { name: "记录投递", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("投递已记录，申请状态已更新为「已投递」");
  await expect(selector).toHaveValue("");
  await expect(greeting).toHaveValue("");
  await expect(page.getByPlaceholder("补充投递备注")).toHaveValue("");
  const records = page.getByRole("region", { name: "投递记录", exact: true });
  await expect(records.getByText("第 1 次投递", { exact: true })).toBeVisible();
  await records.getByRole("button", { name: "投递记录操作" }).click();
  await page.getByRole("button", { name: "编辑备注", exact: true }).click();
  const note = page.getByLabel("投递备注", { exact: true });
  await note.fill("更正备注");
  await page.getByRole("heading", { name: "新增投递" }).click();
  await expect(note).toHaveValue("更正备注");
  await note.press("Enter");
  await expect(records.getByText("更正备注", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("submissions-desktop.png"), fullPage: true });
  await records.getByRole("button", { name: "投递记录操作" }).click();
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await page.getByRole("button", { name: "取消切换", exact: true }).click();
  await expect(records.getByText("第 1 次投递", { exact: true })).toHaveCount(0);
  expect((await (await request.get(base + `/applications/${applicationId}`)).json()).status).toBe(
    "applied",
  );
  const summary = await (await request.get(base + `/applications/${applicationId}/summary`)).json();
  expect(summary.submission).toBeNull();
  await selector.selectOption(resume.id);
  await page.getByRole("button", { name: "记录投递", exact: true }).click();
  await expect(records.getByText("第 2 次投递", { exact: true })).toBeVisible();
  await records.getByRole("button", { name: "投递记录操作" }).click();
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await page.getByRole("button", { name: "确认切换", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get(base + `/applications/${applicationId}`)).json()).status,
    )
    .toBe("tracking");
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("submissions-narrow.png"), fullPage: true });
});

test("Greeting adjustments auto-save, regenerate in place and delete only unused exact records", async ({
  page,
  request,
}) => {
  await profile(page);
  await newResume(page, request);
  const workspace = (await (await request.get(base + "/resume-workspaces")).json())[0];
  const resolved = await request.post(base + `/resume-workspaces/${workspace.id}/resolve`, {
    data: { expected_revision: workspace.revision },
  });
  expect(resolved.status()).toBe(200);
  const resume = (await (await request.get(base + "/resume-library/versions")).json()).items[0];
  const job = await (
    await request.post(base + "/jobs", {
      data: { company_name: "独立招呼语测试", title: "研发", jd_text: "Python API" },
    })
  ).json();
  const created = await request.post(base + "/workflows/prepare_application", {
    data: {
      profile_id: resume.profile_id,
      resume_revision_id: resume.id,
      job_revision_id: job.job_revision_id,
      targets: ["greeting_generation"],
    },
  });
  expect(created.status()).toBe(201);
  const path = `/applications/${job.application_id}/apply/greeting`;
  await page.goto(path);
  const records = page.getByLabel("招呼语记录");
  await expect(records.locator("option")).toHaveCount(1);
  const original = await records.inputValue();
  await page.getByRole("button", { name: "调整", exact: true }).click();
  await page.getByPlaceholder("输入调整意见").fill("突出测试能力，保持事实。");
  await page.getByRole("button", { name: "开始调整", exact: true }).click();
  await expect(records.locator("option")).toHaveCount(2);
  await expect(records).not.toHaveValue(original);
  await expect(page.getByRole("button", { name: "保存", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重新生成", exact: true }).click();
  await expect(page.getByRole("button", { name: "正在生成…", exact: true })).toHaveCount(1);
  await expect(records.locator("option")).toHaveCount(3);
  const latest = await records.inputValue();
  await page.reload();
  await expect(records).toHaveValue(latest);
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(records.locator("option")).toHaveCount(3);
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(records.locator("option")).toHaveCount(2);
  await expect(records).not.toHaveValue(latest);
  await page.reload();
  await expect(records.locator("option")).toHaveCount(2);
});

for (const scenario of ["foreground", "away", "background"] as const) {
  const leave = scenario === "away",
    background = scenario === "background";
  test(`Mock delayed generation retains session and ${scenario}`, async ({
    page,
    request,
  }, info) => {
    await profile(page);
    await newResume(page, request);
    const workspace = (await (await request.get(base + "/resume-workspaces")).json())[0];
    const job = await (
      await request.post(base + "/jobs", {
        data: {
          company_name: "模拟隔离公司",
          title: "研发",
          jd_text: "需要 Python 项目经验。",
        },
      })
    ).json();
    const root = `/applications/${job.application_id}`;
    await page.goto(root + "/summary");
    const materials = page.getByRole("region", { name: "当前使用简历", exact: true });
    await materials.getByRole("button", { name: "更换", exact: true }).click();
    await materials.getByLabel("简历", { exact: true }).selectOption(workspace.id);
    await materials.getByRole("button", { name: "保存", exact: true }).click();
    await expect(materials.getByRole("button", { name: "更换", exact: true })).toBeVisible();
    await page.goto(root + "/interview/mock");
    await request.post("http://127.0.0.1:3131/__provider/hold");
    let releaseCreation!: () => void;
    const creationGate = new Promise<void>((resolve) => {
      releaseCreation = resolve;
    });
    await page.route("**/api/product/mock-interviews", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const response = await route.fetch();
      await creationGate;
      if (leave) await route.abort();
      else await route.fulfill({ response });
    });
    let dispatch!: () => void;
    const dispatchGate = new Promise<void>((resolve) => {
      dispatch = resolve;
    });
    await page.route("**/api/product/mock-interviews/*/generate", async (route) => {
      await dispatchGate;
      const response = await route.fetch();
      if (!leave && !background) await route.abort();
      else await route.fulfill({ response });
    });
    try {
      await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "正在创建模拟面试…", exact: true }),
      ).toBeVisible();
      const unregistered = page.waitForResponse(
        (r) => r.url().includes("task-status/mock-interviews/") && r.url().includes("request_id="),
      );
      releaseCreation();
      expect((await (await unregistered).json()).state).toBe("pending");
      await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
      dispatch();
      await expect
        .poll(
          async () =>
            (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).entered,
        )
        .toBe(true);
      await expect(page).toHaveURL(/session=/);
      const session = new URL(page.url()).searchParams.get("session")!;
      await expect(page.getByText("正在准备第 1 题…", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "检查状态", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "查询并恢复", exact: true })).toHaveCount(0);
      await expect(page.getByText(/主问题 0/)).toHaveCount(0);
      await page.screenshot({
        path: info.outputPath("mock-real-first-loading.png"),
        fullPage: true,
      });
      if (leave) {
        await page.getByRole("link", { name: "概览", exact: true }).click();
        await expect(page).toHaveURL(/summary$/);
      }
      if (background)
        await page.evaluate(() => {
          Object.defineProperty(document, "visibilityState", {
            configurable: true,
            get: () => "hidden",
          });
          document.dispatchEvent(new Event("visibilitychange"));
        });
      await request.post("http://127.0.0.1:3131/__provider/release");
      await expect
        .poll(
          async () =>
            (await (await request.get(base + `/mock-interviews/${session}`)).json()).status,
        )
        .toBe("waiting_answer");
      if (background) {
        await expect(
          page.getByRole("button", { name: "未处理通知 1 条", exact: true }),
        ).toBeVisible();
        await page.evaluate(() => {
          Object.defineProperty(document, "visibilityState", {
            configurable: true,
            get: () => "visible",
          });
          document.dispatchEvent(new Event("visibilitychange"));
        });
      }
      if (leave) {
        const notification = page.getByRole("complementary", { name: "任务通知" });
        await expect(notification).toContainText("新题已准备好");
        const link = notification.getByRole("link", { name: "查看结果" });
        await expect(link).toHaveAttribute("href", new RegExp(`session=${session}`));
        await link.click();
      }
      await expect(page.getByLabel("本题回答", { exact: true })).toBeVisible();
      await page.reload();
      await expect(page.getByLabel("本题回答", { exact: true })).toBeVisible();
      await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
      for (let visit = 0; visit < 2; visit++) {
        await page.getByRole("button", { name: "面试", exact: true }).click();
        await page.getByRole("menuitem", { name: "模拟面试", exact: true }).click();
        await expect(page).toHaveURL(/\/interview\/mock$/);
        await expect(page.getByRole("button", { name: "开始模拟面试", exact: true })).toBeVisible();
        await page.getByText("继续未完成的模拟面试（1）", { exact: true }).click();
        if (visit === 0) {
          await page.screenshot({
            path: info.outputPath("mock-home-continue-desktop.png"),
            fullPage: true,
          });
          await page.setViewportSize({ width: 375, height: 812 });
          expect(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          ).toBe(true);
          await page.screenshot({
            path: info.outputPath("mock-home-continue-375.png"),
            fullPage: true,
          });
          await page.setViewportSize({ width: 1280, height: 720 });
        }
        await expect(page.getByText(/连接中断|恢复确认/)).toHaveCount(0);
        await page.getByRole("link", { name: "继续模拟", exact: true }).click();
        await expect(page).toHaveURL(new RegExp(`session=${session}`));
        await expect(page.getByPlaceholder("输入你的回答…", { exact: true })).toBeVisible();
        await expect(page.getByText("尚未回答", { exact: true })).toHaveCount(0);
        await expect(page.getByText("本题回答", { exact: true })).toHaveCount(0);
      }
      await page.screenshot({
        path: info.outputPath("mock-real-resumed-desktop.png"),
        fullPage: true,
      });
      await page.setViewportSize({ width: 375, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({ path: info.outputPath("mock-real-resumed-375.png"), fullPage: true });
      const history = await (
        await request.get(base + `/mock-interviews?application_id=${job.application_id}`)
      ).json();
      expect(history.items).toHaveLength(1);
      const calls = await (await request.get("http://127.0.0.1:3131/__provider/status")).json();
      expect(calls.calls).toEqual(["mock_interview_turn_generation"]);
      if (!leave) {
        const input = page.getByPlaceholder("输入你的回答…", { exact: true });
        await input.fill("合成回答：使用事务验证边界。");
        await request.post("http://127.0.0.1:3131/__provider/mock-fault?kind=answer_save_failed");
        await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
        await expect(
          page.getByRole("button", { name: "提交回答并继续", exact: true }),
        ).toBeEnabled();
        await expect(input).toHaveValue("合成回答：使用事务验证边界。");
        await expect(page.getByText("我的回答", { exact: true })).toHaveCount(0);
        const unsaved = await (await request.get(base + `/mock-interviews/${session}`)).json();
        expect(unsaved.turns[0].answer).toBeNull();
        expect(unsaved.pending_question_id).toBe(unsaved.turns[0].id);
        await request.post("http://127.0.0.1:3131/__provider/hold");
        let dispatch!: () => void;
        const dispatchGate = new Promise<void>((resolve) => {
          dispatch = resolve;
        });
        // Delay dispatch, then drop only the response. API, transaction and generation stay real.
        await page.route(`**/api/product/mock-interviews/${session}/answers`, async (route) => {
          await dispatchGate;
          await route.fetch();
          await route.abort();
        });
        await page
          .getByPlaceholder("输入你的回答…", { exact: true })
          .fill("合成回答：使用事务验证边界。");
        await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
        await expect(input).toBeVisible();
        await expect(input).toHaveValue("合成回答：使用事务验证边界。");
        await expect(page.getByText("我的回答", { exact: true })).toHaveCount(0);
        dispatch();
        await expect
          .poll(
            async () =>
              (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).entered,
          )
          .toBe(true);
        await expect(page.getByText("我的回答", { exact: true })).toBeVisible();
        await expect(page.getByText("合成回答：使用事务验证边界。", { exact: true })).toBeVisible();
        await expect(page.getByRole("status")).toHaveText("正在准备下一道问题…");
        await expect(input).toHaveCount(0);
        await page.screenshot({
          path: info.outputPath("mock-real-saved-waiting-375.png"),
          fullPage: true,
        });
        const saved = await (await request.get(base + `/mock-interviews/${session}`)).json();
        expect(saved.turns[0].answer).toBe("合成回答：使用事务验证边界。");
        expect(saved.pending_question_id).toBeNull();
        await request.post("http://127.0.0.1:3131/__provider/release");
        await expect(page.locator("[data-question-id]")).toHaveCount(2);
        await expect(page.getByText("合成回答：使用事务验证边界。", { exact: true })).toBeVisible();
        await expect(page.getByText(/连接中断|恢复确认/)).toHaveCount(0);
        await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
        const persisted = await (await request.get(base + `/mock-interviews/${session}`)).json();
        expect(
          persisted.turns.filter((turn: { answer: string | null }) => turn.answer !== null),
        ).toHaveLength(1);
        const status = await (await request.get("http://127.0.0.1:3131/__provider/status")).json();
        expect(status.calls).toHaveLength(1);
        const topic = page.locator("[data-question-id] p").first();
        await expect(topic).toHaveCSS("font-size", "16px");
        await expect(topic).toHaveCSS("font-weight", "600");
        await expect(topic).toHaveCSS("line-height", "26px");
        await page.screenshot({
          path: info.outputPath("mock-response-lost-resolved-375.png"),
          fullPage: true,
        });
      }
      await page.goto(root + `/interview/history?session=${session}`);
      await expect(page.getByLabel("本题回答", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "提前结束", exact: true })).toHaveCount(0);
    } finally {
      releaseCreation();
      await request.post("http://127.0.0.1:3131/__provider/release");
    }
  });
}

test("Mock failure, saved-output recovery and unknown use real receipts without duplicate calls", async ({
  page,
  request,
}, info) => {
  await profile(page);
  await newResume(page, request);
  const workspace = (await (await request.get(base + "/resume-workspaces")).json())[0];
  const job = await (
    await request.post(base + "/jobs", {
      data: { company_name: "恢复隔离公司", title: "研发", jd_text: "Python 项目经验" },
    })
  ).json();
  const root = `/applications/${job.application_id}`;
  await page.goto(root + "/summary");
  const materials = page.getByRole("region", { name: "当前使用简历", exact: true });
  await materials.getByRole("button", { name: "更换", exact: true }).click();
  await materials.getByLabel("简历", { exact: true }).selectOption(workspace.id);
  await materials.getByRole("button", { name: "保存", exact: true }).click();
  await expect(materials.getByRole("button", { name: "更换", exact: true })).toBeVisible();
  const fault = (kind: string) =>
    request.post(`http://127.0.0.1:3131/__provider/mock-fault?kind=${kind}`);
  const calls = async () =>
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.filter(
      (x: string) => x === "mock_interview_turn_generation",
    ).length;
  await fault("provider_timeout");
  await page.goto(root + "/interview/mock");
  await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试生成", exact: true })).toBeVisible();
  const session = new URL(page.url()).searchParams.get("session")!;
  const read = async () => await (await request.get(base + `/mock-interviews/${session}`)).json();
  const failed = (await read()).latest_request_id;
  await page.screenshot({ path: info.outputPath("mock-confirmed-failure.png"), fullPage: true });
  await page.getByRole("button", { name: "重试生成", exact: true }).click();
  await expect(page.getByPlaceholder("输入你的回答…")).toBeVisible();
  expect(await calls()).toBe(2);
  await fault("artifact_save_failed");
  await page.getByPlaceholder("输入你的回答…").fill("合成第一题回答");
  await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
  await expect(
    page.getByText("结果已生成，但保存失败，请重试保存。", { exact: true }).first(),
  ).toBeVisible();
  const savedFailure = (await read()).latest_request_id;
  await page.getByRole("button", { name: "检查状态", exact: true }).click();
  await expect(page.locator("[data-question-id]")).toHaveCount(2);
  await expect(page.getByPlaceholder("输入你的回答…")).toBeVisible();
  expect(await calls()).toBe(3);
  const recovered = await (
    await request.get(base + `/task-status/mock-interviews/${session}?request_id=${savedFailure}`)
  ).json();
  expect(recovered.state).toBe("success");
  const old = await (
    await request.get(base + `/task-status/mock-interviews/${session}?request_id=${failed}`)
  ).json();
  expect(old.state).toBe("failure");
  expect((await read()).turns[0].answer).toBe("合成第一题回答");
  await page.screenshot({
    path: info.outputPath("mock-saved-output-recovered.png"),
    fullPage: true,
  });
  await fault("execution_outcome_unknown");
  await page.getByPlaceholder("输入你的回答…").fill("合成第二题回答");
  await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
  await expect(page.getByRole("button", { name: "检查状态", exact: true })).toBeVisible();
  expect(await calls()).toBe(4);
  await page.getByRole("button", { name: "检查状态", exact: true }).click();
  await expect(page.getByRole("button", { name: "检查状态", exact: true })).toBeEnabled();
  expect(await calls()).toBe(4);
  const unknown = await read();
  expect(unknown.turns).toHaveLength(2);
  expect(unknown.turns[1].answer).toBe("合成第二题回答");
  await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("mock-unknown-checked.png"), fullPage: true });
});

for (const kind of ["company", "fit", "preparation"] as const) {
  test(`unused ${kind} record deletes through Product BFF and disappears after reload`, async ({
    page,
    request,
  }) => {
    await profile(page);
    await newResume(page, request);
    const workspace = (await (await request.get(base + "/resume-workspaces")).json())[0];
    const job = await (
      await request.post(base + "/jobs", {
        data: {
          company_name: "删除测试公司",
          title: "研发",
          jd_text: "Python 服务开发",
        },
      })
    ).json();
    const root = `/applications/${job.application_id}`;
    await page.goto(root + "/summary");
    const materials = page.getByRole("region", { name: "当前使用简历", exact: true });
    await materials.getByRole("button", { name: "更换", exact: true }).click();
    await materials.getByLabel("简历", { exact: true }).selectOption(workspace.id);
    await materials.getByRole("button", { name: "保存", exact: true }).click();
    await expect(materials.getByRole("button", { name: "更换", exact: true })).toBeVisible();
    const binding = await (
      await request.get(base + `/applications/${job.application_id}/context`)
    ).json();
    await page.goto(
      root + (kind === "preparation" ? "/interview/preparation" : `/research-fit/${kind}`),
    );
    if (kind === "fit")
      await page.getByLabel("简历", { exact: true }).selectOption(binding.resume_revision_id);
    await page
      .getByRole("button", {
        name: kind === "company" ? "开始研究" : kind === "fit" ? "开始匹配" : "开始面试准备",
        exact: true,
      })
      .click();
    const selector = page.getByLabel(
      kind === "company" ? "研究记录" : kind === "fit" ? "匹配记录" : "准备记录",
      { exact: true },
    );
    await expect(selector).toBeVisible();
    await expect.poll(() => selector.inputValue()).not.toBe("");
    const selected = await selector.inputValue();
    await page.getByRole("button", { name: "删除记录", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
    await expect(page.getByRole("button", { name: "删除记录", exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("button", { name: "删除记录", exact: true })).toHaveCount(0);
    const exact =
      kind === "company"
        ? `${base}/companies/${job.company_id}/research/${selected}`
        : `${base}/preparation-artifacts/${selected}/result?application_id=${job.application_id}`;
    expect((await request.get(exact)).ok()).toBe(true);
  });
}

test("Actual intake atomically saves and edits the same record with text/calendar date and cancel", async ({
  page,
  request,
}, info) => {
  const job = await (
    await request.post(base + "/jobs", {
      data: {
        company_name: "真实录入测试公司",
        title: "研发",
        jd_text: "离线面试录入",
      },
    })
  ).json();
  const root = `/applications/${job.application_id}`;
  await page.goto(root + "/interview/actual");
  await expect(page.getByLabel("轮次", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "新增记录", exact: true }).click();
  await expect(page.getByLabel("轮次", { exact: true })).toHaveValue("1");
  await page.getByLabel("面试类型", { exact: true }).selectOption("technical");
  await page.getByLabel("面试时间", { exact: true }).fill("2026-11-01 09:30");
  await page.getByRole("button", { name: "选择面试日期时间", exact: true }).click();
  await page.getByRole("button", { name: "2026年11月7日", exact: true }).click();
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByLabel("问题1", { exact: true }).fill("如何设计事务边界？");
  await page.getByLabel("回答", { exact: true }).fill("先明确原子写入范围。");
  await page.screenshot({ path: info.outputPath("actual-real-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "选择面试日期时间", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("actual-calendar-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "2026年11月7日", exact: true }).press("Escape");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page).toHaveURL(/interview\/history\?actual=/);
  const id = new URL(page.url()).searchParams.get("actual")!;
  const before = await (await request.get(base + `/interviews/${id}`)).json();
  expect(before.status).toBe("completed");
  expect(before.round_name).toBe("真实录入测试公司 · 研发 · 第1轮 · 技术");
  await page.getByRole("link", { name: "编辑记录", exact: true }).click();
  await expect(page.getByLabel("面试时间", { exact: true })).toHaveValue("2026-11-07 09:30");
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await page.getByLabel("回答", { exact: true }).fill("这是取消的修改。");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`history\\?actual=${id}`));
  expect(await (await request.get(base + `/interviews/${id}`)).json()).toEqual(before);
  await page.getByRole("link", { name: "编辑记录", exact: true }).click();
  await page.getByLabel("回答", { exact: true }).fill("修改后保留原子事务和冲突检测。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`history\\?actual=${id}`));
  await expect(page.getByText("修改后保留原子事务和冲突检测。", { exact: true })).toBeVisible();
  const after = await (await request.get(base + `/interviews/${id}`)).json();
  expect(after.content_revision).toBe(before.content_revision + 1);
  expect(after.entries[0].entry_id).toBe(before.entries[0].entry_id);
  expect(after.occurred_at).toBe(before.occurred_at);
  expect(
    (await (await request.get(base + `/interviews?application_id=${job.application_id}`)).json())
      .length,
  ).toBe(1);
});

for (const scenario of ["delayed", "zero", "last-group"] as const) {
  test(`Mock model decisions ${scenario} flow through persistence, decoder, history and finish notification`, async ({
    page,
    request,
  }, info) => {
    try {
      await profile(page);
      await newResume(page, request);
      const workspace = (await (await request.get(base + "/resume-workspaces")).json())[0];
      const job = await (
        await request.post(base + "/jobs", {
          data: { company_name: "动态模拟公司", title: "研发", jd_text: "Python 工程经验。" },
        })
      ).json();
      const root = `/applications/${job.application_id}`;
      await page.goto(root + "/summary");
      const materials = page.getByRole("region", { name: "当前使用简历", exact: true });
      await materials.getByRole("button", { name: "更换", exact: true }).click();
      await materials.getByLabel("简历", { exact: true }).selectOption(workspace.id);
      await materials.getByRole("button", { name: "保存", exact: true }).click();
      await expect(materials.getByRole("button", { name: "更换", exact: true })).toBeVisible();
      const choices =
        scenario === "delayed"
          ? ["primary", "primary", "follow_up", "follow_up", "primary", "finish"]
          : scenario === "zero"
            ? ["primary", "primary", "primary", "finish"]
            : ["primary", "primary", "primary", "follow_up", "finish"];
      await request.post("http://127.0.0.1:3131/__provider/mock-plan", { data: choices });
      await page.goto(root + "/interview/mock");
      await page.getByLabel("问题数量模式", { exact: true }).selectOption("custom");
      await page.getByLabel("主问题数量", { exact: true }).fill("3");
      await page.getByLabel("追问上限", { exact: true }).fill("3");
      await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
      const input = page.getByPlaceholder("输入你的回答…");
      await expect(input).toBeVisible();
      const session = new URL(page.url()).searchParams.get("session")!;
      const labels =
        scenario === "delayed"
          ? ["1", "2", "2.1", "2.2", "3"]
          : scenario === "zero"
            ? ["1", "2", "3"]
            : ["1", "2", "3", "3.1"];
      for (let i = 0; i < labels.length; i++) {
        await expect(
          page
            .locator("[data-current-question=true]")
            .getByText(`问题 ${labels[i]}`, { exact: true }),
        ).toBeVisible();
        if (i === 2) {
          await page.goto(root + `/interview/history?session=${session}`);
          await expect(input).toHaveCount(0);
          await page.getByRole("link", { name: "继续模拟", exact: true }).click();
          await expect(page).toHaveURL(new RegExp(`/interview/mock\\?session=${session}`));
          await page.reload();
          await expect(input).toBeVisible();
        }
        await input.fill(`第 ${labels[i]} 题的合成回答。`);
        if (i === labels.length - 1) {
          await request.post("http://127.0.0.1:3131/__provider/hold");
          await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
          await expect(page.getByRole("status")).toHaveText("正在准备下一道问题…");
          await page.getByRole("link", { name: "概览", exact: true }).click();
          await request.post("http://127.0.0.1:3131/__provider/release");
          const notices = page.getByRole("complementary", { name: "任务通知" });
          await expect(notices).toContainText("模拟面试已完成");
          await expect(notices).not.toContainText("新题已准备好");
          await notices.getByRole("link", { name: "查看结果", exact: true }).click();
          await expect(page).toHaveURL(new RegExp(`/interview/mock\\?session=${session}`));
          await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
        } else {
          await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
          await expect(page.locator("[data-question-id]")).toHaveCount(i + 2);
          await expect(input).toBeEnabled();
        }
      }
      const saved = await (await request.get(base + `/mock-interviews/${session}`)).json();
      expect(saved.status).toBe("completed");
      expect(saved.turns.map((t: { question_number: string }) => t.question_number)).toEqual(
        labels,
      );
      expect(saved.turns).toHaveLength(choices.length - 1);
      for (const turn of saved.turns) {
        const element = page.locator(`[data-question-id="${turn.id}"]`);
        await expect(element).toHaveCSS(
          "margin-left",
          turn.question.kind === "follow_up" ? "20px" : "0px",
        );
        await expect(element.locator("p").nth(1)).toHaveCSS("font-size", "16px");
        await expect(element.locator("p").nth(1)).toHaveCSS("line-height", "26px");
        if (turn.question.kind === "follow_up") {
          await expect(element.locator("..")).toContainText(`问题 ${turn.main_question_number}`);
          await expect(
            element.locator("..").locator(`[data-question-id="${turn.question.primary_entry_id}"]`),
          ).toHaveCount(1);
        }
      }
      const groups = page.locator("li").filter({ has: page.locator("[data-question-id]") });
      await expect(groups).toHaveCount(3);
      await expect(groups.first()).toHaveCSS("border-bottom-width", "1px");
      await expect(groups.last()).toHaveCSS("border-bottom-width", "0px");
      await page.reload();
      await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
      await expect(page.locator("[data-question-id]")).toHaveCount(labels.length);
      await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "开始新的模拟面试", exact: true })).toHaveCount(
        0,
      );
      for (const width of [1280, 375]) {
        await page.setViewportSize({ width, height: 900 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
          true,
        );
        const roles = await page.locator("main h1, [data-question-id] p").evaluateAll((nodes) =>
          nodes.map((node) => {
            const style = getComputedStyle(node);
            return {
              text: node.textContent,
              size: style.fontSize,
              weight: style.fontWeight,
              line: style.lineHeight,
              color: style.color,
            };
          }),
        );
        await writeFile(
          info.outputPath(`dynamic-${scenario}-${width}-roles.json`),
          JSON.stringify(roles, null, 2),
        );
        await page.screenshot({
          path: info.outputPath(`dynamic-${scenario}-${width}.png`),
          fullPage: true,
        });
      }
      await page.goto(root + "/interview/mock");
      await expect(page.getByRole("button", { name: "开始模拟面试", exact: true })).toBeVisible();
      await expect(page.getByText(/继续未完成的模拟面试/)).toHaveCount(0);
    } finally {
      await request.post("http://127.0.0.1:3131/__provider/release");
    }
  });
}
