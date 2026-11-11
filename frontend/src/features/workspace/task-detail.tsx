"use client";
import Link from "next/link";
import { useEffect } from "react";
import { useRead } from "./client";
import { errorText } from "./contracts";
import { taskDestination, taskStatusPath, type TrackedTask, type TaskState } from "./task-tracker";
export function TaskDetail({ task }: { task: TrackedTask }) {
  const read = useRead<TaskState>(taskStatusPath(task));
  const { reload } = read;
  useEffect(() => {
    if (read.data && !["pending", "running", "unknown", "ready"].includes(read.data.state)) return;
    const timer = setInterval(reload, 2500);
    return () => clearInterval(timer);
  }, [read.data, reload]);
  const state = read.data?.state;
  const text = read.error
    ? errorText(read.error)
    : !state
      ? "正在读取…"
      : state === "removed"
        ? "这条复盘记录已删除。"
        : state === "failure"
          ? errorText(read.data?.reason || "request_failed")
          : state === "cancelled"
            ? "任务已停止"
            : state === "unknown"
              ? "结果尚未确认，请勿重复提交。"
              : state === "awaiting_save"
                ? "内容已生成，等待确认保存。"
                : state === "reused"
                  ? "已使用已有结果"
                  : state === "success"
                    ? "任务已完成"
                    : state === "partial"
                      ? "部分内容已完成"
                      : "正在处理…";
  const deleted = read.data?.workspace?.available === false;
  const hasResult =
    read.data &&
    !deleted &&
    ["success", "reused", "partial"].includes(read.data.state) &&
    Object.keys(read.data.selection).length > 0;
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">生成任务</h1>
      <p role="status">{text}</p>
      {hasResult && (
        <Link className="underline" href={taskDestination(task, read.data!)}>
          查看结果
        </Link>
      )}
      {deleted ? (
        <p>该申请已删除，无法打开工作区。</p>
      ) : (
        read.data && (
          <p>
            <Link className="underline" href={task.href}>
              返回任务页面
            </Link>
          </p>
        )
      )}
      {deleted && (
        <Link className="underline" href="/applications">
          返回申请列表
        </Link>
      )}
    </section>
  );
}
