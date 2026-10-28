import type { Metadata } from "next";
import Link from "next/link";
import { PageHeading } from "@/components/ui/typography";
import { Surface } from "@/components/ui/surface";
import { ApplicationFilters } from "@/features/applications/filters";
import { ReadProblem, DateTime } from "@/components/product/read-state";
import { applications } from "@/features/applications/server";
import { optionalRead } from "@/features/applications/repository";
import { parseQuery, listHref, type Search, type ListQuery } from "@/features/applications/queries";
import { ApplicationStatusBadge, Pager } from "@/features/applications/views";

export const metadata: Metadata = { title: "申请" };
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<Search> }) {
  let query: ListQuery;
  try {
    query = parseQuery(await searchParams);
  } catch {
    return (
      <>
        <PageHeading title="申请" />
        <Surface>
          <p role="alert">筛选或分页参数无效。</p>
          <Link href="/applications" className="text-accent-ink underline">
            重置筛选
          </Link>
        </Surface>
      </>
    );
  }
  const [listing, selected] = await Promise.all([
    optionalRead(() => applications.list(query)),
    query.company_id
      ? optionalRead(() => applications.company(query.company_id!))
      : Promise.resolve(null),
  ]);
  return (
    <>
      <PageHeading title="申请" description="按公司与状态查看申请，进入对应职位的工作空间。" />
      <Link
        href="/applications/new"
        className="mb-5 inline-flex min-h-11 items-center rounded-control border border-line bg-paper px-4 text-accent-ink"
      >
        添加职位
      </Link>
      <ApplicationFilters
        query={query}
        companyName={selected?.state === "ready" ? selected.value.name : undefined}
      />
      {listing.state === "unavailable" || selected?.state === "unavailable" ? (
        <ReadProblem title="暂时无法读取申请列表或关联信息" href={listHref(query)} />
      ) : (
        <>
          <p className="mb-4 text-sm text-secondary">
            第 {query.page} 页 · 本页 {listing.value.items.length} 条 · 按创建时间从新到旧
          </p>
          {listing.value.items.length ? (
            <ul className="grid gap-4" aria-label="申请列表">
              {listing.value.items.map(({ application, job }) => (
                <li key={application.id}>
                  <Link
                    href={`/applications/${application.id}/summary`}
                    className="block rounded-panel focus-visible:outline-2 focus-visible:outline-accent-ink"
                    prefetch={false}
                  >
                    <Surface className="flex flex-wrap items-start justify-between gap-4 hover:border-accent-ink">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-secondary">{job.company_name}</p>
                        <h2 className="mt-1 text-base font-semibold break-words">{job.title}</h2>
                        <p className="mt-3 text-xs text-secondary">
                          创建于 <DateTime value={application.created_at} /> · JD 第 {job.revision}{" "}
                          版
                        </p>
                      </div>
                      <ApplicationStatusBadge status={application.status} />
                    </Surface>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <Surface>
              <p>
                {query.page > 1 ? "本页没有申请。可以返回上一页。" : "当前筛选下没有申请记录。"}
              </p>
            </Surface>
          )}
          <Pager
            label="申请分页"
            previous={query.page > 1 ? listHref(query, { page: query.page - 1 }) : undefined}
            next={listing.value.has_more ? listHref(query, { page: query.page + 1 }) : undefined}
          />
        </>
      )}
    </>
  );
}
