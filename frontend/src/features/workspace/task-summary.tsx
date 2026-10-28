"use client";
import Link from "next/link";
import type { Page, Result, Target } from "./contracts";
import { useRead } from "./client";
import { Panel, ReadState } from "./ui";
const tasks: [Target, string, string][] = [
  ["fit_analysis", "岗位匹配", "research-fit"],
  ["resume_tailoring", "简历优化", "apply/resume"],
  ["greeting_generation", "招呼语", "apply/greeting"],
  ["interview_preparation", "面试准备", "interview/preparation"],
];
function Task({ applicationId, task }: { applicationId: string; task: (typeof tasks)[number] }) {
  const read = useRead<Page<{ created_at: string; result: Result }>>(
    `applications/${applicationId}/results?target=${task[0]}&limit=1`,
  );
  return (
    <li className="space-y-1">
      <Link
        className="text-accent-ink underline"
        href={`/applications/${applicationId}/${task[2]}`}
      >
        {task[1]}
      </Link>
      <ReadState loaded={!!read.data} error={read.error} />
      {read.data && (
        <p className="text-sm text-secondary">
          {read.data.items[0]
            ? `最近生成于 ${new Date(read.data.items[0].created_at).toLocaleString("zh-CN")}`
            : "尚未生成"}
        </p>
      )}
    </li>
  );
}
export function TaskSummary({ applicationId }: { applicationId: string }) {
  return (
    <Panel title="已有成果">
      <ul className="grid gap-4 sm:grid-cols-2">
        {tasks.map((task) => (
          <Task key={task[0]} applicationId={applicationId} task={task} />
        ))}
      </ul>
    </Panel>
  );
}
