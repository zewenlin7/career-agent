import { expect, test } from "@playwright/test";
import { id } from "../fixtures/product-api";

test("Applications filters, company discovery, URL pagination and refresh", async ({ page }) => {
  await page.goto("/applications");
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(20);
  await page
    .getByRole("navigation", { name: "申请分页" })
    .getByRole("link", { name: "下一页" })
    .click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(4);
  await page.reload();
  await expect(page.getByText("第 2 页", { exact: false })).toBeVisible();
  await page.getByLabel("状态", { exact: true }).selectOption("applied");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page).not.toHaveURL(/page=2/);
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(1);
  await page.getByLabel("公司", { exact: true }).fill("晨星");
  await page.getByRole("button", { name: "晨星科技", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`company_id=${id(1001)}`));
  await expect(page).toHaveURL(/status=applied/);
  await expect(page.getByRole("link", { name: /后端工程师/ })).toBeVisible();
});

test("workspace exact context, same-company switch and inherited placeholder", async ({
  page,
}, info) => {
  await page.goto(`/applications/${id(1)}/summary`);
  const context = page.getByRole("region", { name: "当前申请" });
  await expect(context.getByText("后端工程师", { exact: true })).toBeVisible();
  await expect(context.getByText("已投递", { exact: true })).toBeVisible();
  await expect(context.getByText(id(2001), { exact: true })).toHaveCount(0);
  await context.getByText("同公司职位 / 申请切换", { exact: true }).click();
  await context.getByRole("link", { name: /Agent 工程师/ }).click();
  await expect(page).toHaveURL(new RegExp(`/applications/${id(2)}/summary`));
  await expect(
    page.getByRole("region", { name: "当前申请" }).getByText("面试中", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "投递材料", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/applications/${id(2)}/apply/resume`));
  await expect(
    page.getByRole("region", { name: "当前申请" }).getByText("Agent 工程师", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "简历", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: info.outputPath("workspace-mobile.png"), fullPage: true });
});

test("Summary uses facts, distinguishes unavailable/empty/history, and never renders private extras", async ({
  page,
}, info) => {
  await page.goto(`/applications/${id(1)}/summary`);
  await expect(page.getByRole("region", { name: "已有成果" })).toBeVisible();
  await expect(page.getByText("建议更新资料", { exact: true })).toBeVisible();
  await expect(page.getByText("等待回答", { exact: true })).toBeVisible();
  await expect(page.getByText("历史复盘结果", { exact: true })).toBeVisible();
  await expect(page.getByText("已核对岗位要求", { exact: true })).toBeVisible();
  await page.getByText("查看当前 JD · 第 2 版", { exact: true }).click();
  expect(await page.evaluate(() => Object.hasOwn(window, "__injected"))).toBe(false);
  expect(await page.locator("body").innerText()).not.toContain("PRIVATE_PAYLOAD_NOT_RENDERED");
  await page.screenshot({ path: info.outputPath("summary-desktop.png"), fullPage: true });
  await page.goto(`/applications/${id(24)}/summary`);
  await expect(
    page.getByRole("region", { name: "最新公司研究记录" }).getByRole("status"),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "已有成果" })).toBeVisible();
});

test("bad bindings and invalid queries fail closed without exposing provider errors", async ({
  page,
}) => {
  await page.goto("/applications?status=success");
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("筛选或分页参数无效。");
  await page.goto(`/applications/${id(999)}/summary`);
  await expect(page.getByRole("heading", { name: "找不到这个页面" })).toBeVisible();
  await page.goto(`/applications/${id(88)}/summary`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "暂时无法读取申请及职位关联",
  );
  await expect(page.getByRole("region", { name: "当前申请" })).toHaveCount(0);
  await page.goto(`/applications?company_id=${id(1003)}`);
  await expect(page.getByText("当前筛选下没有申请记录。", { exact: true })).toBeVisible();
});

test("Applications/Summary reads stay GET-only, no Internal paths and no Ops header", async ({
  page,
  request,
}) => {
  await page.goto(`/applications/${id(1)}/summary`);
  const calls = await (await request.get("http://127.0.0.1:3111/__requests")).json();
  expect(calls.length).toBeGreaterThan(0);
  for (const call of calls) {
    expect(call.method).toBe("GET");
    expect(call.hasOpsToken).toBe(false);
    expect(call.path).not.toMatch(/\/ops\/|\/evaluation\/|\/execute/);
  }
});
