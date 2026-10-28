"use client";
import { useState } from "react";
import type { Context, Mode, Research, Page } from "./contracts";
import { useRead } from "./client";
import { Panel, Pages, ReadState, Refs, Select } from "./ui";
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
      <p>更新于 {new Date(value.fetched_at).toLocaleString("zh-CN")}</p>
      <p className="text-sm">
        有效期至 {value.expires_at}；
        {value.reusable_for_current_execution ? "资料仍在有效期内" : "历史资料，建议更新"}。
      </p>
      <h3 className="font-semibold">有来源支持的结论</h3>
      <ul className="space-y-3">
        {value.data.report.conclusions.map((c, i) => (
          <li key={i}>
            {c.text}
            <ul className="mt-1 text-sm text-secondary">
              {c.evidence_refs.map((ref) => {
                const source = value.data.evidence.find((e) => e.id === ref);
                const href = source && safeUrl(source.source_url);
                return source ? (
                  <li key={ref}>
                    {href ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        {source.title}
                      </a>
                    ) : (
                      source.title
                    )}
                  </li>
                ) : null;
              })}
            </ul>
            <Refs values={{ evidence_refs: c.evidence_refs }} />
          </li>
        ))}
      </ul>
      <h3 className="font-semibold">推断（不作为已证实事实）</h3>
      <ul>
        {value.data.report.inference.map((c, i) => (
          <li key={i}>
            {c.text}
            <ul className="mt-1 text-sm text-secondary">
              {c.evidence_refs.map((ref) => {
                const source = value.data.evidence.find((e) => e.id === ref);
                const href = source && safeUrl(source.source_url);
                return source ? (
                  <li key={ref}>
                    {href ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        {source.title}
                      </a>
                    ) : (
                      source.title
                    )}
                  </li>
                ) : null;
              })}
            </ul>
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
            <p className="text-sm text-secondary">
              网页资料 · 抓取于 {new Date(e.retrieved_at).toLocaleString("zh-CN")}
            </p>
            <Refs values={{ id: e.id, provider: e.provider }} />
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
        <p>职位说明 · 第 {ctx.job.revision} 版</p>
        <details>
          <summary className="cursor-pointer">职位描述原文</summary>
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
      <OperationPanel
        ctx={ctx}
        kind="company_research"
        onModeChange={setMode}
        onResult={() => {
          setSelected("");
          setOffset(0);
          setRefresh((n) => n + 1);
        }}
      >
        <ResearchReads
          key={`${mode}:${refresh}`}
          company={ctx.company.id}
          mode={mode}
          offset={offset}
          setOffset={setOffset}
          selected={selected}
          setSelected={setSelected}
        />
      </OperationPanel>
      <h2 className="font-serif text-xl">岗位匹配</h2>
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
  const report =
    history.data?.items.find((r) => r.id === selected) ||
    (!selected ? current.data || history.data?.items[0] : undefined);
  return (
    <div className="space-y-5">
      <ReadState
        loaded={!!history.data}
        error={history.error}
        empty={history.data?.items.length === 0}
      />
      {!!history.data?.items.length && (
        <Select
          label="研究版本"
          value={report?.id || ""}
          onChange={(event) => setSelected(event.target.value)}
        >
          {current.data && !history.data.items.some((item) => item.id === current.data?.id) && (
            <option value={current.data.id}>
              最近研究 · {new Date(current.data.fetched_at).toLocaleString("zh-CN")}
            </option>
          )}
          {history.data.items.map((item) => (
            <option key={item.id} value={item.id}>
              公司研究 · {new Date(item.fetched_at).toLocaleString("zh-CN")}
            </option>
          ))}
        </Select>
      )}
      {history.data && <Pages offset={offset} setOffset={setOffset} more={history.data.has_more} />}
      {report && <Report value={report} />}
    </div>
  );
}
