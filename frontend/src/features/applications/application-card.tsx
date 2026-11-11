"use client";
import Link from "next/link";
import { useRef } from "react";
import { useRouter } from "next/navigation";
import { Surface } from "@/components/ui/surface";
import { DateTime } from "@/components/product/read-state";
import { ApplicationStatusBadge } from "./views";
import type { Application, Job } from "./contracts";
import { useConfirmation } from "@/features/profile-area/confirmation";
import { api, useAction } from "@/features/workspace/client";
import { errorText } from "@/features/workspace/contracts";
export function ApplicationCard({ application, job }: { application: Application; job: Job }) {
  const router = useRouter(),
    action = useAction(),
    confirm = useConfirmation();
  const menu = useRef<HTMLDetailsElement>(null);
  return (
    <Surface className="relative flex flex-wrap items-start justify-between gap-4 hover:border-accent-ink">
      <Link
        href={`/applications/${application.id}/summary`}
        aria-label={`${job.company_name} · ${job.title}`}
        prefetch={false}
        className="absolute inset-0 rounded-panel focus-visible:outline-2 focus-visible:outline-accent-ink"
      />
      <div className="pointer-events-none min-w-0 flex-1">
        <p className="text-sm text-secondary">{job.company_name}</p>
        <h2 className="mt-1 text-base font-semibold break-words">{job.title}</h2>
        <p className="mt-3 text-xs text-secondary">
          创建于 <DateTime value={application.created_at} />
        </p>
      </div>
      <div className="pointer-events-none relative flex items-center gap-2">
        <ApplicationStatusBadge status={application.status} />
        {application.status === "closed" && (
          <details
            ref={menu}
            className="pointer-events-auto relative"
            onKeyDown={(e) => {
              if (e.key === "Escape" && menu.current) {
                menu.current.open = false;
                menu.current.querySelector("summary")?.focus();
              }
            }}
          >
            <summary
              aria-label={`管理${job.title}`}
              className="flex size-9 cursor-pointer list-none items-center justify-center rounded-control text-secondary hover:bg-inset [&::-webkit-details-marker]:hidden"
            >
              ···
            </summary>
            <div className="absolute top-full right-0 z-20 w-32 rounded-control border border-line bg-paper p-1 shadow-soft">
              <button
                type="button"
                disabled={action.busy}
                className="w-full px-3 py-2 text-left text-sm text-error"
                onClick={async () => {
                  if (menu.current) menu.current.open = false;
                  if (
                    !(await confirm.confirm(
                      `删除「${job.company_name} · ${job.title}」？将从申请列表移除，当前界面不支持恢复。`,
                    ))
                  )
                    return;
                  void action.run(async () => {
                    await api(`applications/${application.id}`, "DELETE");
                    router.refresh();
                  });
                }}
              >
                删除申请
              </button>
            </div>
          </details>
        )}
      </div>
      {action.error && (
        <p role="alert" className="relative w-full text-sm text-error">
          {errorText(action.error)}
        </p>
      )}
      {confirm.confirmation}
    </Surface>
  );
}
