import type { ComponentProps } from "react";
import { cx } from "@/lib/styles";

// Presentation tones only, not backend execution or quality enums.
export function Badge({
  tone = "neutral",
  className,
  ...props
}: ComponentProps<"span"> & { tone?: "neutral" | "accent" }) {
  return (
    <span
      className={cx(
        "inline-flex rounded-full border px-2.5 py-0.5 text-xs",
        tone === "neutral"
          ? "border-line bg-surface text-secondary"
          : "border-transparent bg-accent-soft text-accent-ink",
        className,
      )}
      {...props}
    />
  );
}
