import { notFound } from "next/navigation";
import { UUID_PATTERN } from "@/features/applications/contracts";
import { TaskDetail } from "@/features/workspace/task-detail";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ family: string; taskId: string }>;
  searchParams: Promise<{ request_id?: string; return_to?: string }>;
}) {
  const { family, taskId } = await params;
  const query = await searchParams;
  if (
    !["operations", "product-drafts", "mock-interviews", "interview-debriefs"].includes(family) ||
    !UUID_PATTERN.test(taskId) ||
    (query.request_id && !UUID_PATTERN.test(query.request_id))
  )
    notFound();
  const href =
    query.return_to?.startsWith("/") &&
    !query.return_to.startsWith("//") &&
    !query.return_to.includes("\\")
      ? query.return_to
      : "/applications";
  return (
    <TaskDetail
      task={{
        key: `${family}:${taskId}`,
        family,
        id: taskId,
        title: "生成任务",
        href,
        requestId: query.request_id,
      }}
    />
  );
}
