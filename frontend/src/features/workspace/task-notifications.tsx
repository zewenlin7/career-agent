"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "./client";
import { taskMessage } from "./task-feedback";
import {
  dismissTask,
  markTaskShown,
  pendingNotices,
  recordTaskState,
  taskChange,
  taskDestination,
  taskStatusPath,
  trackedTasks,
  visibleTaskErrors,
  type TrackedTask,
  type TaskState,
} from "./task-tracker";

export function TaskNotifications() {
  const [tasks, setTasks] = useState<TrackedTask[]>([]);
  const [open, setOpen] = useState(false);
  const [verified, setVerified] = useState<Record<string, TaskState>>({});
  const [popup, setPopup] = useState<string | null>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const paused = hovered || focused;
  const [foreground, setForeground] = useState(true);
  const box = useRef<HTMLElement>(null);
  const remaining = useRef(8000);
  useEffect(() => {
    const update = () => setTasks(trackedTasks());
    const visibility = () => setForeground(document.visibilityState === "visible");
    update();
    visibility();
    window.addEventListener(taskChange, update);
    window.addEventListener("storage", update);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.removeEventListener(taskChange, update);
      window.removeEventListener("storage", update);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      for (const task of trackedTasks()) {
        if (
          task.notice &&
          task.dismissedState === task.notice.state &&
          !["unknown", "awaiting_save", "partial"].includes(task.notice.state) &&
          !(task.family === "mock-interviews" && task.notice.reason === "artifact_save_failed")
        )
          continue;
        try {
          const state = await api<TaskState>(taskStatusPath(task));
          if (active) {
            setVerified((previous) => ({ ...previous, [task.key]: state }));
            recordTaskState(task.key, state);
          }
        } catch {
          /* A failed read never proves execution failure. */
        }
      }
      if (active) timer = setTimeout(() => void poll(), 2500);
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  const notices = pendingNotices(tasks);
  useEffect(() => {
    if (popup && visibleTaskErrors.has(popup)) {
      const frame = requestAnimationFrame(() => setPopup(null));
      return () => cancelAnimationFrame(frame);
    }
    if (popup || open || !foreground) return;
    const next = pendingNotices(tasks).find((t) => t.shownState !== t.notice!.state);
    if (!next) return;
    // Only a currently rendered exact operation error suppresses the popup.
    if (visibleTaskErrors.has(next.key)) {
      markTaskShown(next.key, next.notice!.state);
      return;
    }
    const frame = requestAnimationFrame(() => {
      // Removing the last notice unmounts its focus/hover target without a blur
      // or mouseleave event. Reconcile against the live DOM for each new popup.
      setHovered(box.current?.matches(":hover") ?? false);
      setFocused(
        !!box.current?.contains(document.activeElement) &&
          !!document.activeElement?.matches(":focus-visible"),
      );
      remaining.current = 8000;
      setPopup(next.key);
      markTaskShown(next.key, next.notice!.state);
    });
    return () => cancelAnimationFrame(frame);
  }, [tasks, popup, open, foreground]);
  useEffect(() => {
    if (!popup || paused || !foreground || open) return;
    const began = performance.now();
    const timer = setTimeout(() => setPopup(null), remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (performance.now() - began));
    };
  }, [popup, paused, foreground, open]);
  useEffect(() => {
    const outside = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setPopup(null);
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  if (!notices.length) return null;
  const current = notices.find((t) => t.key === popup);
  const remove = (task: TrackedTask) => {
    dismissTask(task.key, task.notice!.state);
    if (popup === task.key) setPopup(null);
  };
  const render = (task: TrackedTask) => {
    const state = task.notice!;
    const reachable = verified[task.key] && verified[task.key].workspace?.available !== false;
    const deleted = verified[task.key]?.workspace?.available === false;
    const success = ["success", "reused", "partial"].includes(state.state);
    return (
      <div key={task.key} className="space-y-2 border-b border-line p-4 last:border-0">
        <div className="flex items-start justify-between gap-3">
          <p className={`font-semibold ${state.state === "failure" ? "text-error" : "text-ink"}`}>
            <span aria-hidden="true">{success ? "✓" : state.state === "failure" ? "!" : "○"}</span>{" "}
            {task.title}
            {state.state === "failure"
              ? "失败"
              : state.state === "success"
                ? "完成"
                : state.state === "reused"
                  ? "使用已有结果"
                  : "状态更新"}
          </p>
          <button
            className="shrink-0 px-1 text-secondary"
            aria-label={`关闭${task.title}通知`}
            onClick={() => remove(task)}
          >
            ×
          </button>
        </div>
        <p role="status" className="text-base font-normal leading-relaxed">
          {taskMessage(task.title, state)}
        </p>
        {deleted && <p>该申请已删除，无法打开工作区。</p>}
        {success && reachable && (
          <Link
            className="text-base text-accent-ink underline"
            href={taskDestination(task, state)}
            onClick={() => remove(task)}
          >
            查看结果
          </Link>
        )}
        {!success &&
          reachable &&
          task.family === "interview-debriefs" &&
          state.state !== "removed" && (
            <Link
              className="text-base text-accent-ink underline"
              href={task.href}
              onClick={() => remove(task)}
            >
              查看执行状态
            </Link>
          )}
      </div>
    );
  };
  return (
    <aside
      ref={box}
      aria-label="任务通知"
      className="fixed right-4 bottom-4 z-40 w-[min(24rem,calc(100vw-2rem))] text-base"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={(event) => setFocused(event.target.matches(":focus-visible"))}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false);
      }}
    >
      {(open || current) && (
        <div
          className="mb-2 max-h-[min(28rem,65vh)] overflow-y-auto rounded-control border border-line bg-paper shadow-soft"
          aria-label={open ? "未处理通知" : "新通知"}
        >
          {open ? notices.map(render) : current && render(current)}
        </div>
      )}
      <div className="flex justify-end">
        <button
          aria-label={`未处理通知 ${notices.length} 条`}
          aria-expanded={open}
          className="inline-flex min-h-11 items-center gap-2 rounded-control border border-line bg-paper px-3 py-2 text-secondary shadow-soft"
          onClick={() => {
            setOpen(!open);
            setPopup(null);
          }}
        >
          <svg
            aria-hidden="true"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
          </svg>{" "}
          通知 <span>{notices.length}</span>
        </button>
      </div>
    </aside>
  );
}
