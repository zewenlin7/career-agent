import { test, expect } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("company search filters to zero and the whole application card navigates", async ({
  page,
}) => {
  await page.goto("/applications");
  await page.getByLabel("公司", { exact: true }).fill("不存在的合成公司");
  await expect(page.getByText("当前筛选下没有申请记录。", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "清除筛选", exact: true }).click();
  const card = page.getByRole("list", { name: "申请列表" }).getByRole("link").first();
  await card.click({ position: { x: 15, y: 15 } });
  await expect(page).toHaveURL(/\/summary$/);
});

test("blank Mock answer makes no request and early end preserves the typed answer", async ({
  page,
}) => {
  await page.goto(`${root}/interview/mock`);
  await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
  await expect(page.getByLabel("本题回答", { exact: true })).toBeVisible();
  const submitted: Record<string, unknown>[] = [];
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().endsWith("/answers"))
      submitted.push(req.postDataJSON());
  });
  await page.getByLabel("本题回答", { exact: true }).fill("   ");
  await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
  await expect(page.getByText("请输入回答后再提交。", { exact: true })).toBeVisible();
  expect(submitted).toHaveLength(0);
  await page.getByLabel("本题回答", { exact: true }).fill(" 我使用事务验证回滚。 ");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "提前结束", exact: true }).click();
  await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
  expect(submitted).toHaveLength(1);
  expect(submitted[0]).toMatchObject({ answer: "我使用事务验证回滚。", end_early: true });
  await expect(page.getByText("我使用事务验证回滚。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始新的模拟面试", exact: true })).toBeVisible();
});

test("Knowledge Notes edit and delete use current revision without technical UI", async ({
  page,
}) => {
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByLabel("笔记标题", { exact: true }).fill("验证方法");
  await page.getByLabel("笔记内容", { exact: true }).fill("补充测试案例。");
  await page.getByRole("button", { name: "保存笔记", exact: true }).click();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByLabel("笔记标题", { exact: true }).fill("验证计划");
  await page.getByRole("button", { name: "保存笔记", exact: true }).click();
  await expect(page.getByRole("heading", { name: "验证计划", exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("heading", { name: "验证计划", exact: true })).toHaveCount(0);
});

test("refinement is an explicit paid intent, followed by review and separate adoption", async ({
  page,
}) => {
  await page.goto(`${root}/apply/greeting`);
  await page.getByRole("button", { name: "开始招呼语", exact: true }).click();
  await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toBeVisible();
  let executions = 0,
    adoptions = 0;
  const row = {
    id: id(99001),
    task: "greeting_refinement",
    status: "pending",
    reason: null,
    output: null as unknown,
    adopted: null as unknown,
  };
  await page.route("**/api/product/product-drafts**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (path.endsWith("/execute")) {
      executions++;
      row.status = "completed";
      row.output = {
        locale: "zh-CN",
        greeting_text: "您好，我参与过 Python 数据服务项目，期待交流。",
        fact_refs: [id(9010)],
        requirement_refs: [id(7001)],
      };
    } else if (path.endsWith("/adopt")) {
      adoptions++;
      row.adopted = { result_id: id(99002) };
    } else if (req.method() === "POST")
      expect(req.postDataJSON()).toMatchObject({
        task: "greeting_refinement",
        feedback: "突出测试与错误恢复。",
        mode: "live",
      });
    await route.fulfill({ json: row });
  });
  await page.getByRole("button", { name: "调整", exact: true }).click();
  await page.getByLabel("告诉 AI 你想怎么调整", { exact: true }).fill("突出测试与错误恢复。");
  expect(executions).toBe(0);
  await page.getByRole("button", { name: "根据意见调整", exact: true }).click();
  await expect(
    page.getByText("您好，我参与过 Python 数据服务项目，期待交流。", { exact: true }),
  ).toBeVisible();
  expect(executions).toBe(1);
  expect(adoptions).toBe(0);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("已保存。", { exact: true })).toBeVisible();
  expect(adoptions).toBe(1);
});

test("Quick Mock completes three primary questions and leaves no active answer form", async ({
  page,
}) => {
  await page.goto(`${root}/interview/mock`);
  await page.getByLabel("练习重点", { exact: true }).selectOption("mixed");
  await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
  for (let index = 1; index <= 3; index++) {
    await page.getByLabel("本题回答", { exact: true }).fill(`我通过第 ${index} 个测试验证。`);
    await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
    await expect(page.getByText(`我通过第 ${index} 个测试验证。`, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
  await expect(page.getByLabel("本题回答", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "开始新的模拟面试", exact: true })).toBeVisible();
});
