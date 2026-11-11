// Synthetic HTTP fixtures only; never imported by app/src. Field names follow FastAPI contracts.
export const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const time = (n = 0) => new Date(Date.UTC(2026, 9, 24, 4, 0) - n * 60_000).toISOString();
export const companies = [
  { id: id(1001), name: "晨星科技", created_at: time() },
  { id: id(1002), name: "远山实验室", created_at: time(1) },
  { id: id(1003), name: "尚无申请公司", created_at: time(2) },
  ...Array.from({ length: 10 }, (_, i) => ({
    id: id(1100 + i),
    name: `样本公司 ${i + 1}`,
    created_at: time(i + 3),
  })),
];
export function application(n: number) {
  return {
    id: id(n),
    job_id: id(2000 + n),
    created_at: time(n),
    status: n === 1 ? "applied" : n === 2 ? "interviewing" : "tracking",
    revision: 2,
    events: [
      {
        id: id(5000 + n),
        created_at: time(n),
        application_id: id(n),
        sequence: 1,
        kind: "created",
        from_status: null,
        to_status: "tracking",
        note: null,
      },
      {
        id: id(6000 + n),
        created_at: time(),
        application_id: id(n),
        sequence: 2,
        kind: "note",
        from_status: null,
        to_status: null,
        note: "已核对岗位要求",
      },
    ],
  };
}
export function job(n: number) {
  return {
    id: id(2000 + n),
    company_id: id(n === 24 ? 1002 : 1001),
    company_name: n === 24 ? "远山实验室" : "晨星科技",
    application_id: id(n === 88 ? 2 : n),
    created_at: time(n),
    job_revision_id: id(4000 + n),
    revision: 2,
    title: n === 1 ? "后端工程师" : n === 2 ? "Agent 工程师" : `研发职位 ${n}`,
    jd_text: "使用 Python / FastAPI 构建服务。\n外部文本 <script>window.__injected=true</script>",
    requirements: [
      {
        id: id(7000 + n),
        text: "熟悉 Python",
        category: "skill",
        importance: "must",
        source_quote: "Python",
        extraction_metadata: null,
      },
    ],
  };
}
export const applications = Array.from({ length: 24 }, (_, i) => application(i + 1));
function paged<T>(items: T[], search: URLSearchParams) {
  const limit = Number(search.get("limit") || 50),
    offset = Number(search.get("offset") || 0);
  return {
    items: items.slice(offset, offset + limit),
    limit,
    offset,
    has_more: offset + limit < items.length,
  };
}
function numberId(s: string | undefined) {
  return Number(s?.slice(-12));
}
export function summaryFixture(
  app: { id: unknown; revision: unknown; status: unknown; events: unknown },
  jd: { jd_text: unknown; job_revision_id: unknown; created_at: unknown },
) {
  const events = app.events as {
    id: string;
    kind: string;
    note: string | null;
    to_status: string | null;
    created_at: string;
    removed?: boolean;
    entry_revision?: number;
  }[];
  const base = `/applications/${app.id}`;
  return {
    revision: app.revision,
    status: app.status,
    jd: { text: jd.jd_text, id: jd.job_revision_id, saved_at: jd.created_at },
    resume: null,
    submission: null,
    mock: null,
    actual: { count: 0, latest: null },
    debrief: { count: 0, latest: null },
    preparation: [
      ["company_research", "公司研究", "research-fit/company"],
      ["fit_analysis", "岗位匹配", "research-fit/fit"],
      ["resume_tailoring", "简历优化", "apply/resume"],
      ["greeting_generation", "招呼语", "apply/greeting"],
      ["interview_preparation", "面试准备", "interview/preparation"],
    ].map(([kind, label, page]) => ({
      kind,
      label,
      href: base + "/" + page,
      created_at: null,
      available: false,
      stale: false,
    })),
    notes: events
      .filter((e) => e.kind === "note" && !e.removed)
      .reverse()
      .map((e) => ({
        ...e,
        text: e.note,
        kind: "note",
        status: null,
        revision: e.entry_revision || 1,
        editable: true,
      })),
    records: events
      .filter((e) => e.kind !== "note" && !e.removed)
      .reverse()
      .map((e) => ({
        ...e,
        text: e.note,
        kind: e.kind === "created" ? "created" : "status",
        status: e.to_status,
        revision: e.entry_revision || 1,
        editable: e.kind !== "created",
      })),
  };
}
export function fixtureResponse(url: URL): { status: number; body: unknown } {
  const p = url.pathname,
    q = url.searchParams;
  const ok = (body: unknown) => ({ status: 200, body });
  const missing = { status: 404, body: { error: { code: "not_found" } } };
  if (p === "/api/v1/companies")
    return ok(
      paged(
        companies.filter((c) => !q.get("q") || c.name.includes(q.get("q")!)),
        q,
      ),
    );
  if (p === "/api/v1/applications")
    return ok(
      paged(
        applications.filter(
          (a) =>
            (!q.get("status") || a.status === q.get("status")) &&
            (!q.get("company_q") ||
              companies
                .find((c) => c.id === job(numberId(a.id)).company_id)
                ?.name.includes(q.get("company_q")!)) &&
            (!q.get("company_id") || job(numberId(a.id)).company_id === q.get("company_id")) &&
            (!q.getAll("company_ids").length ||
              q.getAll("company_ids").includes(job(numberId(a.id)).company_id)),
        ),
        q,
      ),
    );
  const contextMatch = p.match(/^\/api\/v1\/applications\/([^/]+)\/context$/);
  if (contextMatch)
    return ok({
      application_id: contextMatch[1],
      job_revision_id: job(numberId(contextMatch[1])).job_revision_id,
      revision: 1,
    });
  const summaryMatch = p.match(/^\/api\/v1\/applications\/([^/]+)\/summary$/);
  if (summaryMatch)
    return ok(
      summaryFixture(application(numberId(summaryMatch[1])), job(numberId(summaryMatch[1]))),
    );
  let m = p.match(/^\/api\/v1\/applications\/([^/]+)$/);
  if (m)
    return numberId(m[1]) === 88
      ? ok(application(88))
      : applications.some((a) => a.id === m![1])
        ? ok(application(numberId(m[1])))
        : missing;
  m = p.match(/^\/api\/v1\/jobs\/([^/]+)$/);
  if (m) return ok(job(numberId(m[1]) - 2000));
  m = p.match(/^\/api\/v1\/companies\/([^/]+)$/);
  if (m)
    return companies.find((c) => c.id === m![1])
      ? ok(companies.find((c) => c.id === m![1]))
      : missing;
  m = p.match(/^\/api\/v1\/companies\/([^/]+)\/research$/);
  if (m) {
    if (m[1] === id(1002))
      return {
        status: 503,
        body: { error: "PRIVATE_PAYLOAD_NOT_RENDERED raw provider /private/path" },
      };
    return ok(
      paged(
        [
          {
            id: id(8001),
            company_id: m[1],
            research_version: 3,
            fetched_at: time(),
            expires_at: "2026-12-24T04:00:00Z",
            historical_readable: true,
            reusable_for_current_execution: false,
            data: { mode: "fixture", report: { private: "PRIVATE_PAYLOAD_NOT_RENDERED" } },
          },
        ],
        q,
      ),
    );
  }
  m = p.match(/^\/api\/v1\/applications\/([^/]+)\/preparation-packages$/);
  if (m)
    return ok(
      m[1] === id(1)
        ? [
            {
              id: id(8101),
              run_id: id(8201),
              job_revision_id: id(3999),
              profile_id: id(9001),
              outcome: {
                status: "partial",
                reason: "layout_failed",
                targets: {
                  fit_analysis: { status: "completed", artifact_id: id(8102), reason: null },
                  resume_tailoring: {
                    status: "failed",
                    artifact_id: null,
                    reason: "layout_failed",
                  },
                },
              },
            },
          ]
        : [],
    );
  m = p.match(/^\/api\/v1\/applications\/([^/]+)\/submissions$/);
  if (m)
    return ok(
      paged(
        m[1] === id(1)
          ? [
              {
                id: id(8301),
                created_at: time(),
                request_id: id(8302),
                expected_revision: 2,
                application_id: m[1],
                event_id: id(6001),
                resume_revision_id: id(8401),
                render_artifact_id: id(8501),
                greeting_id: null,
                package_id: id(8101),
                note: null,
              },
            ]
          : [],
        q,
      ),
    );
  if (p === "/api/v1/mock-interviews")
    return ok(
      paged(
        q.get("application_id") === id(1)
          ? [
              {
                id: id(8601),
                job_id: id(2001),
                run_id: id(8202),
                created_at: time(),
                status: "waiting_answer",
                revision: 3,
                pending_question_id: id(8602),
              },
            ]
          : [],
        q,
      ),
    );
  if (p === "/api/v1/interviews")
    return ok(
      q.get("application_id") === id(1)
        ? [
            {
              id: id(8701),
              application_id: id(1),
              round_name: "技术一面",
              status: "completed",
              created_at: time(10),
              occurred_at: time(20),
              content_revision: 2,
              notes: [{ text: "PRIVATE_PAYLOAD_NOT_RENDERED", recorded_at: time() }],
              entries: [],
            },
          ]
        : [],
    );
  if (p === "/api/v1/interview-debriefs")
    return ok(
      paged(
        q.get("application_id") === id(1)
          ? [
              {
                id: id(8801),
                generation_id: id(8801),
                selected_run_id: id(8802),
                root_run_id: id(8801),
                run_id: id(8203),
                status: "partial",
                is_selected: false,
                source_kind: "actual",
                source_id: id(8701),
                source_hash: "a".repeat(64),
                created_at: time(),
                detail_url: `/api/v1/interview-debriefs/${id(8801)}`,
                historical_detail_url: `/api/v1/interview-debriefs/${id(8801)}?historical=true`,
                supersedes_run_id: null,
              },
            ]
          : [],
        q,
      ),
    );
  return missing;
}
