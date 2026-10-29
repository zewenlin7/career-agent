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
  await page.getByLabel("公司来源").selectOption(existing ? "existing" : "new");
  if (existing) {
    await page.getByLabel("输入公司名称").fill("合成公司");
    await page.getByRole("button", { name: "合成公司", exact: true }).click();
  } else await page.getByLabel("公司名称").fill("合成公司");
  await page.getByLabel("职位名称").fill(existing ? "后端开发" : "Python 工程师");
  await page.getByLabel("职位描述").fill("使用 Python 构建数据服务。需要项目经验。");
  await page.getByRole("button", { name: "创建职位", exact: true }).click();
  await expect(page).toHaveURL(/\/summary$/);
}
async function run(page: Page) {
  const button = page.getByRole("button", { name: /^开始(简历优化|招呼语|面试准备)$/ });
  await button.click();
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
  await page.goto(`${root}/research-fit`);
  const research = page.getByRole("region", { name: "公司研究", exact: true });
  await research.getByRole("button", { name: "开始公司研究", exact: true }).click();
  await expect(research.getByText("公司提供数据服务。")).toBeVisible();
  const fit = page.getByRole("region", { name: "岗位匹配", exact: true });
  await expect(fit.getByRole("button", { name: "开始岗位匹配", exact: true })).toBeDisabled();
  await fit.getByLabel("简历（选填）").selectOption(id(8401));
  await fit.getByRole("button", { name: "开始岗位匹配", exact: true }).click();
  await expect(page.getByText("不确定")).toBeVisible();
  await page.goto(`${root}/apply/resume`);

  await run(page);
  await page.goto(`${root}/apply/greeting`);

  await run(page);
  await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toBeVisible();
  await page.goto(`${root}/summary`);
  await page.getByLabel("更新为").selectOption("preparing");
  await page.getByRole("button", { name: "更新状态" }).click();
  await page.getByLabel("添加申请笔记").fill("已整理申请材料，尚未投递。");
  await page.getByRole("button", { name: "追加申请笔记" }).click();
  await expect(page.getByText("笔记已保存。")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("tracking-mobile.png"), fullPage: true });
  await page.goto(`${root}/interview/preparation`);

  await run(page);
  await expect(page.getByText("团队如何合作？")).toBeVisible();
  await page.goto(`${root}/interview/actual`);
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByLabel("问题", { exact: true }).fill("介绍项目设计");
  await page.getByLabel("回答", { exact: true }).fill("实现了数据服务。");
  await page.getByRole("button", { name: "完成记录", exact: true }).click();
  await expect(page.getByText("面试记录已保存。")).toBeVisible();
  await page.goto(`${root}/review/debriefs`);
  await page.getByRole("button", { name: /第 1 轮/ }).click();
  await page.getByRole("button", { name: "开始复盘" }).click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByLabel("笔记标题").fill("复盘记录");
  await page.getByLabel("笔记内容").fill("补充项目测试案例。");
  await page.getByRole("button", { name: "保存笔记" }).click();
  await page.reload();
  await expect(page.getByText("补充项目测试案例。")).toBeVisible();
  const app = await (
    await request.get(`http://127.0.0.1:3111/api/v1/applications/${id(1)}`)
  ).json();
  expect(app.status).toBe("preparing");
  await job(page, true);
  const companies = await (await request.get("http://127.0.0.1:3111/api/v1/companies")).json();
  expect(companies.items).toHaveLength(1);
  await writeFile(info.outputPath("request-contracts.json"), JSON.stringify(writes, null, 2));
});
test("tracking conflict requires refresh and correction reason", async ({ page }) => {
  await profileSource(page);
  await baseResume(page);
  await job(page);
  const target = page.getByLabel("更新为");
  expect(
    await target
      .locator("option")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLOptionElement).value)),
  ).not.toContain("offer");
  await page.route(`**/api/product/applications/${id(1)}`, async (route) => {
    if (route.request().method() === "PATCH")
      await route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } });
    else await route.continue();
  });
  await target.selectOption("preparing");
  await page.getByRole("button", { name: "更新状态" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "记录已变化" })).toBeVisible();
  await page.unroute(`**/api/product/applications/${id(1)}`);
  await page.getByRole("button", { name: "刷新状态" }).click();
  await page.getByText("更正历史记录").click();
  await page.getByRole("checkbox", { name: "此前状态记录有误" }).check();
  await target.selectOption("offer");
  await expect(page.getByLabel("更正原因")).toHaveAttribute("required", "");
  await page.getByLabel("更正原因").fill("补录已经发生的真实结果");
  await page.getByRole("button", { name: "更新状态" }).click();
  await expect(
    page.getByRole("region", { name: "申请状态" }).getByText("当前：已获 Offer", { exact: true }),
  ).toBeVisible();
});

test("new Job interruption is not retried; mobile form stays readable with explicit recovery", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/applications/new");
  await page.getByLabel("公司来源").selectOption("new");
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
  await expect(page.getByRole("button", { name: "创建职位", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "已核对，重新填写" })).toBeVisible();
  expect(calls).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("new-job-mobile.png"), fullPage: true });
});

test("Company Research is one click without any Profile or facts", async ({ page }) => {
  await job(page);
  await page.goto(`${root}/research-fit`);
  const research = page.getByRole("region", { name: "公司研究", exact: true });
  await expect(research.getByRole("combobox", { name: "资料版本" })).toHaveCount(0);
  const bodies: Record<string, unknown>[] = [];
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().endsWith("/research"))
      bodies.push(req.postDataJSON().request);
  });
  await research.getByRole("button", { name: "开始公司研究", exact: true }).click();
  await expect(research.getByText("公司提供数据服务。")).toBeVisible();
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).not.toHaveProperty("profile_id");
  await expect(research.getByRole("button", { name: "执行操作" })).toHaveCount(0);
});
