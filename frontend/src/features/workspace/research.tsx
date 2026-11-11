"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { JDEditor } from "../applications/jd-editor";
import type { Context, Research } from "./contracts";
import { DeleteRecord } from "./delete-record";
import { api, ApiError, useRead } from "./client";
import { readHistory } from "./history";
import { ReadState, Select } from "./ui";
import { OperationPanel, PreparationPage } from "./preparation";
import { ResultDestination } from "./result-destination";
import { researchRecordName } from "./record-labels";
import { useResultHistory } from "./result-history";
export type ResearchSection = "description" | "company" | "fit";
function safeUrl(raw: string) {
  try {
    const u = new URL(raw);
    return ["https:", "http:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
function Report({ value, management }: { value: Research; management?: ReactNode }) {
  let first = true;
  const heading = (title: string) => {
    const action = first ? management : null;
    first = false;
    return (
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">{title}</h3>
        {action}
      </div>
    );
  };
  return (
    <article className="space-y-6 text-base font-normal leading-relaxed">
      {(
        [
          ["研究结论", value.data.report.conclusions],
          ["推断", value.data.report.inference],
        ] as const
      )
        .filter(([, items]) => items.length > 0)
        .map(([title, items]) => (
          <section key={title}>
            {heading(title)}
            <ul className="space-y-4">
              {items.map((item, index) => (
                <li key={index}>
                  <p>{item.text}</p>
                  <ul className="mt-1 flex flex-wrap gap-x-3 text-sm text-secondary">
                    {item.evidence_refs.map((ref) => {
                      const source = value.data.evidence.find((e) => e.id === ref);
                      if (!source) return null;
                      const href = safeUrl(source.source_url);
                      return (
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
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        ))}
      {value.data.report.unknowns.length > 0 && (
        <section>
          {heading("未知事项")}
          <ul className="space-y-2">
            {value.data.report.unknowns.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
export function ResearchFit({ ctx, section }: { ctx: Context; section: ResearchSection }) {
  if (section === "description") return <JobDescription ctx={ctx} />;
  if (section === "fit") return <PreparationPage ctx={ctx} target="fit_analysis" />;
  return <CompanyResearch ctx={ctx} />;
}
function JobDescription({ ctx }: { ctx: Context }) {
  const revision = useSearchParams().get("revision");
  const exact = useRead<{ job_id: string; jd_text: string; created_at: string }>(
    revision ? `job-revisions/${revision}` : null,
  );
  if (!revision)
    return (
      <section id="job-description">
        <JDEditor
          applicationId={ctx.application.id}
          revision={ctx.job.revision}
          revisionId={ctx.job.job_revision_id}
          text={ctx.job.jd_text}
        />
      </section>
    );
  return (
    <section id="job-description" className="min-w-0 space-y-4">
      <h1 className="text-2xl font-semibold">职位描述</h1>
      <ReadState
        loaded={!!exact.data}
        error={
          exact.error ||
          (exact.data && exact.data.job_id !== ctx.job.id ? "context_revision_mismatch" : undefined)
        }
      />
      {exact.data?.job_id === ctx.job.id && (
        <p className="whitespace-pre-wrap text-base font-normal leading-relaxed [overflow-wrap:anywhere]">
          {exact.data.jd_text}
        </p>
      )}
    </section>
  );
}
function CompanyResearch({ ctx }: { ctx: Context }) {
  const search = useSearchParams(),
    router = useRouter(),
    path = usePathname();
  const [selectionError, setSelectionError] = useState<string>();
  const [selecting, setSelecting] = useState<{ origin: string; token: number }>();
  const [historyNotice, setHistoryNotice] = useState<string>();
  const [confirmed, setConfirmed] = useState<Research>();
  const selectionRequest = useRef(0);
  useEffect(
    () => () => {
      selectionRequest.current++;
    },
    [],
  );
  const history = useResultHistory<Research>(
    `companies/${ctx.company.id}/research`,
    (row) => row.id,
  );
  const requested = search.get("research") || "";
  useEffect(() => {
    selectionRequest.current++;
  }, [requested]);
  const selected = (!history.isRemoved(requested) && requested) || history.data?.items[0]?.id || "";
  const exact = useRead<Research>(
    selected ? `companies/${ctx.company.id}/research/${selected}` : null,
  );
  const displayed = history.isRemoved(selected)
    ? undefined
    : exact.data || (confirmed?.id === selected ? confirmed : undefined);
  const select = async (id: string) => {
    const request = ++selectionRequest.current;
    setSelectionError(undefined);
    setSelecting({ origin: requested, token: request });
    try {
      const row = await api<Research>(`companies/${ctx.company.id}/research/${id}`);
      if (row.id !== id || row.company_id !== ctx.company.id)
        throw new ApiError("invalid_response");
      if (request !== selectionRequest.current) return;
      setConfirmed(row);
      const href = `${path}?research=${encodeURIComponent(id)}`;
      router.push(href, { scroll: false });
    } catch (error) {
      if (request === selectionRequest.current)
        setSelectionError(error instanceof ApiError ? error.code : "request_failed");
    } finally {
      setSelecting((current) => (current?.token === request ? undefined : current));
    }
  };
  const items = history.data?.items || [];
  return (
    <OperationPanel
      ctx={ctx}
      kind="company_research"
      hasResearch={!!selected}
      onResult={(op) => {
        if (op.status === "success" && op.research_report_id) {
          history.reload();
          if (window.location.pathname === path)
            window.history.replaceState(null, "", `${path}?research=${op.research_report_id}`);
        }
      }}
    >
      <ReadState
        loaded={!!history.data}
        error={history.error}
        empty={!!history.data && !items.length && !selected}
      />
      {(items.length > 0 || selected) && (
        <Select
          inline
          recordWidth="company"
          label="研究记录"
          value={selected}
          onChange={(e) => void select(e.target.value)}
        >
          {selected && !items.some((item) => item.id === selected) && (
            <option value={selected}>
              {researchRecordName(ctx.company.name, displayed?.fetched_at)}
            </option>
          )}
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {researchRecordName(ctx.company.name, item.fetched_at)}
            </option>
          ))}
        </Select>
      )}
      {historyNotice && (
        <p role="alert" className="text-sm text-error">
          {historyNotice}
        </p>
      )}
      {(selectionError || exact.error) && (
        <div>
          <p role="alert" className="text-sm text-error">
            {(selectionError || exact.error) === "not_found"
              ? "未找到这份研究记录。"
              : "暂时无法读取这份研究，请重试。"}
          </p>
          {!selectionError && <Button onClick={exact.reload}>重试</Button>}
        </div>
      )}
      {(selecting?.origin === requested || (exact.loading && !displayed)) && (
        <p role="status">正在读取…</p>
      )}
      {displayed && (
        <ResultDestination
          identity={displayed.id}
          requested={search.get("research")}
          ready={!history.loading}
        >
          <Report
            value={displayed}
            management={
              <DeleteRecord
                path={`companies/${ctx.company.id}/research/${displayed.id}`}
                onDeleted={async () => {
                  const deleted = displayed.id;
                  const remaining = items.filter((row) => row.id !== deleted);
                  history.exclude(deleted);
                  setConfirmed(remaining[0]);
                  setSelectionError(undefined);
                  setHistoryNotice(undefined);
                  const next = remaining[0]?.id;
                  window.history.replaceState(null, "", next ? `${path}?research=${next}` : path);
                  try {
                    const fresh = await readHistory<Research>(
                      `companies/${ctx.company.id}/research`,
                      new AbortController().signal,
                    );
                    history.reload();
                    if (
                      window.location.pathname === path &&
                      (new URL(window.location.href).searchParams.get("research") || "") ===
                        (next || "")
                    ) {
                      const first = fresh.items.find(
                        (row) => row.id !== deleted && !history.isRemoved(row.id),
                      );
                      setConfirmed(first);
                      window.history.replaceState(
                        null,
                        "",
                        first ? `${path}?research=${first.id}` : path,
                      );
                    }
                  } catch {
                    setHistoryNotice("记录已删除，历史记录暂时无法刷新，请稍后重试。");
                  }
                }}
              />
            }
          />
        </ResultDestination>
      )}
    </OperationPanel>
  );
}
