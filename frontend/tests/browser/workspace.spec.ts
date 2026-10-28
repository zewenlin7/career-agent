import { test, expect, type Page } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
async function bindings(page: Page) {
  await expect(page.getByLabel("个人资料版本")).toHaveCount(0);
}
async function execute(page: Page) {
  const button = page.getByRole("button", { name: /^(开始简历优化|开始招呼语|开始面试准备)$/ });
  await button.click();
  await expect(button).toBeEnabled();
}
test("Company current/history is company-scoped; Fit has explicit operation and no-evidence semantics", async ({
  page,
  request,
}) => {
  const researchBodies: Record<string, unknown>[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith(`/api/product/companies/${id(1001)}/research`))
      researchBodies.push(r.postDataJSON());
  });
  await page.goto(`${root}/research-fit`);
  await expect(page.getByText("公司提供数据服务。")).toBeVisible();
  const research = page.getByRole("region", { name: "公司研究", exact: true });
  await research.getByRole("checkbox").check();
  await research.getByRole("button", { name: "开始公司研究", exact: true }).click();
  expect(researchBodies).toHaveLength(1);
  expect(researchBodies[0]).toMatchObject({
    kind: "company_research",
    request: {
      force_research_refresh: true,
      job_revision_id: id(4001),
      mode: "live",
    },
  });
  const fit = page.getByRole("region", { name: "岗位匹配", exact: true });
  await expect(fit.getByRole("button", { name: "开始岗位匹配", exact: true })).toBeDisabled();
  await fit.getByLabel("简历（选填）").selectOption(id(8401));
  await fit.getByRole("button", { name: "开始岗位匹配", exact: true }).click();
  await expect(page.getByText("不确定")).toBeVisible();
  await page.reload();
  await expect(fit.getByLabel("历史结果")).toBeVisible();
  await expect(fit.getByText("不确定", { exact: true })).toBeVisible();
  const calls = await (await request.get("http://127.0.0.1:3111/__requests")).json();
  expect(calls.every((c: { hasOpsToken: boolean }) => !c.hasOpsToken)).toBe(true);
});
test("Resume exact rendering, Greeting history, Submission CAS and Interview Prep package binding", async ({
  page,
}) => {
  await page.goto(`${root}/apply/resume`);
  await bindings(page);
  await execute(page);
  await expect(page.getByText("使用 Python 构建数据服务。").first()).toBeVisible();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "保存到简历库", exact: true }).click();
  await expect(page.getByRole("button", { name: "已保存", exact: true })).toBeVisible();
  await page.goto(`${root}/apply/greeting`);
  await bindings(page);
  await execute(page);
  await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toBeVisible();
  let submitted: Record<string, unknown> | undefined;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith(`/api/product/applications/${id(1)}/submissions`))
      submitted = r.postDataJSON();
  });
  await page.goto(`${root}/apply/submissions`);
  await bindings(page);
  await expect(page.getByRole("button", { name: "记录投递", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: "我已完成真实投递" }).check();
  await page.getByRole("button", { name: "记录投递", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "投递已记录" })).toBeVisible();
  expect(submitted).toMatchObject({
    expected_revision: 2,
    resume_revision_id: id(8401),
    render_artifact_id: id(8501),
  });
  const duplicate = await page.evaluate(
    async ({ path, body }) => {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return { status: response.status, body: await response.json() };
    },
    { path: `/api/product/applications/${id(1)}/submissions`, body: submitted },
  );
  expect(duplicate.status).toBe(200);
  await expect(page.getByRole("button", { name: "记录投递", exact: true })).toBeDisabled();
  await page.goto(`${root}/interview/preparation`);
  await expect(page.getByLabel("使用哪次简历准备结果")).toHaveCount(0);
  await execute(page);
  await expect(page.getByText("团队如何合作？")).toBeVisible();
});
test("Mock immutable answer, failure preservation, generation-only retry, early end and discovery", async ({
  page,
}) => {
  await page.goto(`${root}/interview/mock`);
  await page.getByLabel("练习重点", { exact: true }).selectOption("technical");
  await bindings(page);
  await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
  await expect(page.getByText("请介绍你的 Python 项目。")).toBeVisible();
  await page.getByLabel("本题回答").fill("我使用 Python 编写了数据服务。");
  await page.getByRole("button", { name: "提交回答并继续" }).click();
  await expect(page.getByText("我使用 Python 编写了数据服务。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试生成问题" })).toBeVisible();
  await page.getByRole("button", { name: "重试生成问题" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "提前结束", exact: true }).click();
  await expect(page.getByText("模拟面试已完成")).toBeVisible();
  await page.goto(`${root}/interview/history`);
  await page.getByRole("button", { name: /模拟面试 ·/ }).click();
  await expect(page.getByText("我使用 Python 编写了数据服务。")).toBeVisible();
});
test("Actual intake primary/follow-up/correction/notes and Application Knowledge Notes", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual`);
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByLabel("轮次", { exact: true }).selectOption("2");
  await page.getByLabel("问题", { exact: true }).first().fill("介绍项目");
  await page.getByLabel("回答", { exact: true }).first().fill("实现数据服务");
  await page.getByRole("button", { name: "添加追问", exact: true }).first().click();
  await page.getByLabel("问题", { exact: true }).nth(1).fill("如何测试？");
  await page.getByLabel("回答", { exact: true }).first().fill("实现 Python 数据服务");
  await page.getByLabel("笔记", { exact: true }).fill("待补充测试案例");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.getByText("草稿已保存。")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("问题", { exact: true }).first()).toHaveValue("介绍项目");
  await page.getByRole("button", { name: "完成记录", exact: true }).click();
  await expect(page.getByText("面试记录已保存。")).toBeVisible();
  await page.goto(`${root}/interview/history`);
  await page.getByRole("button", { name: "真实面试", exact: true }).click();
  await page.getByRole("button", { name: /第 2 轮/ }).click();
  await expect(page.getByText("实现 Python 数据服务")).toBeVisible();
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByLabel("笔记标题").fill("测试经验");
  await page.getByLabel("笔记内容").fill("补充边界测试。");
  await page.getByRole("button", { name: "保存笔记" }).click();
  await expect(page.getByRole("heading", { name: "测试经验" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("补充边界测试。")).toBeVisible();
});
test("Debrief POST SSE preserves display order and exact historical generation", async ({
  page,
}, info) => {
  await page.goto(`${root}/review/debriefs`);
  await page.getByRole("button", { name: /技术一面 ·/ }).click();
  await page.getByRole("button", { name: "开始复盘" }).click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await expect(page.getByText("如何验证？", { exact: true })).toBeVisible();
  const headings = await page.locator("article h3").allTextContents();
  expect(headings).toEqual(["第 1 题组", "综合复盘"]);
  await page.getByText("根据同一面试记录重新生成", { exact: true }).click();
  await page.getByRole("button", { name: "重新生成复盘", exact: true }).click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.getByLabel("复盘版本", { exact: true }).selectOption({ index: 1 });
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("debrief-mobile.png"), fullPage: true });
});
test("Product BFF rejects cross-origin writes and Internal access", async ({ request }) => {
  expect(
    (
      await request.post("/api/product/operations", {
        data: {},
        headers: { Origin: "https://evil.example" },
      })
    ).status(),
  ).toBe(403);
  expect((await request.get("/api/product/ops/metrics")).status()).toBe(422);
});

test("needs-input, decision, partial and recovery outcomes never become successful execution", async ({
  page,
}) => {
  for (const [status] of [
    ["needs_input", "需要补充输入"],
    ["decision_required", "需要用户决定"],
    ["partial", "部分完成"],
    ["failure", "失败"],
    ["recovery_required", "需要人工恢复"],
  ]) {
    await page.goto(`${root}/apply/greeting`);
    await bindings(page);
    let dispatched = 0;
    await page.route("**/api/product/operations/*/execute", async (route) => {
      dispatched++;
      const operationId = route.request().url().split("/").at(-2);
      await route.fulfill({
        json: {
          id: operationId,
          request_id: id(91),
          kind: "prepare_application",
          status,
          reason:
            status === "recovery_required" ? "recovery_decision_required" : "context_required",
          package_id: null,
          research_report_id: null,
          run_id: id(92),
          created_at: "2026-10-24T00:00:00Z",
          allowed_actions: status === "recovery_required" ? ["inspect_recovery"] : ["read"],
        },
      });
    });
    await page.getByRole("button", { name: "开始招呼语", exact: true }).click();
    await expect.poll(() => dispatched).toBe(1);
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "执行操作", exact: true })).toHaveCount(0);
    expect(dispatched).toBe(1);
    await page.unroute("**/api/product/operations/*/execute");
  }
});

test("Actual CAS conflict preserves draft and performs no automatic mutation retry", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual`);
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  let calls = 0;
  await page.route("**/api/product/interviews/*", async (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    calls++;
    expect(route.request().postDataJSON().expected_revision).toBe(1);
    await route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } });
  });
  await page.getByLabel("问题", { exact: true }).fill("尚未保存的问题");
  await page.getByRole("button", { name: "完成记录", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "记录已变化" })).toBeVisible();
  await expect(page.getByLabel("问题", { exact: true })).toHaveValue("尚未保存的问题");
  expect(calls).toBe(1);
});

test("Product default views hide internal ids and developer controls at 375px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const route of [
    "research-fit",
    "apply/resume",
    "apply/greeting",
    "apply/submissions",
    "interview/mock",
    "interview/actual",
    "interview/history",
    "review/debriefs",
    "review/knowledge-notes",
    "summary",
  ]) {
    await page.goto(`${root}/${route}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const visible = await page.locator("main").innerText();
    expect(visible).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    expect(visible).not.toMatch(
      /CAS|expected_revision|fact_refs|operation_id|fixture|current pointer|技术详情|查看关联标识|开发与测试设置|准备结果与历史/,
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole("button", { name: "创建操作", exact: true })).toHaveCount(0);
    await expect(page.getByRole("combobox", { name: "测试模式" })).not.toBeVisible();
  }
});
