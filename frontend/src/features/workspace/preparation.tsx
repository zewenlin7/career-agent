"use client";
import Link from "next/link";
import { useState, useEffect, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { Context, Mode, Operation, Page, Result, Target } from "./contracts";
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
}: {
  ctx: Context;
  kind: "company_research" | "prepare_application" | "prepare_interview";
  target?: Target;
  onResult?: () => void;
  children?: ReactNode;
  onModeChange?: (mode: Mode) => void;
  selectedProfile?: string;
  onProfileChange?: (profile: string) => void;
}) {
  const binding = useRead<ApplicationBinding>(
    kind !== "company_research" ? `applications/${ctx.application.id}/context` : null,
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
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [force, setForce] = useState(false);
  const [intent, setIntent] = useState(0);
  const action = useAction(),
    requestId = useRequestId();
  const history = useRead<Page<HistoryItem>>(
    target
      ? `applications/${ctx.application.id}/results?target=${target}&limit=20&offset=${offset}`
      : null,
  );
  const reloadHistory = history.reload;
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
  const finish = (result: Operation) => {
    setOperation(result);
    if (result.status !== "running" && result.status !== "pending") {
      reloadHistory();
      onResult?.();
    }
  };
  const start = () =>
    action.run(async () => {
      if (missing) throw new ApiError("resume_selection_required");
      const choice = resumes.data?.items.find((r) => r.id === fitResume);
      const resolved = target === "fit_analysis" && choice ? await resolveResume(choice) : null;
      const b = binding.data;
      const body = {
        kind,
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
          ...(kind === "company_research" ? { force_research_refresh: force } : {}),
        },
      };
      const created = await api<Operation>(
        kind === "company_research" ? `companies/${ctx.company.id}/research` : "operations",
        "POST",
        { ...body, request_id: requestId({ intent, ...body }) },
      );
      setOperation(created);
      setSelected("");
      if (created.status === "pending")
        finish(await api<Operation>(`operations/${created.id}/execute`, "POST", {}));
      else finish(created);
      setIntent((n) => n + 1);
    });
  useEffect(() => {
    if (operation?.status !== "running") return;
    const timer = setInterval(() => {
      void api<Operation>(`operations/${operation.id}`)
        .then((result) => {
          setOperation(result);
          if (result.status !== "running") {
            reloadHistory();
            onResult?.();
          }
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [operation?.id, operation?.status, reloadHistory, onResult]);
  const busy = action.busy || operation?.status === "running";
  const item =
    history.data?.items.find((i) => i.result.target_artifact_id === selected) ||
    (!operation ? history.data?.items[0] : undefined);
  return (
    <Panel title={title}>
      {target && (
        <>
          <ReadState loaded={!!history.data} error={history.error} />
          {!!history.data?.items.length && (
            <Select
              label="历史结果"
              value={
                selected ||
                (!operation ? history.data.items[0].result.target_artifact_id : "") ||
                ""
              }
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">本次结果</option>
              {history.data.items.map((i) => (
                <option key={i.result.target_artifact_id} value={i.result.target_artifact_id || ""}>
                  {ctx.job.title} · {title} ·{" "}
                  {new Date(i.created_at).toLocaleString("zh-CN", {
                    month: "long",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </option>
              ))}
            </Select>
          )}
          {history.data && (offset > 0 || history.data.has_more) && (
            <Pages offset={offset} setOffset={setOffset} more={history.data.has_more} size={20} />
          )}
        </>
      )}
      {target === "fit_analysis" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Select
            label="个人资料（选填）"
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
            label="简历（选填）"
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
          <ErrorNotice code={profiles.error || resumes.error} />
        </div>
      )}
      {missing && target === "fit_analysis" && (
        <p className="text-sm text-secondary">请选择个人资料或简历。</p>
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
      <ErrorNotice code={binding.error} />
      {kind === "company_research" && (
        <label className="flex gap-2 text-sm">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          重新获取最新资料
        </label>
      )}
      <Button
        variant="primary"
        disabled={busy || missing || operation?.status === "recovery_required"}
        onClick={() => void start()}
      >
        {busy ? "正在生成…" : `开始${title}`}
      </Button>
      <ErrorNotice code={action.error || operation?.reason || undefined} />
      {operation?.status === "recovery_required" && <p>结果需要核对，请暂勿重复生成。</p>}
      {item ? (
        <ResultCard
          result={item.result}
          packageId=""
          applicationId={ctx.application.id}
          onSaved={reloadHistory}
        />
      ) : (
        operation?.package_id && (
          <PackageDetail id={operation.package_id} target={target} ctx={ctx} />
        )
      )}
      {children}
    </Panel>
  );
}
export function PreparationPage({
  ctx,
  target,
}: {
  ctx: Context;
  target: Target;
  selectedProfile?: string;
  onProfileChange?: (profile: string) => void;
}) {
  return (
    <OperationPanel
      ctx={ctx}
      kind={target === "interview_preparation" ? "prepare_interview" : "prepare_application"}
      target={target}
    />
  );
}
