import type { Metadata } from "next";
import Link from "next/link";
import { PageHeading } from "@/components/ui/typography";
import { Surface } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ReadProblem, DateTime } from "@/components/product/read-state";
import { applications } from "@/features/applications/server";
import { optionalRead } from "@/features/applications/repository";
import { applicationStatuses, statusLabels } from "@/features/applications/contracts";
import { parseQuery, listHref, type Search, type ListQuery } from "@/features/applications/queries";
import { ApplicationStatusBadge, Pager } from "@/features/applications/views";

export const metadata: Metadata = { title: "Applications" };
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<Search> }) {
  let query: ListQuery;
  try {
    query = parseQuery(await searchParams);
  } catch {
    return (
      <>
        <PageHeading title="Applications" />
        <Surface>
          <p role="alert">筛选或分页参数无效。</p>
          <Link href="/applications" className="text-accent-ink underline">
            重置筛选
          </Link>
        </Surface>
      </>
    );
  }
  const [listing, companies, selected] = await Promise.all([
    optionalRead(() => applications.list(query)),
    optionalRead(() => applications.companies(query)),
    query.company_id
      ? optionalRead(() => applications.company(query.company_id!))
      : Promise.resolve(null),
  ]);
  return (
    <>
      <PageHeading
        title="Applications"
        description="按公司与状态查看申请，进入对应职位的工作空间。"
      />
      <Surface tone="warm" className="mb-6 space-y-5" aria-label="申请筛选">
        <form action="/applications" method="get" className="flex flex-wrap items-end gap-3">
          {query.company_id && <input type="hidden" name="company_id" value={query.company_id} />}
          <div className="grid gap-2">
            <label htmlFor="status" className="text-sm font-medium">
              申请状态
            </label>
            <select
              id="status"
              name="status"
              defaultValue={query.status || ""}
              className="min-h-11 rounded-control border border-line bg-paper px-3 py-2 text-sm"
            >
              <option value="">全部状态</option>
              {applicationStatuses.map((s) => (
                <option key={s} value={s}>
                  {statusLabels[s]}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit">筛选</Button>
          <Link
            href="/applications"
            className="inline-flex min-h-11 items-center px-2 text-sm text-secondary underline underline-offset-4"
          >
            清除筛选
          </Link>
        </form>
        <details open={Boolean(query.company_q || query.company_page > 1)}>
          <summary className="cursor-pointer text-sm">
            公司筛选：
            {selected?.state === "ready"
              ? selected.value.name
              : query.company_id
                ? "指定公司（名称暂不可用）"
                : "全部公司"}
          </summary>
          <form action="/applications" method="get" className="mt-4 flex flex-wrap items-end gap-3">
            {query.status && <input type="hidden" name="status" value={query.status} />}
            {query.company_id && <input type="hidden" name="company_id" value={query.company_id} />}
            <div className="w-full max-w-sm">
              <Input
                id="company-query"
                name="company_q"
                label="查找公司"
                maxLength={200}
                defaultValue={query.company_q}
                hint="先查找，再选择公司筛选申请。"
              />
            </div>
            <Button type="submit">查找公司</Button>
          </form>
          {companies.state === "unavailable" ? (
            <p className="mt-4 text-sm" role="status">
              公司列表暂时无法读取。
            </p>
          ) : (
            <>
              <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
                <li>
                  <Link
                    prefetch={false}
                    href={listHref(query, { company_id: undefined, page: 1 })}
                    className="inline-flex min-h-11 items-center text-accent-ink underline"
                  >
                    全部公司
                  </Link>
                </li>
                {companies.value.items.map((c) => (
                  <li key={c.id}>
                    <Link
                      prefetch={false}
                      href={listHref(query, { company_id: c.id, page: 1 })}
                      className="inline-flex min-h-11 items-center break-words text-accent-ink underline"
                      aria-current={query.company_id === c.id ? "true" : undefined}
                    >
                      {c.name}
                    </Link>
                  </li>
                ))}
              </ul>
              {!companies.value.items.length && (
                <p className="text-sm text-secondary">没有找到公司。</p>
              )}
              <Pager
                label="公司选项分页"
                previous={
                  query.company_page > 1
                    ? listHref(query, { company_page: query.company_page - 1 })
                    : undefined
                }
                next={
                  companies.value.has_more
                    ? listHref(query, { company_page: query.company_page + 1 })
                    : undefined
                }
              />
            </>
          )}
        </details>
      </Surface>
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
                  <Surface className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-secondary">{job.company_name}</p>
                      <h2 className="mt-1 text-base font-semibold break-words">
                        <Link
                          prefetch={false}
                          href={`/applications/${application.id}/summary`}
                          className="underline-offset-4 hover:text-accent-ink hover:underline"
                        >
                          {job.title}
                        </Link>
                      </h2>
                      <p className="mt-3 text-xs text-secondary">
                        创建于 <DateTime value={application.created_at} /> · JD 第 {job.revision} 版
                      </p>
                    </div>
                    <ApplicationStatusBadge status={application.status} />
                  </Surface>
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
