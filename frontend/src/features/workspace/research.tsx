"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Context, Mode, Research, Page } from "./contracts";
import { useRead } from "./client";
import { ModeSelect, Panel, Pages, ReadState, Refs } from "./ui";
import { OperationPanel, PreparationPage } from "./preparation";
function safeUrl(raw: string) {
  try {
    const u = new URL(raw);
    return ["https:", "http:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
function Report({ value }: { value: Research }) {
  return (
    <article className="space-y-4">
      <p>
        研究版本 {value.research_version} · {value.data.mode} · 取得于 {value.fetched_at}
      </p>
      <p className="text-sm">
        有效期至 {value.expires_at}；
        {value.reusable_for_current_execution ? "后端确认可复用" : "历史可读，不代表当前可复用"}。
      </p>
      <h3 className="font-semibold">有来源支持的结论</h3>
      <ul className="space-y-3">
        {value.data.report.conclusions.map((c, i) => (
          <li key={i}>
            {c.text}
            <Refs values={{ evidence_refs: c.evidence_refs }} />
          </li>
        ))}
      </ul>
      <h3 className="font-semibold">推断（不作为已证实事实）</h3>
      <ul>
        {value.data.report.inference.map((c, i) => (
          <li key={i}>
            {c.text}
            <Refs values={{ evidence_refs: c.evidence_refs }} />
          </li>
        ))}
      </ul>
      <h3 className="font-semibold">未知事项</h3>
      <ul>
        {value.data.report.unknowns.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
      <details>
        <summary className="cursor-pointer">外部证据与来源</summary>
        {value.data.evidence.map((e) => (
          <article key={e.id} className="mt-3 space-y-2">
            <p>
              {safeUrl(e.source_url) ? (
                <a
                  href={safeUrl(e.source_url)!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  {e.title}
                </a>
              ) : (
                e.title
              )}
            </p>
            <p className="whitespace-pre-wrap text-sm">{e.content}</p>
            <Refs values={{ id: e.id, provider: e.provider, retrieved_at: e.retrieved_at }} />
          </article>
        ))}
      </details>
      <Refs values={{ research_report_id: value.id, company_id: value.company_id }} />
    </article>
  );
}
export function ResearchFit({ ctx }: { ctx: Context }) {
  const [mode, setMode] = useState<Mode>("live"),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState(""),
    [refresh, setRefresh] = useState(0);
  return (
    <div className="space-y-7">
      <Panel title="当前职位与要求">
        <p>
          JD revision {ctx.job.revision} · {ctx.job.job_revision_id}
        </p>
        <details>
          <summary className="cursor-pointer">JD 原文</summary>
          <p className="whitespace-pre-wrap">{ctx.job.jd_text}</p>
        </details>
        <ul className="space-y-3">
          {ctx.job.requirements.map((r) => (
            <li key={r.id}>
              <p>{r.text}</p>
              <Refs values={r} />
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title={`${ctx.company.name} · 公司研究`}>
        <p className="text-sm">
          同公司各职位复用公司研究；不是本 Application 独有。当前结果由后端 freshness /
          compatibility 决定。
        </p>
        <ModeSelect value={mode} onChange={setMode} />
        <ResearchReads
          key={`${mode}:${refresh}`}
          company={ctx.company.id}
          mode={mode}
          offset={offset}
          setOffset={setOffset}
          selected={selected}
          setSelected={setSelected}
        />
      </Panel>
      <OperationPanel ctx={ctx} kind="company_research" onResult={() => setRefresh((n) => n + 1)} />
      <h2 className="font-serif text-xl">Fit Analysis</h2>
      <PreparationPage ctx={ctx} target="fit_analysis" />
    </div>
  );
}
function ResearchReads({
  company,
  mode,
  offset,
  setOffset,
  selected,
  setSelected,
}: {
  company: string;
  mode: Mode;
  offset: number;
  setOffset: (n: number) => void;
  selected: string;
  setSelected: (s: string) => void;
}) {
  const current = useRead<Research>(`companies/${company}/research/current?mode=${mode}`),
    history = useRead<Page<Research>>(
      `companies/${company}/research?mode=${mode}&limit=10&offset=${offset}`,
    );
  const report = history.data?.items.find((r) => r.id === selected);
  return (
    <div className="space-y-5">
      <h3 className="font-semibold">当前可复用研究</h3>
      <ReadState loaded={!!current.data} error={current.error} />
      {current.data && <Report value={current.data} />}
      <h3 className="font-semibold">研究历史</h3>
      <ReadState
        loaded={!!history.data}
        error={history.error}
        empty={history.data?.items.length === 0}
      />
      <ul>
        {history.data?.items.map((r) => (
          <li key={r.id}>
            <Button onClick={() => setSelected(r.id)}>
              研究版本 {r.research_version} · {r.fetched_at}
            </Button>
          </li>
        ))}
      </ul>
      {history.data && <Pages offset={offset} setOffset={setOffset} more={history.data.has_more} />}{" "}
      {report && <Report value={report} />}
    </div>
  );
}
