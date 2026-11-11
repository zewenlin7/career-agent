import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { id, time } from "../fixtures/product-api";
import type { Mock } from "../../src/features/workspace/contracts";

const root = `/applications/${id(1)}`;
const session = id(30100),
  primary = id(30101),
  followup = id(30102);
function record(): Mock {
  return {
    id: session,
    application_id: id(1),
    revision: 5,
    status: "waiting_answer",
    generation_active: false,
    pending_question_id: followup,
    stop_reason: null,
    completion_type: null,
    primary_question_count: 1,
    followup_count: 1,
    interviewer_turn_count: 2,
    policy: { primary_target: 3, followup_max: 1 },
    context: {
      job_id: id(2001),
      binding: { profile_id: id(9001), resume_revision_id: id(8401), job_revision_id: id(4001) },
    },
    turns: [
      {
        id: primary,
        sequence: 1,
        question_number: "1",
        question: {
          kind: "primary",
          question: "请说明事务边界。",
          topic: "旧内部考点",
          primary_entry_id: null,
        },
        answer: "先保存用户回答，再启动下一次生成。",
        accepted_model_call_id: null,
      },
      {
        id: followup,
        sequence: 2,
        question_number: "1.1",
        question: {
          kind: "follow_up",
          question: "连接中断时，如何核对已保存的状态？",
          topic: "旧追问考点",
          primary_entry_id: primary,
        },
        answer: null,
        accepted_model_call_id: null,
      },
    ],
  };
}
async function evidence(page: Page, info: TestInfo, name: string) {
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    const roles = await page
      .locator("main h1, main p, main button, main textarea, main select, main label, main a")
      .evaluateAll((nodes) =>
        nodes
          .filter((n) => n.getClientRects().length)
          .map((n) => {
            const style = getComputedStyle(n);
            return {
              tag: n.tagName,
              text: n.textContent?.slice(0, 70),
              size: style.fontSize,
              weight: style.fontWeight,
              line: style.lineHeight,
              color: style.color,
            };
          }),
      );
    await writeFile(info.outputPath(`${name}-${width}-roles.json`), JSON.stringify(roles, null, 2));
    await page.screenshot({ path: info.outputPath(`${name}-${width}.png`), fullPage: true });
  }
}
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("Mock follow-up owns question, saved answer, editor and aligned actions without topic labels", async ({
  page,
}, info) => {
  const data = record();
  await page.route(`**/api/product/mock-interviews/${session}`, (r) => r.fulfill({ json: data }));
  await page.goto(`${root}/interview/mock?session=${session}`);
  await expect(page.getByText("问题 1.1", { exact: true })).toBeVisible();
  await expect(page.getByText("旧内部考点", { exact: false })).toHaveCount(0);
  const first = page.locator(`[data-question-id="${primary}"]`);
  const next = page.locator(`[data-question-id="${followup}"]`);
  await expect(first.getByText("我的回答", { exact: true })).toBeVisible();
  await expect(next.getByPlaceholder("输入你的回答…")).toBeVisible();
  const submit = next.getByRole("button", { name: "提交回答并继续", exact: true });
  const end = next.getByRole("button", { name: "提前结束", exact: true });
  await expect(submit).toBeVisible();
  const a = (await submit.boundingBox())!,
    b = (await end.boundingBox())!;
  expect(a.y).toBe(b.y);
  expect(a.height).toBe(b.height);
  await expect(first.getByText("我的回答", { exact: true })).toHaveCSS("font-size", "16px");
  const roles = await page
    .locator("[data-question-id] p, [data-question-id] textarea, [data-question-id] button")
    .evaluateAll((nodes) =>
      nodes.map((n) => {
        const s = getComputedStyle(n);
        return {
          tag: n.tagName,
          text: n.textContent?.slice(0, 30),
          size: s.fontSize,
          weight: s.fontWeight,
          line: s.lineHeight,
        };
      }),
    );
  await writeFile(info.outputPath("answer-roles.json"), JSON.stringify(roles, null, 2));
  await evidence(page, info, "followup-answer");
  await end.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await evidence(page, info, "early-end-confirm");
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(next.getByPlaceholder("输入你的回答…")).toBeVisible();
});

for (const completion of [null, "user_ended_early", "target_reached"] as const)
  test(`read-only history continuation and completion ${completion}`, async ({ page }, info) => {
    const data = record();
    if (completion) {
      data.status = "completed";
      data.completion_type = completion;
      data.pending_question_id = null;
      if (completion === "target_reached") {
        data.policy.primary_target = 1;
        data.turns[1].answer = "通过持久化记录确认处理结果。";
      }
    }
    await page.route(`**/api/product/mock-interviews/${session}`, (r) => r.fulfill({ json: data }));
    await page.route("**/api/product/mock-interviews?*", (r) =>
      r.fulfill({
        json: { items: [{ ...data, created_at: time() }], limit: 100, offset: 0, has_more: false },
      }),
    );
    await page.goto(`${root}/interview/history?session=${session}`);
    await expect(page.getByText("问题 1.1", { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("输入你的回答…")).toHaveCount(0);
    const link = page.getByRole("link", { name: "继续模拟", exact: true });
    if (!completion)
      await expect(link).toHaveAttribute("href", `${root}/interview/mock?session=${session}`);
    else await expect(link).toHaveCount(0);
    await evidence(page, info, `history-${completion || "unfinished"}`);
    if (completion) {
      await page.goto(`${root}/interview/mock?session=${session}`);
      await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "开始新的模拟面试", exact: true })).toHaveCount(
        0,
      );
      await evidence(page, info, `completed-${completion}`);
    }
  });

test("answer remains an input until persistence confirms it, then loading stays below the saved answer", async ({
  page,
}, info) => {
  const data = record();
  let save!: () => void, finish!: () => void;
  const saving = new Promise<void>((r) => {
      save = r;
    }),
    generating = new Promise<void>((r) => {
      finish = r;
    });
  await page.route(`**/api/product/mock-interviews/${session}`, (r) => r.fulfill({ json: data }));
  await page.route(`**/api/product/mock-interviews/${session}/answers`, async (r) => {
    await saving;
    data.turns[1].answer = "用户仍能看见这段回答。";
    data.pending_question_id = null;
    data.status = "ready_to_generate";
    data.generation_active = true;
    data.revision++;
    await generating;
    await r.fulfill({ json: data });
  });
  await page.goto(`${root}/interview/mock?session=${session}`);
  const input = page.getByPlaceholder("输入你的回答…");
  await input.fill("用户仍能看见这段回答。");
  await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
  try {
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("用户仍能看见这段回答。");
    await expect(
      page.locator(`[data-question-id="${followup}"]`).getByText("我的回答", { exact: true }),
    ).toHaveCount(0);
    save();
    const current = page.locator(`[data-question-id="${followup}"]`);
    await expect(current.getByText("我的回答", { exact: true })).toBeVisible();
    await expect(current.getByText("用户仍能看见这段回答。", { exact: true })).toBeVisible();
    await expect(current.getByRole("status")).toHaveText("正在准备下一道问题…");
    await expect(input).toHaveCount(0);
    await evidence(page, info, "saved-answer-generating");
  } finally {
    save();
    finish();
  }
});

test("home and unfinished sessions share accepted typography across viewports", async ({
  page,
}, info) => {
  await page.route("**/api/product/mock-interviews?*", (r) =>
    r.fulfill({
      json: {
        items: [
          {
            ...record(),
            created_at: time(),
            display_number: 2,
            focus: "technical",
            policy: { mode: "quick", primary_target: 3, followup_max: 1 },
          },
        ],
        offset: 0,
        limit: 100,
        has_more: false,
      },
    }),
  );
  await page.goto(root + "/interview/mock");
  const heading = page.getByRole("heading", { name: "模拟面试", exact: true });
  await expect(heading).toHaveCSS("font-size", "24px");
  await expect(heading).toHaveCSS("font-weight", "600");
  await expect(heading).toHaveCSS("line-height", "32px");
  const toggle = page.getByRole("button", { name: "继续未完成的模拟面试（1）", exact: true });
  await expect(toggle).toHaveCSS("font-size", "16px");
  await evidence(page, info, "home-collapsed");
  await toggle.click();
  const name = page.getByText("第 2 次模拟面试", { exact: true });
  await expect(name).toHaveCSS("font-size", "16px");
  await expect(name).toHaveCSS("font-weight", "600");
  const progress = page.getByText(/技术 · 快速 · 主问题 1/);
  await expect(progress).toHaveCSS("font-size", "16px");
  await expect(progress).toHaveCSS("line-height", "26px");
  await expect(page.getByRole("link", { name: "继续模拟", exact: true })).toHaveCSS(
    "font-size",
    "16px",
  );
  const roles = await page
    .locator("main h1, main label, main select, main button, main p, main a")
    .evaluateAll((nodes) =>
      nodes.map((n) => {
        const s = getComputedStyle(n);
        return {
          text: n.textContent?.slice(0, 60),
          size: s.fontSize,
          weight: s.fontWeight,
          line: s.lineHeight,
        };
      }),
    );
  await writeFile(info.outputPath("home-roles.json"), JSON.stringify(roles, null, 2));
  await evidence(page, info, "home-expanded");
  await page.getByLabel("问题数量模式", { exact: true }).selectOption("custom");
  await expect(page.getByLabel("主问题数量", { exact: true })).toHaveCSS("font-size", "16px");
  await evidence(page, info, "home-custom");
});

test("confirmed completion cannot show next-question loading while its response is delayed", async ({
  page,
}) => {
  const data = record();
  let finish!: () => void;
  const responseGate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route(`**/api/product/mock-interviews/${session}`, (r) => r.fulfill({ json: data }));
  await page.route(`**/api/product/mock-interviews/${session}/answers`, async (r) => {
    data.turns[1].answer = "最后的回答。";
    data.pending_question_id = null;
    data.status = "completed";
    data.completion_type = "target_reached";
    data.revision++;
    await responseGate;
    await r.fulfill({ json: data });
  });
  await page.goto(`${root}/interview/mock?session=${session}`);
  await page.getByPlaceholder("输入你的回答…").fill("最后的回答。");
  await page.getByRole("button", { name: "提交回答并继续", exact: true }).click();
  try {
    await expect(page.getByText("模拟面试已完成", { exact: true })).toBeVisible();
    await expect(page.getByText("最后的回答。", { exact: true })).toBeVisible();
    await expect(page.getByRole("status")).toHaveCount(0);
    await expect(page.getByPlaceholder("输入你的回答…")).toHaveCount(0);
  } finally {
    finish();
  }
});
