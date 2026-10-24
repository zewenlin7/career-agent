"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { Context, Mode, Operation, Page, PackageRow, PackageView, Target } from "./contracts";
import { api, ApiError, useAction, useRead, useRequestId } from "./client";
import {
  BindingFields,
  ErrorNotice,
  ModeSelect,
  Panel,
  Pages,
  ReadState,
  Refs,
  Select,
  Status,
} from "./ui";
import { History, PackageDetail } from "./results";
export function OperationPanel({
  ctx,
  kind,
  target,
  onResult,
}: {
  ctx: Context;
  kind: "company_research" | "prepare_application" | "prepare_interview";
  target?: Target;
  onResult?: () => void;
}) {
  const [profile, setProfile] = useState(""),
    [resume, setResume] = useState(""),
    [mode, setMode] = useState<Mode>("fixture"),
    [force, setForce] = useState(false),
    [packageId, setPackageId] = useState(""),
    [operation, setOperation] = useState<Operation>(),
    [offset, setOffset] = useState(0),
    [packageOffset, setPackageOffset] = useState(0);
  const [intent, setIntent] = useState(0);
  const action = useAction(),
    requestId = useRequestId(),
    router = useRouter();
  const ops = useRead<Page<Operation>>(
    `operations?job_revision_id=${ctx.job.job_revision_id}&limit=10&offset=${offset}`,
  );
  const packages = useRead<PackageRow[]>(
    kind === "prepare_interview"
      ? `applications/${ctx.application.id}/preparation-packages?limit=10&offset=${packageOffset}`
      : null,
  );
  const selectedPackage = useRead<PackageView>(
    packageId ? `preparation-artifacts/${packageId}/product-view` : null,
  );
  const fromPackage = selectedPackage.data?.results.find(
    (r) => r.kind === "resume_tailoring" && r.status === "success",
  );
  const needsResume = kind !== "company_research" && target !== "fit_analysis";
  const create = () =>
    action.run(async () => {
      if (
        kind === "prepare_interview" &&
        (!fromPackage ||
          fromPackage.resume_revision_id !== resume ||
          fromPackage.context.profile_id !== profile ||
          fromPackage.context.job_revision_id !== ctx.job.job_revision_id)
      )
        throw new ApiError("context_revision_mismatch");
      const request = {
        job_revision_id: ctx.job.job_revision_id,
        profile_id: profile,
        mode,
        ...(kind === "prepare_application" ? { targets: [target] } : {}),
        ...(needsResume ? { resume_revision_id: resume } : {}),
        ...(kind === "prepare_interview" ? { application_package_id: packageId } : {}),
        ...(kind === "company_research" ? { force_research_refresh: force } : {}),
      };
      const body = { kind, request };
      const result = await api<Operation>(
        kind === "company_research" ? `companies/${ctx.company.id}/research` : "operations",
        "POST",
        { ...body, request_id: requestId({ intent, ...body }) },
      );
      setOperation(result);
      ops.reload();
    });
  const refresh = () =>
    action.run(async () => {
      if (operation) {
        const result = await api<Operation>(`operations/${operation.id}`);
        setOperation(result);
        ops.reload();
        onResult?.();
        router.refresh();
      }
    });
  const execute = () =>
    action.run(async () => {
      if (operation) {
        const result = await api<Operation>(`operations/${operation.id}/execute`, "POST", {});
        setOperation(result);
        ops.reload();
        onResult?.();
        router.refresh();
      }
    });
  return (
    <Panel
      title={
        kind === "company_research"
          ? "显式公司研究"
          : kind === "prepare_interview"
            ? "准备面试"
            : "生成准备结果"
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
        className="max-w-[760px] space-y-4"
      >
        <fieldset disabled={action.busy} className="space-y-4">
          <BindingFields
            ctx={ctx}
            profile={profile}
            setProfile={setProfile}
            resume={resume}
            setResume={setResume}
            needResume={needsResume}
          />
          <ModeSelect value={mode} onChange={setMode} />
          {kind === "company_research" && (
            <label className="flex gap-2 text-sm">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
              强制刷新公司研究及外部搜索 observation（Live 可能产生额外费用）
            </label>
          )}
          {kind === "prepare_interview" && (
            <>
              <Select
                label="已验收简历所在的 Application package"
                value={packageId}
                required
                onChange={(e) => setPackageId(e.target.value)}
              >
                <option value="">请选择 package</option>
                {packages.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id} · {p.outcome?.status}
                  </option>
                ))}
              </Select>
              <ErrorNotice code={packages.error} />
              {packages.data && (
                <Pages
                  offset={packageOffset}
                  setOffset={setPackageOffset}
                  more={packages.data.length === 10}
                />
              )}
              <ErrorNotice code={selectedPackage.error} />
              {fromPackage && (
                <p className="break-all text-sm">
                  此 package 使用 Resume {fromPackage.resume_revision_id}。上方须选择同一 exact
                  Resume 与 Profile。
                </p>
              )}
              <p className="text-sm">
                后端从该 package 固定加载 context，不会自动生成新的 Interview Prep 前置材料。
              </p>
            </>
          )}
          <p className="text-sm text-secondary">
            生成不会记录投递、发送消息或自动变更 Application 状态。先创建稳定操作，再明确执行。
          </p>
          <Button type="submit" variant="primary">
            创建操作
          </Button>
        </fieldset>
      </form>
      {operation && !["pending", "running", "recovery_required"].includes(operation.status) && (
        <Button
          disabled={action.busy}
          onClick={() => {
            setOperation(undefined);
            setIntent((n) => n + 1);
          }}
        >
          开始另一条明确请求
        </Button>
      )}
      <ErrorNotice code={action.error} />
      {action.busy && (
        <p role="status">请求处理中，请勿重复提交。断开连接不代表后台一定继续执行。</p>
      )}
      {operation && (
        <section className="space-y-3 border-t border-line pt-4" aria-label="当前操作">
          <Status value={operation.status} />
          {operation.reason && <p>原因：{operation.reason}</p>}
          <Refs
            values={{
              operation_id: operation.id,
              run_id: operation.run_id,
              request_id: operation.request_id,
              package_id: operation.package_id,
              research_report_id: operation.research_report_id,
            }}
          />
          <p className="break-all text-sm">操作 ID：{operation.id}</p>
          <div className="flex gap-3">
            {operation.status === "pending" && operation.allowed_actions.includes("execute") && (
              <Button
                disabled={action.busy || !!action.error}
                variant="primary"
                onClick={() => void execute()}
              >
                执行操作
              </Button>
            )}
            <Button disabled={action.busy} onClick={() => void refresh()}>
              重新查询操作
            </Button>
          </div>
          {["needs_input", "decision_required"].includes(operation.status) && (
            <p>
              本次操作已结束。请核对缺失 binding
              或分析结果；明确选择后创建新操作，后端按兼容性复用已有结果。
            </p>
          )}
          {operation.status === "recovery_required" && (
            <p>需在 Internal 中处理恢复事件；此处不自动重试。</p>
          )}
          {operation.package_id && (
            <PackageDetail id={operation.package_id} target={target} ctx={ctx} />
          )}
        </section>
      )}
      <details>
        <summary className="cursor-pointer">重新发现当前 JD 的已保存操作</summary>
        <Button onClick={ops.reload}>刷新列表</Button>
        <ReadState loaded={!!ops.data} error={ops.error} />
        <ul className="space-y-2">
          {ops.data?.items
            .filter((o) => o.kind === kind)
            .map((o) => (
              <li key={o.id}>
                <Button onClick={() => setOperation(o)}>
                  {o.kind} · {o.status} · {o.id}
                </Button>
              </li>
            ))}
        </ul>
        {ops.data && <Pages offset={offset} setOffset={setOffset} more={ops.data.has_more} />}
      </details>
    </Panel>
  );
}
export function PreparationPage({ ctx, target }: { ctx: Context; target: Target }) {
  const [refresh, setRefresh] = useState(0);
  return (
    <div className="space-y-6">
      <OperationPanel
        ctx={ctx}
        kind={target === "interview_preparation" ? "prepare_interview" : "prepare_application"}
        target={target}
        onResult={() => setRefresh((n) => n + 1)}
      />
      <History key={refresh} ctx={ctx} target={target} />
    </div>
  );
}
