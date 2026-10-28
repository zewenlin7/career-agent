"use client";
import type { ReactNode } from "react";
import { errorMessage } from "./contracts";
export function InlineError({ code, message }: { code?: string; message?: string }) {
  return code || message ? (
    <p role="alert" className="text-sm text-error">
      {message || errorMessage(code)}
    </p>
  ) : null;
}
export function Area({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className="border-b border-line py-6 first:pt-0">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-xl">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
export const dateLabel = (value: string) =>
  new Date(value).toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });

export function SavedAt({ value }: { value?: string | null }) {
  return value ? (
    <p className="text-xs text-secondary">
      {new Date(value).toLocaleString("sv-SE", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })}
    </p>
  ) : null;
}
