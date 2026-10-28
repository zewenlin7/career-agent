import { test, expect } from "@playwright/test";
import { ids } from "../fixtures/internal-api";
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
test("Overview separates metrics, caches and quality, no token reaches browser; partial error stays explicit", async ({
  page,
  request,
}, info) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) {
      requests.push(r.url());
      expect(r.headers()["x-ops-token"]).toBeUndefined();
    }
  });
  await page.goto("/internal/operations/overview");
  await expect(page.getByRole("region", { name: "执行与 usage population" })).toContainText(
    "0.0001",
  );
  for (const name of [
    "Provider token cache",
    "External observation reuse",
    "Business artifact reuse",
    "Production quality population",
  ])
    await expect(page.getByRole("region", { name, exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Provider token cache" })).toContainText("unknown");
  expect(await page.content()).not.toContain("synthetic-never-forward");
  const calls = await (await request.get("http://127.0.0.1:3111/__requests")).json();
  expect(
    calls
      .filter((r: { path: string }) => r.path.startsWith("/api/v1/ops/"))
      .every((r: { hasOpsToken: boolean }) => r.hasOpsToken),
  ).toBe(true);
  expect(requests.every((u) => u.includes("/api/internal/"))).toBe(true);
  await page.screenshot({ path: info.outputPath("internal-overview-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: info.outputPath("internal-overview-mobile.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.route("**/api/internal/ops/metrics?*", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "controller_not_ready" } }),
    }),
  );
  await page.getByRole("button", { name: "刷新窗口数据" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "controller_not_ready" })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Controller / effective limits / circuits" }),
  ).toBeVisible();
});
test("Runs show agent checkpoint, action observations and exact ModelCall without manufacturing journal joins", async ({
  page,
}) => {
  await page.goto("/internal/operations/runs");
  await page.getByLabel("Run kind").selectOption("agent");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await page.getByRole("button", { name: `查看 ${ids.agent}`, exact: true }).click();
  await expect(page.getByRole("region", { name: "Agent checkpoint / progress" })).toContainText(
    "resume_selection_required",
  );
  await expect(page.getByRole("region", { name: "Action observations" })).toBeVisible();
  const calls = page.getByRole("region", { name: "ModelCall / ToolCall / versions / diagnostics" });
  await calls.getByText("展开 model_calls", { exact: true }).click();
  await expect(calls).toContainText(ids.call);
  await page.getByLabel("Attempt UUID").fill(ids.attempt);
  await page.getByRole("button", { name: "查询 attempt", exact: true }).click();
  await expect(page.getByRole("region", { name: "Attempt metadata" })).toContainText(
    "execution_cancelled",
  );
});
test("Attention preserves categories; reconcile and global kill use explicit confirmation and CAS", async ({
  page,
}) => {
  await page.goto("/internal/operations/incidents");
  await expect(page.getByRole("region", { name: "Attention discovery" })).toContainText(
    "execution_failure",
  );
  await expect(page.getByRole("region", { name: "Attention discovery" })).toContainText(
    "unknown_outcome",
  );
  await page.getByRole("button", { name: `查看 ${ids.incident}`, exact: true }).click();
  await page.getByLabel("Resolution", { exact: true }).selectOption("manual_acknowledge");
  await page.getByRole("checkbox", { name: "确认：Reconcile attempt" }).check();
  await page.getByRole("button", { name: "Reconcile attempt", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("resolved");
  await page.goto("/internal/operations/controls");
  await page.getByLabel("Control action").selectOption("global_kill");
  await expect(page.getByRole("button", { name: "提交 control action" })).toBeDisabled();
  await page.getByRole("checkbox", { name: "我已核对目标、CAS revision 和影响范围" }).check();
  const sent = page.waitForRequest(
    (r) => r.url().endsWith("/api/internal/ops/controls") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "提交 control action" }).click();
  expect((await sent).postDataJSON()).toMatchObject({
    action: "global_kill",
    expected_revision: 3,
    expected_global_revision: 2,
    enabled: true,
  });
  await expect(page.getByRole("status")).toContainText("true");
});
test("Eval suite -> offline run -> trial and invocation metadata; private view is explicit", async ({
  page,
}) => {
  const responses: string[] = [];
  page.on("response", async (r) => {
    if (r.url().includes("/api/internal/evaluation/") && !r.url().includes("private=confirmed"))
      responses.push(await r.text().catch(() => ""));
  });
  await page.goto("/internal/evaluation/test-runs");
  await page.getByRole("button", { name: `查看 ${ids.suite}`, exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "创建 frozen EvalRun" })
      .getByLabel("Suite key", { exact: true }),
  ).toHaveValue("synthetic-suite");
  await page.getByRole("checkbox", { name: "确认创建此 candidate_replay run" }).check();
  await page.getByRole("button", { name: "创建 EvalRun", exact: true }).click();
  await page.getByRole("checkbox", { name: "确认：执行 EvalRun" }).check();
  await page.getByRole("button", { name: "执行 EvalRun", exact: true }).click();
  const runDetail = page.getByRole("region", { name: "EvalRun / frozen CandidateConfig" });
  await expect(runDetail).toContainText("completed");
  await expect(runDetail.getByRole("button", { name: "执行 EvalRun", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: `查看 ${ids.trial}`, exact: true }).click();
  await page.getByRole("button", { name: `查看 operation ${ids.invocation}`, exact: true }).click();
  await expect(
    page.getByRole("region", { name: "OperationInvocationSnapshot metadata" }),
  ).toContainText(ids.call);
  expect(responses.join(" ")).not.toContain("PRIVATE_");
  const priv = page.getByRole("region", { name: "显式 invocation input/output 审阅" });
  await priv.getByRole("button", { name: "确认读取私有内容" }).click();
  await priv.getByText("展开 input_snapshot", { exact: true }).click();
  await expect(priv).toContainText("PRIVATE_INPUT_SYNTHETIC");
  await priv.getByRole("button", { name: "关闭私有内容" }).click();
  await expect(priv).not.toContainText("PRIVATE_INPUT_SYNTHETIC");
});
test("Quality preserves categorical criteria and comparison missing coverage remains INCONCLUSIVE", async ({
  page,
}) => {
  await page.goto("/internal/evaluation/production-quality");
  await page.getByRole("button", { name: `查看 ${ids.judge}`, exact: true }).click();
  const judge = page.getByRole("region", {
    name: "Judge criteria / confidence / evidence / provenance",
  });
  await judge.getByText("展开 result", { exact: true }).click();
  await judge.getByText("展开 criteria", { exact: true }).click();
  await expect(judge).toContainText("minor_issue");
  await expect(judge).toContainText("medium");
  await page.goto("/internal/evaluation/comparisons");
  await page.getByRole("button", { name: `查看 ${ids.comparison}`, exact: true }).click();
  const view = page.getByRole("region", {
    name: "Comparison outcome / config diff / dimensions / coverage",
  });
  await view.getByText("展开 cases", { exact: true }).click();
  await expect(view).toContainText("INCONCLUSIVE");
  await expect(view).toContainText("REVIEW_REQUIRED");
  const form = page.getByRole("region", { name: "创建 comparison" });
  await form
    .getByLabel("比较两个 EvalRun · canonical JSON")
    .fill(JSON.stringify({ baseline_run_id: ids.evalrun, candidate_run_id: ids.evalrun }));
  await form.getByRole("checkbox").check();
  await form.getByRole("button", { name: "比较两个 EvalRun", exact: true }).click();
  await expect(form.getByRole("status")).toContainText("REVIEW_REQUIRED");
});
test("Blind annotation hides Judge; capture triage/export/promotion never return raw capture by default", async ({
  page,
  request,
}, info) => {
  await page.goto("/internal/evaluation/calibration-triage");
  await page.getByRole("button", { name: `查看 ${ids.queue}`, exact: true }).click();
  await expect(page.getByRole("button", { name: "读取 calibration report" })).toBeDisabled();
  const blind = page.getByRole("region", { name: "Blind labeling" });
  await blind.getByRole("button", { name: "确认读取私有内容" }).click();
  await expect(blind).not.toContainText("Synthetic observation");
  await blind.getByLabel("提交 blind annotation · canonical JSON").fill(
    JSON.stringify({
      subject: {
        subject_id: ids.subject,
        task_type: "greeting_generation",
        accepted_model_call_id: ids.call,
        operation_id: ids.invocation,
        origin: "business",
      },
      annotator: "synthetic-reviewer",
      population: "targeted",
      criteria: [
        {
          criterion: "relevance",
          rating: "pass",
          confidence: "medium",
          uncertainty_reasons: [],
          reason: "Synthetic human review",
          evidence_refs: ["source:1"],
        },
      ],
      blind: true,
    }),
  );
  await blind.getByRole("checkbox", { name: "确认提交 提交 blind annotation" }).check();
  await blind.getByRole("button", { name: "提交 blind annotation", exact: true }).click();
  await expect(blind.getByRole("status")).toContainText(ids.annotation);
  const calls = await (await request.get("http://127.0.0.1:3111/__requests")).json();
  expect(calls.some((r: { path: string }) => r.path.includes("/judges/"))).toBe(false);
  await page.getByRole("button", { name: "关闭当前盲标" }).click();
  await page.getByRole("button", { name: "读取 calibration report" }).click();
  await expect(
    page.getByRole("region", { name: "Calibration statistics / population slices" }),
  ).toContainText("unique_subject_count");
  await page.getByRole("button", { name: `查看 ${ids.capture}`, exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Capture identity / immutable payload metadata / events" }),
  ).not.toContainText("PRIVATE_CAPTURE_SYNTHETIC");
  const triage = page.getByRole("region", { name: "Triage decision" });
  await triage.getByRole("checkbox").check();
  await triage.getByRole("button", { name: "保存 triage", exact: true }).click();
  await expect(triage.getByRole("status")).toContainText("triaged");
  await page.getByRole("button", { name: "显式读取 Sanitized capture export" }).click();
  await expect(page.getByRole("region", { name: "Sanitized capture export" })).toContainText(
    "requires_explicit_promotion",
  );
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: info.outputPath("internal-triage-mobile.png"), fullPage: true });
});
test("Internal BFF requires same-origin intent, rejects arbitrary routes and never returns credentials/errors", async ({
  page,
  request,
}) => {
  await page.goto("/internal/operations/overview");
  expect((await request.get("http://127.0.0.1:3100/api/internal/ops/controller")).status()).toBe(
    403,
  );
  const results = await page.evaluate(async () => {
    const read = async (path: string, init: RequestInit = {}) => {
      const r = await fetch(`/api/internal/${path}`, {
        ...init,
        headers: { "X-Internal-Request": "1", ...init.headers },
      });
      return { status: r.status, text: await r.text() };
    };
    return [
      await read("ops/routing"),
      await read("ops/controls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: "never" }),
      }),
      await read("ops/controller"),
      await read("evaluation/captures/90000000-0000-4000-8000-000000000020"),
    ];
  });
  expect(results[0].status).toBe(422);
  expect(results[1].status).toBe(422);
  expect(results[2].status).toBe(200);
  expect(JSON.stringify(results)).not.toContain("synthetic-never-forward");
  expect(JSON.stringify(results)).not.toContain("PRIVATE_CAPTURE_SYNTHETIC");
});

test("Advanced canonical contracts validate JSON locally, cancellation refreshes state, promotion is explicit", async ({
  page,
}) => {
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/internal/"))
      writes.push({ path: new URL(r.url()).pathname, body: r.postDataJSON() });
  });
  await page.goto("/internal/evaluation/test-runs");
  await page.getByRole("button", { name: `查看 ${ids.suite}`, exact: true }).click();
  await page.getByLabel("EvalRun limits · JSON").fill("not-json");
  await page.getByRole("checkbox", { name: "确认创建此 candidate_replay run" }).check();
  await page.getByRole("button", { name: "创建 EvalRun", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "创建 frozen EvalRun" }).getByRole("alert"),
  ).toContainText("invalid_request");
  expect(writes).toHaveLength(0);
  await page.getByLabel("EvalRun limits · JSON").fill("{}");
  await page.getByLabel("Execution mode").selectOption("origin_reexecution");
  await page.getByRole("checkbox", { name: "确认创建此 origin_reexecution run" }).check();
  await page.getByRole("button", { name: "创建 EvalRun", exact: true }).click();
  await page.getByRole("checkbox", { name: "确认：取消 EvalRun" }).check();
  await page.getByRole("button", { name: "取消 EvalRun", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "EvalRun / frozen CandidateConfig" }),
  ).toContainText("cancelled");
  expect(writes[0].body).toMatchObject({
    mode: "origin_reexecution",
    explicit_diagnostic: true,
    suite_id: "synthetic-suite",
    suite_version: 1,
  });
  expect(writes.some((w) => w.path.endsWith("/execute"))).toBe(false);
  await page.goto("/internal/evaluation/calibration-triage");
  await page.getByRole("button", { name: `查看 ${ids.capture}`, exact: true }).click();
  const triage = page.getByRole("region", { name: "Triage decision" });
  await triage.getByRole("checkbox").check();
  await triage.getByRole("button", { name: "保存 triage", exact: true }).click();
  await expect(triage.getByRole("status")).toContainText("triaged");
  await page.getByRole("button", { name: "显式读取 Sanitized capture export" }).click();
  await expect(page.getByRole("region", { name: "Sanitized capture export" })).toContainText(
    "requires_explicit_promotion",
  );
  expect(writes.some((w) => w.path.endsWith("/promote"))).toBe(false);
  const promote = page.getByRole("region", { name: "Explicit promotion" });
  await promote.getByLabel("Promote regression case · canonical JSON").fill(
    JSON.stringify({
      case: {
        case_id: "sanitized-component",
        case_version: 1,
        entrypoint: {
          kind: "component",
          component_kind: "model_task",
          name: "greeting_generation",
        },
        source_type: "sanitized",
        source_snapshot: { safe: true },
        model_input: null,
        evaluation_clock: "2026-10-24T08:00:00Z",
        expectations: [{ check_id: "output_schema", operator: "valid" }],
      },
      confirmed_repo_safe: true,
    }),
  );
  await promote.getByRole("checkbox").check();
  await promote.getByRole("button", { name: "Promote regression case", exact: true }).click();
  await expect(promote.getByRole("status")).toContainText(ids.case);
  expect(writes.at(-1)?.body.confirmed_repo_safe).toBe(true);
});
