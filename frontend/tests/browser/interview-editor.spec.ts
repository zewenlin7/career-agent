import { test, expect } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("date-time panel preserves partial choices in either order and invalid text stays local", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual`);
  await page.getByRole("button", { name: "新增记录", exact: true }).click();
  const input = page.getByPlaceholder("YYYY-MM-DD HH:mm");
  await page.getByRole("button", { name: "选择面试日期时间", exact: true }).click();
  await expect(input).toHaveValue("");
  await page.getByLabel("分钟", { exact: true }).selectOption("30");
  await page.getByLabel("小时", { exact: true }).selectOption("09");
  const date = page.getByRole("button", { name: /^\d+年\d+月1日$/ });
  const label = (await date.getAttribute("aria-label"))!;
  const [, year, month] = /^(\d+)年(\d+)月1日$/.exec(label)!;
  await date.click();
  await expect(input).toHaveValue(`${year}-${month.padStart(2, "0")}-01 09:30`);
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await input.fill("2026-02-30 09:30");
  await page.getByLabel("面试类型", { exact: true }).selectOption("technical");
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByPlaceholder("输入问题").fill("测试日期校验");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(input).toHaveAttribute("aria-invalid", "true");
  await expect(input.locator("..").getByRole("alert")).toHaveText(
    "请填写有效时间 YYYY-MM-DD HH:mm，或留空。",
  );
  await expect(input).toHaveValue("2026-02-30 09:30");
});

test("editor cancel returns to selection, back returns to mode choice, exact history stays exact", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual?actual=${id(8701)}`);
  await expect(page.getByLabel("问题1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page).toHaveURL(`${root}/interview/actual?mode=edit`);
  await page.reload();
  await expect(page.getByLabel("面试记录", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("问题1", { exact: true })).toHaveCount(0);
  await page.getByLabel("面试记录", { exact: true }).selectOption(id(8701));
  await page.getByRole("button", { name: "← 返回操作选择", exact: true }).click();
  await expect(page).toHaveURL(`${root}/interview/actual`);
  await page.reload();
  await expect(page.getByRole("button", { name: "新增记录", exact: true })).toBeVisible();
  await expect(page.getByLabel("问题1", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "编辑记录", exact: true }).click();
  await page.getByLabel("面试记录", { exact: true }).selectOption(id(8701));
  await page.getByLabel("回答", { exact: true }).first().fill("尚未保存的修改");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByLabel("回答", { exact: true }).first()).toHaveValue("尚未保存的修改");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByLabel("面试记录", { exact: true })).toHaveValue("");
  await page.goto(`${root}/interview/actual?actual=${id(8701)}&return=history`);
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page).toHaveURL(`${root}/interview/history?actual=${id(8701)}`);
});
