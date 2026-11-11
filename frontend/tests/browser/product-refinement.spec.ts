import { test, expect } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("company candidates stay separate from applied filters and the whole card navigates", async ({
  page,
}) => {
  await page.goto("/applications");
  await page.getByLabel("公司", { exact: true }).fill("不存在的合成公司");
  await expect(page.getByText("没有找到公司", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(20);
  await page.getByLabel("公司", { exact: true }).fill("尚无申请");
  await page.getByRole("option", { name: "尚无申请公司", exact: true }).click();
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page.getByText("当前筛选下没有申请记录。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "清除筛选", exact: true }).click();
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

  await page.getByRole("button", { name: "提前结束", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
  expect(submitted).toHaveLength(1);
  expect(submitted[0]).toMatchObject({ answer: "我使用事务验证回滚。", end_early: true });
  await expect(page.getByText("我使用事务验证回滚。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始新的模拟面试", exact: true })).toHaveCount(0);
});

test("Knowledge Notes edit and delete use current revision without technical UI", async ({
  page,
}) => {
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByRole("button", { name: "新增笔记", exact: true }).click();
  await page.getByLabel("笔记标题", { exact: true }).fill("验证方法");
  await page.getByLabel("笔记内容", { exact: true }).fill("补充测试案例。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "管理笔记：验证方法", exact: true }).click();
  await page.getByRole("menuitem", { name: "编辑", exact: true }).click();
  await page.getByLabel("笔记标题", { exact: true }).fill("验证计划");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: "验证计划", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "管理笔记：验证计划", exact: true }).click();
  await page.getByRole("menuitem", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByRole("heading", { name: "验证计划", exact: true })).toHaveCount(0);
});

test("failed Greeting adjustment keeps its input and previous result, with one local error", async ({
  page,
}) => {
  await page.goto(`${root}/apply/greeting`);
  await page.getByRole("button", { name: "生成", exact: true }).click();
  const original = page.getByText("您好，我有 Python 数据服务项目经验，期待交流。", {
    exact: true,
  });
  await expect(original).toBeVisible();
  let executions = 0;
  await page.route("**/api/product/product-drafts**", async (route) => {
    const execute = route.request().url().endsWith("/execute");
    if (execute) executions++;
    await route.fulfill({
      json: {
        id: id(99001),
        task: "greeting_refinement",
        lineage: { intent: "refine" },
        status: execute ? "failed" : "pending",
        reason: execute ? "budget_exhausted" : null,
        output: null,
        adopted: null,
      },
    });
  });
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({
      json: { state: "failure", reason: "budget_exhausted", selection: {} },
    }),
  );
  await page.getByRole("button", { name: "调整", exact: true }).click();
  await page.getByPlaceholder("输入调整意见").fill("突出测试与错误恢复。");
  await page.getByRole("button", { name: "开始调整", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "招呼语调整未能继续：当前生成预算不足" }),
  ).toHaveCount(1);
  await expect(original).toBeVisible();
  await expect(page.getByPlaceholder("输入调整意见")).toHaveValue("突出测试与错误恢复。");
  await expect(page.getByRole("button", { name: "保存", exact: true })).toHaveCount(0);
  expect(executions).toBe(1);
  await expect(page.getByRole("button", { name: /未处理通知/ })).toBeVisible();
  await expect(
    page.getByLabel("新通知", { exact: true }).filter({ hasText: "预算不足" }),
  ).toHaveCount(0);
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
  await expect(page.getByRole("button", { name: "开始新的模拟面试", exact: true })).toHaveCount(0);
});

test("failed new Greeting generation preserves default history and one error at its own button", async ({
  page,
}) => {
  await page.goto(`${root}/apply/greeting`);
  await page.getByRole("button", { name: "生成", exact: true }).click();
  const old = page.getByText("您好，我有 Python 数据服务项目经验，期待交流。", { exact: true });
  await expect(old).toBeVisible();
  await page.goto(`${root}/apply/greeting`);
  await expect(old).toBeVisible();
  let release!: () => void;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/product/operations/*/execute", async (route) => {
    await hold;
    await route.fulfill({
      json: {
        id: route.request().url().split("/").at(-2),
        status: "failure",
        reason: "budget_exhausted",
        package_id: null,
      },
    });
  });
  await page.getByRole("button", { name: "生成", exact: true }).click();
  await expect(page.getByRole("button", { name: "正在生成…", exact: true })).toHaveCount(1);
  await expect(old).toBeVisible();
  release();
  await expect(
    page.getByRole("alert").filter({ hasText: "招呼语未能继续：当前生成预算不足" }),
  ).toHaveCount(1);
  await expect(old).toBeVisible();
  await expect(page.getByLabel("招呼语记录").locator("option")).toHaveCount(1);
});
