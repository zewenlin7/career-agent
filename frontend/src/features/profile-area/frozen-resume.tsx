/* eslint-disable @next/next/no-img-element -- authenticated local photo endpoint */
"use client";
import Link from "next/link";
import { useRead } from "../workspace/client";
import { ErrorNotice } from "../workspace/ui";
import { endpoint } from "../workspace/client";
import type { ResumeDocument } from "../onboarding/contracts";
import type { Presentation } from "./contracts";
import { ResumeView } from "./resume-view";
import { DateTime } from "@/components/product/read-state";
export function FrozenResume({ revision, pdf }: { revision: string; pdf?: string }) {
  const read = useRead<{
    name: string;
    input_snapshot: { display_name: string; personal?: Record<string, string> };
    document: ResumeDocument;
    presentation: Presentation;
    created_at: string;
    pdf_id: string | null;
  }>(`resume-revisions/${revision}/snapshot${pdf ? `?pdf=${encodeURIComponent(pdf)}` : ""}`);
  const row = read.data;
  return (
    <section className="min-w-0">
      <Link href="/profile/resumes" className="text-sm text-secondary">
        ← 返回简历库
      </Link>
      <ErrorNotice code={read.error} />
      {row ? (
        <>
          <h1 className="mt-5 font-serif text-3xl font-semibold">{row.name}</h1>
          <p className="mt-2 text-sm text-secondary">
            <DateTime value={row.created_at} />
          </p>
          <header className="mt-5 flex items-start justify-between gap-5 border-b border-line pb-5">
            <div className="min-w-0">
              <h2 className="text-2xl font-semibold">{row.input_snapshot.display_name}</h2>
              <p className="mt-2 break-words text-sm text-secondary">
                {Object.entries(row.input_snapshot.personal || {})
                  .filter(([key, value]) => key !== "photo_id" && value)
                  .map(([, value]) => value)
                  .join(" · ")}
              </p>
            </div>
            {row.input_snapshot.personal?.photo_id && (
              <img
                alt="简历照片"
                src={endpoint(`profile-photos/${row.input_snapshot.personal.photo_id}`)}
                className="h-28 w-20 shrink-0 object-contain"
              />
            )}
          </header>
          <ResumeView
            sections={row.document.sections}
            presentation={row.presentation}
            onPresentation={() => {}}
          />
          {row.pdf_id && (
            <div className="mt-5 flex gap-4">
              <a
                target="_blank"
                rel="noopener noreferrer"
                href={`/api/product/artifacts/${row.pdf_id}/download?inline=true`}
                className="text-accent-ink underline"
              >
                预览 PDF
              </a>
              <a
                href={`/api/product/artifacts/${row.pdf_id}/download`}
                download
                className="text-accent-ink underline"
              >
                下载 PDF
              </a>
            </div>
          )}
        </>
      ) : (
        !read.error && <p>正在读取…</p>
      )}
    </section>
  );
}
