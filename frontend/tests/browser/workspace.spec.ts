import { test, expect, type Page } from "@playwright/test";
import { id, application, job, summaryFixture } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
async function bindings(page: Page) {
  await expect(page.getByLabel("个人资料版本")).toHaveCount(0);
}
async function execute(page: Page) {
  const button = page.getByRole("button", { name: /^(开始优化|生成|开始面试准备)$/ });
  const optimizing = (await button.textContent()) === "开始优化";
  await button.click();
  const cancel = page.getByRole("button", { name: "取消替换", exact: true });
  if (optimizing || (await cancel.isVisible())) await cancel.click();
  await expect(button).toBeEnabled();
}
test("Company current/history is company-scoped; Fit has explicit operation and no-evidence semantics", async ({
  page,
  request,
}) => {
  const researchBodies: Record<string, unknown>[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith(`/api/product/companies/${id(1001)}/research`))
      researchBodies.push(r.postDataJSON());
  });
  await page.goto(`${root}/research-fit/company`);
  await expect(page.getByText("公司提供数据服务。")).toBeVisible();
  const research = page.getByRole("region", { name: "公司研究", exact: true });
  await expect(research.getByRole("checkbox")).toHaveCount(0);
  await research.getByRole("button", { name: "重新研究", exact: true }).click();
  expect(researchBodies).toHaveLength(1);
  expect(researchBodies[0]).toMatchObject({
    kind: "company_research",
    request: {
      force_research_refresh: true,
      job_revision_id: id(4001),
      mode: "live",
    },
  });
  await page.getByRole("button", { name: "研究与匹配" }).click();
  await page.getByRole("menuitem", { name: "岗位匹配", exact: true }).click();
  const fit = page.getByRole("region", { name: "岗位匹配", exact: true });
  await expect(fit.getByRole("button", { name: "开始匹配", exact: true })).toBeDisabled();
  await fit.getByLabel("简历").selectOption(id(8401));
  await fit.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByText("不确定")).toBeVisible();
  await page.reload();
  await expect(fit.getByLabel("匹配记录")).toBeVisible();
  await expect(fit.getByText("不确定", { exact: true })).toBeVisible();
  const calls = await (await request.get("http://127.0.0.1:3111/__requests")).json();
  expect(calls.every((c: { hasOpsToken: boolean }) => !c.hasOpsToken)).toBe(true);
});
test("Resume exact rendering, Greeting history, Submission CAS and Interview Prep package binding", async ({
  page,
}, info) => {
  await page.goto(`${root}/apply/resume`);
  await bindings(page);
  await execute(page);
  await expect(page.getByText("使用 Python 构建数据服务。").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "保存到简历库", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "简历优化", exact: true })).toHaveCount(1);
  const optimize = page.getByLabel("优化记录", { exact: true });
  await expect(optimize).toHaveCSS("font-weight", "400");
  await expect(optimize.locator("option:checked")).toHaveText("合成简历");
  const selectorBox = await optimize.boundingBox();
  const startBox = await page.getByRole("button", { name: "开始优化", exact: true }).boundingBox();
  expect(startBox!.y).toBeLessThan(selectorBox!.y);
  expect(Math.abs(startBox!.x + startBox!.width / 2 - 640)).toBeLessThan(10);
  await expect(page.getByText("基于「").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("optimization-desktop.png"), fullPage: true });
  await page.goto(`${root}/apply/greeting`);
  await bindings(page);
  await execute(page);
  await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "招呼语", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("招呼语记录", { exact: true })).toHaveCSS("font-weight", "400");
  await page.screenshot({ path: info.outputPath("greeting-desktop.png"), fullPage: true });
  let submitted: Record<string, unknown> | undefined;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith(`/api/product/applications/${id(1)}/submissions`))
      submitted = r.postDataJSON();
  });
  await page.goto(`${root}/apply/submissions`);
  await bindings(page);
  await expect(page.getByRole("button", { name: "记录投递", exact: true })).toBeDisabled();
  await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
  await page.getByRole("button", { name: "记录投递", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "投递已记录" })).toBeVisible();
  expect(submitted).toMatchObject({
    expected_revision: 2,
    resume_revision_id: id(8401),
    render_artifact_id: id(8501),
  });
  const duplicate = await page.evaluate(
    async ({ path, body }) => {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return { status: response.status, body: await response.json() };
    },
    { path: `/api/product/applications/${id(1)}/submissions`, body: submitted },
  );
  expect(duplicate.status).toBe(200);
  await expect(page.getByRole("button", { name: "记录投递", exact: true })).toBeDisabled();
  await page.goto(`${root}/interview/preparation`);
  await expect(page.getByLabel("使用哪次简历准备结果")).toHaveCount(0);
  await execute(page);
  await expect(page.getByText("团队如何合作？")).toBeVisible();
  await expect(page.getByLabel("准备记录", { exact: true })).toHaveCSS("font-weight", "400");
  await page.screenshot({ path: info.outputPath("interview-prep-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("interview-prep-mobile.png"), fullPage: true });
});
test("Mock immutable answer, failure preservation, generation-only retry, early end and discovery", async ({
  page,
}) => {
  await page.goto(`${root}/interview/mock`);
  await page.getByLabel("练习重点", { exact: true }).selectOption("technical");
  await bindings(page);
  await page.getByRole("button", { name: "开始模拟面试", exact: true }).click();
  await expect(page.getByText("请介绍你的 Python 项目。")).toBeVisible();
  await page.getByLabel("本题回答").fill("我使用 Python 编写了数据服务。");
  await page.getByRole("button", { name: "提交回答并继续" }).click();
  await expect(page.getByText("我使用 Python 编写了数据服务。")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试生成", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "重试生成", exact: true }).click();
  await page.getByRole("button", { name: "提前结束", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByText("模拟面试已完成")).toBeVisible();
  await page.goto(`${root}/interview/history`);
  await page.getByLabel("面试记录", { exact: true }).selectOption({ index: 1 });
  await expect(page.getByText("我使用 Python 编写了数据服务。")).toBeVisible();
});
test("Actual intake primary/follow-up/correction/notes and Application Knowledge Notes", async ({
  page,
}, info) => {
  await page.goto(`${root}/interview/actual`);
  await expect(page.getByLabel("轮次", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "新增记录", exact: true }).click();
  await page.getByLabel("轮次", { exact: true }).fill("2");
  await page.getByLabel("面试类型", { exact: true }).selectOption("technical");
  await page.getByLabel("面试时间", { exact: true }).fill("2026-11-01 09:30");
  await page.getByRole("button", { name: "选择面试日期时间", exact: true }).click();
  await page.getByRole("button", { name: "2026年11月17日", exact: true }).click();
  await expect(page.getByLabel("面试时间", { exact: true })).toHaveValue("2026-11-17 09:30");
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByLabel("问题1", { exact: true }).fill("介绍项目");
  await page.getByLabel("回答", { exact: true }).first().fill("实现 Python 数据服务");
  await page.getByRole("button", { name: "添加追问", exact: true }).first().click();
  await page.getByLabel("问题1.1", { exact: true }).fill("如何测试？");
  await page.screenshot({ path: info.outputPath("actual-edit-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("actual-edit-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByLabel("笔记", { exact: true }).fill("待补充测试案例");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page).toHaveURL(/interview\/history\?actual=/);
  await expect(page.getByText("实现 Python 数据服务")).toBeVisible();
  await page.reload();
  await expect(page.getByText("实现 Python 数据服务")).toBeVisible();
  await page.getByRole("link", { name: "编辑记录", exact: true }).click();
  await expect(page.getByLabel("问题1", { exact: true })).toHaveValue("介绍项目");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByText("实现 Python 数据服务")).toBeVisible();
  await page.goto(`${root}/review/knowledge-notes`);
  await page.getByRole("button", { name: "新增笔记", exact: true }).click();
  await page.getByLabel("笔记标题").fill("测试经验");
  await page.getByLabel("笔记内容").fill("补充边界测试。");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("heading", { name: "测试经验" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("补充边界测试。")).toBeVisible();
});
test("Debrief POST SSE preserves display order and exact historical generation", async ({
  page,
}, info) => {
  await page.goto(`${root}/review/debriefs`);
  await page.getByLabel("面试记录", { exact: true }).selectOption(`actual:${id(8701)}`);
  await page.getByRole("button", { name: "开始复盘" }).click();
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.locator("[data-result-destination] details summary").click();
  await expect(page.getByText("如何验证？", { exact: true })).toBeVisible();
  const headings = await page.locator("article h2:visible").allTextContents();
  expect(headings).toEqual(["第 1 题组", "综合复盘"]);
  await expect(page.getByRole("button", { name: "重新生成复盘", exact: true })).toHaveCount(0);
  await page.getByLabel("复盘记录", { exact: true }).selectOption({ index: 1 });
  await expect(page.getByText("回答具有具体依据")).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("debrief-mobile.png"), fullPage: true });
});
test("Product BFF rejects cross-origin writes and Internal access", async ({ request }) => {
  expect(
    (
      await request.post("/api/product/operations", {
        data: {},
        headers: { Origin: "https://evil.example" },
      })
    ).status(),
  ).toBe(403);
  expect((await request.get("/api/product/ops/metrics")).status()).toBe(422);
});

test("needs-input, decision, partial and recovery outcomes never become successful execution", async ({
  page,
}) => {
  for (const [status] of [
    ["needs_input", "需要补充输入"],
    ["decision_required", "需要用户决定"],
    ["partial", "部分完成"],
    ["failure", "失败"],
    ["recovery_required", "需要人工恢复"],
  ]) {
    await page.goto(`${root}/apply/greeting`);
    await bindings(page);
    let dispatched = 0;
    await page.route("**/api/product/operations/*/execute", async (route) => {
      dispatched++;
      const operationId = route.request().url().split("/").at(-2);
      await route.fulfill({
        json: {
          id: operationId,
          request_id: id(91),
          kind: "prepare_application",
          status,
          reason:
            status === "recovery_required" ? "recovery_decision_required" : "context_required",
          package_id: null,
          research_report_id: null,
          run_id: id(92),
          created_at: "2026-10-24T00:00:00Z",
          allowed_actions: status === "recovery_required" ? ["inspect_recovery"] : ["read"],
        },
      });
    });
    await page.getByRole("button", { name: "生成", exact: true }).click();
    await expect.poll(() => dispatched).toBe(1);
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "执行操作", exact: true })).toHaveCount(0);
    expect(dispatched).toBe(1);
    await page.unroute("**/api/product/operations/*/execute");
  }
});

test("Actual CAS conflict preserves draft and performs no automatic mutation retry", async ({
  page,
}) => {
  await page.goto(`${root}/interview/actual?actual=${id(8701)}`);
  let calls = 0;
  await page.route("**/api/product/interviews/*", async (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    calls++;
    expect(route.request().postDataJSON().expected_revision).toBe(2);
    await route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } });
  });
  await page.getByLabel("问题1", { exact: true }).fill("尚未保存的问题");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "记录已变化" })).toBeVisible();
  await expect(page.getByLabel("问题1", { exact: true })).toHaveValue("尚未保存的问题");
  expect(calls).toBe(1);
});

test("Product default views hide internal ids and developer controls at 375px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const route of [
    "research-fit",
    "apply/resume",
    "apply/greeting",
    "apply/submissions",
    "interview/mock",
    "interview/actual",
    "interview/history",
    "review/debriefs",
    "review/knowledge-notes",
    "summary",
  ]) {
    await page.goto(`${root}/${route}`);
    if (route === "summary")
      await expect(page.getByRole("region", { name: "职位描述", exact: true })).toBeVisible();
    else await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const visible = await page.locator("main").innerText();
    expect(visible).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
    expect(visible).not.toMatch(
      /CAS|expected_revision|fact_refs|operation_id|fixture|current pointer|技术详情|查看关联标识|开发与测试设置|准备结果与历史/,
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole("button", { name: "创建操作", exact: true })).toHaveCount(0);
    await expect(page.getByRole("combobox", { name: "测试模式" })).not.toBeVisible();
  }
});

test("exact result navigation does not choose a newer result or generate", async ({
  page,
  request,
}) => {
  await page.goto(`${root}/apply/greeting`);
  await execute(page);
  const first = await (
    await request.get(
      `http://127.0.0.1:3111/api/v1/applications/${id(1)}/results?target=greeting_generation`,
    )
  ).json();
  const old = first.items[0];
  await execute(page);
  const latest = await (
    await request.get(
      `http://127.0.0.1:3111/api/v1/applications/${id(1)}/results?target=greeting_generation`,
    )
  ).json();
  expect(latest.items).toHaveLength(2);
  await page.goto(`${root}/apply/greeting?result=${old.result.target_artifact_id}`);
  await expect(page.getByLabel("招呼语记录")).toHaveValue(old.result.target_artifact_id);
  await expect(page.getByText("您好，我有 Python 数据服务项目经验，期待交流。")).toBeVisible();
  const before = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
    (r: { method: string }) => r.method !== "GET",
  ).length;
  await page.goto(`${root}/apply/greeting?result=${latest.items[0].result.target_artifact_id}`);
  await expect(page.getByLabel("招呼语记录")).toHaveValue(
    latest.items[0].result.target_artifact_id,
  );
  const after = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
    (r: { method: string }) => r.method !== "GET",
  ).length;
  expect(after).toBe(before);
});

test("five exact result destinations wait for content and yield scrolling to user", async ({
  page,
  request,
}) => {
  const links: { href: string; identity: string }[] = [
    { href: `${root}/research-fit?research=${id(8001)}`, identity: id(8001) },
  ];
  for (const [target, path] of [
    ["fit_analysis", "research-fit"],
    ["resume_tailoring", "apply/resume"],
    ["greeting_generation", "apply/greeting"],
    ["interview_preparation", "interview/preparation"],
  ]) {
    const op = await (
      await request.post("http://127.0.0.1:3111/api/v1/operations", {
        data: {
          request_id: crypto.randomUUID(),
          kind: target === "interview_preparation" ? "prepare_interview" : "prepare_application",
          request: { targets: [target] },
        },
      })
    ).json();
    await request.post(`http://127.0.0.1:3111/api/v1/operations/${op.id}/execute`);
    const history = await (
      await request.get(
        `http://127.0.0.1:3111/api/v1/applications/${id(1)}/results?target=${target}`,
      )
    ).json();
    const identity = history.items[0].result.target_artifact_id;
    links.push({ href: `${root}/${path}?result=${identity}`, identity });
  }
  const beforeReads = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
    (r: { method: string }) => r.method !== "GET",
  ).length;
  for (const link of links) {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const endpoint = link.href.includes("research=")
      ? `**/api/product/companies/*/research/${link.identity}`
      : `**/api/product/preparation-artifacts/${link.identity}/result?*`;
    let requested = false;
    await page.route(endpoint, async (route) => {
      requested = true;
      await gate;
      await route.continue();
    });
    await page.goto(link.href);
    await expect.poll(() => requested).toBe(true);
    release();
    const body = page.locator(`[data-result-destination="${link.identity}"]`);
    await expect(body).toHaveCount(1);
    await expect(body).toBeVisible();
    await expect
      .poll(async () => {
        const rect = await body.boundingBox();
        const viewport = await page.evaluate(() => ({
          y: scrollY,
          max: document.documentElement.scrollHeight - innerHeight,
          height: innerHeight,
        }));
        // Short final results cannot reach the top after the document hits its scroll boundary.
        return (
          Math.abs(rect!.y - 24) < 3 ||
          (Math.abs(viewport.y - viewport.max) < 2 &&
            rect!.y >= 0 &&
            rect!.y + Math.min(rect!.height, 100) < viewport.height)
        );
      })
      .toBe(true);
    const beforeScroll = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, -100);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(beforeScroll);
    await page.unroute(endpoint);
  }
  const afterReads = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
    (r: { method: string }) => r.method !== "GET",
  ).length;
  expect(afterReads).toBe(beforeReads);
});

test("Summary research and prep links position after async reads and repeat navigation", async ({
  page,
  request,
}) => {
  const base = "http://127.0.0.1:3111/api/v1";
  const op = await (
    await request.post(`${base}/operations`, {
      data: { request_id: crypto.randomUUID(), kind: "prepare_interview", request: {} },
    })
  ).json();
  await request.post(`${base}/operations/${op.id}/execute`);
  const history = await (
    await request.get(`${base}/applications/${id(1)}/results?target=interview_preparation`)
  ).json();
  const result = history.items[0].result.target_artifact_id;
  const summary = summaryFixture(application(1), job(1));
  summary.preparation = [
    {
      label: "公司研究",
      kind: "company_research",
      href: `${root}/research-fit?research=${id(8001)}`,
      available: true,
      stale: false,
      created_at: null,
    },
    {
      label: "面试准备",
      kind: "interview_preparation",
      href: `${root}/interview/preparation?result=${result}`,
      available: true,
      stale: false,
      created_at: null,
    },
  ];
  await page.route(`**/api/product/applications/${id(1)}/summary`, (route) =>
    route.fulfill({ json: summary }),
  );
  const mutationCount = async () =>
    (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
      (r: { method: string }) => r.method !== "GET",
    ).length;
  const before = await mutationCount();
  for (const [label, identity] of [
    ["公司研究", id(8001)],
    ["面试准备", result],
  ]) {
    await page.goto(`${root}/summary`);
    for (let visit = 0; visit < 3; visit++) {
      await page
        .getByRole("region", { name: "最新准备结果" })
        .getByRole("link", { name: label, exact: true })
        .click();
      const target = page.locator(`[data-result-destination="${identity}"]`);
      await expect(target).toBeVisible();
      await expect
        .poll(async () => {
          const rect = (await target.boundingBox())!;
          const maxed = await page.evaluate(
            () => Math.abs(scrollY - (document.documentElement.scrollHeight - innerHeight)) < 2,
          );
          return Math.abs(rect.y - 24) < 3 || (maxed && rect.y >= 0 && rect.y < 600);
        })
        .toBe(true);
      const top = await page.evaluate(() => scrollY);
      await page.mouse.wheel(0, -100);
      await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThan(top);
      // A later unrelated layout update must not reclaim scrolling after user intent.
      await page.evaluate(() => {
        const extra = document.createElement("div");
        extra.style.height = "80px";
        document.body.append(extra);
      });
      await expect.poll(() => page.evaluate(() => scrollY)).toBeLessThan(top);
      await page.goBack();
      await expect(page.getByRole("region", { name: "最新准备结果" })).toBeVisible();
    }
  }
  expect(await mutationCount()).toBe(before);
});

test("Mock current question and completed record plus exact Debrief have read-only destinations", async ({
  page,
  request,
}) => {
  const base = "http://127.0.0.1:3111/api/v1";
  let mock = await (
    await request.post(`${base}/mock-interviews`, {
      data: {
        focus: "mixed",
        context: { profile_id: id(8101), job_revision_id: id(4001), resume_revision_id: id(8401) },
      },
    })
  ).json();
  mock = await (
    await request.post(`${base}/mock-interviews/${mock.id}/generate`, {
      data: { expected_revision: mock.revision },
    })
  ).json();
  const before = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).length;
  await page.goto(`${root}/interview/mock?session=${mock.id}`);
  const question = page.locator('[data-current-question="true"]');
  await expect(question).toBeVisible();
  await expect.poll(async () => (await question.boundingBox())!.y).toBeLessThan(600);
  await expect(page.getByLabel("本题回答")).toBeVisible();
  const reads = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).slice(
    before,
  );
  expect(reads.every((r: { method: string }) => r.method === "GET")).toBe(true);
  await request.post(`${base}/mock-interviews/${mock.id}/end`, {
    data: { expected_revision: mock.revision },
  });
  await page.goto(`${root}/interview/history?session=${mock.id}`);
  await expect(page.locator(`[data-result-destination="${mock.id}"]`)).toBeVisible();
  await expect(page.getByText("模拟面试已完成")).toBeInViewport();
  await request.get(`${base}/interviews/${id(8701)}`);
  const debrief = await (
    await request.post(`${base}/interview-debriefs`, { data: { interview_id: id(8701) } })
  ).json();
  await request.post(`${base}/interview-debriefs/${debrief.id}/execute`);
  const count = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).length;
  await page.goto(`${root}/review/debriefs?debrief=${debrief.id}`);
  await expect(page.locator(`[data-result-destination="${debrief.id}"]`)).toBeVisible();
  await expect(page.locator("[data-result-destination] details summary")).toHaveText(
    "查看原始问答",
  );
  await expect(page.locator("[data-result-destination] details")).not.toHaveAttribute("open", "");
  await expect(page.getByRole("heading", { name: "第 1 题组", exact: true })).toBeVisible();
  const after = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).slice(count);
  expect(after.every((r: { method: string }) => r.method === "GET")).toBe(true);
});

test("Apply body typography matches accepted research/Fit and Summary roles at full content width", async ({
  page,
}, info) => {
  const style = async (locator: import("@playwright/test").Locator) =>
    locator.evaluate((el) => ({
      size: getComputedStyle(el).fontSize,
      weight: getComputedStyle(el).fontWeight,
      line: getComputedStyle(el).lineHeight,
    }));
  await page.goto(`${root}/summary`);
  const summary = await style(page.locator(".summary-body").first());
  await page.goto(`${root}/research-fit/company`);
  const research = await style(page.getByText("公司提供数据服务。", { exact: true }));
  await page.goto(`${root}/research-fit/fit`);
  await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByRole("heading", { name: "不确定", exact: true })).toBeVisible();
  const fit = await style(page.locator("article p.whitespace-pre-wrap").first());
  await page.goto(`${root}/apply/greeting`);
  await execute(page);
  const body = page.getByText("您好，我有 Python 数据服务项目经验，期待交流。", { exact: true });
  expect(await style(body)).toEqual(research);
  expect(await style(body)).toEqual(fit);
  expect((await style(body)).size).toEqual(summary.size);
  expect((await style(body)).weight).toEqual(summary.weight);
  const available = await body.locator("..").boundingBox();
  const content = await body.boundingBox();
  expect(content!.width).toBeGreaterThan(1000);
  expect(Math.abs(available!.width - content!.width)).toBeLessThan(2);
  await page.screenshot({ path: info.outputPath("greeting-full-width.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("greeting-narrow.png"), fullPage: true });
});

test("Interview history loads beyond 100 records and type changes clear selection without execution", async ({
  page,
}) => {
  const requests: number[] = [];
  await page.route("**/api/product/interviews?**", (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("application_id")).toBe(id(1));
    const offset = Number(url.searchParams.get("offset") || 0);
    requests.push(offset);
    return route.fulfill({
      json: Array.from({ length: offset === 0 ? 100 : 1 }, (_, index) => ({
        id: id(90000 + offset + index),
        application_id: id(1),
        round_name: `历史面试${offset + index + 1}`,
        round_number: null,
        interview_type: null,
        occurred_at: null,
        content_revision: 1,
        status: "completed",
        entries: [],
        notes: [],
        context_binding: {},
      })),
    });
  });
  let writes = 0;
  page.on("request", (request) => {
    if (request.method() !== "GET") writes++;
  });
  await page.goto(`${root}/interview/history`);
  await expect(page.getByLabel("记录类型", { exact: true })).toHaveCount(0);
  const records = page.getByLabel("面试记录", { exact: true });
  await expect(records.locator('optgroup[label="真实面试"] option')).toHaveCount(101);
  await expect(records.locator("option").last()).toHaveText("真实面试 · 历史面试101");
  expect(requests).toEqual([0, 100]);
  await expect(records).toHaveValue("");
  await expect(page.getByRole("button", { name: "下一页", exact: true })).toHaveCount(0);
  expect(writes).toBe(0);
});
