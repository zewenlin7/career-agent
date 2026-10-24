"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Context, PackageRow, PackageView, Result, Submission, Page } from "./contracts";
import { api, endpoint, useRead } from "./client";
import { Panel, Pages, ReadState, Refs, Status } from "./ui";
import { collectSubmissionHistory } from "./submission-history";
export const readSubmissions = (path: string, signal: AbortSignal) =>
  collectSubmissionHistory((offset) =>
    api<Page<Submission>>(`${path}?limit=100&offset=${offset}`, "GET", undefined, signal),
  );
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const text = (v: unknown) => (typeof v === "string" ? v : "");
const labels: Record<string, string> = {
  matched: "有事实支持",
  partial: "部分匹配",
  no_evidence: "暂无证据（不等于不具备）",
  explicit_gap: "明确差距",
  strengths: "优势",
  issues: "问题",
  knowledge_gap_hypotheses: "知识缺口假设",
  improvement_suggestions: "改进建议",
  recurring_issues: "反复出现的问题",
  practice_recommendations: "练习建议",
  knowledge_candidates: "知识候选（未写入知识库）",
  technical_questions: "技术问题",
  project_deep_dive_questions: "项目深挖",
  behavioral_questions: "行为问题",
  company_specific_questions: "公司相关问题",
  summary: "概述",
  education: "教育经历",
  experience: "工作经历",
  projects: "项目经历",
  skills: "技能",
};
export function ResumeContent({ content }: { content: Record<string, unknown> }) {
  return (
    <div className="space-y-5 max-w-[760px]">
      {list(content.sections).map((raw, i) => {
        const s = obj(raw);
        return (
          <section key={i}>
            <h3 className="font-semibold">{labels[text(s.name)] || text(s.name)}</h3>
            <ul className="mt-2 space-y-2">
              {list(s.items).map((raw, j) => {
                const item = obj(raw);
                return (
                  <li key={j} className="whitespace-pre-wrap break-words">
                    {text(item.text)}
                    <Refs
                      values={{
                        fact_refs: item.fact_refs,
                        requirement_refs: item.requirement_refs,
                      }}
                    />
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
export function ResultContent({
  result,
  requirements = {},
}: {
  result: Result;
  requirements?: Record<string, string>;
}) {
  const c = result.content;
  if (!c) return null;
  if (result.kind === "resume_tailoring") return <ResumeContent content={c} />;
  if (result.kind === "greeting_generation")
    return <p className="max-w-[760px] whitespace-pre-wrap break-words">{text(c.greeting_text)}</p>;
  if (result.kind === "fit_analysis")
    return (
      <ul className="space-y-4">
        {list(c.items).map((raw, i) => {
          const x = obj(raw);
          return (
            <li key={i} className="border-b border-line pb-4">
              <h4 className="mb-3 font-semibold">
                {requirements[text(x.requirement_ref)] ||
                  "要求原文暂未读取（见 exact requirement ref）"}
              </h4>
              <Status value={labels[text(x.status)] || text(x.status)} />
              <p className="mt-3 whitespace-pre-wrap">{text(x.explanation)}</p>
              {text(x.missing_evidence) && (
                <p className="text-sm text-secondary">待补证据：{text(x.missing_evidence)}</p>
              )}
              <Refs values={{ requirement_ref: x.requirement_ref, fact_refs: x.fact_refs }} />
            </li>
          );
        })}
      </ul>
    );
  return (
    <div className="max-w-[760px] space-y-5">
      {["likely_topics", "knowledge_gaps", "questions_to_ask_interviewer"].map((k) => (
        <section key={k}>
          <h3 className="font-semibold">
            {
              {
                likely_topics: "可能涉及的话题",
                knowledge_gaps: "待补知识",
                questions_to_ask_interviewer: "可向面试官提问",
              }[k]
            }
          </h3>
          <ul className="list-disc pl-5">
            {list(c[k]).map((s, i) => (
              <li key={i}>{text(s)}</li>
            ))}
          </ul>
        </section>
      ))}
      {[
        "technical_questions",
        "project_deep_dive_questions",
        "behavioral_questions",
        "company_specific_questions",
      ].map((k) => (
        <section key={k}>
          <h3 className="font-semibold">{labels[k]}</h3>
          {list(c[k]).map((raw, i) => {
            const q = obj(raw);
            return (
              <article key={i} className="mt-4 border-l border-line pl-4">
                <p>{text(q.question)}</p>
                <p className="text-sm text-secondary">
                  {text(q.why_likely)} · {text(q.what_is_being_tested)}
                </p>
                <ul className="list-disc pl-5">
                  {list(q.answer_outline).map((s, j) => (
                    <li key={j}>{text(s)}</li>
                  ))}
                </ul>
                <Refs
                  values={{
                    fact_refs: q.related_fact_refs,
                    requirement_refs: q.related_requirement_refs,
                  }}
                />
              </article>
            );
          })}
        </section>
      ))}
    </div>
  );
}
export function PdfLinks({ id }: { id: string }) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="space-y-3">
      <div className="flex gap-4">
        <Button onClick={() => setPreview(!preview)}>
          {preview ? "关闭 PDF 预览" : "预览 PDF"}
        </Button>
        <a
          className="inline-flex min-h-11 items-center text-accent-ink underline"
          href={endpoint(`artifacts/${id}/download`)}
        >
          下载 PDF
        </a>
      </div>
      {preview && (
        <>
          <iframe
            title="简历 PDF 预览"
            src={endpoint(`artifacts/${id}/download?inline=true`)}
            className="h-[640px] w-full border border-line"
          />
          <p className="text-sm">浏览器无法预览时，请使用下载链接；文件缺失或损坏仍由后端拒绝。</p>
        </>
      )}
    </div>
  );
}
export function ResultCard({
  result,
  packageId,
  submissions = [],
}: {
  result: Result;
  packageId: string;
  submissions?: Submission[];
}) {
  const jd = useRead<{ job_id: string; requirements: { id: string; text: string }[] }>(
    result.kind === "fit_analysis" ? `job-revisions/${result.context.job_revision_id}` : null,
  );
  const requirements =
    jd.data?.job_id === result.context.job_id
      ? Object.fromEntries(jd.data.requirements.map((r) => [r.id, r.text]))
      : {};
  const used = submissions.filter((s) =>
    result.kind === "resume_tailoring"
      ? s.resume_revision_id === result.resume_revision_id
      : result.kind === "greeting_generation" && s.greeting_id === result.result_id,
  );
  return (
    <article className="space-y-4 border-t border-line pt-4">
      <div className="flex flex-wrap gap-3">
        <Status value={result.status} />
        <span className="text-sm">{result.reused ? "复用已有结果" : "本次结果"}</span>
        {used.length > 0 && <span className="text-sm">已用于真实 Submission</span>}
      </div>
      {result.reason && <p className="text-sm">原因：{result.reason}</p>}
      <ResultContent result={result} requirements={requirements} />
      {result.content && result.kind === "greeting_generation" && (
        <Refs
          values={{
            fact_refs: result.content.fact_refs,
            requirement_refs: result.content.requirement_refs,
          }}
        />
      )}
      {result.download_url && result.render_artifact_id && (
        <PdfLinks id={result.render_artifact_id} />
      )}
      <Refs
        values={{
          package_id: packageId,
          result_id: result.result_id,
          source_resume_revision_id: result.source_resume_revision_id,
          resume_revision_id: result.resume_revision_id,
          revision: result.revision,
          render_artifact_id: result.render_artifact_id,
          ...result.context,
          versions: result.versions,
        }}
      />
    </article>
  );
}
export function PackageDetail({
  id,
  target,
  ctx,
  submissions = [],
}: {
  id: string;
  target?: string;
  ctx: Context;
  submissions?: Submission[];
}) {
  const read = useRead<PackageView>(`preparation-artifacts/${id}/product-view`);
  const invalid = read.data?.results.some(
    (r) => r.context.job_id !== ctx.job.id || r.context.company_id !== ctx.company.id,
  );
  return (
    <div className="space-y-4">
      <ReadState loaded={!!read.data} error={invalid ? "context_revision_mismatch" : read.error} />
      {read.data && !invalid && (
        <>
          <Status value={read.data.status} />
          {read.data.results
            .filter((r) => !target || r.kind === target)
            .map((r) => (
              <ResultCard key={r.kind} result={r} packageId={id} submissions={submissions} />
            ))}
          {target && !read.data.results.some((r) => r.kind === target) && (
            <p>此 package 没有请求该结果。</p>
          )}
        </>
      )}
    </div>
  );
}
export function History({ ctx, target }: { ctx: Context; target: string }) {
  const [offset, setOffset] = useState(0),
    [selected, setSelected] = useState("");
  const rows = useRead<PackageRow[]>(
    `applications/${ctx.application.id}/preparation-packages?limit=10&offset=${offset}`,
  );
  const subs = useRead<Submission[]>(
    `applications/${ctx.application.id}/submissions`,
    readSubmissions,
  );
  return (
    <Panel title="准备结果与历史">
      <ReadState loaded={!!rows.data} error={rows.error} empty={rows.data?.length === 0} />
      <ul className="space-y-2">
        {rows.data?.map((r) => (
          <li key={r.id}>
            <Button onClick={() => setSelected(r.id)} aria-pressed={selected === r.id}>
              {r.outcome?.status || "历史结果"} ·{" "}
              {r.job_revision_id === ctx.job.job_revision_id ? "当前 JD" : "历史 JD"} · {r.id}
            </Button>
          </li>
        ))}
      </ul>
      {rows.data && <Pages offset={offset} setOffset={setOffset} more={rows.data.length === 10} />}
      <p className="text-sm text-secondary">
        按后端 package 历史顺序展示；选择后只读取该 package
        的对应结果。生成记录不代表当前选择或实际使用。
      </p>
      {subs.error && <p>实际使用记录暂时不可读取。</p>}
      {selected && (
        <PackageDetail id={selected} target={target} ctx={ctx} submissions={subs.data} />
      )}
    </Panel>
  );
}
export function Evaluation({ value }: { value: Record<string, unknown> }) {
  return (
    <div className="space-y-4">
      {Object.entries(labels)
        .filter(([k]) => Array.isArray(value[k]))
        .map(([k, label]) => (
          <section key={k}>
            <h4 className="font-semibold">{label}</h4>
            <ul className="space-y-2">
              {list(value[k]).map((raw, i) => {
                const f = obj(raw);
                return (
                  <li key={i}>
                    <p>{text(f.content)}</p>
                    <ul className="text-sm text-secondary">
                      {list(f.evidence).map((raw, j) => {
                        const e = obj(raw);
                        return (
                          <li key={j}>
                            第 {String(e.question_number)} 题 · {text(e.label)}：{text(e.preview)}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      {!!value.example_answer && (
        <section>
          <h4 className="font-semibold">示例回答</h4>
          <p>{text(obj(value.example_answer).content)}</p>
        </section>
      )}
    </div>
  );
}
