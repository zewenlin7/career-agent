"use client";
import { SourceLinks } from "./source-links";
import { DeleteRecord } from "./delete-record";
import { taskMessage } from "./task-feedback";
import { visibleTaskErrors, taskChange } from "./task-tracker";
import { useResumeReplacement } from "./resume-replacement";
import { readHistory } from "./history";
import { ResultDestination } from "./result-destination";
import { researchRecordName, resultRecordName } from "./record-labels";
import { useResultHistory } from "./result-history";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useState, useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { Context, Operation, Page, Result, Target, Research } from "./contracts";
import { api, ApiError, useAction, useRead, useRequestId } from "./client";
import type { NamedProfile } from "../profile-area/personal";
import { resumeChoices, resolveResume, type ResumeChoice } from "../profile-area/library";
import type { ApplicationBinding } from "./application-binding";
import { ErrorNotice, Panel, Pages, ReadState, Select } from "./ui";
import { PackageDetail, ResultCard } from "./results";
type HistoryItem = { created_at: string; result: Result };
export function OperationPanel({
  ctx,
  kind,
  target,
  onResult,
  children,
  hasResearch = false,
}: {
  ctx: Context;
  kind: "company_research" | "prepare_application" | "prepare_interview";
  target?: Target;
  onResult?: (operation: Operation) => void;
  hasResearch?: boolean;
  children?: ReactNode;
}) {
  const replacement = useResumeReplacement(ctx.application.id);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    // A route transition starts before unmount. Late completion must not cancel it.
    const leaving = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
      const link =
        event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (
        link &&
        link.origin === window.location.origin &&
        link.pathname !== window.location.pathname
      )
        mounted.current = false;
    };
    document.addEventListener("click", leaving, true);
    return () => {
      mounted.current = false;
      document.removeEventListener("click", leaving, true);
    };
  }, []);
  const binding = useRead<ApplicationBinding>(
    kind !== "company_research" ? `applications/${ctx.application.id}/context` : null,
  );
  const [researchChoice, setResearchChoice] = useState("none");
  const researchChoices = useRead<Page<Research>>(
    target === "interview_preparation" ? `companies/${ctx.company.id}/research?mode=live` : null,
    readHistory<Research>,
  );
  const selectedResearch = researchChoices.data?.items.find((r) => r.id === researchChoice);
  const automaticResearch = useRead<Research>(
    target === "greeting_generation"
      ? `companies/${ctx.company.id}/research/current?mode=live`
      : null,
  );
  const [fitProfile, setFitProfile] = useState("");
  const [fitResume, setFitResume] = useState("");
  const profiles = useRead<{ items: NamedProfile[] }>(
    target === "fit_analysis" ? "profile-library" : null,
  );
  const resumes = useRead<{ items: ResumeChoice[] }>(
    target === "fit_analysis" ? "resume-library/versions?limit=100" : null,
    resumeChoices,
  );
  const [operation, setOperation] = useState<Operation>();
  const operationKey = `career-operation:${ctx.application.id}:${kind}:${target || "research"}`;
  const [restoring, setRestoring] = useState(!!operationKey);
  const [restoreError, setRestoreError] = useState<string>();
  const [offset, setOffset] = useState(0);
  const search = useSearchParams(),
    router = useRouter(),
    pathname = usePathname();
  const selectionChanged = useRef(false);
  const selectionRequest = useRef(0);
  const [selectionError, setSelectionError] = useState<string>();
  const [historyNotice, setHistoryNotice] = useState<string>();
  const [selecting, setSelecting] = useState<{ origin: string; token: number }>();
  const [confirmed, setConfirmed] = useState<HistoryItem>();
  const chooseResult = async (id: string) => {
    if (!target) return;
    selectionChanged.current = true;
    const request = ++selectionRequest.current;
    setSelectionError(undefined);
    setSelecting({ origin: selected, token: request });
    try {
      const row = await api<HistoryItem>(
        `preparation-artifacts/${id}/result?application_id=${ctx.application.id}`,
      );
      if (
        row.result.target_artifact_id !== id ||
        row.result.kind !== target ||
        row.result.available === false
      )
        throw new ApiError("not_found");
      if (!mounted.current || request !== selectionRequest.current) return;
      setConfirmed(row);
      setSelected(id);
      router.push(`${pathname}?result=${encodeURIComponent(id)}`, { scroll: false });
    } catch (error) {
      if (mounted.current && request === selectionRequest.current)
        setSelectionError(error instanceof ApiError ? error.code : "request_failed");
    } finally {
      if (mounted.current)
        setSelecting((current) => (current?.token === request ? undefined : current));
    }
  };
  const [localSelected, setSelected] = useState(
    search.get("result") || search.get("artifact") || "",
  );
  // Result selection remains authoritative for browser back/forward navigation.
  const selected = target ? search.get("result") || search.get("artifact") || "" : localSelected;
  useEffect(() => {
    selectionRequest.current++;
  }, [selected]);
  const [notice, setNotice] = useState<{ id: string; resultId: string; text: string }>();
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(undefined), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  const exact = useRead<HistoryItem>(
    selected && target
      ? `preparation-artifacts/${selected}/result?application_id=${ctx.application.id}`
      : null,
  );
  const [intent, setIntent] = useState(0);
  const [refining, setRefining] = useState(false);
  const action = useAction(),
    requestId = useRequestId();
  useEffect(() => {
    if (!operation?.id || !(action.error || operation.reason)) return;
    const key = `operations:${operation.id}`;
    visibleTaskErrors.add(key);
    window.dispatchEvent(new Event(taskChange));
    return () => {
      visibleTaskErrors.delete(key);
    };
  }, [operation?.id, operation?.reason, action.error]);
  const history = useResultHistory<HistoryItem>(
    target
      ? `applications/${ctx.application.id}/results?target=${target}&limit=20&offset=${offset}`
      : null,
    (row) => row.result.target_artifact_id,
  );
  const reloadHistory = history.reload;
  useEffect(() => {
    if (exact.data?.result.available !== false || !history.data || history.loading) return;
    const next = history.data.items[0]?.result.target_artifact_id;
    router.replace(next ? `${pathname}?result=${encodeURIComponent(next)}` : pathname, {
      scroll: false,
    });
  }, [exact.data, history.data, history.loading, pathname, router]);
  const title =
    kind === "company_research"
      ? "公司研究"
      : kind === "prepare_interview"
        ? "面试准备"
        : target === "fit_analysis"
          ? "岗位匹配"
          : target === "resume_tailoring"
            ? "简历优化"
            : "招呼语";
  const needsResume = kind !== "company_research" && target !== "fit_analysis";
  const missing =
    target === "fit_analysis"
      ? !fitProfile && !fitResume
      : kind !== "company_research" &&
        (!binding.data?.profile_id || (needsResume && !binding.data?.resume_revision_id));
  const notified = useRef<string | undefined>(undefined);
  const settled = useRef<string | undefined>(undefined);
  const finish = async (result: Operation, restoringResult = false) => {
    if (!mounted.current) return;
    setOperation(result);
    if (result.status !== "running" && result.status !== "pending") {
      if (settled.current !== result.id) {
        settled.current = result.id;
        setIntent((n) => n + 1);
      }
      if (
        operationKey &&
        result.status !== "recovery_required" &&
        sessionStorage.getItem(operationKey) === result.id
      )
        sessionStorage.removeItem(operationKey);
      if (result.status === "success") {
        if (notified.current === result.id) return;
        reloadHistory();
        if (target && result.package_id && !(restoringResult && selected)) {
          const view = await api<{ results: Result[] }>(
            `preparation-artifacts/${result.package_id}/product-view`,
          );
          const exactResult = view.results.find((item) => item.kind === target);
          if (!exactResult?.target_artifact_id || exactResult.status !== "success")
            throw new ApiError("fit_result_unavailable");
          if (mounted.current && !selectionChanged.current) {
            window.history.replaceState(
              null,
              "",
              `${pathname}?result=${encodeURIComponent(exactResult.target_artifact_id)}`,
            );
            if (target === "fit_analysis" && exactResult.reused)
              setNotice({
                id: result.id,
                resultId: exactResult.target_artifact_id,
                text: "已找到匹配分析。此前已使用相同的职位描述和求职材料完成分析，本次直接展示已有结果，未重新生成。",
              });
          }
        }
        notified.current = result.id;
        if (
          target === "resume_tailoring" &&
          mounted.current &&
          !restoringResult &&
          result.package_id
        ) {
          const view = await api<{ results: Result[] }>(
            `preparation-artifacts/${result.package_id}/product-view`,
          );
          const resume = view.results.find((item) => item.kind === target);
          if (resume?.resume_revision_id && !resume.reused)
            await replacement.offer(resume.resume_revision_id);
        }
        if (mounted.current && !(restoringResult && search.get("research"))) onResult?.(result);
      }
    }
  };
  const finishRef = useRef(finish);
  useEffect(() => {
    finishRef.current = finish;
  });
  useEffect(() => {
    if (!operationKey) return;
    let active = true;
    const id = sessionStorage.getItem(operationKey);
    // Read the original durable identity only. Never replay a pending/unknown execute.
    void (id ? api<Operation>(`operations/${id}`) : Promise.resolve(null))
      .then(async (op) => {
        if (active && op) await finishRef.current(op, true);
      })
      .catch((error) => {
        if (active)
          setRestoreError(error instanceof ApiError ? error.code : "connection_interrupted");
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, [operationKey]);
  const start = () =>
    action.run(async () => {
      if (missing) throw new ApiError("resume_selection_required");
      setNotice(undefined);
      selectionChanged.current = false;
      const choice = resumes.data?.items.find((r) => r.id === fitResume);
      const resolved = target === "fit_analysis" && choice ? await resolveResume(choice) : null;
      const b = binding.data;
      const body = {
        kind,
        ...(target === "fit_analysis" ? { application_id: ctx.application.id } : {}),
        ...(b && target !== "fit_analysis"
          ? { application_binding: { application_id: ctx.application.id, revision: b.revision } }
          : {}),
        request: {
          job_revision_id: b?.job_revision_id || ctx.job.job_revision_id,
          ...(kind !== "company_research"
            ? target === "fit_analysis"
              ? {
                  profile_id: fitProfile || resolved?.profile_id,
                  resume_revision_id: resolved?.id || null,
                  fit_input: fitProfile && fitResume ? "both" : fitResume ? "resume" : "profile",
                }
              : { profile_id: b?.profile_id, resume_revision_id: b?.resume_revision_id }
            : {}),
          mode: "live",
          ...(kind === "prepare_application" ? { targets: [target] } : {}),
          ...(kind === "company_research" ? { force_research_refresh: true } : {}),
          ...(target === "interview_preparation"
            ? {
                use_company_research: !!selectedResearch,
                research_report_id: selectedResearch?.id || null,
              }
            : {}),
        },
      };
      const created = await api<Operation>(
        kind === "company_research" ? `companies/${ctx.company.id}/research` : "operations",
        "POST",
        { ...body, request_id: requestId({ intent, ...body }) },
      );
      if (operationKey) sessionStorage.setItem(operationKey, created.id);
      if (mounted.current) setOperation(created);

      if (created.status === "pending")
        await finish(await api<Operation>(`operations/${created.id}/execute`, "POST", {}));
      else await finish(created);
    });
  useEffect(() => {
    if (operation?.status !== "running" && operation?.status !== "pending") return;
    const timer = setInterval(() => {
      void api<Operation>(`operations/${operation.id}`)
        .then((result) => finishRef.current(result))
        .catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [operation?.id, operation?.status]);
  const busy =
    action.busy ||
    restoring ||
    !!restoreError ||
    operation?.status === "running" ||
    operation?.status === "pending";
  const item = history.isRemoved(selected)
    ? undefined
    : (exact.data && exact.data.result.kind === target && exact.data.result.available !== false
        ? exact.data
        : undefined) ||
      (confirmed?.result.target_artifact_id === selected ? confirmed : undefined) ||
      history.data?.items.find((i) => i.result.target_artifact_id === selected) ||
      (!selected ? history.data?.items[0] : undefined);
  const startButton = (
    <Button
      variant="primary"
      disabled={
        busy ||
        refining ||
        missing ||
        (target === "interview_preparation" && !researchChoices.data) ||
        operation?.status === "recovery_required"
      }
      onClick={() => void start()}
    >
      {busy
        ? "正在生成…"
        : kind === "company_research"
          ? hasResearch
            ? "重新研究"
            : "开始研究"
          : target === "fit_analysis"
            ? "开始匹配"
            : target === "resume_tailoring"
              ? "开始优化"
              : target === "greeting_generation"
                ? "生成"
                : `开始${title}`}
    </Button>
  );
  const historySelector = target ? (
    <>
      <ReadState loaded={!!history.data} error={history.error} />
      {!!history.data?.items.length && (
        <Select
          inline
          label={
            target === "fit_analysis"
              ? "匹配记录"
              : target === "resume_tailoring"
                ? "优化记录"
                : target === "greeting_generation"
                  ? "招呼语记录"
                  : "准备记录"
          }
          value={selected || history.data.items[0]?.result.target_artifact_id || ""}
          onChange={(e) => void chooseResult(e.target.value)}
        >
          {exact.data &&
            exact.data.result.available !== false &&
            !history.isRemoved(selected) &&
            !history.data.items.some((i) => i.result.target_artifact_id === selected) && (
              <option value={selected}>
                {resultRecordName(
                  target,
                  ctx.company.name,
                  exact.data.result.context.job_title,
                  exact.data.created_at,
                  exact.data.result.resume_name,
                )}
              </option>
            )}
          {history.data.items.map((i) => (
            <option key={i.result.target_artifact_id} value={i.result.target_artifact_id || ""}>
              {resultRecordName(
                target,
                ctx.company.name,
                i.result.context.job_title,
                i.created_at,
                i.result.resume_name,
              )}
            </option>
          ))}
        </Select>
      )}
      {history.data && (offset > 0 || history.data.has_more) && (
        <Pages offset={offset} setOffset={setOffset} more={history.data.has_more} size={20} />
      )}
    </>
  ) : null;
  const material =
    target === "resume_tailoring" ||
    target === "greeting_generation" ||
    target === "interview_preparation";
  const Container =
    kind === "company_research" || target === "fit_analysis" || material ? PlainTask : Panel;
  return (
    <Container title={title}>
      {(kind === "company_research" || target === "fit_analysis" || material) && (
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {kind === "company_research" && startButton}
          {target === "resume_tailoring" && (
            <Link className="text-sm text-accent-ink underline" href="/profile/resumes">
              管理简历库
            </Link>
          )}
        </div>
      )}
      <ErrorNotice code={selectionError || exact.error} />
      {historyNotice && (
        <p role="alert" className="text-sm text-error">
          {historyNotice}
        </p>
      )}
      {selecting?.origin === selected && <p role="status">正在读取…</p>}
      {target !== "fit_analysis" && !material && historySelector}
      {item?.result.context.job_revision_id &&
        item.result.context.job_revision_id !== ctx.job.job_revision_id && (
          <p className="text-sm text-secondary">基于修改前的职位描述</p>
        )}
      {target === "fit_analysis" && (
        <div className="grid max-w-4xl items-end gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_auto]">
          <Select
            label="个人资料"
            value={fitProfile}
            disabled={busy}
            onChange={(e) => setFitProfile(e.target.value)}
          >
            <option value="">不使用</option>
            {profiles.data?.items
              .filter((p) => p.profile_id)
              .map((p) => (
                <option key={p.id} value={p.profile_id!}>
                  {p.name}
                </option>
              ))}
          </Select>
          <Select
            label="简历"
            value={fitResume}
            disabled={busy}
            onChange={(e) => setFitResume(e.target.value)}
          >
            <option value="">不使用</option>
            {resumes.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
          <div className="flex items-end">{startButton}</div>
        </div>
      )}
      {missing && target !== "fit_analysis" && (
        <p>
          请先在
          <Link className="underline" href={`/applications/${ctx.application.id}/summary`}>
            概览
          </Link>
          中选择简历。
        </p>
      )}
      <ErrorNotice code={binding.error || profiles.error || resumes.error} />
      {target === "interview_preparation" && (
        <div className="flex justify-center">
          <Select
            inline
            recordWidth="company"
            label="公司研究"
            value={researchChoice}
            disabled={busy}
            onChange={(e) => setResearchChoice(e.target.value)}
          >
            <option value="none">不使用</option>
            {researchChoices.data?.items
              .filter((r) => r.compatible_for_interview)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {researchRecordName(ctx.company.name, r.fetched_at)}
                </option>
              ))}
          </Select>
        </div>
      )}
      {material ? (
        <div className="space-y-2 text-center">
          <div className="flex justify-center">{startButton}</div>
          {binding.data?.resume_revision_id && (
            <SourceLinks
              applicationId={ctx.application.id}
              companyId={ctx.company.id}
              profile={target === "resume_tailoring" ? binding.data.profile_id : undefined}
              jd={binding.data.job_revision_id}
              resume={binding.data.resume_revision_id}
              resumeName={binding.data.resume_name}
              research={
                target === "interview_preparation"
                  ? selectedResearch?.id
                  : automaticResearch.data?.id
              }
              companyName={ctx.company.name}
              researchFetchedAt={
                target === "interview_preparation"
                  ? selectedResearch?.fetched_at
                  : automaticResearch.data?.fetched_at
              }
            />
          )}
        </div>
      ) : (
        kind !== "company_research" && target !== "fit_analysis" && startButton
      )}
      {action.error || operation?.reason ? (
        <p role="alert" className="text-base text-error">
          {taskMessage(title, {
            state: action.error ? "failure" : operation?.status || "unknown",
            reason: action.error || operation?.reason,
          })}
        </p>
      ) : (
        <ErrorNotice code={restoreError} />
      )}

      {operation?.status === "recovery_required" && <p>结果需要核对，请暂勿重复生成。</p>}
      {(target === "fit_analysis" || material) && historySelector}
      {notice && selected === notice.resultId && (
        <div role="status" className="flex items-start gap-3 text-sm text-secondary">
          <p>{notice.text}</p>
          <button
            aria-label="关闭复用提示"
            onClick={() => setNotice(undefined)}
            className="shrink-0"
          >
            ×
          </button>
        </div>
      )}
      {item ? (
        <ResultDestination
          identity={selected || item.result.target_artifact_id || ""}
          requested={search.get("result") || search.get("artifact")}
          ready={!history.loading && !binding.loading && !profiles.loading && !resumes.loading}
        >
          <ResultCard
            management={
              (target === "fit_analysis" || target === "interview_preparation") &&
              item.result.target_artifact_id && (
                <DeleteRecord
                  path={`applications/${ctx.application.id}/results/${item.result.target_artifact_id}`}
                  onDeleted={async () => {
                    const deleted = item.result.target_artifact_id!;
                    const remaining =
                      history.data?.items.filter(
                        (row) => row.result.target_artifact_id !== deleted,
                      ) || [];
                    history.exclude(deleted);
                    setConfirmed(remaining[0]);
                    setSelectionError(undefined);
                    setHistoryNotice(undefined);
                    const next = remaining[0]?.result.target_artifact_id;
                    window.history.replaceState(
                      null,
                      "",
                      next ? `${pathname}?result=${next}` : pathname,
                    );
                    try {
                      const fresh = await readHistory<HistoryItem>(
                        `applications/${ctx.application.id}/results?target=${target}`,
                        new AbortController().signal,
                      );
                      reloadHistory();
                      if (
                        window.location.pathname === pathname &&
                        (new URL(window.location.href).searchParams.get("result") || "") ===
                          (next || "")
                      ) {
                        const first = fresh.items.find(
                          (row) =>
                            row.result.target_artifact_id !== deleted &&
                            !history.isRemoved(row.result.target_artifact_id),
                        );
                        setConfirmed(first);
                        const firstId = first?.result.target_artifact_id;
                        window.history.replaceState(
                          null,
                          "",
                          firstId ? `${pathname}?result=${firstId}` : pathname,
                        );
                      }
                    } catch {
                      setHistoryNotice("记录已删除，历史记录暂时无法刷新，请稍后重试。");
                    }
                  }}
                />
              )
            }
            result={item.result}
            applicationId={ctx.application.id}
            onSaved={reloadHistory}
            disabled={busy}
            onBusyChange={setRefining}
          />
        </ResultDestination>
      ) : (
        !history.hasRemoved &&
        !selected &&
        operation?.status === "success" &&
        operation?.package_id && (
          <PackageDetail id={operation.package_id} target={target} ctx={ctx} />
        )
      )}
      {children}
      {replacement.confirmation}
    </Container>
  );
}
export function PreparationPage({ ctx, target }: { ctx: Context; target: Target }) {
  return (
    <OperationPanel
      ctx={ctx}
      kind={target === "interview_preparation" ? "prepare_interview" : "prepare_application"}
      target={target}
    />
  );
}

function PlainTask({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-5">
      {children}
    </section>
  );
}
