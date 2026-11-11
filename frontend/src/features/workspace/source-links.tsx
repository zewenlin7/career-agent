"use client";
import Link from "next/link";
import { Fragment, useId, useRef, useState, type ReactNode } from "react";
import { useRead } from "./client";
import { Button } from "@/components/ui/button";
import { ReadState } from "./ui";
import { researchRecordName } from "./record-labels";
import { ProfileView } from "../profile-area/profile-editor";
import type { Snapshot } from "../profile-area/contracts";
export function SourceLinks({
  applicationId,
  jd,
  resume,
  resumeName,
  research,
  companyName,
  companyId,
  researchFetchedAt,
  profile,
}: {
  applicationId: string;
  jd?: string;
  resume?: string | null;
  resumeName?: string | null;
  research?: string | null;
  companyName?: string;
  companyId?: string;
  researchFetchedAt?: string | null;
  profile?: string | null;
}) {
  const dialogId = useId();
  const report = useRead<{ id: string; company_id: string; fetched_at: string }>(
    research && companyId && !researchFetchedAt
      ? `companies/${companyId}/research/${research}`
      : null,
  );
  const savedResume = useRead<{ name: string }>(
    resume && !resumeName ? `resume-revisions/${resume}/snapshot` : null,
  );
  const dialog = useRef<HTMLDialogElement>(null);
  const [opened, setOpened] = useState<"jd" | "profile" | null>(null);
  const description = useRead<{ jd_text: string }>(
    opened === "jd" && jd ? `job-revisions/${jd}` : null,
  );
  const profileRead = useRead<Snapshot>(
    opened === "profile" && profile ? `profile/revisions/${profile}` : null,
  );
  const sources: ReactNode[] = [];
  if (jd)
    sources.push(
      <a
        className="underline"
        href={`/applications/${applicationId}/research-fit/description?revision=${jd}`}
        onClick={(event) => {
          if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          )
            return;
          event.preventDefault();
          setOpened("jd");
          dialog.current?.showModal();
        }}
      >
        职位描述
      </a>,
    );
  if (resume)
    sources.push(
      <Link className="underline" href={`/profile/resumes?revision=${resume}`}>
        {resumeName || savedResume.data?.name || "所选简历"}
      </Link>,
    );
  if (profile)
    sources.push(
      <button
        type="button"
        className="underline font-normal"
        onClick={() => {
          setOpened("profile");
          dialog.current?.showModal();
        }}
      >
        个人资料
      </button>,
    );
  if (research)
    sources.push(
      <Link
        className="underline"
        href={`/applications/${applicationId}/research-fit/company?research=${research}`}
      >
        {researchRecordName(
          companyName,
          researchFetchedAt ??
            (report.data?.id === research && report.data.company_id === companyId
              ? report.data.fetched_at
              : undefined),
        )}
      </Link>,
    );
  if (!sources.length) return null;
  return (
    <>
      <p className="text-sm text-secondary">
        基于
        {sources.map((source, index) => (
          <Fragment key={index}>
            {index > 0 && "、"}「{source}」
          </Fragment>
        ))}
        生成
      </p>
      <dialog
        ref={dialog}
        aria-labelledby={dialogId}
        className="fixed inset-0 m-auto max-h-[80vh] w-[min(48rem,calc(100%-2rem))] overflow-y-auto rounded-control bg-paper p-6 backdrop:bg-black/30"
      >
        <h2 id={dialogId} className="mb-3 text-lg font-semibold">
          {opened === "profile" ? "个人资料" : "职位描述"}
        </h2>
        {opened === "profile" ? (
          <>
            <ReadState loaded={!!profileRead.data} error={profileRead.error} />
            {profileRead.data && <ProfileView data={profileRead.data.data} />}
          </>
        ) : (
          <>
            <ReadState loaded={!!description.data} error={description.error} />
            <p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-base leading-relaxed">
              {description.data?.jd_text}
            </p>
          </>
        )}
        <div className="mt-4 flex justify-end">
          <Button onClick={() => dialog.current?.close()}>关闭</Button>
        </div>
      </dialog>
    </>
  );
}
