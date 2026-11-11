import { test, expect, type Page } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { id } from "../fixtures/product-api";
const statement = "使用 Python 构建数据服务。";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset?empty=true");
});
// Profile/Facts/Resume UI now has a separate real PostgreSQL/FastAPI browser suite.
// Seed only these prerequisites here; paid workflows remain canonical offline fixtures.
async function profileSource(page: Page) {
  const api = "http://127.0.0.1:3111/api/v1";
  await page.request.put(`${api}/profile`, {
    data: {
      expected_revision: 0,
      data: {
        display_name: "合成求职者",
        education: [],
        experiences: [],
        projects: [
          { organization: "个人项目", role: "开发者", description: statement, fact_ids: [] },
        ],
        skills: [],
        preferences: {},
      },
    },
  });
}
async function baseResume(page: Page) {
  const api = "http://127.0.0.1:3111/api/v1";
  const profile = await (await page.request.get(`${api}/profile`)).json();
  const document = {
    locale: "zh-CN",
    metadata: { label: "求职简历" },
    schema_version: "resume-v2",
    template: "resume_zh_cn_a4_single_v1",
    target_page_count: 1,
    profile_id: profile.id,
    profile_revision: profile.revision,
    job_revision_id: null,
    sections: [
      {
        section_id: id(8550),
        name: "projects",
        ordering: 0,
        priority: 80,
        required: true,
        items: [
          {
            item_id: id(8551),
            kind: "entry",
            text: statement,
            short_text: null,
            fact_refs: profile.data.projects[0].fact_ids,
            requirement_refs: [],
            hard_claims: [],
            priority: 80,
            required: true,
            ordering: 0,
          },
        ],
      },
    ],
  };
  const resume = await (
    await page.request.post(`${api}/resume-variants`, { data: document })
  ).json();
  await page.request.post(`${api}/resume-variants/${resume.id}/render`, {
    data: { revision: resume.revision },
  });
}
async function job(page: Page, existing = false) {
  await page.goto("/applications/new");
  if (existing) {
    await page.getByLabel("公司名称").fill("合成公司");
    await page.getByRole("option", { name: "合成公司", exact: true }).click();
  } else await page.getByLabel("公司名称").fill("合成公司");
  await page.getByLabel("职位名称").fill(existing ? "后端开发" : "Python 工程师");
  await page.getByLabel("职位描述").fill("使用 Python 构建数据服务。需要项目经验。");
  await page.getByRole("button", { name: "创建职位", exact: true }).click();
  await expect(page).toHaveURL(/\/summary$/);
}
async function run(page: Page) {
  const button = page.getByRole("button", { name: /^(开始优化|生成|开始面试准备)$/ });
  const optimizing = (await button.textContent()) === "开始优化";
  await button.click();
  if (optimizing) await page.getByRole("button", { name: "取消替换", exact: true }).click();
  await expect(button).toBeEnabled();
}
async function bindBase(page: Page) {
  await page.goto(`${root}/summary`);
  await page.getByRole("button", { name: "更换", exact: true }).click();
  await page
    .getByRole("region", { name: "当前使用简历" })
    .getByLabel("简历", { exact: true })
    .selectOption(id(8401));
  await page
    .getByRole("region", { name: "当前使用简历" })
    .getByRole("button", { name: "保存", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "更换", exact: true })).toBeVisible();
}
test("empty account creates verified context/base, then reaches existing preparation/interview/review flows", async ({
  page,
  request,
}, info) => {
  test.setTimeout(120000);
  const writes: { path: string; method: string; body: unknown }[] = [];
  page.on("request", (r) => {
    if (["POST", "PUT", "PATCH"].includes(r.method()))
      writes.push({ path: new URL(r.url()).pathname, method: r.method(), body: r.postDataJSON() });
  });
  await profileSource(page);
  await baseResume(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await job(page);
  await bindBase(page);
  await page.goto(`${root}/research-fit/company`);
  const research = page.getByRole("region", { name: "公司研究", exact: true });
  await research.getByRole("button", { name: /^(开始研究|重新研究)$/, exact: true }).click();
  await expect(research.getByText("公司提供数据服务。")).toBeVisible();
  await page.getByRole("button", { name: "研究与匹配" }).click();
  await page.getByRole("menuitem", { name: "岗位匹配", exact: true }).click();
  const fit = page.getByRole("region", { name: "岗位匹配", exact: true });
  await expect(fit.getByRole("button", { name: "开始匹配", exact: true })).toBeDisabled();
  await fit.getByLabel("简历").selectOption(id(8401));
  await fit.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByText("不确定")).toBeVisible();
  await page.goto(`${root}/apply/resume`);

  await run(page);
  await page.goto(`${root}/apply/greeting`);

  await run(page);
  await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toBeVisible();
  await page.goto(`${root}/summary`);
  await page
    .getByRole("region", { name: "申请状态", exact: true })
    .getByRole("button", { name: "更改" })
    .click();
  await page.getByLabel("状态", { exact: true }).selectOption("interviewing");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "添加申请笔记" }).click();
  await page.getByLabel("新笔记").fill("已整理申请材料，尚未投递。");
  await page.getByLabel("新笔记").press("Enter");
  await expect(page.getByText("已整理申请材料，尚未投递。", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("tracking-mobile.png"), fullPage: true });
  await page.goto(`${root}/interview/preparation`);

  await run(page);
  await expect(page.getByText("团队如何合作？")).toBeVisible();
  await page.goto(`${root}/interview/actual`);
  await page.getByRole("button", { name: "新增记录", exact: true }).click();
  await page.getByLabel("面试类型", { exact: true }).selectOption("technical");
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByLabel("问题1", { exact: true }).fill("介绍项目设计");
  await page.getByLabel("回答", { exact: true }).fill("实现了数据服务。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page).toHaveURL(/interview\/history\?actual=/);
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "开始复盘" }).click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByRole("button", { name: "新增笔记", exact: true }).click();
  await page.getByLabel("笔记标题").fill("复盘记录");
  await page.getByLabel("笔记内容").fill("补充项目测试案例。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.reload();
  await expect(page.getByText("补充项目测试案例。")).toBeVisible();
  const app = await (
    await request.get(`http://127.0.0.1:3111/api/v1/applications/${id(1)}`)
  ).json();
  expect(app.status).toBe("interviewing");
  await job(page, true);
  const companies = await (await request.get("http://127.0.0.1:3111/api/v1/companies")).json();
  expect(companies.items).toHaveLength(1);
  await writeFile(info.outputPath("request-contracts.json"), JSON.stringify(writes, null, 2));
});
test("status conflict preserves input; all six states are directly selectable", async ({
  page,
}) => {
  await job(page);
  const card = page.getByRole("region", { name: "申请状态", exact: true });
  await card.getByRole("button", { name: "更改" }).click();
  const target = card.getByLabel("状态", { exact: true });
  await expect(target.locator("option")).toHaveCount(6);
  await target.selectOption("offer");
  await card.getByLabel("备注（可选）").fill("收到录用通知");
  await page.route(`**/api/product/applications/${id(1)}`, (route) =>
    route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } }),
  );
  await card.getByRole("button", { name: "保存", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  await expect(target).toHaveValue("offer");
  await expect(card.getByLabel("备注（可选）")).toHaveValue("收到录用通知");
  await page.unroute(`**/api/product/applications/${id(1)}`);
  await card.getByRole("button", { name: "保存", exact: true }).click();
  await expect(card.getByText("已获录用", { exact: true })).toBeVisible();
  await expect(page.getByText("更正历史记录")).toHaveCount(0);
});

test("new Job interruption is not retried; mobile form stays readable with explicit recovery", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/applications/new");
  await page.getByLabel("公司名称").fill("新的合成公司");
  await page.getByLabel("职位名称").fill("工程师");
  await page.getByLabel("职位描述").fill("使用 Python 开发服务。");
  let calls = 0;
  await page.route("**/api/product/jobs", async (route) => {
    calls += 1;
    await route.fulfill({ status: 502, json: { error: { code: "connection_interrupted" } } });
  });
  await page.getByRole("button", { name: "创建职位", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建职位", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "另建一条申请" })).toBeVisible();
  expect(calls).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("new-job-mobile.png"), fullPage: true });
});

test("Company Research is one click without any Profile or facts", async ({ page }) => {
  await job(page);
  await page.goto(`${root}/research-fit/company`);
  const research = page.getByRole("region", { name: "公司研究", exact: true });
  await expect(research.getByRole("combobox", { name: "资料版本" })).toHaveCount(0);
  const bodies: Record<string, unknown>[] = [];
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().endsWith("/research"))
      bodies.push(req.postDataJSON().request);
  });
  await research.getByRole("button", { name: /^(开始研究|重新研究)$/, exact: true }).click();
  await expect(research.getByText("公司提供数据服务。")).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).not.toHaveProperty("profile_id");
  await expect(research.getByRole("button", { name: "执行操作" })).toHaveCount(0);
});

test("new application uses one company field, exact reuse, and clears a stale selection", async ({
  page,
}, info) => {
  const seed = await page.request.post("http://127.0.0.1:3111/api/v1/jobs", {
    data: { company_name: "合成公司", title: "旧职位", jd_text: "旧 JD", requirements: [] },
  });
  const old = await seed.json();
  await page.goto("/applications/new");
  const company = page.getByRole("combobox", { name: "公司名称", exact: true });
  await expect(company).toHaveAttribute("placeholder", "输入公司名称");
  await expect(page.getByLabel("职位名称")).toHaveAttribute("placeholder", "输入职位名称");
  await expect(page.getByLabel("职位描述")).toHaveAttribute("placeholder", "粘贴完整职位描述");
  await expect(page.getByText("公司来源", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "添加职位" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "← 返回申请列表" })).toBeVisible();
  await expect(page.getByText("岗位要求（高级，可选）")).toHaveCount(0);
  const before = (await page.getByLabel("职位名称").boundingBox())!;
  await company.fill("合成");
  const menu = page.getByRole("listbox", { name: "公司候选" });
  await expect(menu).toBeVisible();
  expect((await menu.boundingBox())!.width).toBeCloseTo((await company.boundingBox())!.width, 0);
  expect((await page.getByLabel("职位名称").boundingBox())!.y).toEqual(before.y);
  await company.press("ArrowDown");
  await company.press("Enter");
  await expect(company).toHaveValue("合成公司");
  await expect(menu).toHaveCount(0);
  // Editing a selected label must drop the old identity, even if later restored exactly.
  await company.fill("完全不同公司");
  await page.waitForTimeout(400);
  await expect(menu).toHaveCount(0);
  await expect(page.getByText("没有找到公司")).toHaveCount(0);
  await page.getByLabel("职位名称").fill("新职位");
  await page.getByLabel("职位描述").fill("新 JD");
  expect(await company.evaluate((el) => getComputedStyle(el).fontWeight)).toBe("400");
  expect(
    await page
      .getByText("公司名称", { exact: true })
      .evaluate((el) => getComputedStyle(el).fontWeight),
  ).toBe("600");
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("new-application-mobile.png"), fullPage: true });
  const submitted = page.waitForRequest(
    (r) => r.url().endsWith("/api/product/jobs") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "创建职位" }).click();
  const payload = (await submitted).postDataJSON();
  expect(payload.company_id).toBeUndefined();
  expect(payload.requirements).toBeUndefined();
  await expect(page).toHaveURL(/\/summary$/);
  const jobs = await (await page.request.get("http://127.0.0.1:3111/api/v1/jobs")).json();
  expect(jobs[1].company_id).not.toBe(old.company_id);
  await page.goto("/applications/new");
  await company.fill("合成公司");
  await page.getByLabel("职位名称").fill("另一职位");
  await page.getByLabel("职位描述").fill("另一 JD");
  await page.getByRole("button", { name: "创建职位" }).click();
  await expect(page).toHaveURL(/\/summary$/);
  const reused = await (await page.request.get("http://127.0.0.1:3111/api/v1/jobs")).json();
  expect(reused[2].company_id).toBe(old.company_id);
});

test("new company input preserves IME and ambiguity requires explicit choice without repeated POST", async ({
  page,
}) => {
  const queries: string[] = [];
  await page.route("**/api/product/companies?*", async (route) => {
    queries.push(new URL(route.request().url()).searchParams.get("q")!);
    await route.fulfill({
      json: {
        items: [
          { id: id(1001), name: "同名公司" },
          { id: id(1002), name: "同名公司" },
        ],
        has_more: false,
        offset: 0,
        limit: 8,
      },
    });
  });
  let calls = 0;
  await page.route("**/api/product/jobs", async (route) => {
    calls++;
    await new Promise((resolve) => setTimeout(resolve, 150));
    if (!route.request().postDataJSON().company_id)
      await route.fulfill({ status: 409, json: { error: { code: "company_selection_required" } } });
    else await route.fulfill({ status: 201, json: { application_id: id(1) } });
  });
  await page.goto("/applications/new");
  const input = page.getByLabel("公司名称", { exact: true });
  await input.fill("预热");
  await expect(page.getByRole("option", { name: "同名公司" })).toHaveCount(2);
  await input.fill("");
  queries.length = 0;
  await input.dispatchEvent("compositionstart");
  await input.fill("tong");
  await page.waitForTimeout(450);
  expect(queries).toEqual([]);
  await input.fill("同名公司");
  await input.dispatchEvent("compositionend", { data: "同名公司" });
  await expect.poll(() => queries).toEqual(["同名公司"]);
  await page.getByLabel("职位名称").fill("工程师");
  await page.getByLabel("职位描述").fill("合成 JD");
  await page.getByRole("button", { name: "创建职位" }).evaluate((el: HTMLButtonElement) => {
    el.click();
    el.click();
  });
  await expect(page.getByRole("main").getByRole("alert")).toContainText("找到多家同名公司");
  expect(calls).toBe(1);
  await input.focus();
  await page.getByRole("option", { name: "同名公司" }).nth(1).click();
  const submitted = page.waitForRequest(
    (r) => r.url().endsWith("/api/product/jobs") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "创建职位" }).click();
  expect((await submitted).postDataJSON().company_id).toBe(id(1002));
  await expect.poll(() => calls).toBe(2);
});

test("Research page JD edit cancels, saves exact binding, and preserves conflicting input", async ({
  page,
}) => {
  await job(page);
  await page.getByRole("link", { name: "查看完整职位描述" }).click();
  const area = page.locator("#job-description");
  await area.getByRole("button", { name: "编辑", exact: true }).click();
  const jd = area.getByLabel("职位描述");
  await expect(area.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await jd.fill("取消的 JD");
  await area.getByRole("button", { name: "取消", exact: true }).click();
  await expect(jd).toHaveCount(0);
  await area.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(jd).toHaveValue("使用 Python 构建数据服务。需要项目经验。");
  await jd.fill("新 JD：Python 与 SQL 服务开发。");
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") writes.push(r.url());
  });
  await area.getByRole("button", { name: "保存", exact: true }).click();
  await expect(jd).toHaveCount(0);
  expect(writes).toEqual([]);
  await expect(area.getByText("新 JD：Python 与 SQL 服务开发。", { exact: true })).toBeVisible();
  const binding = await (
    await page.request.get(`http://127.0.0.1:3111/api/v1/applications/${id(1)}/context`)
  ).json();
  expect(binding.job_revision).toBe(2);
  await area.getByRole("button", { name: "编辑", exact: true }).click();
  await jd.fill("保留我的新输入");
  await page.route("**/api/product/applications/*/jd", (route) =>
    route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } }),
  );
  await area.getByRole("button", { name: "保存", exact: true }).click();
  await expect(jd).toHaveValue("保留我的新输入");
  await expect(area.getByRole("alert")).toContainText("资料已被修改");
});

test("closed application menu confirms deletion without navigation and retains filters on valid page", async ({
  page,
}, info) => {
  const api = "http://127.0.0.1:3111/api/v1";
  for (let n = 1; n <= 21; n++) {
    const r = await (
      await page.request.post(`${api}/jobs`, {
        data: { company_name: "删除测试公司", title: `职位 ${n}`, jd_text: "完整 JD" },
      })
    ).json();
    await page.request.patch(`${api}/applications/${r.application_id}`, {
      data: { expected_revision: 1, status: "closed", correction: true, reason: "结束申请" },
    });
  }
  await page.goto("/applications?status=closed&page=2");
  const card = page.getByRole("list", { name: "申请列表" }).getByRole("listitem").first();
  await card.getByText("···").click();
  await expect(page).toHaveURL(/status=closed&page=2$/);
  await card.getByRole("button", { name: "删除申请" }).click();
  await expect(page.getByRole("dialog")).toContainText("删除测试公司 · 职位 1");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(card).toBeVisible();
  await card.getByText("···").focus();
  await page.keyboard.press("Enter");
  await card.getByRole("button", { name: "删除申请" }).click();
  await page.getByRole("button", { name: "确定", exact: true }).click();
  await expect(page).toHaveURL(/\/applications\?status=closed$/);
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(20);
  await expect(page.getByText("20 条申请", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "申请分页" })).toHaveCount(0);
  const heading = (await page.getByRole("heading", { name: "申请", exact: true }).boundingBox())!;
  const add = (await page.getByRole("link", { name: "添加职位" }).boundingBox())!;
  expect(Math.abs(heading.y - add.y)).toBeLessThan(15);
  await page.screenshot({ path: info.outputPath("applications-actions.png"), fullPage: true });
});

test("Summary notes and records edit in place, keep IME/blur input and scroll all entries", async ({
  page,
}, info) => {
  await job(page);
  const notes = page.getByRole("region", { name: "申请笔记", exact: true });
  const records = page.getByRole("region", { name: "申请记录", exact: true });
  await expect(notes.getByText("暂无笔记")).toBeVisible();
  for (let n = 0; n < 8; n++) {
    await notes.getByRole("button", { name: "添加申请笔记" }).click();
    const input = notes.getByLabel("新笔记");
    await input.fill(`笔记 ${n}`);
    await input.press("Enter");
    await expect(input).toHaveCount(0);
  }
  await expect(notes.getByRole("listitem")).toHaveCount(8);
  await expect(records.getByRole("listitem")).toHaveCount(1);
  const top = notes.getByRole("listitem").first();
  await top.hover();
  await top.getByLabel("管理记录").click();
  await page.getByRole("menuitem", { name: "编辑", exact: true }).click();
  const text = top.getByLabel("笔记", { exact: true });
  await expect(page.getByRole("menuitem", { name: "保存", exact: true })).toBeHidden();
  await text.fill("编辑中");
  await text.press("Shift+Enter");
  await text.press("x");
  await text.dispatchEvent("keydown", { key: "Enter", isComposing: true });
  await page.getByRole("heading", { name: "申请笔记", exact: true }).click();
  await expect(text).toHaveValue("编辑中\nx");
  await text.press("Enter");
  await expect(text).toHaveCount(0);
  await expect(top).toContainText("编辑中");
  await top.getByText("编辑中", { exact: false }).dblclick();
  await expect(text).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "保存", exact: true })).toBeHidden();
  await top.getByLabel("编辑操作").click();
  await page.getByRole("menuitem", { name: "取消", exact: true }).click();
  await expect(text).toHaveCount(0);
  await top.hover();
  await top.getByLabel("管理记录").click();
  await page.getByRole("menuitem", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(notes.getByRole("listitem")).toHaveCount(8);
  await top.getByLabel("管理记录").click();
  await page.getByRole("menuitem", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(notes.getByRole("listitem")).toHaveCount(7);
  await page.reload();
  await expect(notes.getByRole("listitem")).toHaveCount(7);
  await expect(notes).toHaveCSS("height", "430px");
  await expect(records).toHaveCSS("height", "430px");
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("notes-mobile.png"), fullPage: true });
});
