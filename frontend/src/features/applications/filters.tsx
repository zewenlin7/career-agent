"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Surface } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { useRead } from "@/features/workspace/client";
import { Field, Select, control, ErrorNotice } from "@/features/workspace/ui";
import type { Page } from "@/features/workspace/contracts";
import { applicationStatuses, statusLabels, type ApplicationStatus } from "./contracts";
import { listHref, type ListQuery } from "./queries";
export function ApplicationFilters({
  query,
  companyName,
}: {
  query: ListQuery;
  companyName?: string;
}) {
  const router = useRouter();
  const [search, setSearch] = useState(query.company_q || companyName || "");
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    if (!typing || (!query.company_id && query.company_q === search.trim())) return;
    const timer = setTimeout(
      () =>
        router.replace(
          listHref(query, { company_q: search.trim(), company_id: undefined, page: 1 }),
        ),
      350,
    );
    return () => clearTimeout(timer);
  }, [typing, search, query, router]);
  const companies = useRead<Page<{ id: string; name: string }>>(
    typing && search.trim() ? `companies?q=${encodeURIComponent(search.trim())}&limit=8` : null,
  );
  return (
    <Surface tone="warm" className="mb-6" aria-label="申请筛选">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setTyping(false);
          router.push(
            listHref(query, { company_q: search.trim(), company_id: undefined, page: 1 }),
          );
        }}
      >
        <Select
          label="状态"
          value={query.status || ""}
          onChange={(e) =>
            router.push(
              listHref(query, {
                status: (e.target.value || undefined) as ApplicationStatus | undefined,
                page: 1,
              }),
            )
          }
        >
          <option value="">全部状态</option>
          {applicationStatuses.map((s) => (
            <option key={s} value={s}>
              {statusLabels[s]}
            </option>
          ))}
        </Select>
        <div className="min-w-0 flex-1 space-y-2">
          <Field label="公司">
            <input
              className={control}
              placeholder="搜索公司"
              value={search}
              maxLength={200}
              onChange={(e) => {
                setSearch(e.target.value);
                setTyping(true);
              }}
            />
          </Field>
          <ErrorNotice code={companies.error} />
          {typing && search.trim() && companies.data && (
            <ul className="rounded-control border border-line bg-paper p-2">
              {companies.data.items.map((c) => (
                <li key={c.id}>
                  <Button
                    onClick={() => {
                      setSearch(c.name);
                      setTyping(false);
                      router.push(listHref(query, { company_q: "", company_id: c.id, page: 1 }));
                    }}
                  >
                    {c.name}
                  </Button>
                </li>
              ))}
              {!companies.data.items.length && <li className="p-2 text-sm">没有找到公司</li>}
            </ul>
          )}
        </div>
        <Button type="submit">筛选</Button>
        <Link
          className="inline-flex min-h-11 items-center text-sm underline"
          href="/applications"
          onClick={() => {
            setSearch("");
            setTyping(false);
          }}
        >
          清除筛选
        </Link>
      </form>
    </Surface>
  );
}
