import type { ReactNode } from "react";
import { Navigation } from "@/components/layout/navigation";
import { sectionNavigation } from "@/lib/navigation";
export default async function Layout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ applicationId: string }>;
}) {
  const { applicationId } = await params;
  return (
    <>
      <div className="mb-7">
        <Navigation items={sectionNavigation(applicationId, "interview")} label="Interview 导航" />
      </div>
      {children}
    </>
  );
}
