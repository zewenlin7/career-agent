import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageHeading, SectionHeading } from "@/components/ui/typography";
import { Surface } from "@/components/ui/surface";
import { ReadProblem, DateTime } from "@/components/product/read-state";
import { BackendError } from "@/lib/api/error";
import { applications, getApplicationContext } from "@/features/applications/server";
import { UUID_PATTERN, statusLabels } from "@/features/applications/contracts";
import { SummaryRecords } from "@/features/applications/views";
export const metadata: Metadata = { title: "Summary" };
export default async function Page({ params }: { params: Promise<{ applicationId: string }> }) {
  const id = (await params).applicationId.toLowerCase();
  if (!UUID_PATTERN.test(id)) notFound();
  let ctx;
  try {
    ctx = await getApplicationContext(id);
  } catch (error) {
    if (error instanceof BackendError && error.status === 404) notFound();
    return <ReadProblem href={`/applications/${id}/summary`} />;
  }
  const summary = await applications.summary(ctx);
  const events = [...ctx.application.events].sort((a, b) => b.sequence - a.sequence).slice(0, 5);
  const eventLabels: Record<string, string> = {
    created: "创建申请",
    status_changed: "状态变更",
    correction: "状态更正",
    note: "申请笔记",
  };
  return (
    <>
      <PageHeading title="Summary" description="申请事实与已有记录概览；以下时间使用北京时间。" />
      <Surface className="mb-5" aria-label="职位信息">
        <SectionHeading>当前职位与 JD</SectionHeading>
        <p className="mt-3 text-sm text-secondary">
          申请创建于 <DateTime value={ctx.application.created_at} /> · Application revision{" "}
          {ctx.application.revision}
        </p>
        <details className="mt-4">
          <summary className="cursor-pointer text-sm">
            查看当前 JD · 第 {ctx.job.revision} 版
          </summary>
          <p className="mt-4 max-w-[760px] whitespace-pre-wrap break-words text-sm leading-relaxed">
            {ctx.job.jd_text}
          </p>
        </details>
      </Surface>
      <SummaryRecords context={ctx} summary={summary} />
      <Surface className="mt-5" aria-label="最近申请记录">
        <SectionHeading>最近申请记录</SectionHeading>
        {events.length ? (
          <ol className="mt-4 space-y-5">
            {events.map((e) => (
              <li key={e.id} className="border-l-2 border-line pl-4 text-sm">
                <p className="font-medium">
                  {eventLabels[e.kind] || `业务记录（${e.kind}）`}
                  {e.to_status && ` · ${statusLabels[e.to_status]}`}
                </p>
                <p className="mt-1 text-xs text-secondary">
                  <DateTime value={e.created_at} /> · 事件序号 {e.sequence}
                </p>
                {e.note && (
                  <p className="mt-2 max-w-[760px] whitespace-pre-wrap break-words">{e.note}</p>
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-3 text-sm text-secondary">尚无申请事件。</p>
        )}
      </Surface>
    </>
  );
}
