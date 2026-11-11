import { ApplicationSummary } from "@/features/applications/summary";
export const dynamic = "force-dynamic";
export default async function Page({ params }: { params: Promise<{ applicationId: string }> }) {
  return <ApplicationSummary id={(await params).applicationId} />;
}
