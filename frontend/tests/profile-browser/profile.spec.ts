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
    await page.getByRole("button", { name: "根据意见调整", exact: true }).click();
    await expect(page.getByRole("button", { name: "保存", exact: true })).toBeVisible();
    if (target === "resume_tailoring") page.once("dialog", (d) => d.dismiss());
    await page.getByRole("button", { name: "保存", exact: true }).click();
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
      .getByLabel("历史结果", { exact: true })
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
  await page.goto(`/applications/${job.application_id}/research-fit`);
  const fit = page.getByRole("region", { name: "岗位匹配", exact: true });
  await expect(fit.getByRole("button", { name: "开始岗位匹配", exact: true })).toBeDisabled();
  await fit.getByLabel("简历（选填）").selectOption(binding.resume_revision_id);
  await expect(fit.getByRole("button", { name: "开始岗位匹配", exact: true })).toBeEnabled();
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
