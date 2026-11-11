import { test, expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { id, time } from "../fixtures/product-api";
import type { Mock } from "../../src/features/workspace/contracts";

const root = `/applications/${id(1)}`;
const mockId = id(28601);
const question = "请说明事务边界 https://example.com/" + "long-question".repeat(18);
const answer = "使用实际案例回答。" + "LongAnswerWithoutSpaces".repeat(14);
function mockRecord(kinds: string[]): Mock {
  let primary = 0;
  let followup = 0;
  let parent: string | null = null;
  return {
    id: mockId,
    application_id: id(1),
    revision: 1,
    status: "completed",
    generation_active: false,
    pending_question_id: null,
    stop_reason: null,
    completion_type: "target_reached",
    primary_question_count: kinds.filter((k) => k === "primary").length,
    followup_count: kinds.filter((k) => k === "follow_up").length,
    interviewer_turn_count: kinds.length,
    policy: {
      primary_target: kinds.filter((k) => k === "primary").length,
      followup_max: Math.max(2, kinds.filter((k) => k === "follow_up").length),
    },
    context: {
      job_id: id(2001),
      binding: { profile_id: id(9001), resume_revision_id: id(8401), job_revision_id: id(4001) },
    },
    turns: kinds.map((kind, index) => {
      const entry = id(28610 + index);
      if (kind === "primary") {
        primary++;
        followup = 0;
        parent = entry;
      } else followup++;
      return {
        id: entry,
        sequence: index + 1,
        question_number: `${primary}${followup ? `.${followup}` : ""}`,
        main_question_number: primary,
        followup_index: followup || null,
        question: {
          kind: kind as "primary" | "follow_up",
          topic: "事务与可靠性",
          question: index ? `问题 ${index + 1}` : question,
          primary_entry_id: kind === "primary" ? null : parent,
        },
        answer: index ? `回答 ${index + 1}` : answer,
        accepted_model_call_id: null,
      };
    }),
  };
}
async function borders(locator: Locator) {
  return locator.locator("*").evaluateAll((nodes) =>
    nodes
      .filter((n) => parseFloat(getComputedStyle(n).borderBottomWidth) > 0)
      .map((n) => {
        const r = n.getBoundingClientRect();
        return { x: r.x, width: r.width, bottom: r.bottom };
      }),
  );
}
async function screenshot(page: Page, info: TestInfo, name: string) {
  await page.screenshot({ path: info.outputPath(`${name}-desktop.png`), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath(`${name}-375.png`), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
}
test.beforeEach(async ({ request, page }) => {
  await request.get("http://127.0.0.1:3111/__reset");
  await page.setViewportSize({ width: 1280, height: 900 });
});

test("Mock number, question and answer use readable roles and whole-group separators", async ({
  page,
}, info) => {
  const record = mockRecord(["primary", "follow_up", "follow_up", "primary", "follow_up"]);
  await page.route(`**/api/product/mock-interviews/${mockId}`, (r) => r.fulfill({ json: record }));
  await page.route("**/api/product/mock-interviews?*", (r) =>
    r.fulfill({
      json: { items: [{ ...record, created_at: time() }], has_more: false, offset: 0, limit: 100 },
    }),
  );
  await page.goto(`${root}/interview/history?session=${mockId}`);
  const current = page.locator(`[data-question-id="${record.turns[0].id}"]`);
  await expect(current.getByText(question, { exact: true })).toBeVisible();
  const styles = await current
    .locator("p:not([data-saved-answer] > p:first-child)")
    .evaluateAll((nodes) =>
      nodes.map((n) => {
        const s = getComputedStyle(n);
        return { size: s.fontSize, weight: s.fontWeight, line: s.lineHeight, color: s.color };
      }),
    );
  expect(styles[0]).toEqual({
    size: "16px",
    weight: "600",
    line: "26px",
    color: "rgb(28, 20, 16)",
  });
  for (const role of styles.slice(1))
    expect(role).toEqual({ size: "16px", weight: "400", line: "26px", color: "rgb(28, 20, 16)" });
  await expect(current.getByText("我的回答", { exact: true })).toHaveCSS("font-size", "16px");
  const list = page.locator(`[data-result-destination="${mockId}"] ol`);
  const box = (await list.boundingBox())!;
  const lines = await borders(list);
  expect(lines).toHaveLength(1);
  expect(lines[0].x).toBe(box.x);
  expect(lines[0].width).toBe(box.width);
  const tail = (await page
    .locator(`[data-question-id="${record.turns.at(-1)!.id}"]`)
    .boundingBox())!;
  expect(lines[0].bottom).toBeLessThan(tail.y);
  await writeFile(info.outputPath("mock-role-styles.json"), JSON.stringify(styles, null, 2));
  await screenshot(page, info, "mock-history");
});

test("single and multiple primary groups have separators only between groups", async ({
  page,
}, info) => {
  let record = mockRecord(["primary"]);
  await page.route(`**/api/product/mock-interviews/${mockId}`, (r) => r.fulfill({ json: record }));
  await page.route("**/api/product/mock-interviews?*", (r) =>
    r.fulfill({
      json: { items: [{ ...record, created_at: time() }], has_more: false, offset: 0, limit: 100 },
    }),
  );
  for (const kinds of [
    ["primary"],
    ["primary", "follow_up", "follow_up"],
    ["primary", "primary"],
  ]) {
    record = mockRecord(kinds);
    await page.goto(`${root}/interview/history?session=${mockId}`);
    await expect(page.locator("[data-question-id]")).toHaveCount(kinds.length);
    expect(await borders(page.locator(`[data-result-destination="${mockId}"] ol`))).toHaveLength(
      kinds.filter((k) => k === "primary").length - 1,
    );
  }
  await page.route(`**/api/product/interviews/${id(8701)}`, async (r) => {
    const response = await r.fetch();
    const data = await response.json();
    data.entries.push({
      ...data.entries[0],
      entry_id: id(8704),
      order: 3,
      question: "第二组主问题",
    });
    await r.fulfill({ json: data });
  });
  await page.goto(`${root}/interview/history?actual=${id(8701)}`);
  await expect(page.getByText("第二组主问题", { exact: false })).toBeVisible();
  const transcript = page.getByText("问题1　介绍项目", { exact: true }).locator("../../..");
  expect(await borders(transcript)).toHaveLength(1);
  await screenshot(page, info, "actual-history-groups");
});

test("Fit repeated results do not leave a trailing divider", async ({ page }) => {
  await page.goto(`${root}/research-fit/fit`);
  await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  const item = page.getByText("暂无相关事实证据。", { exact: true }).locator("..");
  await expect(item).toBeVisible();
  await expect(item).toHaveCSS("border-bottom-width", "0px");
});

for (const mode of ["new", "edit"] as const)
  test(`Actual ${mode} keeps action groups compact and preserves move, ownership and delete behavior`, async ({
    page,
  }, info) => {
    await page.goto(`${root}/interview/actual${mode === "edit" ? `?actual=${id(8701)}` : ""}`);
    if (mode === "new") {
      await page.getByRole("button", { name: "新增记录", exact: true }).click();
      await page.getByRole("button", { name: "添加问题", exact: true }).click();
      await page.getByLabel("问题1", { exact: true }).fill("第一组");
      await page.getByRole("button", { name: "添加追问", exact: true }).click();
      await page.getByLabel("问题1.1", { exact: true }).fill("第一个追问");
    }
    await page.getByRole("button", { name: "添加问题", exact: true }).click();
    await page.getByLabel("问题2", { exact: true }).fill("第二组");
    const visibleGroups = page.locator("fieldset > div").filter({
      has: page.getByPlaceholder("输入问题"),
    });
    await expect(visibleGroups).toHaveCount(2);
    await expect(visibleGroups.first()).toHaveCSS("border-bottom-width", "1px");
    await expect(visibleGroups.last()).toHaveCSS("border-bottom-width", "0px");
    const fullWidth = (await page.locator("fieldset").boundingBox())!.width;
    expect((await visibleGroups.first().boundingBox())!.width).toBe(fullWidth);
    const group = page.getByLabel("问题1", { exact: true }).locator("../..");
    const add = group.getByRole("button", { name: "添加追问", exact: true });
    const assign = group.getByRole("button", { name: "调整归属", exact: true });
    const up = group.getByRole("button", { name: "上移问题", exact: true });
    const down = group.getByRole("button", { name: "下移问题", exact: true });
    const remove = group.getByRole("button", { name: "删除", exact: true });
    await expect(up).toBeDisabled();
    await expect(down).toBeEnabled();
    await expect(up).toHaveAttribute("title", "上移问题");
    const [a, b, c, d, e] = await Promise.all(
      [add, assign, up, down, remove].map((n) => n.boundingBox()),
    );
    expect(a!.x).toBeLessThan(b!.x);
    expect(b!.x + b!.width + 40).toBeLessThan(c!.x);
    expect(c!.x).toBeLessThan(d!.x);
    expect(d!.x).toBeLessThan(e!.x);
    expect(c!.height).toBeLessThan(a!.height);
    expect(c!.width).toBeLessThanOrEqual(32);
    await expect(group.getByLabel("归属", { exact: true })).toHaveCount(0);
    await down.click();
    await expect(page.getByLabel("问题1", { exact: true })).toHaveValue("第二组");
    await expect(page.getByLabel("问题2.1", { exact: true })).toBeVisible();
    const child = page.getByLabel("问题2.1", { exact: true }).locator("../..");
    await expect(child.getByRole("button", { name: "添加追问", exact: true })).toHaveCount(0);
    await child.getByRole("button", { name: "调整归属", exact: true }).click();
    await child.getByLabel("归属", { exact: true }).selectOption({ label: "问题1" });
    await expect(page.getByLabel("问题1.1", { exact: true })).toBeVisible();
    const moved = page.getByLabel("问题1.1", { exact: true }).locator("../..");
    await moved.getByRole("button", { name: "删除", exact: true }).click();
    await expect(page.getByRole("dialog")).toContainText("删除这道追问及其回答？");
    await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
    await expect(page.getByLabel("问题1.1", { exact: true })).toBeVisible();
    await moved.getByRole("button", { name: "删除", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
    await expect(page.getByLabel("问题1.1", { exact: true })).toHaveCount(0);
    await expect(
      page
        .getByLabel("问题2", { exact: true })
        .locator("../..")
        .getByRole("button", { name: "下移问题", exact: true }),
    ).toBeDisabled();
    await screenshot(page, info, `actual-${mode}-actions`);
  });
