import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ApplicationCard } from "@/features/applications/application-card";
import { PageHeading } from "@/components/ui/typography";
import { Surface } from "@/components/ui/surface";
import { ApplicationFilters } from "@/features/applications/filters";
import { ReadProblem } from "@/components/product/read-state";
import { applications } from "@/features/applications/server";
import { optionalRead } from "@/features/applications/repository";
import { parseQuery, listHref, type Search, type ListQuery } from "@/features/applications/queries";
import { Pager } from "@/features/applications/views";

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
    optionalRead(() => Promise.all(query.company_ids.map((id) => applications.company(id)))),
  ]);
  if (listing.state === "ready" && !listing.value.items.length && query.page > 1)
    redirect(listHref(query, { page: query.page - 1 }));
  return (
    <>
      <div className="mb-7 flex items-center justify-between gap-4">
        <h1 className="font-serif text-3xl leading-relaxed font-semibold tracking-[-0.3px]">
          申请
        </h1>
        <Link
          href="/applications/new"
          className="inline-flex min-h-11 items-center rounded-control border border-line bg-paper px-4 text-accent-ink"
        >
          添加职位
        </Link>
      </div>
      <ApplicationFilters
        key={listHref(query, { page: 1 })}
        query={query}
        companies={selected.state === "ready" ? selected.value : []}
      />
      {listing.state === "unavailable" || selected?.state === "unavailable" ? (
        <ReadProblem title="暂时无法读取申请列表或关联信息" href={listHref(query)} />
      ) : (
        <>
          <p className="mb-4 text-sm text-secondary">
            {query.page > 1 || listing.value.has_more
              ? `第 ${query.page} 页 · 本页 ${listing.value.items.length} 条`
              : `${listing.value.items.length} 条申请`}
          </p>
          {listing.value.items.length ? (
            <ul className="grid gap-4" aria-label="申请列表">
              {listing.value.items.map(({ application, job }) => (
                <li key={application.id}>
                  <ApplicationCard application={application} job={job} />
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
          {(query.page > 1 || listing.value.has_more) && (
            <Pager
              label="申请分页"
              previous={query.page > 1 ? listHref(query, { page: query.page - 1 }) : undefined}
              next={listing.value.has_more ? listHref(query, { page: query.page + 1 }) : undefined}
            />
          )}
        </>
      )}
    </>
  );
}
