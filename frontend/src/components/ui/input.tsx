import type { ComponentProps } from "react";
import { cx } from "@/lib/styles";

type Props = Omit<ComponentProps<"input">, "id" | "aria-describedby" | "aria-invalid"> & {
  id: string;
  label: string;
  hint?: string;
  error?: string;
};
export function Input({ id, label, hint, error, className, ...props }: Props) {
  return (
    <div className="grid gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        {...props}
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={error || hint ? `${id}-description` : undefined}
        className={cx(
          "min-h-11 w-full rounded-control border bg-paper px-3 py-2 text-ink placeholder:text-secondary disabled:cursor-not-allowed disabled:bg-surface focus:border-accent focus:shadow-[0_0_0_3px_rgba(201,100,66,.09)]",
          error ? "border-error" : "border-line",
          className,
        )}
      />
      {(error || hint) && (
        <p
          id={`${id}-description`}
          className={cx("text-sm", error ? "text-error" : "text-secondary")}
        >
          {error || hint}
        </p>
      )}
    </div>
  );
}
