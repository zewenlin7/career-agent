"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Surface } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Field, control } from "@/features/workspace/ui";
import { CompanySearch, type Company } from "./company-search";
import { applicationStatuses, statusLabels, type ApplicationStatus } from "./contracts";
import { listHref, type ListQuery } from "./queries";
export function ApplicationFilters({
  query,
  companies: initialCompanies,
}: {
  query: ListQuery;
  companies: Company[];
}) {
  const router = useRouter();
  const [status, setStatus] = useState(query.status || "");
  const [selected, setSelected] = useState(initialCompanies);
  const [search, setSearch] = useState("");
  const composition = useRef(false);
  return (
    <Surface tone="warm" className="mb-6" aria-label="申请筛选">
      <form
        className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3 sm:flex"
        onSubmit={(e) => {
          e.preventDefault();
          if (composition.current) return;
          router.push(
            listHref({
              status: (status || undefined) as ApplicationStatus | undefined,
              company_ids: selected.map((c) => c.id),
              page: 1,
            }),
          );
        }}
      >
        <div className="min-w-0 self-start sm:flex-1">
          <CompanySearch
            value={search}
            onChange={setSearch}
            onComposing={(value) => {
              composition.current = value;
            }}
            disabled={(company) =>
              selected.some((s) => s.id === company.id) || selected.length >= 50
            }
            onSelect={(company) => {
              setSelected((items) =>
                items.some((s) => s.id === company.id) ? items : [...items, company],
              );
              setSearch("");
            }}
          />
        </div>
        <Field label="状态">
          <select
            className={`${control} font-normal`}
            value={status}
            onChange={(e) => setStatus(e.target.value as ApplicationStatus | "")}
          >
            <option value="">全部状态</option>
            {applicationStatuses.map((s) => (
              <option key={s} value={s}>
                {statusLabels[s]}
              </option>
            ))}
          </select>
        </Field>
        <div className="col-start-2 flex flex-col gap-2 sm:flex-row sm:gap-3">
          <Button type="submit">筛选</Button>
          <Button
            onClick={() => {
              setSearch("");
              setSelected([]);
              setStatus("");
              router.push("/applications");
            }}
          >
            清除筛选
          </Button>
        </div>
      </form>

      {!!selected.length && (
        <ul aria-label="已选公司" className="mt-3 flex flex-wrap gap-2">
          {selected.map((c) => (
            <li
              key={c.id}
              className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-paper py-0.5 pr-1 pl-3 text-sm"
            >
              <span className="break-words">{c.name}</span>
              <button
                type="button"
                className="flex size-6 shrink-0 items-center justify-center rounded-full text-secondary hover:bg-inset hover:text-ink focus-visible:outline-2 focus-visible:outline-accent-ink"
                aria-label={`移除${c.name}`}
                onClick={() => setSelected((items) => items.filter((s) => s.id !== c.id))}
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}
