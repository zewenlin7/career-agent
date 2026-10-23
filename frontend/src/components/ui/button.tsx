import Link from "next/link";
import type { ComponentProps } from "react";
import { cx } from "@/lib/styles";

type Variant = "primary" | "secondary" | "quiet";
function buttonStyle(variant: Variant) {
  return cx(
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-control border px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    // Darker reference hover color is used for readable white text on a full text button.
    variant === "primary" &&
      "border-accent-hover bg-accent-hover text-white enabled:hover:bg-accent-ink",
    variant === "secondary" &&
      "border-line bg-paper text-secondary enabled:hover:border-accent enabled:hover:text-accent-ink",
    variant === "quiet" &&
      "border-transparent text-secondary enabled:hover:bg-surface enabled:hover:text-ink",
  );
}
export function Button({
  variant = "secondary",
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { variant?: Variant }) {
  return <button type={type} className={cx(buttonStyle(variant), className)} {...props} />;
}
export function ButtonLink({
  variant = "secondary",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: Variant }) {
  return (
    <Link
      className={cx(buttonStyle(variant), "hover:underline underline-offset-4", className)}
      {...props}
    />
  );
}
