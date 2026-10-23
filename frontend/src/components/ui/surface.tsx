import type { ComponentProps } from "react";
import { cx } from "@/lib/styles";

export function Surface({
  tone = "paper",
  className,
  ...props
}: ComponentProps<"section"> & { tone?: "paper" | "warm" }) {
  return (
    <section
      className={cx(
        "rounded-panel border border-line p-6",
        tone === "paper" ? "bg-paper" : "bg-surface",
        className,
      )}
      {...props}
    />
  );
}
