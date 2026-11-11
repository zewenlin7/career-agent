import { writeFile } from "node:fs/promises";
import { test, expect, type Page, type APIRequestContext, type TestInfo } from "@playwright/test";
const base = "http://127.0.0.1:3131/api/v1";
test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:3131/__reset");
});
async function expectCompleted(page: Page) {
  await expect
    .poll(
      async () => {
        const id =
          new URL(page.url()).searchParams.get("debrief") ||
          new URL(page.url()).searchParams.get("task");
        if (!id) return null;
        const row = await (
          await page.request.get(`${base}/interview-debriefs/${id}?historical=true`)
        ).json();
        return row.status;
      },
      { timeout: 20000 },
    )
    .toBe("completed");
  await expect(page.getByText("正在生成复盘…", { exact: true })).toHaveCount(0);
  await expect(
    page
      .getByLabel("复盘执行状态")
      .getByText(/尚无已保存分析|题组.*已保存|综合复盘已保存|复盘已完成/),
  ).toHaveCount(0);
  await expect(page.locator("[data-result-destination]").last()).toBeVisible();
}
async function seed(request: APIRequestContext) {
  const job = await (
    await request.post(`${base}/jobs`, {
      data: { company_name: "复盘合成公司", title: "工程师", jd_text: "测试可靠执行" },
    })
  ).json();
  const primary = crypto.randomUUID(),
    follow = crypto.randomUUID(),
    second = crypto.randomUUID();
  const entries = [
    {
      entry_id: primary,
      order: 1,
      kind: "primary",
      question: "如何验证事务与并发？",
      answer: "用隔离数据库验证提交和回滚。",
    },
    {
      entry_id: follow,
      order: 2,
      kind: "follow_up",
      primary_entry_id: primary,
      question: "并发保存怎样避免覆盖？",
      answer: "使用行锁与 revision CAS。",
    },
    {
      entry_id: second,
      order: 3,
      kind: "primary",
      question: "主",
      answer: "保留原始内容。https://example.invalid/" + "long".repeat(50),
    },
  ];
  const response = await request.post(`${base}/interviews`, {
    data: {
      request_id: crypto.randomUUID(),
      application_id: job.application_id,
      round_number: 1,
      interview_type: "technical",
      entries,
      notes_text: "合成笔记\n第二行",
      status: "completed",
    },
  });
  expect(response.status()).toBe(201);
  return {
    job,
    source: await response.json(),
    primary,
    follow,
    second,
    root: `/applications/${job.application_id}`,
  };
}
async function snapshot(page: Page, info: TestInfo, name: string) {
  const styles = [];
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole("heading", { level: 1 }).last()).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    styles.push(
      await page.locator("main").evaluate(
        (node, width) => ({
          width,
          texts: [...node.querySelectorAll("h1,h2,h3,p,label,select,option,button")].map((e) => {
            const s = getComputedStyle(e);
            return {
              text: e.textContent?.slice(0, 80),
              fontSize: s.fontSize,
              fontWeight: s.fontWeight,
              lineHeight: s.lineHeight,
            };
          }),
        }),
        width,
      ),
    );
    const title = page.getByRole("heading", { level: 1 }).last();
    expect(
      await title.evaluate((el) => {
        const s = getComputedStyle(el);
        return [s.fontSize, s.fontWeight, s.lineHeight];
      }),
    ).toEqual(["24px", "600", "32px"]);
    await page.screenshot({ path: info.outputPath(`${name}-${width}.png`), fullPage: true });
  }
  await writeFile(info.outputPath(`${name}-computed.json`), JSON.stringify(styles, null, 2));
}
test("review selects groups, keeps whole overall, freezes evidence, creates independent analyses and deletes exact result", async ({
  page,
  request,
}, info) => {
  const { root, source, primary, follow, second } = await seed(request);
  const writes: Record<string, unknown>[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/interview-debriefs"))
      writes.push(r.postDataJSON());
  });
  await page.goto(`${root}/review/debriefs`);
  const select = page.getByLabel("面试记录", { exact: true });
  await select.selectOption(`actual:${source.id}`);
  await expect(page.getByRole("button", { name: "开始复盘", exact: true })).toBeEnabled();
  await select.selectOption("");
  await expect(page.getByRole("button", { name: "开始复盘", exact: true })).toBeDisabled();
  await select.selectOption(`actual:${source.id}`);
  await page.getByLabel("逐题范围", { exact: true }).selectOption("selected");
  await expect(
    page.getByRole("checkbox", { name: "问题 1 · 如何验证事务与并发？", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "选择题组", exact: true }).click();
  await expect(page.getByText("含 1 个追问", { exact: true })).toBeVisible();
  const joined = await page.locator("#review-group-options").evaluate((el) => ({
    top: el.getBoundingClientRect().top,
    buttonBottom: el.previousElementSibling!.getBoundingClientRect().bottom,
  }));
  expect(Math.abs(joined.top - joined.buttonBottom)).toBeLessThanOrEqual(1);
  await page.getByRole("checkbox", { name: "问题 1 · 如何验证事务与并发？", exact: true }).check();
  await page.getByText("查看完整题组", { exact: true }).first().click();
  await expect(page.getByText("问题 1.1：并发保存怎样避免覆盖？", { exact: true })).toBeVisible();
  await snapshot(page, info, "review-group-expanded");
  await page.getByRole("button", { name: "已选 1 组 · 问题1", exact: true }).click();
  await snapshot(page, info, "review-group-collapsed");
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  const result = page.locator("[data-result-destination]");
  await expect(result.getByRole("heading", { name: "综合复盘", exact: true })).toBeVisible();
  await expect(page.getByLabel("复盘记录", { exact: true }).locator("option")).toHaveCount(2);
  expect(writes[0]).toMatchObject({
    primary_entry_ids: [primary],
    question_analysis: "selected",
    overall_analysis: true,
  });
  const id = await result.getAttribute("data-result-destination");
  const saved = await (
    await request.get(`${base}/interview-debriefs/${id}?historical=true`)
  ).json();
  expect(saved.snapshot.entries).toHaveLength(3);
  expect(saved.artifacts.map((a: { group_ref: string }) => a.group_ref)).toEqual([primary, null]);
  expect(saved.usage.model_calls).toBe(2);
  expect(
    await result
      .locator("article li > span")
      .first()
      .evaluate((el) => {
        const s = getComputedStyle(el);
        return [s.fontSize, s.fontWeight, s.lineHeight];
      }),
  ).toEqual(["16px", "400", "26px"]);
  await snapshot(page, info, "review-analysis");
  await expect(result.locator("details")).not.toHaveAttribute("open", "");
  await result.getByRole("button", { name: "1", exact: true }).first().click();
  await expect(result.locator("details")).toHaveAttribute("open", "");
  await result.getByRole("button", { name: "1.1", exact: true }).first().click();
  await expect(result.locator(`[id="frozen-${id}-${follow}"]`)).toBeFocused();
  await expect(result.getByRole("heading", { name: "笔记", exact: true })).toBeVisible();
  await expect(result.getByText("主", { exact: true })).toBeVisible();
  await snapshot(page, info, "review-frozen");
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expectCompleted(page);
  await expect(page.getByLabel("复盘记录", { exact: true })).not.toHaveValue(id!);
  const secondId = await page.getByLabel("复盘记录", { exact: true }).inputValue();
  expect(secondId).toBeTruthy();
  expect(writes[0].request_id).not.toBe(writes[1].request_id);
  expect(
    (await (await request.get(`${base}/interview-debriefs/${secondId}?historical=true`)).json())
      .usage.model_calls,
  ).toBe(2);
  expect(
    (await (await request.get(`${base}/interview-debriefs/${id}?historical=true`)).json()).usage
      .model_calls,
  ).toBe(2);
  // Selecting history must not replace the independent input form.
  await select.selectOption("");
  await page.getByLabel("复盘记录", { exact: true }).selectOption(id!);
  await expect(page).toHaveURL(new RegExp(`debrief=${id}`));
  await expect(select).toHaveValue("");
  await expect(page.getByRole("button", { name: "开始复盘", exact: true })).toBeDisabled();
  const updated = await request.patch(`${base}/interviews/${source.id}`, {
    data: {
      expected_revision: source.content_revision,
      entries: source.entries.map((e: { entry_id: string }) =>
        e.entry_id === second ? { ...e, answer: "已修改" } : e,
      ),
    },
  });
  expect(updated.status()).toBe(200);
  await page.reload();
  await expect(page.getByText("这场面试记录已修改，当前复盘仍基于修改前的内容。")).toBeVisible();
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByLabel("复盘记录", { exact: true })).toHaveValue(secondId);
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByText("还没有复盘记录。")).toBeVisible();
  expect((await request.get(`${base}/interview-debriefs/${id}?historical=true`)).status()).toBe(
    410,
  );
});

test("notes shared editor preserves identity, cancellation, real modified time and Chinese content", async ({
  page,
  request,
}, info) => {
  const { root, job } = await seed(request);
  await page.goto(`${root}/review/knowledge-notes`);
  await expect(page.getByText("还没有笔记", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "新增笔记", exact: true }).click();
  await page.getByPlaceholder("输入笔记标题").fill("中文笔记");
  const body = "第一行\n第二行\nhttps://example.invalid/" + "long".repeat(60);
  await page.getByPlaceholder("输入笔记内容").fill(body);
  await snapshot(page, info, "notes-editor");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByPlaceholder("输入笔记内容")).toHaveValue(body);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: "中文笔记", exact: true })).toBeVisible();
  const rows = async () =>
    (await (await request.get(`${base}/applications/${job.application_id}/knowledge-notes`)).json())
      .items;
  const first = (await rows())[0];
  await page.getByRole("button", { name: "管理笔记：中文笔记", exact: true }).click();
  await page.getByRole("menuitem", { name: "编辑", exact: true }).click();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: "中文笔记", exact: true })).toBeVisible();
  expect((await rows())[0]).toMatchObject({
    id: first.id,
    revision: first.revision,
    updated_at: first.updated_at,
  });
  await page.getByRole("button", { name: "管理笔记：中文笔记", exact: true }).click();
  await page.getByRole("menuitem", { name: "编辑", exact: true }).click();
  await page.getByPlaceholder("输入笔记标题").fill("修改笔记");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: "修改笔记", exact: true })).toBeVisible();
  expect((await rows())[0]).toMatchObject({ id: first.id, revision: first.revision + 1 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "修改笔记", exact: true })).toBeVisible();
  expect(
    await page
      .locator("article[data-note-id] > p")
      .last()
      .evaluate((el) => {
        const s = getComputedStyle(el);
        return [s.fontSize, s.fontWeight, s.lineHeight];
      }),
  ).toEqual(["16px", "400", "26px"]);
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    const article = page.locator("article[data-note-id]").first();
    const bounds = await article.evaluate((el) => [
      el.getBoundingClientRect().right,
      el.parentElement!.parentElement!.getBoundingClientRect().right,
      el.querySelector("button")!.getBoundingClientRect().right,
    ]);
    expect(Math.abs(bounds[0] - bounds[1])).toBeLessThanOrEqual(1);
    expect(Math.abs(bounds[0] - bounds[2])).toBeLessThanOrEqual(1);
  }
  await snapshot(page, info, "notes-list");
  await page.getByRole("button", { name: "管理笔记：修改笔记", exact: true }).click();
  await page.getByRole("menuitem", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByText("还没有笔记", { exact: true })).toBeVisible();
});

test("delayed execution navigates to exact persisted result via notification without duplicate calls", async ({
  page,
  request,
}) => {
  const { root, source } = await seed(request);
  await request.post("http://127.0.0.1:3131/__provider/hold");
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).entered,
    )
    .toBe(true);
  await page.getByRole("button", { name: "复盘", exact: true }).click();
  await page.getByRole("menuitem", { name: "求职笔记", exact: true }).click();
  await expect(page).toHaveURL(`${root}/review/knowledge-notes`);
  await request.post("http://127.0.0.1:3131/__provider/release");
  await expect(page.getByRole("link", { name: "查看结果", exact: true })).toBeVisible({
    timeout: 20000,
  });
  await page.getByRole("link", { name: "查看结果", exact: true }).click();
  await expect(page).toHaveURL(/review\/debriefs\?.*debrief=/);
  await expect(page.getByRole("heading", { name: "综合复盘", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "综合复盘", exact: true })).toBeVisible();
  const calls = (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls;
  expect(calls).toEqual(["interview_overall_debrief"]);
});

for (const fault of ["invalid_group", "invalid_evidence", "save_failed", "unknown"] as const) {
  test(`review ${fault} uses exact failed task and preserves saved targets`, async ({
    page,
    request,
  }) => {
    const { root, source } = await seed(request);
    await request.post(`http://127.0.0.1:3131/__provider/review-fault?kind=${fault}`);
    await page.goto(`${root}/review/debriefs`);
    await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
    await page.getByRole("button", { name: "开始复盘", exact: true }).click();
    const status = page.getByLabel("复盘执行状态", { exact: true });
    if (fault === "unknown") {
      await expect(status.getByText(/结果尚未确认/).first()).toBeVisible({ timeout: 20000 });
      await expect(status.getByRole("button", { name: "重试失败项", exact: true })).toHaveCount(0);
      const before = (await (await request.get("http://127.0.0.1:3131/__provider/status")).json())
        .calls;
      await status.getByRole("button", { name: "检查状态", exact: true }).click();
      await expect(status.getByText("状态未变化，尚未确认的执行不会自动重试。")).toBeVisible();
      await page.reload();
      await expect(status.getByRole("button", { name: "重试失败项", exact: true })).toHaveCount(0);
      expect(
        (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls,
      ).toEqual(before);
    } else {
      const retry = status.getByRole("button", { name: "重试失败项", exact: true });
      await expect(retry).toBeVisible({ timeout: 20000 });
      await expect(status.getByRole("button", { name: "检查状态", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: /未处理通知/ })).toHaveCount(0);
      const before = (await (await request.get("http://127.0.0.1:3131/__provider/status")).json())
        .calls.length;
      await request.post("http://127.0.0.1:3131/__provider/review-fault?kind=none");
      await page.getByLabel("面试记录", { exact: true }).selectOption("");
      await retry.click();
      await expectCompleted(page);
      expect(
        (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.length,
      ).toBe(before + (fault === "save_failed" ? 0 : fault === "invalid_evidence" ? 1 : 2));
      await expect(page.getByLabel("面试记录", { exact: true })).toHaveValue("");
      await expect(page.getByLabel("复盘记录", { exact: true }).locator("option")).toHaveCount(2);
      const single = page.getByRole("article", { name: "第 2 题组", exact: true });
      await expect(single.getByText("依据：", { exact: false })).toHaveCount(0);
      await expect(single.getByRole("button", { name: "查看原始问答", exact: true })).toBeVisible();
    }
  });
}

test("hard refresh during a provider call preserves the task without automatic redispatch", async ({
  page,
  request,
}) => {
  const { root, source } = await seed(request);
  await request.post("http://127.0.0.1:3131/__provider/hold");
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.length,
    )
    .toBe(1);
  await page.reload();
  await request.post("http://127.0.0.1:3131/__provider/release");
  const status = page.getByLabel("复盘执行状态", { exact: true });
  await expect(status.getByRole("button", { name: "检查状态", exact: true })).toBeVisible();
  await status.getByRole("button", { name: "检查状态", exact: true }).click();
  await expect(status.getByText(/结果尚未确认/).first()).toBeVisible();
  await expect(status.getByRole("button", { name: "重试失败项", exact: true })).toHaveCount(0);
  expect(
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.length,
  ).toBe(1);
});

test("lost note response reuses one persistent identity and CAS conflict preserves editor input", async ({
  page,
  request,
}) => {
  const { root, job } = await seed(request);
  let lose = true;
  await page.route("**/api/product/knowledge-notes", async (route) => {
    if (route.request().method() === "POST" && lose) {
      lose = false;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByRole("button", { name: "新增笔记", exact: true }).click();
  await page.getByPlaceholder("输入笔记标题").fill("只保存一次");
  await page.getByPlaceholder("输入笔记内容").fill("保留输入");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: /./ })).toBeVisible();
  await expect(page.getByPlaceholder("输入笔记内容")).toHaveValue("保留输入");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: "只保存一次", exact: true })).toBeVisible();
  const rows = await (
    await request.get(`${base}/applications/${job.application_id}/knowledge-notes`)
  ).json();
  expect(rows.items).toHaveLength(1);
  const note = rows.items[0];
  await page.getByRole("button", { name: "管理笔记：只保存一次", exact: true }).click();
  await page.getByRole("menuitem", { name: "编辑", exact: true }).click();
  await page.getByPlaceholder("输入笔记内容").fill("当前未保存输入");
  const concurrent = await request.patch(`${base}/knowledge-notes/${note.id}`, {
    data: {
      application_id: job.application_id,
      expected_revision: note.revision,
      title: note.title,
      content: "另一窗口修改",
    },
  });
  expect(concurrent.status()).toBe(200);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    page.getByText("记录已变化或请求冲突。请重新读取后核对，未自动重试。"),
  ).toBeVisible();
  await expect(page.getByPlaceholder("输入笔记内容")).toHaveValue("当前未保存输入");
  expect(
    (await (await request.get(`${base}/applications/${job.application_id}/knowledge-notes`)).json())
      .items[0].content,
  ).toBe("另一窗口修改");
});

test("lost review create response resumes the original generation before any execution", async ({
  page,
  request,
}) => {
  const { root, source, job } = await seed(request);
  let lose = true;
  await page.route("**/api/product/interview-debriefs", async (route) => {
    if (route.request().method() === "POST" && lose) {
      lose = false;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: /./ })).toBeVisible();
  expect(
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls,
  ).toEqual([]);
  const original = (
    await (
      await request.get(`${base}/interview-debriefs?application_id=${job.application_id}`)
    ).json()
  ).items[0];
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect(page.getByRole("heading", { name: "综合复盘", exact: true })).toBeVisible();
  await expect(page.locator(`[data-result-destination="${original.generation_id}"]`)).toBeVisible();
  const rows = (
    await (
      await request.get(`${base}/interview-debriefs?application_id=${job.application_id}`)
    ).json()
  ).items;
  expect(rows).toHaveLength(1);
  expect(
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls,
  ).toEqual(["interview_overall_debrief"]);
});

test("Debrief foreground terminal feedback stays inline; background produces one exact notice", async ({
  page,
  request,
}, info) => {
  const { root, source } = await seed(request);
  await request.post("http://127.0.0.1:3131/__provider/hold");
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect(page.getByLabel("复盘执行状态")).toContainText("正在生成复盘");
  await expect(page.getByLabel("复盘执行状态")).toHaveText("正在生成复盘…");
  await snapshot(page, info, "review-generating");
  await request.post("http://127.0.0.1:3131/__provider/release");
  await expectCompleted(page);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const tasks = JSON.parse(localStorage.getItem("career-task-handles-v1") || "[]");
        return tasks.filter(
          (t: { notice?: { state: string }; dismissedState?: string }) =>
            t.notice && t.notice.state !== t.dismissedState,
        ).length;
      }),
    )
    .toBe(0);
  await snapshot(page, info, "review-feedback");
  // A different scope creates another exact generation; leaving visibility must notify.
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await request.post("http://127.0.0.1:3131/__provider/hold");
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect(page.getByLabel("复盘执行状态")).toContainText("正在生成复盘");
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await request.post("http://127.0.0.1:3131/__provider/release");
  await expect(page.getByRole("button", { name: "未处理通知 1 条", exact: true })).toBeVisible();
  await page.reload();
  await expectCompleted(page);
  await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
});

test("compact groups keep source order, clear hidden selections and show full long questions on demand", async ({
  page,
  request,
}, info) => {
  const { root, source, job } = await seed(request);
  const long =
    "如何在多请求同时提交、响应丢失和重试时保证事务身份、来源引用与执行状态一致？".repeat(8);
  const changed = await request.patch(`${base}/interviews/${source.id}`, {
    data: {
      expected_revision: source.content_revision,
      entries: source.entries.map((e: { kind: string }) =>
        e.kind === "primary" ? { ...e, question: long } : e,
      ),
    },
  });
  expect(changed.status()).toBe(200);
  const other = await (
    await request.post(`${base}/interviews`, {
      data: {
        request_id: crypto.randomUUID(),
        application_id: job.application_id,
        round_number: 2,
        interview_type: "technical",
        status: "completed",
        entries: [
          {
            entry_id: crypto.randomUUID(),
            order: 1,
            kind: "primary",
            question: "另一场问题",
            answer: "另一场回答",
          },
        ],
      },
    })
  ).json();
  await page.goto(`${root}/review/debriefs`);
  const sourceSelect = page.getByLabel("面试记录", { exact: true });
  const scope = page.getByLabel("逐题范围", { exact: true });
  await sourceSelect.selectOption(`actual:${source.id}`);
  await expect(page.getByRole("button", { name: "选择题组", exact: true })).toHaveCount(0);
  await scope.selectOption("selected");
  await expect(page.getByRole("button", { name: "开始复盘", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "选择题组", exact: true }).click();
  const checkboxes = page.locator("#review-group-options input");
  await checkboxes.nth(1).check();
  await checkboxes.nth(0).check();
  await expect(
    page.getByRole("button", { name: "已选 2 组 · 问题1、问题2", exact: true }),
  ).toBeVisible();
  const excerpt = page.locator("#review-group-options .line-clamp-2").first();
  expect(
    await excerpt.evaluate((e) => ({
      clamp: getComputedStyle(e).webkitLineClamp,
      font: getComputedStyle(e).fontSize,
      height: e.clientHeight,
    })),
  ).toEqual({ clamp: "2", font: "16px", height: 52 });
  await snapshot(page, info, "review-long-options");
  await checkboxes.nth(1).uncheck();
  await scope.selectOption("all");
  await scope.selectOption("selected");
  await expect(page.getByRole("button", { name: "选择题组", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "选择题组", exact: true }).click();
  await checkboxes.nth(0).check();
  await sourceSelect.selectOption(`actual:${other.id}`);
  await expect(page.getByRole("button", { name: "选择题组", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始复盘", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await expect(scope).toHaveCount(0);
  const created = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/interview-debriefs"),
  );
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  expect((await created).postDataJSON()).toMatchObject({
    question_analysis: "none",
    interview_id: other.id,
  });
  expect((await created).postDataJSON()).not.toHaveProperty("primary_entry_ids");
  await expectCompleted(page);
});

test("confirmed failed overall keeps previous history visible and retries only explicitly", async ({
  page,
  request,
}, info) => {
  const { root, source, job } = await seed(request);
  const previous = await (
    await request.post(`${base}/interview-debriefs`, {
      data: {
        request_id: crypto.randomUUID(),
        application_id: job.application_id,
        source_kind: "actual",
        interview_id: source.id,
        expected_source_revision: source.content_revision,
        question_analysis: "all",
        overall_analysis: false,
      },
    })
  ).json();
  expect((await request.post(`${base}/interview-debriefs/${previous.id}/execute`)).status()).toBe(
    200,
  );
  await page.goto(`${root}/review/debriefs?debrief=${previous.id}`);
  await expect(page.locator(`[data-result-destination="${previous.id}"]`)).toBeVisible();
  await request.post("http://127.0.0.1:3131/__provider/review-fault?kind=invalid_evidence");
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  const status = page.getByLabel("复盘执行状态", { exact: true });
  await expect(status).toContainText("综合复盘失败：生成内容的问答依据未通过核验。");
  await expect(status.getByRole("button", { name: "重试失败项", exact: true })).toBeVisible();
  await expect(status.getByRole("button", { name: "检查状态", exact: true })).toHaveCount(0);
  await expect(page.locator(`[data-result-destination="${previous.id}"]`)).toBeVisible();
  await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
  await snapshot(page, info, "review-failed-preserves-history");
  const before = (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls
    .length;
  await request.post("http://127.0.0.1:3131/__provider/review-fault?kind=none");
  await status.getByRole("button", { name: "重试失败项", exact: true }).click();
  await expectCompleted(page);
  expect(
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.length,
  ).toBe(before + 1);
});

test("failure actions belong to selected generation and generic navigation is clean", async ({
  page,
  request,
}, info) => {
  const { root, source } = await seed(request);
  await page.goto(`${root}/review/debriefs`);
  await request.post("http://127.0.0.1:3131/__provider/review-fault?kind=invalid_evidence");
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  const status = page.getByLabel("复盘执行状态", { exact: true });
  await expect(status).toContainText("综合复盘失败");
  const id = new URL(page.url()).searchParams.get("debrief")!;
  expect(id).toBeTruthy();
  const calls = (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls
    .length;
  await page.getByLabel("复盘记录", { exact: true }).selectOption("");
  await expect(page.getByRole("button", { name: "重试失败项", exact: true })).toHaveCount(0);
  await page.getByLabel("复盘记录", { exact: true }).selectOption(id);
  await expect(status.getByRole("button", { name: "重试失败项", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "复盘", exact: true }).click();
  await page.getByRole("menuitem", { name: "求职笔记", exact: true }).click();
  await page.getByRole("button", { name: "复盘", exact: true }).click();
  await page.getByRole("menuitem", { name: "面试复盘", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试失败项", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("复盘记录", { exact: true })).toHaveValue("");
  await page.getByLabel("复盘记录", { exact: true }).selectOption(id);
  await expect(page.getByLabel("复盘记录", { exact: true })).toHaveValue(id);
  await expect(page).toHaveURL(new RegExp(`debrief=${id}$`));
  await page.reload();
  await expect(status.getByRole("button", { name: "重试失败项", exact: true })).toBeVisible();
  expect(
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.length,
  ).toBe(calls);
  await snapshot(page, info, "selected-partial-feedback");
  await request.post("http://127.0.0.1:3131/__provider/review-fault?kind=none");
  await status.getByRole("button", { name: "重试失败项", exact: true }).click();
  await expectCompleted(page);
  expect(
    (await (await request.get("http://127.0.0.1:3131/__provider/status")).json()).calls.length,
  ).toBe(calls + 1);
  await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
});

test("late completion cannot replace a newer history choice and still notifies once", async ({
  page,
  request,
}) => {
  const { root, source } = await seed(request);
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
  await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expectCompleted(page);
  const first = await page.getByLabel("复盘记录", { exact: true }).inputValue();
  await request.post("http://127.0.0.1:3131/__provider/hold");
  await page.getByRole("button", { name: "开始复盘", exact: true }).click();
  await expect(page.getByLabel("复盘执行状态")).toContainText("正在生成复盘");
  const active = new URL(page.url()).searchParams.get("task");
  expect(active).not.toBe(first);
  await page.getByLabel("复盘记录", { exact: true }).selectOption("");
  await page.getByLabel("复盘记录", { exact: true }).selectOption(first);
  await request.post("http://127.0.0.1:3131/__provider/release");
  await expect(page.getByRole("button", { name: "未处理通知 1 条", exact: true })).toBeVisible();
  await expect(page.getByLabel("复盘记录", { exact: true })).toHaveValue(first);
  await expect(page).toHaveURL(new RegExp(`debrief=${first}$`));
  await expectCompleted(page);
  const row = await (
    await request.get(`${base}/interview-debriefs/${active}?historical=true`)
  ).json();
  expect(row.status).toBe("completed");
  expect(row.usage.model_calls).toBe(1);
});

for (const outcome of ["partial", "failure", "unknown"] as const) {
  for (const location of ["away", "background"] as const) {
    test(`Debrief ${outcome} ${location} notice is exact and stays handled`, async ({
      page,
      request,
    }) => {
      const { root, source } = await seed(request);
      await request.post(
        `http://127.0.0.1:3131/__provider/review-fault?kind=${outcome === "unknown" ? "unknown" : "invalid_evidence"}`,
      );
      await request.post("http://127.0.0.1:3131/__provider/hold");
      await page.goto(`${root}/review/debriefs`);
      await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${source.id}`);
      if (outcome !== "partial")
        await page.getByRole("checkbox", { name: "逐题分析", exact: true }).uncheck();
      await page.getByRole("button", { name: "开始复盘", exact: true }).click();
      await expect(page.getByLabel("复盘执行状态")).toContainText("正在生成复盘");
      const id = new URL(page.url()).searchParams.get("task")!;
      if (location === "away") {
        await page.getByRole("button", { name: "复盘", exact: true }).click();
        await page.getByRole("menuitem", { name: "求职笔记", exact: true }).click();
      } else
        await page.evaluate(() => {
          Object.defineProperty(document, "visibilityState", {
            configurable: true,
            get: () => "hidden",
          });
          document.dispatchEvent(new Event("visibilitychange"));
        });
      await request.post("http://127.0.0.1:3131/__provider/release");
      await expect(
        page.getByRole("button", { name: "未处理通知 1 条", exact: true }),
      ).toBeVisible();
      await expect
        .poll(() =>
          page.evaluate((id) => {
            const rows = JSON.parse(localStorage.getItem("career-task-handles-v1") || "[]");
            return rows
              .filter((r: { id: string }) => r.id === id)
              .map((r: { notice?: { state: string } }) => r.notice?.state);
          }, id),
        )
        .toEqual([outcome]);
      await page.goto(`${root}/review/debriefs?debrief=${id}`);
      await expect(
        page.getByLabel("复盘执行状态").getByRole("button", {
          name: outcome === "unknown" ? "检查状态" : "重试失败项",
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.getByRole("button", { name: "未处理通知 1 条", exact: true })).toHaveCount(
        0,
      );
      await page.reload();
      await expect(page.getByLabel("复盘记录", { exact: true })).toHaveValue(id);
      await expect(page.getByRole("button", { name: "未处理通知 1 条", exact: true })).toHaveCount(
        0,
      );
      const row = await (
        await request.get(`${base}/interview-debriefs/${id}?historical=true`)
      ).json();
      expect(row.usage.model_calls).toBe(outcome === "partial" ? 3 : 1);
    });
  }
}
