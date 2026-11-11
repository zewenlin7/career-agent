"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useConfirmation } from "../profile-area/confirmation";
import { api, ApiError, useRequestId } from "./client";

export function DeleteRecord({
  path,
  onDeleted,
}: {
  path: string;
  onDeleted: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const requestId = useRequestId();
  const { confirm, confirmation } = useConfirmation();
  const notice = useConfirmation("知道了", "", "无法删除记录");
  return (
    <>
      <Button
        variant="danger"
        className="shrink-0"
        disabled={busy}
        onClick={async () => {
          if (!(await confirm("确定删除当前整条记录？"))) return;
          setBusy(true);
          try {
            const result = await api<{ deleted: boolean; used_by: string[] }>(path, "DELETE", {
              request_id: requestId(path),
            });
            if (result.deleted) await onDeleted();
            else void notice.confirm(`此记录已用于${result.used_by.join("、")}，无法删除。`);
          } catch (error) {
            const code = error instanceof ApiError ? error.code : "request_failed";
            void notice.confirm(
              code === "debrief_running"
                ? "这次复盘仍在执行，暂不能删除。"
                : code === "historical_reference_unavailable"
                  ? "无法确认这条历史记录的归属，暂不能删除。"
                  : code === "result_references_unavailable"
                    ? "暂时无法核实这条记录的引用，请稍后重试。"
                    : "暂时无法读取或删除记录，请稍后重试。",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        删除记录
      </Button>
      {confirmation}
      {notice.confirmation}
    </>
  );
}
