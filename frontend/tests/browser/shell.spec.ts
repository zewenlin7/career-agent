import { expect, test } from "@playwright/test";
import {
  applicationNavigation,
  sectionNavigation,
  operationsNavigation,
  evaluationNavigation,
} from "../../src/lib/navigation";

test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("all IA routes render; browser never calls backend APIs directly", async ({ page }) => {
  const errors: string[] = [];
  const apiCalls: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (req) => {
    if (req.url().includes("/api/")) apiCalls.push(req.url());
  });
  const id = "00000000-0000-4000-8000-000000000001";
  const pages = [
    { href: "/applications", label: "申请" },
    { href: "/profile", label: "个人资料" },
    ...applicationNavigation(id).slice(0, 2),
    ...sectionNavigation(id, "apply"),
    ...sectionNavigation(id, "interview"),
    ...sectionNavigation(id, "review"),
    ...operationsNavigation,
    ...evaluationNavigation,
  ];
  for (const item of pages) {
    await page.goto(item.href);
    await expect(
      page.getByRole("heading", { name: item.label, exact: true, level: 1 }),
    ).toBeVisible();
  }
  expect(errors).toEqual([]);
  expect(
    apiCalls.every((url) => /^http:\/\/127\.0\.0\.1:3100\/api\/(product|internal)\//.test(url)),
  ).toBe(true);
});

test("shell navigation, narrow viewport and keyboard access", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/applications$/);
  await page.screenshot({ path: testInfo.outputPath("product-desktop.png"), fullPage: true });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page
    .getByRole("navigation", { name: "主导航", exact: true })
    .getByRole("link", { name: "个人资料", exact: true })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "主导航", exact: true })
      .getByRole("link", { name: "个人资料", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "系统管理", exact: true }).click();
  await expect(page).toHaveURL(/\/internal\/operations\/overview$/);
  await page.screenshot({ path: testInfo.outputPath("internal-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of [
    "/internal/evaluation/calibration-triage",
    "/applications/00000000-0000-4000-8000-000000000001/interview/history",
  ]) {
    await page.goto(path);
    await page.screenshot({
      path: testInfo.outputPath(
        path.includes("internal") ? "internal-mobile.png" : "application-mobile.png",
      ),
      fullPage: true,
    });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
});
