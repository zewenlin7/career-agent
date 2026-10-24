import { test, expect, type Page } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
async function bindings(page: Page, withResume = true) {
  await page.getByLabel("Profile 历史版本（明确选择）").selectOption(id(9001));
  if (withResume)
    await page.getByLabel("来源 Resume exact revision（不自动选择）").selectOption(id(8401));
}
async function execute(page: Page) {
  await page.getByRole("button", { name: "创建操作", exact: true }).click();
  await expect(page.getByRole("region", { name: "当前操作" })).toBeVisible();
  await page.getByRole("button", { name: "执行操作", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "当前操作" }).getByText("成功", { exact: true }).first(),
  ).toBeVisible();
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
  await page
    .getByRole("region", { name: "晨星科技 · 公司研究" })
    .getByLabel("执行模式")
    .selectOption("fixture");
  await expect(page.getByText("公司提供数据服务。")).toBeVisible();
  const research = page.getByRole("region", { name: "显式公司研究" });
  await research.getByLabel("Profile 历史版本（明确选择）").selectOption(id(9001));
  await research.getByRole("checkbox").check();
  await research.getByRole("button", { name: "创建操作", exact: true }).click();
  await research.getByRole("button", { name: "执行操作", exact: true }).click();
  expect(researchBodies).toHaveLength(1);
  expect(researchBodies[0]).toMatchObject({
    kind: "company_research",
    request: {
      force_research_refresh: true,
      profile_id: id(9001),
      job_revision_id: id(4001),
      mode: "fixture",
    },
  });
  const fit = page.getByRole("region", { name: "生成准备结果" });
  await fit.getByLabel("Profile 历史版本（明确选择）").selectOption(id(9001));
  await fit.getByRole("button", { name: "创建操作", exact: true }).click();
  await fit.getByRole("button", { name: "执行操作", exact: true }).click();
  await expect(page.getByText("暂无证据（不等于不具备）")).toBeVisible();
  await page.reload();
  await fit.getByText("重新发现当前 JD 的已保存操作").click();
  await expect(fit.getByRole("button", { name: /prepare_application · success/ })).toBeVisible();
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
  await page
    .getByRole("region", { name: "Resume variant / revision 历史" })
    .getByLabel("查看哪个 Profile 的简历")
    .selectOption(id(9001));
  await page
    .getByRole("button", { name: new RegExp(`revision 1 · 同一 Job · ${id(8401)}`) })
    .click();
  await page.getByRole("button", { name: "渲染此 exact revision 的 PDF" }).click();
  await expect(page.getByText("PDF 已验收")).toBeVisible();
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
  await page.getByLabel("实际使用的 accepted RenderArtifact ID").fill(id(8501));
  await page.getByRole("checkbox", { name: "确认这是已经发生的实际投递" }).check();
  await page.getByRole("button", { name: "记录真实 Submission", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "已记录 Submission" })).toBeVisible();
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
  await expect(
    page.getByRole("button", { name: "记录真实 Submission", exact: true }),
  ).toBeDisabled();
  await page.goto(`${root}/interview/preparation`);
  await bindings(page);
  const select = page.getByLabel("已验收简历所在的 Application package");
  const options = await select.locator("option").all();
  expect(options.length).toBeGreaterThan(1);
  // Tailoring is the earlier package; Greeting is newest. Explicitly choose the matching one.
  await select.selectOption({ index: 2 });
  await expect(page.getByText(/此 package 使用 Resume/)).toBeVisible();
  await execute(page);
  await expect(page.getByText("团队如何合作？")).toBeVisible();
});
test("Mock immutable answer, failure preservation, generation-only retry, early end and discovery", async ({
  page,
}) => {
  await page.goto(`${root}/interview/mock`);
  await bindings(page);
  await page.getByRole("button", { name: "创建 Mock", exact: true }).click();
  await page.getByRole("button", { name: "生成下一题", exact: true }).click();
  await expect(page.getByText("请介绍你的 Python 项目。")).toBeVisible();
  await page.getByLabel("本题回答（接受后不可编辑）").fill("我使用 Python 编写了数据服务。");
  await page.getByRole("button", { name: "提交回答并继续" }).click();
  await expect(page.getByText("我使用 Python 编写了数据服务。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试生成问题" })).toBeVisible();
  await page.getByRole("button", { name: "重试生成问题" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "提前结束", exact: true }).click();
  await expect(page.getByText("用户提前结束")).toBeVisible();
  await page.goto(`${root}/interview/history`);
  await page.getByRole("button", { name: /Mock ·/ }).click();
  await expect(page.getByText("我使用 Python 编写了数据服务。")).toBeVisible();
});
test("Actual intake primary/follow-up/correction/notes and Application Knowledge Notes", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual`);
  await page.getByLabel("面试轮次（自由文本）").fill("技术二面");
  await page.getByRole("button", { name: "创建真实面试记录" }).click();
  await page.getByLabel("问题", { exact: true }).fill("介绍项目");
  await page.getByLabel("回答（可留空）").fill("实现数据服务");
  await page.getByRole("button", { name: "追加问答", exact: true }).click();
  await page.getByLabel("问题类型").selectOption("follow_up");
  await page.getByLabel("所属主问题").selectOption({ index: 1 });
  await page.getByLabel("问题", { exact: true }).fill("如何测试？");
  await page.getByRole("button", { name: "追加问答", exact: true }).click();
  await page.getByRole("button", { name: "更正此问答" }).first().click();
  await page.getByLabel("回答（可留空）").fill("实现 Python 数据服务");
  await page.getByRole("button", { name: "保存更正" }).click();
  await expect(page.getByText("实现 Python 数据服务", { exact: true })).toBeVisible();
  await page.getByLabel("追加自由笔记（不会自动解析成问答）").fill("待补充测试案例");
  await page.getByRole("button", { name: "追加笔记", exact: true }).click();
  await expect(page.getByText("待补充测试案例", { exact: true })).toBeVisible();
  await page.goto(`${root}/interview/history`);
  await page.getByRole("button", { name: "Actual Interviews", exact: true }).click();
  await page.getByRole("button", { name: /技术二面 ·/ }).click();
  await expect(page.getByText("实现 Python 数据服务")).toBeVisible();
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByLabel("笔记标题").fill("测试经验");
  await page.getByLabel("笔记内容").fill("补充边界测试。");
  await page.getByRole("button", { name: "保存 Knowledge Note" }).click();
  await expect(page.getByRole("heading", { name: "测试经验" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("补充边界测试。")).toBeVisible();
});
test("Debrief POST SSE preserves display order and exact historical generation", async ({
  page,
}, info) => {
  await page.goto(`${root}/review/debriefs`);
  await page.getByRole("button", { name: /技术一面 ·/ }).click();
  await page.getByRole("button", { name: "创建复盘 run" }).click();
  await page.getByRole("button", { name: "执行复盘（POST SSE）" }).click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await expect(page.getByText("如何验证？", { exact: true })).toBeVisible();
  const headings = await page.locator("article h3").allTextContents();
  expect(headings).toEqual(["第 1 题组", "Overall 综合复盘"]);
  await page.getByText("针对同一 frozen source 重新生成", { exact: true }).click();
  await page.getByRole("button", { name: "创建新 generation", exact: true }).click();
  await expect(page.getByRole("button", { name: "执行复盘（POST SSE）" })).toBeVisible();
  await expect(page.getByText("回答具有具体依据")).toHaveCount(0);
  await page.getByRole("button", { name: "查看此历史 generation" }).last().click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
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
  for (const [status, label] of [
    ["needs_input", "需要补充输入"],
    ["decision_required", "需要用户决定"],
    ["partial", "部分完成"],
    ["failure", "失败"],
    ["recovery_required", "需要人工恢复"],
  ]) {
    await page.goto(`${root}/apply/greeting`);
    await bindings(page);
    await page.getByRole("button", { name: "创建操作", exact: true }).click();
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
    await page.getByRole("button", { name: "执行操作", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "当前操作" }).getByText(label, { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "执行操作", exact: true })).toHaveCount(0);
    expect(dispatched).toBe(1);
    await page.unroute("**/api/product/operations/*/execute");
  }
});

test("Actual CAS conflict preserves draft and performs no automatic mutation retry", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual`);
  await page.getByLabel("面试轮次（自由文本）").fill("合成面试");
  await page.getByRole("button", { name: "创建真实面试记录" }).click();
  let calls = 0;
  await page.route("**/api/product/interviews/*/entries", async (route) => {
    calls++;
    expect(route.request().postDataJSON().expected_revision).toBe(1);
    await route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } });
  });
  await page.getByLabel("问题", { exact: true }).fill("尚未保存的问题");
  await page.getByRole("button", { name: "追加问答", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "记录已变化" })).toBeVisible();
  await expect(page.getByLabel("问题", { exact: true })).toHaveValue("尚未保存的问题");
  expect(calls).toBe(1);
});
