"use client";
import { Fragment, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
/** Exact-result navigation resets local selectors, including same-route client navigation. */
export function TargetBoundary({
  children,
  preserveInputs = false,
}: {
  children: ReactNode;
  preserveInputs?: boolean;
}) {
  const search = useSearchParams();
  return <Fragment key={preserveInputs ? "task" : search.toString()}>{children}</Fragment>;
}
