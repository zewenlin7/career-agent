import { test, expect } from "@playwright/test";
import { id, time } from "../fixtures/product-api";

const root = `/applications/${id(1)}`;

for (const count of [0, 1, 3])
  test(`submission separators only appear between ${count} rows`, async ({ page }, info) => {
    await page.route(`**/api/product/applications/${id(1)}/submissions?*`, (route) =>
      route.fulfill({
        json: {
          items: Array.from({ length: count }, (_, n) => ({
            id: id(29900 + n),
            display_number: n + 1,
            revision: 1,
            created_at: time(),
            resume_revision_id: id(8401),
            render_artifact_id: id(8501),
            resume_name: "合成简历",
            greeting_id: null,
            note: null,
          })),
          has_more: count > 1,
          offset: 0,
          limit: 10,
        },
      }),
    );
    await page.goto(root + "/apply/submissions");
    const rows = page.getByRole("region", { name: "投递记录", exact: true }).locator("article");
    await expect(rows).toHaveCount(count);
    if (count) {
      await expect(rows.last()).toHaveCSS("border-bottom-width", "0px");
      if (count > 1) await expect(rows.first()).toHaveCSS("border-bottom-width", "1px");
    }
    await page.screenshot({
      path: info.outputPath(`submissions-${count}-desktop.png`),
      fullPage: true,
    });
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({
      path: info.outputPath(`submissions-${count}-375.png`),
      fullPage: true,
    });
  });
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("home loads every unfinished session and only exact links enter a session", async ({
  page,
}, info) => {
  const rows = Array.from({ length: 102 }, (_, n) => ({
    id: id(29600 + n),
    application_id: id(1),
    display_number: n + 1,
    status: n === 0 ? "completed" : "waiting_answer",
    revision: 3,
    created_at: time(),
    focus: "mixed",
    policy: { mode: "quick", primary_target: 3, followup_max: 1 },
    primary_question_count: 1,
    followup_count: 0,
    generation_active: false,
    stop_reason: null,
  }));
  await page.route("**/api/product/mock-interviews?*", (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    return route.fulfill({
      json: {
        items: rows.slice(offset, offset + 100),
        has_more: offset + 100 < rows.length,
        offset,
        limit: 100,
      },
    });
  });
  await page.goto(root + "/interview/mock");
  const toggle = page.getByText("继续未完成的模拟面试（101）", { exact: true });
  await expect(toggle).toBeVisible();
  await expect(page.getByRole("link", { name: "继续模拟", exact: true })).toHaveCount(0);
  await toggle.click();
  const links = page.getByRole("link", { name: "继续模拟", exact: true });
  await expect(links).toHaveCount(101);
  await expect(links.last()).toHaveAttribute(
    "href",
    `${root}/interview/mock?session=${rows[101].id}`,
  );
  await page.screenshot({ path: info.outputPath("mock-home-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("mock-home-375.png"), fullPage: true });
  await toggle.click();
  await expect(links).toHaveCount(0);
});

test("generation has one loading message, no premature recovery and no zero counters", async ({
  page,
}, info) => {
  const session = id(29800);
  const value = {
    id: session,
    application_id: id(1),
    revision: 2,
    status: "ready_to_generate",
    generation_active: true,
    pending_question_id: null,
    stop_reason: null,
    completion_type: null,
    primary_question_count: 0,
    followup_count: 0,
    interviewer_turn_count: 0,
    policy: { primary_target: 3, followup_max: 1 },
    context: { job_id: id(2001), binding: {} },
    turns: [],
  };
  await page.route(`**/api/product/mock-interviews/${session}`, (r) => r.fulfill({ json: value }));
  await page.goto(`${root}/interview/mock?session=${session}`);
  await expect(page.getByText("正在准备第 1 题…", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "查询并恢复", exact: true })).toHaveCount(0);
  await expect(page.getByText(/主问题 0/)).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("mock-first-loading-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("mock-first-loading-375.png"), fullPage: true });
});
