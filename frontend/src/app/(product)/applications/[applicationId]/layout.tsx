import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { Navigation } from "@/components/layout/navigation";
import { applicationNavigation } from "@/lib/navigation";
import { BackendError } from "@/lib/api/error";
import { ReadProblem } from "@/components/product/read-state";
import { applications, getApplicationContext } from "@/features/applications/server";
import { optionalRead } from "@/features/applications/repository";
import { UUID_PATTERN } from "@/features/applications/contracts";
import { ApplicationStatusBadge, Identity } from "@/features/applications/views";

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
    if (error instanceof BackendError && error.status === 404) notFound();
    return <ReadProblem title="暂时无法读取申请及职位关联" href={`/applications/${id}/summary`} />;
  }
  const siblings = await optionalRead(() => applications.siblings(ctx));
  return (
    <>
      <div className="mb-5 text-sm">
        <Link href="/applications" className="text-secondary underline underline-offset-4">
          Applications
        </Link>
        <span aria-hidden="true" className="mx-3 text-muted">
          /
        </span>
        <span>Application</span>
      </div>
      <section
        aria-label="当前申请"
        className="mb-6 rounded-panel border border-line bg-surface p-5 sm:p-6"
      >
        <Link
          prefetch={false}
          href={`/applications?company_id=${ctx.company.id}`}
          className="text-sm text-secondary underline underline-offset-4"
        >
          {ctx.company.name}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <p className="min-w-0 break-words font-serif text-xl font-semibold">{ctx.job.title}</p>
          <ApplicationStatusBadge status={ctx.application.status} />
        </div>
        <p className="mt-2 text-sm text-secondary">
          当前 JD 第 {ctx.job.revision} 版 · {ctx.job.requirements.length} 条已记录要求
        </p>
        <Identity
          values={[
            ["Application", ctx.application.id],
            ["Job", ctx.job.id],
            ["Company", ctx.company.id],
            ["当前 JD revision", ctx.job.job_revision_id],
          ]}
        />
        <details className="mt-5 border-t border-line pt-4">
          <summary className="cursor-pointer text-sm font-medium">同公司职位 / 申请切换</summary>
          {siblings.state === "unavailable" ? (
            <p role="status" className="mt-3 text-sm">
              其他申请暂时无法读取。
            </p>
          ) : (
            <ul className="mt-3 space-y-1">
              {siblings.value.items.map(({ application, job }) => (
                <li key={application.id}>
                  <Link
                    prefetch={false}
                    href={`/applications/${application.id}/summary`}
                    aria-current={application.id === id ? "page" : undefined}
                    className="inline-flex min-h-11 flex-wrap items-center gap-3 rounded-control px-2 py-2 text-sm text-accent-ink underline underline-offset-4"
                  >
                    {job.title}
                    <span className="text-secondary">
                      {application.id === id ? "当前申请" : "进入 Summary"}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link
            prefetch={false}
            href={`/applications?company_id=${ctx.company.id}`}
            className="mt-2 inline-flex min-h-11 items-center text-sm text-secondary underline underline-offset-4"
          >
            查看该公司全部申请（分页）
          </Link>
        </details>
      </section>
      <div className="mb-7 border-b border-line pb-4">
        <Navigation items={applicationNavigation(id)} label="Application 导航" />
      </div>
      {children}
    </>
  );
}
