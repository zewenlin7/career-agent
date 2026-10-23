import { Surface } from "@/components/ui/surface";
import { SectionHeading } from "@/components/ui/typography";

export function ReadProblem({
  title = "暂时无法读取数据",
  href,
}: {
  title?: string;
  href: string;
}) {
  return (
    <Surface aria-label={title} className="max-w-[760px]">
      <div role="alert">
        <SectionHeading>{title}</SectionHeading>
        <p className="mt-2 text-sm text-secondary">
          请稍后重新加载。这里不会把读取失败显示成没有记录。
        </p>
      </div>
      <a
        className="mt-4 inline-flex min-h-11 items-center text-sm text-accent-ink underline underline-offset-4"
        href={href}
      >
        重新加载
      </a>
    </Surface>
  );
}
export function DateTime({ value }: { value: string }) {
  return (
    <time dateTime={value} title={value}>
      {new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Shanghai",
      }).format(new Date(value))}
    </time>
  );
}
