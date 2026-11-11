import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { statusLabels, type ApplicationStatus } from "./contracts";

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge>{statusLabels[status]}</Badge>;
}
export function Pager({
  previous,
  next,
  label,
}: {
  previous?: string;
  next?: string;
  label: string;
}) {
  return (
    <nav aria-label={label} className="mt-5 flex flex-wrap items-center gap-5 text-sm">
      {previous ? (
        <Link
          prefetch={false}
          className="inline-flex min-h-11 items-center text-accent-ink underline underline-offset-4"
          href={previous}
        >
          上一页
        </Link>
      ) : (
        <span className="text-secondary">已在第一页</span>
      )}
      {next && (
        <Link
          prefetch={false}
          className="inline-flex min-h-11 items-center text-accent-ink underline underline-offset-4"
          href={next}
        >
          下一页
        </Link>
      )}
    </nav>
  );
}
export function Identity(_props: { values: [string, string][] }) {
  void _props;
  return null;
}
