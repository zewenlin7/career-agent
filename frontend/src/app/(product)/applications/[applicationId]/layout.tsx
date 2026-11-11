import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { Navigation } from "@/components/layout/navigation";
import { applicationNavigation } from "@/lib/navigation";
import { BackendError } from "@/lib/api/error";
import { ReadProblem, DateTime } from "@/components/product/read-state";
import { applications, getApplicationContext } from "@/features/applications/server";
import { optionalRead } from "@/features/applications/repository";
import { UUID_PATTERN } from "@/features/applications/contracts";
import { ApplicationStatusBadge } from "@/features/applications/views";

export default async function ApplicationLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ applicationId: string }>;
}) {
  const id = (await params).applicationId.toLowerCase();
  if (!UUID_PATTERN.test(id)) notFound();
  let ctx;
  try {
    ctx = await getApplicationContext(id);
  } catch (error) {
    if (error instanceof BackendError && error.status === 404)
      return (
        <section className="space-y-4">
          <h1 className="text-2xl font-semibold">申请不可访问</h1>
          <p>该申请已删除或不存在，无法打开工作区。</p>
          <Link className="underline" href="/applications">
            返回申请列表
          </Link>
        </section>
      );
    return <ReadProblem title="暂时无法读取申请及职位关联" href={`/applications/${id}/summary`} />;
  }
  const siblings = await optionalRead(() => applications.siblings(ctx));
  return (
    <>
      <Link href="/applications" className="mb-5 inline-block text-sm text-secondary">
        ← 返回申请列表
      </Link>
      <section
        aria-label="当前申请"
        className="mb-6 rounded-panel border border-line bg-surface p-5 sm:p-6"
      >
        <p className="text-sm text-secondary">{ctx.company.name}</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <p className="min-w-0 break-words font-serif text-xl font-semibold">{ctx.job.title}</p>
          <ApplicationStatusBadge status={ctx.application.status} />
        </div>
        <p className="mt-2 text-sm text-secondary">
          创建于 <DateTime value={ctx.application.created_at} />
        </p>
        {siblings.state === "ready" && siblings.value.items.length > 1 && (
          <details className="mt-5 border-t border-line pt-4">
            <summary className="cursor-pointer text-sm font-medium">同公司职位 / 申请切换</summary>
            {
              <ul className="mt-3 space-y-1">
                {siblings.value.items.map(({ application, job }) => (
                  <li key={application.id}>
                    {application.id === id ? (
                      <span className="inline-flex min-h-11 items-center px-2 text-sm">
                        {job.title}（当前申请）
                      </span>
                    ) : (
                      <Link
                        prefetch={false}
                        href={`/applications/${application.id}/summary`}
                        className="inline-flex min-h-11 items-center px-2 text-sm text-accent-ink underline underline-offset-4"
                      >
                        {job.title}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            }
          </details>
        )}
      </section>
      <div className="mb-7 border-b border-line pb-4">
        <Navigation items={applicationNavigation(id)} label="申请导航" />
      </div>
      {children}
    </>
  );
}
