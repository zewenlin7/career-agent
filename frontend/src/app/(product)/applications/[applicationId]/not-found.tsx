import { PageHeading } from "@/components/ui/typography";
import { ButtonLink } from "@/components/ui/button";
export default function NotFound() {
  return (
    <>
      <PageHeading title="找不到这条申请" description="请从申请列表 重新选择已有申请。" />
      <ButtonLink href="/applications">返回申请列表</ButtonLink>
    </>
  );
}
