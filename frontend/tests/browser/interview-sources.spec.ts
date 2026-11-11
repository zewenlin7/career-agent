import { test, expect, type BrowserContext } from "@playwright/test";
import { id, time } from "../fixtures/product-api";
import { context as frozenContext, resumeDocument } from "../fixtures/workspace-api";
import type { Result } from "../../src/features/workspace/contracts";

const root = `/applications/${id(1)}`;
const historicalJD = id(4401);
const target = id(24001);
const predecessorResume = id(9401);
const selectedResume = id(9402);

async function selectedResult(context: BrowserContext, result: Result) {
  await context.route(`**/api/product/applications/${id(1)}/results?*`, async (route) => {
    await route.fulfill({
      json: { items: [{ created_at: time(), result }], limit: 100, offset: 0, has_more: false },
    });
  });
  await context.route(`**/api/product/preparation-artifacts/${target}/result?*`, async (route) => {
    await route.fulfill({ json: { created_at: time(), result } });
  });
  await context.route(`**/api/product/job-revisions/${historicalJD}`, async (route) => {
    await route.fulfill({
      json: {
        job_id: frozenContext.job_id,
        job_revision_id: historicalJD,
        revision: 1,
        created_at: time(),
        jd_text: "历史职位描述：只读旧来源，不能替换成当前职位描述。",
        requirements: [],
      },
    });
  });
}

function historicalResult(kind: Result["kind"]): Result {
  return {
    available: true,
    kind,
    status: "success",
    target_artifact_id: target,
    result_id: kind === "resume_tailoring" ? null : id(24002),
    resume_revision_id: kind === "resume_tailoring" ? selectedResume : null,
    resume_name: "所选历史优化简历",
    source_resume_revision_id: predecessorResume,
    source_resume_name: "原始生成简历",
    refinement_resume_revision_id: kind === "resume_tailoring" ? selectedResume : predecessorResume,
    refinement_resume_name: kind === "resume_tailoring" ? "所选历史优化简历" : "原始生成简历",
    resume_variant_id: null,
    revision: null,
    render_artifact_id: null,
    download_url: null,
    content:
      kind === "resume_tailoring"
        ? resumeDocument
        : kind === "greeting_generation"
          ? { greeting_text: "历史招呼语，保留原有项目事实。" }
          : {
              likely_topics: ["历史准备话题"],
              knowledge_gaps: [],
              questions_to_ask_interviewer: [],
              technical_questions: [],
              project_deep_dive_questions: [],
              behavioral_questions: [],
              company_specific_questions: [],
            },
    context: { ...frozenContext, job_revision_id: historicalJD, job_revision: 1 },
    reused: false,
    versions: {},
    reason: null,
    allowed_actions: ["read"],
  };
}

test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("main generation JD source stays exact while a historical result is selected", async ({
  page,
  context,
}) => {
  await selectedResult(context, historicalResult("interview_preparation"));
  await context.route(`**/api/product/job-revisions/${id(4001)}`, (route) =>
    route.fulfill({
      json: {
        job_id: frozenContext.job_id,
        job_revision_id: id(4001),
        jd_text: "当前生成入口的职位描述，历史选择不改变输入。",
        requirements: [],
      },
    }),
  );
  await page.goto(`${root}/interview/preparation?result=${target}`);
  const record = page.locator(`[data-result-destination="${target}"]`);
  await expect(record.getByRole("link", { name: "职位描述", exact: true })).toHaveCount(0);
  const link = page.getByRole("link", { name: "职位描述", exact: true });
  await expect(link).toHaveAttribute(
    "href",
    `${root}/research-fit/description?revision=${id(4001)}`,
  );
  await link.click();
  await expect(page.getByRole("dialog", { name: "职位描述", exact: true })).toContainText(
    "当前生成入口的职位描述",
  );
  await page
    .getByRole("dialog", { name: "职位描述", exact: true })
    .getByRole("button", { name: "关闭" })
    .click();
  const newTab = await context.newPage();
  await newTab.goto((await link.getAttribute("href"))!);
  await expect(
    newTab.getByText("当前生成入口的职位描述，历史选择不改变输入。", { exact: true }),
  ).toBeVisible();
  await expect(newTab.getByRole("button", { name: "编辑", exact: true })).toHaveCount(0);
  await expect(newTab).toHaveURL(new RegExp(`revision=${id(4001)}$`));
  await newTab.close();
});

test("historical Tailoring adjustment uses the selected Resume and target while current binding differs", async ({
  page,
  context,
}) => {
  await selectedResult(context, historicalResult("resume_tailoring"));
  let submitted: Record<string, unknown> | undefined;
  await context.route("**/api/product/product-drafts", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 409, json: { error: { code: "execution_capacity_full" } } });
  });
  await page.goto(`${root}/apply/resume?result=${target}`);
  const record = page.locator(`[data-result-destination="${target}"]`);
  await expect(page.getByRole("link", { name: "合成简历", exact: true })).toHaveAttribute(
    "href",
    `/profile/resumes?revision=${id(8401)}`,
  );
  await expect(record.getByRole("link", { name: "原始生成简历", exact: true })).toHaveCount(0);
  await record.getByRole("button", { name: "调整", exact: true }).click();
  await expect(record.locator("p").filter({ hasText: /^基于.*生成$/ })).toHaveCount(0);
  await record
    .getByPlaceholder("输入调整意见")
    .fill("保留原事实，突出事务测试。推送前仅使用所选历史记录。");
  await record.getByRole("button", { name: "开始调整", exact: true }).click();
  await expect.poll(() => submitted?.source_artifact_id).toBe(target);
  expect(submitted).toMatchObject({
    application_id: id(1),
    task: "resume_refinement",
    source_artifact_id: target,
    intent: "refine",
  });
  expect(submitted).not.toHaveProperty("source_resume_revision_id");
  expect(submitted).not.toHaveProperty("application_binding");
  expect(submitted).not.toHaveProperty("research_report_id");
});

for (const [kind, route, label] of [
  ["interview_preparation", "interview/preparation", "原准备记录"],
  ["greeting_generation", "apply/greeting", "原招呼语"],
] as const) {
  test(`${kind} adjustment keeps the exact target without a repeated source row`, async ({
    page,
    context,
  }) => {
    await selectedResult(context, historicalResult(kind));
    let submitted: Record<string, unknown> | undefined;
    await context.route("**/api/product/product-drafts", async (route) => {
      submitted = route.request().postDataJSON();
      await route.fulfill({ status: 409, json: { error: { code: "execution_capacity_full" } } });
    });
    await page.goto(`${root}/${route}?result=${target}`);
    const record = page.locator(`[data-result-destination="${target}"]`);
    await record.getByRole("button", { name: "调整", exact: true }).click();
    await expect(record.getByRole("link", { name: label, exact: true })).toHaveCount(0);
    await expect(record.locator("p").filter({ hasText: /^基于.*生成$/ })).toHaveCount(0);
    await record.getByPlaceholder("输入调整意见").fill("保留历史材料，仅调整表达。");
    await record.getByRole("button", { name: "开始调整", exact: true }).click();
    await expect.poll(() => submitted?.source_artifact_id).toBe(target);
  });
}
