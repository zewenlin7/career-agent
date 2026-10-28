import Link from "next/link";
import { TaskSummary } from "../workspace/task-summary";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Surface } from "@/components/ui/surface";
import { SectionHeading } from "@/components/ui/typography";
import { DateTime } from "@/components/product/read-state";
import { statusLabels, type ApplicationStatus, type ApplicationContext } from "./contracts";
import type { Summary, ReadState } from "./repository";

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge>{statusLabels[status]}</Badge>;
}
export function Pager({
  previous,
  next,
  label,
}: {
  previous?: string;
  next?: string;
  label: string;
}) {
  return (
    <nav aria-label={label} className="mt-5 flex flex-wrap items-center gap-5 text-sm">
      {previous ? (
        <Link
          prefetch={false}
          className="inline-flex min-h-11 items-center text-accent-ink underline underline-offset-4"
          href={previous}
        >
          上一页
        </Link>
      ) : (
        <span className="text-secondary">已在第一页</span>
      )}
      {next && (
        <Link
          prefetch={false}
          className="inline-flex min-h-11 items-center text-accent-ink underline underline-offset-4"
          href={next}
        >
          下一页
        </Link>
      )}
    </nav>
  );
}
export function Identity(_props: { values: [string, string][] }) {
  void _props;
  return null;
}
function SummaryCard<T>({
  title,
  result,
  empty,
  children,
}: {
  title: string;
  result: ReadState<T[]>;
  empty: string;
  children: (value: T[]) => ReactNode;
}) {
  return (
    <Surface aria-label={title}>
      <SectionHeading>{title}</SectionHeading>
      <div className="mt-3 space-y-2 text-sm text-secondary">
        {result.state === "unavailable" ? (
          <p role="status">暂时无法读取这部分记录，请重新加载页面。</p>
        ) : result.value.length ? (
          children(result.value)
        ) : (
          <p>{empty}</p>
        )}
      </div>
    </Surface>
  );
}
function items<T>(state: ReadState<{ items: T[] }>): ReadState<T[]> {
  return state.state === "ready" ? { state: "ready", value: state.value.items } : state;
}
const mockLabels = {
  ready_to_generate: "等待生成下一题",
  waiting_answer: "等待回答",
  completed: "已结束",
};
const debriefLabels = {
  ready: "待执行",
  running: "执行中",
  completed: "已完成",
  partial: "部分完成",
  failed: "执行失败",
};
export function SummaryRecords({
  context,
  summary,
}: {
  context: ApplicationContext;
  summary: Summary;
}) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <SummaryCard
        title="最新公司研究记录"
        result={items(summary.research)}
        empty="尚无公司研究记录。"
      >
        {([r]) => (
          <>
            <p>第 {r.research_version} 版 · 公司研究</p>
            <p>
              取得于 <DateTime value={r.fetched_at} />
            </p>
            <p>
              有效期至 <DateTime value={r.expires_at} />
            </p>
            <p>{r.reusable_for_current_execution ? "资料仍可使用" : "建议更新资料"}</p>
            <p className="text-xs">同一公司的研究资料可供不同职位参考。</p>
          </>
        )}
      </SummaryCard>
      <TaskSummary applicationId={context.application.id} />
      <SummaryCard
        title="最近实际投递"
        result={items(summary.submissions)}
        empty="尚无记录了实际使用材料的投递记录。"
      >
        {([r]) => (
          <>
            <p>
              记录于 <DateTime value={r.created_at} />
            </p>
            <p>此处展示实际投递时使用的材料。</p>
            <Identity
              values={[
                ["Submission", r.id],
                ["Resume revision", r.resume_revision_id],
                ["PDF artifact", r.render_artifact_id],
                ...(r.greeting_id ? [["Greeting", r.greeting_id] as [string, string]] : []),
                ...(r.package_id ? [["Package", r.package_id] as [string, string]] : []),
              ]}
            />
          </>
        )}
      </SummaryCard>
      <SummaryCard title="最近模拟面试" result={items(summary.mock)} empty="尚无模拟面试记录。">
        {([r]) => (
          <>
            <p>{mockLabels[r.status]}</p>
            <p>
              创建于 <DateTime value={r.created_at} />
            </p>
          </>
        )}
      </SummaryCard>
      <SummaryCard title="实际面试记录" result={summary.actual} empty="尚无实际面试录入。">
        {([r]) => (
          <>
            <p className="text-ink">{r.round_name}</p>
            <p>
              首条录入 · <DateTime value={r.created_at} />
            </p>
            {r.occurred_at && (
              <p>
                面试时间 <DateTime value={r.occurred_at} />
              </p>
            )}
            <p className="text-xs">现有列表按录入顺序返回；这里不推断最近一场或面试结果。</p>
          </>
        )}
      </SummaryCard>
      <SummaryCard
        title="最近复盘 generation"
        result={items(summary.debrief)}
        empty="尚无面试复盘记录。"
      >
        {([r]) => (
          <>
            <p>
              {r.source_kind === "actual" ? "真实面试" : "模拟面试"} · {debriefLabels[r.status]}
            </p>
            <p>
              <DateTime value={r.created_at} />
            </p>
            <p>{r.is_selected ? "该 generation 是对应复盘的 selected result" : "历史复盘结果"}</p>
          </>
        )}
      </SummaryCard>
    </div>
  );
}
