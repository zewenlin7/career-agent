import { ButtonLink } from "@/components/ui/button";
import { PageHeading } from "@/components/ui/typography";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-[760px] px-6 py-12">
      <PageHeading title="找不到这个页面" description="请检查地址，或返回 Applications。" />
      <ButtonLink href="/applications">返回 Applications</ButtonLink>
    </main>
  );
}
