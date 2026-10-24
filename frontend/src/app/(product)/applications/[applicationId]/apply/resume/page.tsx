import { WorkspaceEntry } from "@/features/workspace/entry";
export default async function Page({ params }: { params: Promise<{ applicationId: string }> }) {
  return <WorkspaceEntry id={(await params).applicationId} feature="resume" />;
}
