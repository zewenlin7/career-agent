import { test, expect } from "@playwright/test";
import { id, time } from "../fixtures/product-api";
import type { Debrief } from "../../src/features/workspace/contracts";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
test("notes load every page with persistent menu, full text, stable last separator", async ({
  page,
}) => {
  const offsets: number[] = [];
  await page.route(`**/api/product/applications/${id(1)}/knowledge-notes?**`, async (route) => {
    const q = new URL(route.request().url()).searchParams,
      offset = Number(q.get("offset") || 0);
    offsets.push(offset);
    await route.fulfill({
      json: {
        items: Array.from({ length: offset === 0 ? 100 : 1 }, (_, i) => ({
          id: id(61000 + offset + i),
          revision: 1,
          title: `笔记 ${offset + i + 1}`,
          content: `完整正文 ${offset + i + 1}\n第二行`,
          created_at: time(i + offset),
          updated_at: null,
        })),
        has_more: offset === 0,
        limit: 100,
        offset,
      },
    });
  });
  await page.goto(`${root}/review/knowledge-notes`);
  await expect(page.locator("article[data-note-id]")).toHaveCount(101);
  await expect(page.getByText("完整正文 101\n第二行", { exact: true })).toBeVisible();
  expect(offsets).toEqual([0, 100]);
  await expect(page.getByRole("button", { name: "下一页", exact: true })).toHaveCount(0);
  const last = page.locator("article[data-note-id]").last();
  expect(await last.evaluate((el) => getComputedStyle(el).borderBottomWidth)).toBe("0px");
  await expect(last.getByRole("button", { name: "管理笔记：笔记 101" })).toHaveCSS("opacity", "1");
});

test("review history reads beyond ready rows, failed switch and rejected deletion preserve exact body", async ({
  page,
  request,
}) => {
  const base = "http://127.0.0.1:3111/api/v1";
  await request.get(`${base}/interviews/${id(8701)}`);
  const saved: Debrief[] = [];
  for (let i = 0; i < 2; i++) {
    const row = await (
      await request.post(`${base}/interview-debriefs`, { data: { interview_id: id(8701) } })
    ).json();
    await request.post(`${base}/interview-debriefs/${row.id}/execute`);
    saved.push(
      await (await request.get(`${base}/interview-debriefs/${row.id}?historical=true`)).json(),
    );
  }
  const offsets: number[] = [];
  let fail = false;
  await page.route("**/api/product/interview-debriefs**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname.split("/api/product/")[1];
    if (path === "interview-debriefs") {
      const offset = Number(url.searchParams.get("offset") || 0);
      offsets.push(offset);
      await route.fulfill({
        json: {
          items:
            offset === 0
              ? Array.from({ length: 100 }, (_, i) => ({
                  generation_id: id(62000 + i),
                  status: "ready",
                  source_kind: "actual",
                  created_at: time(),
                }))
              : saved.map((r) => ({
                  generation_id: r.id,
                  status: "completed",
                  source_kind: "actual",
                  source_name: "真实面试 · 技术一面",
                  created_at: time(),
                })),
          has_more: offset === 0,
          limit: 100,
          offset,
        },
      });
    } else if (path === `interview-debriefs/${saved[0].id}` && fail) {
      await route.fulfill({ status: 503, json: { error: { code: "request_failed" } } });
    } else if (route.request().method() === "DELETE") {
      await route.fulfill({ json: { deleted: false, used_by: ["历史生成来源（合成时间）"] } });
    } else await route.continue();
  });
  await page.goto(`${root}/review/debriefs?debrief=${saved[1].id}`);
  const select = page.getByLabel("复盘记录", { exact: true });
  await expect(select.locator("option")).toHaveCount(3);
  expect(offsets).toEqual([0, 100]);
  await expect(select).toHaveValue(saved[1].id);
  fail = true;
  await select.selectOption(saved[0].id);
  await expect(page.getByRole("alert").filter({ hasText: /./ }).first()).toBeVisible();
  await expect(select).toHaveValue(saved[1].id);
  await expect(page.locator(`[data-result-destination="${saved[1].id}"]`)).toBeVisible();
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "知道了", exact: true }).click();
  await expect(select).toHaveValue(saved[1].id);
  await expect(select.locator("option")).toHaveCount(3);
  fail = false;
  await select.selectOption(saved[0].id);
  await expect(select).toHaveValue(saved[0].id);
  await expect(page.getByRole("button", { name: "重新生成复盘", exact: true })).toHaveCount(0);
});

test("group picker has no empty source popup and notes menu uses full content edge", async ({
  page,
}) => {
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("逐题范围", { exact: true }).selectOption("selected");
  await expect(page.getByRole("button", { name: "选择题组", exact: true })).toHaveCount(0);
  await page.route(`**/api/product/applications/${id(1)}/knowledge-notes?**`, (route) =>
    route.fulfill({
      json: {
        items: [1, 2].map((n) => ({
          id: id(65000 + n),
          revision: 1,
          title: "长标题".repeat(30) + n,
          content: "完整笔记正文",
          created_at: time(n),
        })),
        has_more: false,
        limit: 100,
        offset: 0,
      },
    }),
  );
  await page.goto(`${root}/review/knowledge-notes`);
  const article = page.locator("article[data-note-id]").first();
  await expect(article).toBeVisible();
  const bounds = await article.evaluate((el) => ({
    right: el.getBoundingClientRect().right,
    container: el.parentElement!.parentElement!.getBoundingClientRect().right,
    menu: el.querySelector("button")!.getBoundingClientRect().right,
  }));
  expect(Math.abs(bounds.right - bounds.container)).toBeLessThanOrEqual(1);
  expect(Math.abs(bounds.right - bounds.menu)).toBeLessThanOrEqual(1);
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({
      path: test.info().outputPath(`long-notes-${width}.png`),
      fullPage: true,
    });
  }
});

test("exact result refresh keeps querying an unfinished generation", async ({ page, request }) => {
  const base = "http://127.0.0.1:3111/api/v1";
  await request.get(`${base}/interviews/${id(8701)}`);
  const row = await (
    await request.post(`${base}/interview-debriefs`, { data: { interview_id: id(8701) } })
  ).json();
  await request.post(`${base}/interview-debriefs/${row.id}/execute`);
  const complete = await (
    await request.get(`${base}/interview-debriefs/${row.id}?historical=true`)
  ).json();
  let reads = 0;
  await page.route(`**/api/product/interview-debriefs/${row.id}?historical=true`, async (route) => {
    reads++;
    await route.fulfill({
      json: reads === 1 ? { ...complete, status: "running", execution_active: true } : complete,
    });
  });
  await page.goto(`${root}/review/debriefs?debrief=${row.id}`);
  await expect.poll(() => reads).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("正在生成复盘…", { exact: true })).toHaveCount(0);
  await expect(page.locator(`[data-result-destination="${row.id}"]`)).toBeVisible();
  expect(reads).toBeGreaterThanOrEqual(2);
});

for (const state of ["running", "partial", "completed"] as const) {
  test(`review ${state} shows analysis without persistence reports`, async ({
    page,
    request,
  }, info) => {
    const base = "http://127.0.0.1:3111/api/v1";
    await request.get(`${base}/interviews/${id(8701)}`);
    const row = await (
      await request.post(`${base}/interview-debriefs`, { data: { interview_id: id(8701) } })
    ).json();
    await request.post(`${base}/interview-debriefs/${row.id}/execute`);
    const complete = await (
      await request.get(`${base}/interview-debriefs/${row.id}?historical=true`)
    ).json();
    const artifacts = complete.artifacts.map((a: { id: string; kind: string }) =>
      state === "partial" && a.kind === "overall"
        ? { ...a, status: "failed", presentation: {}, error_code: "invalid_evidence_reference" }
        : a,
    );
    await page.route(`**/api/product/interview-debriefs/${row.id}?historical=true`, (route) =>
      route.fulfill({
        json: {
          ...complete,
          status: state,
          artifacts,
          execution_active: state === "running",
          recovery: Object.fromEntries(
            artifacts
              .filter((a: { status: string }) => a.status === "failed")
              .map((a: { id: string }) => [a.id, "retryable"]),
          ),
        },
      }),
    );
    await page.goto(`${root}/review/debriefs?debrief=${row.id}`);
    await expect(page.locator(`[data-result-destination="${row.id}"]`)).toBeVisible();
    await expect(
      page.getByText(/尚无已保存分析|题组.*已保存|综合复盘已保存|复盘已完成/),
    ).toHaveCount(0);
    if (state === "running")
      await expect(page.getByText("正在生成复盘…", { exact: true })).toBeVisible();
    if (state === "partial")
      await expect(page.getByRole("button", { name: "重试失败项", exact: true })).toBeVisible();
    for (const width of [1280, 375]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({
        path: info.outputPath(`review-${state}-${width}.png`),
        fullPage: true,
      });
    }
  });
}
