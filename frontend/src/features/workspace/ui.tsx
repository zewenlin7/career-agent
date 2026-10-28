"use client";
import type { ReactNode, ReactElement, SelectHTMLAttributes } from "react";
import { cloneElement, useId } from "react";
import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { errorText, statusText } from "./contracts";
import type { Mode } from "./contracts";
export const control =
  "w-full min-h-11 rounded-control border border-line bg-paper px-3 py-2 text-sm";
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactElement<{ id?: string }>;
}) {
  const id = useId();
  return (
    <div className="grid gap-2 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      {cloneElement(children, { id })}
    </div>
  );
}
export function Select({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  return (
    <Field label={label}>
      <select {...props} className={control}>
        {children}
      </select>
    </Field>
  );
}
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Surface className="space-y-4" aria-label={title}>
      <h2 className="font-serif text-lg font-semibold">{title}</h2>
      {children}
    </Surface>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <span className="rounded-control border border-line px-2 py-1 text-sm">
      {statusText[value] || (/^[a-z_]+$/.test(value) ? "暂不可用" : value)}
    </span>
  );
}
export function ErrorNotice({ code }: { code?: string }) {
  return code ? (
    <div
      role="alert"
      className="rounded-control border border-error-line bg-error-soft p-3 text-sm text-error"
    >
      {errorText(code)}{" "}
    </div>
  ) : null;
}
export function ReadState({
  error,
  loaded,
  empty = false,
}: {
  error?: string;
  loaded: boolean;
  empty?: boolean;
}) {
  return error ? (
    <ErrorNotice code={error} />
  ) : !loaded ? (
    <p role="status">正在读取…</p>
  ) : empty ? (
    <p className="text-sm text-secondary">暂无记录。</p>
  ) : null;
}
/** Operational identifiers belong in Internal, never in Product rendering. */
export function Refs(_props: { values: Record<string, unknown> }) {
  void _props;
  return null;
}
export function Pages({
  offset,
  setOffset,
  more,
  size = 10,
}: {
  offset: number;
  setOffset: (n: number) => void;
  more: boolean;
  size?: number;
}) {
  return (
    <nav aria-label="记录分页" className="flex items-center gap-3 text-sm">
      <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - size))}>
        上一页
      </Button>
      <span>第 {Math.floor(offset / size) + 1} 页</span>
      <Button disabled={!more} onClick={() => setOffset(offset + size)}>
        下一页
      </Button>
    </nav>
  );
}
/** Test mode is injected by test providers, not a Product control. */
export function ModeSelect(_props: { value: Mode; onChange: (v: Mode) => void }) {
  void _props;
  return null;
}
