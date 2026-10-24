import { id, time, fixtureResponse } from "./product-api.ts";
import type {
  Actual,
  Debrief,
  Mock,
  Operation,
  PackageView,
  Submission,
} from "../../src/features/workspace/contracts.ts";
const profile = id(9001),
  resume = id(8401),
  variant = id(8400),
  pdf = id(8501),
  jd = id(4001);
export const profileRow = {
  id: profile,
  revision: 1,
  created_at: time(),
  data: {
    display_name: "合成求职者",
    education: [],
    experiences: [],
    projects: [],
    skills: ["Python"],
    preferences: {},
  },
};
export const resumeDocument = {
  locale: "zh-CN",
  metadata: { label: "合成 base" },
  schema_version: "resume-v2",
  template: "resume_zh_cn_a4_single_v1",
  target_page_count: 1,
  profile_id: profile,
  profile_revision: 1,
  job_revision_id: jd,
  sections: [
    {
      section_id: id(8402),
      name: "projects",
      ordering: 0,
      priority: 1,
      required: true,
      items: [
        {
          item_id: id(8403),
          kind: "bullet",
          text: "使用 Python 构建数据服务。",
          fact_refs: [id(9010)],
          requirement_refs: [id(7001)],
          hard_claims: [],
          priority: 1,
          required: true,
          ordering: 0,
          short_text: null,
        },
      ],
    },
  ],
};
export const context = {
  profile_id: profile,
  profile_revision: 1,
  job_id: id(2001),
  job_revision_id: jd,
  job_revision: 2,
  job_title: "后端工程师",
  company_id: id(1001),
};
const research = {
  id: id(8001),
  company_id: id(1001),
  research_version: 3,
  fetched_at: time(),
  expires_at: "2026-12-24T04:00:00Z",
  historical_readable: true,
  reusable_for_current_execution: false,
  data: {
    mode: "fixture",
    trust_level: "untrusted_external",
    report: {
      locale: "zh-CN",
      conclusions: [{ text: "公司提供数据服务。", evidence_refs: [id(8002)] }],
      inference: [],
      unknowns: ["团队规模未知"],
    },
    evidence: [
      {
        id: id(8002),
        title: "公开公司资料",
        source_url: "https://example.com",
        content: "合成公开资料",
        retrieved_at: time(),
        provider: "fixture",
        evidence_version: "research-evidence-v1",
        trust_level: "untrusted_external",
        source_type: "web",
      },
    ],
  },
};
function page<T>(items: T[], q: URLSearchParams) {
  const limit = Number(q.get("limit") || 50),
    offset = Number(q.get("offset") || 0);
  return {
    items: items.slice(offset, offset + limit),
    limit,
    offset,
    has_more: items.length > offset + limit,
  };
}
let seq = 20000;
const operations = new Map<string, Operation>(),
  operationBodies = new Map<string, Record<string, unknown>>(),
  packages = new Map<string, PackageView>(),
  mocks = new Map<string, Mock>(),
  actuals = new Map<string, Actual>(),
  debriefs = new Map<string, Debrief>(),
  selected = new Map<string, string>();
const submissions: Submission[] = [],
  notes: Record<string, unknown>[] = [];
let revision = 2;
export function resetWorkspace() {
  operations.clear();
  operationBodies.clear();
  packages.clear();
  mocks.clear();
  actuals.clear();
  debriefs.clear();
  selected.clear();
  submissions.length = 0;
  notes.length = 0;
  revision = 2;
  seq = 20000;
}
function newId() {
  return id(seq++);
}
function packageFor(kind: string, packageId: string): PackageView {
  const base = {
    kind,
    status: "success",
    result_id: newId(),
    target_artifact_id: newId(),
    resume_revision_id: null,
    source_resume_revision_id:
      kind === "greeting_generation" || kind === "interview_preparation" ? resume : null,
    resume_variant_id: null,
    revision: null,
    render_artifact_id: null,
    download_url: null,
    context,
    reused: false,
    versions: { workflow_version: "preparation-v2" },
    reason: null,
    allowed_actions: ["read"],
  };
  const content: Record<string, unknown> =
    kind === "fit_analysis"
      ? {
          locale: "zh-CN",
          items: [
            {
              requirement_ref: id(7001),
              status: "no_evidence",
              fact_refs: [],
              explanation: "暂无相关事实证据。",
              missing_evidence: "需要补充项目经历",
            },
          ],
          strong_matches: [],
          partial_matches: [],
          evidence_missing: [id(7001)],
          clear_gaps: [],
        }
      : kind === "greeting_generation"
        ? {
            locale: "zh-CN",
            greeting_text: "您好，我有 Python 数据服务项目经验，期待交流。",
            fact_refs: [id(9010)],
            requirement_refs: [id(7001)],
          }
        : kind === "resume_tailoring"
          ? resumeDocument
          : {
              locale: "zh-CN",
              likely_topics: ["Python"],
              technical_questions: [],
              project_deep_dive_questions: [],
              behavioral_questions: [],
              company_specific_questions: [],
              knowledge_gaps: [],
              questions_to_ask_interviewer: ["团队如何合作？"],
            };
  return {
    package_id: packageId,
    run_id: newId(),
    status: "completed",
    results: [
      {
        ...base,
        kind: kind as PackageView["results"][number]["kind"],
        content,
        ...(kind === "resume_tailoring"
          ? {
              result_id: null,
              resume_revision_id: resume,
              resume_variant_id: variant,
              revision: 1,
              render_artifact_id: pdf,
              download_url: `/api/v1/artifacts/${pdf}/download`,
            }
          : {}),
      },
    ],
  };
}
export type FixtureReply = { status: number; body: unknown; sse?: string; pdf?: boolean };
export function workspaceResponse(
  url: URL,
  method: string,
  body: Record<string, unknown>,
): FixtureReply | undefined {
  const p = url.pathname.slice("/api/v1/".length),
    q = url.searchParams,
    ok = (body: unknown): FixtureReply => ({ status: 200, body }),
    fail = (code: string, status = 409) => ({ status, body: { error: { code } } });
  if (p.startsWith("job-revisions/"))
    return ok({
      job_id: id(2001),
      job_revision_id: jd,
      revision: 2,
      requirements: [{ id: id(7001), text: "熟悉 Python" }],
    });
  if (p === "profile/revisions") return ok(page([profileRow], q));
  if (p === "resume-revisions")
    return ok(
      q.get("profile_id") === profile
        ? [
            {
              resume_revision_id: resume,
              resume_variant_id: variant,
              revision: 1,
              profile_id: profile,
              job_revision_id: jd,
              created_at: time(),
              hints: { original: true, same_jd: true, same_job: true, last_used_at: null },
            },
          ]
        : [],
    );
  if (p === `resume-variants/${variant}`)
    return ok({
      id: variant,
      resume_revision_id: resume,
      revision: 1,
      created_at: time(),
      document: resumeDocument,
      input_snapshot: {},
    });
  if (p === `resume-variants/${variant}/render` || p === `artifacts/${pdf}`)
    return ok({
      id: pdf,
      resume_variant_id: variant,
      resume_variant_revision: 1,
      created_at: time(),
      artifact_ref: id(8510),
      file_hash: "a".repeat(64),
      report: {
        render_status: "accepted",
        validation_status: "passed",
        page_count: 1,
        findings: [],
        attempts: [],
        versions: {},
      },
    });
  if (p === `artifacts/${pdf}/download`) return { status: 200, body: null, pdf: true };
  if (p === `companies/${id(1001)}/research/current`)
    return q.get("mode") === "fixture"
      ? ok({ ...research, id: id(7999), research_version: 2, reusable_for_current_execution: true })
      : fail("no_current_research", 404);
  if (p === `companies/${id(1001)}/research` && method === "GET")
    return ok(
      page(
        [
          research,
          { ...research, id: id(7999), research_version: 2, reusable_for_current_execution: true },
        ],
        q,
      ),
    );
  if ((p === "operations" || p === `companies/${id(1001)}/research`) && method === "POST") {
    const old = [...operations.values()].find((o) => o.request_id === body.request_id);
    if (old) return ok(old);
    const op: Operation = {
      id: newId(),
      request_id: String(body.request_id),
      kind: String(body.kind),
      status: "pending",
      reason: null,
      package_id: null,
      research_report_id: null,
      run_id: newId(),
      created_at: time(),
      allowed_actions: ["execute"],
    };
    operations.set(op.id, op);
    operationBodies.set(op.id, body);
    return ok(op);
  }
  if (p === "operations") return ok(page([...operations.values()].reverse(), q));
  let m = p.match(/^operations\/([^/]+)(\/execute)?$/);
  if (m) {
    const op = operations.get(m[1]);
    if (!op) return fail("not_found", 404);
    if (m[2]) {
      const req = operationBodies.get(op.id)!.request as Record<string, unknown>;
      op.status = "success";
      op.allowed_actions = ["read"];
      if (op.kind === "company_research") op.research_report_id = research.id;
      else {
        op.package_id = newId();
        packages.set(
          op.package_id,
          packageFor(
            op.kind === "prepare_interview"
              ? "interview_preparation"
              : (req.targets as string[])[0],
            op.package_id,
          ),
        );
      }
    }
    return ok(op);
  }
  if (p === `applications/${id(1)}/preparation-packages` && packages.size)
    return ok(
      [...packages.values()]
        .reverse()
        .slice(
          Number(q.get("offset") || 0),
          Number(q.get("offset") || 0) + Number(q.get("limit") || 50),
        )
        .map((p) => ({
          id: p.package_id,
          run_id: p.run_id,
          profile_id: profile,
          job_revision_id: jd,
          outcome: { status: p.status },
        })),
    );
  m = p.match(/^preparation-artifacts\/([^/]+)\/product-view$/);
  if (m) {
    return ok(packages.get(m[1]) || packageFor("resume_tailoring", m[1]));
  }
  if (p === `applications/${id(1)}/submissions`) {
    if (method === "POST") {
      const old = submissions.find((s) => s.request_id === body.request_id);
      if (old) return ok(old);
      if (body.expected_revision !== revision) return fail("revision_conflict");
      const r = {
        ...body,
        id: newId(),
        application_id: id(1),
        event_id: newId(),
        created_at: time(),
      } as Submission;
      submissions.push(r);
      revision++;
      return ok(r);
    }
    if (submissions.length) return ok(page(submissions, q));
  }
  if (p === `applications/${id(1)}` && revision > 2) {
    const r = fixtureResponse(url).body as Record<string, unknown>;
    return ok({ ...r, revision, status: "applied" });
  }
  if (p === "mock-interviews" && method === "POST") {
    const r: Mock = {
      id: newId(),
      revision: 1,
      status: "ready_to_generate",
      generation_active: false,
      pending_question_id: null,
      stop_reason: null,
      completion_type: null,
      primary_question_count: 0,
      followup_count: 0,
      interviewer_turn_count: 0,
      policy: { primary_target: 3, followup_max: 1 },
      context: { job_id: id(2001), binding: body.context as Mock["context"]["binding"] },
      turns: [],
    };
    mocks.set(r.id, r);
    return ok(r);
  }
  if (p === "mock-interviews" && mocks.size)
    return ok(
      page(
        [...mocks.values()].map((m) => ({
          ...m,
          job_id: id(2001),
          created_at: time(),
          run_id: newId(),
        })),
        q,
      ),
    );
  m = p.match(/^mock-interviews\/([^/]+)(?:\/(answers|generate|end))?$/);
  if (m) {
    const r = mocks.get(m[1]);
    if (!r) return fail("not_found", 404);
    if (m[2]) {
      if (body.expected_revision !== r.revision) return fail("revision_conflict");
      r.revision++;
      if (m[2] === "end") {
        r.status = "completed";
        r.completion_type = "user_ended_early";
      } else if (m[2] === "answers") {
        const t = r.turns.find((t) => t.id === body.pending_question_id);
        if (!t || t.answer !== null) return fail("pending_question_mismatch");
        t.answer = String(body.answer);
        r.status = "ready_to_generate";
        r.pending_question_id = null;
        r.stop_reason = "provider_request_timeout";
      } else {
        const turn = {
          id: newId(),
          sequence: r.turns.length + 1,
          question: {
            kind: "primary",
            question: "请介绍你的 Python 项目。",
            topic: "项目",
            primary_entry_id: null,
          },
          answer: null,
          accepted_model_call_id: newId(),
        };
        r.turns.push(turn);
        r.primary_question_count++;
        r.interviewer_turn_count++;
        r.pending_question_id = turn.id;
        r.status = "waiting_answer";
        r.stop_reason = null;
      }
    }
    return ok(r);
  }
  if (p === "interviews" && method === "POST") {
    const r: Actual = {
      id: newId(),
      application_id: String(body.application_id),
      content_revision: 1,
      round_name: String(body.round_name),
      occurred_at: body.occurred_at as string | null,
      created_at: time(),
      entries: [],
      notes: [],
    };
    actuals.set(r.id, r);
    return ok(r);
  }
  if (p === "interviews" && actuals.size)
    return ok(
      [...actuals.values()].slice(
        Number(q.get("offset") || 0),
        Number(q.get("offset") || 0) + Number(q.get("limit") || 50),
      ),
    );
  m = p.match(/^interviews\/([^/]+)(?:\/(entries|notes))?$/);
  if (m) {
    let r = actuals.get(m[1]);
    if (!r && m[1] === id(8701)) {
      r = {
        id: id(8701),
        application_id: id(1),
        content_revision: 2,
        round_name: "技术一面",
        occurred_at: time(),
        created_at: time(),
        entries: [
          {
            entry_id: id(8702),
            order: 1,
            kind: "primary",
            question: "介绍项目",
            answer: "Python 服务",
            primary_entry_id: null,
          },
          {
            entry_id: id(8703),
            order: 2,
            kind: "follow_up",
            question: "如何验证？",
            answer: "通过测试",
            primary_entry_id: id(8702),
          },
        ],
        notes: [],
      };
      actuals.set(r.id, r);
    }
    if (!r) return fail("not_found", 404);
    if (method !== "GET") {
      if (body.expected_revision !== r.content_revision) return fail("revision_conflict");
      if (m[2] === "entries") r.entries.push(body.entry as Actual["entries"][number]);
      else if (m[2] === "notes") r.notes.push({ text: String(body.text), recorded_at: time() });
      else {
        if (body.entries) r.entries = body.entries as Actual["entries"];
        if (body.round_name) r.round_name = String(body.round_name);
      }
      r.content_revision++;
    }
    return ok(r);
  }
  if (p === `applications/${id(1)}/knowledge-notes`) return ok(page(notes, q));
  if (p === "knowledge-notes" && method === "POST") {
    const n = {
      ...body,
      id: newId(),
      created_at: time(),
      interview_id: null,
      source_document_id: null,
    };
    notes.push(n);
    return ok(n);
  }
  if (p === "interview-debriefs" && method === "POST") {
    const source = actuals.get(String(body.interview_id));
    if (!source) return fail("source_required");
    const r: Debrief = {
      id: newId(),
      root_run_id: "",
      run_id: newId(),
      status: "ready",
      source_hash: "b".repeat(64),
      event_sequence: 0,
      snapshot: {
        source_kind: "actual",
        interview_id: source.id,
        content_revision: source.content_revision,
        entries: structuredClone(source.entries),
      },
      artifacts: [],
    };
    r.root_run_id = r.id;
    debriefs.set(r.id, r);
    selected.set(r.id, r.id);
    return ok(r);
  }
  if (p === "interview-debriefs" && debriefs.size)
    return ok(
      page(
        [...debriefs.values()].reverse().map((d) => ({
          id: d.id,
          generation_id: d.id,
          selected_run_id: selected.get(d.root_run_id),
          root_run_id: d.root_run_id,
          is_selected: selected.get(d.root_run_id) === d.id,
          status: d.status,
          source_kind: d.snapshot.source_kind,
          source_id: d.snapshot.interview_id,
          created_at: time(),
        })),
        q,
      ),
    );
  m = p.match(/^interview-debriefs\/([^/]+)(?:\/(execute|events|regenerate))?$/);
  if (m) {
    let r = debriefs.get(m[1]);
    if (!r) return fail("not_found", 404);
    if (m[2] === "regenerate") {
      r = {
        ...structuredClone(r),
        id: newId(),
        run_id: newId(),
        status: "ready",
        artifacts: [],
        event_sequence: 0,
      };
      debriefs.set(r.id, r);
      selected.set(r.root_run_id, r.id);
      return ok(r);
    }
    if (m[2] === "execute") {
      r.status = "completed";
      const entries = r.snapshot.entries;
      r.artifacts = [
        {
          id: newId(),
          kind: "overall",
          group_index: null,
          status: "completed",
          error_code: null,
          attempts: 1,
          presentation: {
            display_order: 1000,
            evaluation: {
              strengths: [
                {
                  content: "能提供实例",
                  evidence: [
                    { question_number: 1, label: "主问题", preview: entries[0]?.question },
                  ],
                },
              ],
            },
          },
        },
        {
          id: newId(),
          kind: "group",
          group_index: 1,
          status: "completed",
          error_code: null,
          attempts: 1,
          presentation: {
            display_order: 1,
            qa: entries.map((e) => ({
              question: e.question,
              answer: e.answer,
              answer_missing: !e.answer,
              label: e.kind === "primary" ? "主问题" : "追问",
            })),
            evaluation: {
              strengths: [
                {
                  content: "回答具有具体依据",
                  evidence: [
                    { question_number: 1, label: "来自追问", preview: entries[1]?.question },
                  ],
                },
              ],
            },
          },
        },
      ];
      r.event_sequence = 3;
      return {
        status: 200,
        body: null,
        sse: [
          {
            sequence: 1,
            event: "overall_completed",
            display_section: "overall",
            display_order: 1000,
          },
          {
            sequence: 2,
            event: "group_completed",
            group_index: 1,
            display_section: "questions",
            display_order: 1,
          },
          { sequence: 3, event: "run_completed", display_section: "run", display_order: 1001 },
        ]
          .map((e) => `id: ${e.sequence}\nevent: ${e.event}\ndata: ${JSON.stringify(e)}\n\n`)
          .join(""),
      };
    }
    if (m[2] === "events") return ok([]);
    if (q.get("historical") !== "true") r = debriefs.get(selected.get(r.root_run_id)!) || r;
    return ok(r);
  }
  return undefined;
}
