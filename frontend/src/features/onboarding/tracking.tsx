"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, useRead, useAction } from "@/features/workspace/client";
import { Panel, Field, Select, ReadState, ErrorNotice, control } from "@/features/workspace/ui";
import {
  applicationStatuses,
  statusLabels,
  type Application,
} from "@/features/applications/contracts";
import { transitions } from "./contracts";
export function ApplicationTracking({ id }: { id: string }) {
  const read = useRead<Application>(`applications/${id}`),
    router = useRouter();
  const refresh = () => {
    read.reload();
    router.refresh();
  };
  return (
    <Panel title="申请状态">
      <Button onClick={refresh}>刷新状态</Button>
      <ReadState loaded={!!read.data} error={read.error} />
      {read.data && (
        <TrackingForm key={read.data.revision} application={read.data} onSaved={refresh} />
      )}
      <ApplicationNote id={id} onSaved={refresh} />
    </Panel>
  );
}
function TrackingForm({ application, onSaved }: { application: Application; onSaved: () => void }) {
  const [correction, setCorrection] = useState(false),
    [target, setTarget] = useState(""),
    [done, setDone] = useState(false);
  const action = useAction();
  const options = correction
    ? applicationStatuses.filter((s) => s !== application.status)
    : transitions[application.status];
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        void action.run(async () => {
          await api(`applications/${application.id}`, "PATCH", {
            expected_revision: application.revision,
            status: target,
            correction,
            reason: f.get("reason") || null,
          });
          setDone(true);
          onSaved();
        });
      }}
    >
      <p>当前：{statusLabels[application.status]}</p>
      <details>
        <summary className="cursor-pointer text-sm">更正历史记录</summary>
        <label className="flex gap-2 text-sm">
          <input
            type="checkbox"
            checked={correction}
            onChange={(e) => {
              setCorrection(e.target.checked);
              setTarget("");
            }}
          />
          此前状态记录有误
        </label>
      </details>
      <Select
        label="更新为"
        value={target}
        onChange={(e) => {
          setTarget(e.target.value);
        }}
      >
        <option value="">请选择状态</option>
        {options.map((s) => (
          <option key={s} value={s}>
            {statusLabels[s]}
          </option>
        ))}
      </Select>
      {!options.length && (
        <p className="text-sm">此申请已结束。需要更正时，请展开“更正历史记录”。</p>
      )}
      <Field label={correction ? "更正原因" : "备注（可选）"}>
        <textarea name="reason" required={correction} maxLength={20000} className={control} />
      </Field>
      <Button type="submit" disabled={!target || action.busy || done}>
        更新状态
      </Button>
      <ErrorNotice code={action.error} />
      {action.error && <p className="text-sm">未自动重试。记录可能已变化，请刷新后再操作。</p>}
    </form>
  );
}
function ApplicationNote({ id, onSaved }: { id: string; onSaved: () => void }) {
  const [text, setText] = useState(""),
    [done, setDone] = useState(false),
    [attempted, setAttempted] = useState(false);
  const action = useAction();
  return (
    <form
      className="space-y-3 border-t border-line pt-4"
      onSubmit={(e) => {
        e.preventDefault();
        setAttempted(true);
        void action.run(async () => {
          await api(`applications/${id}/notes`, "POST", { text });
          setText("");
          setDone(true);
          setAttempted(false);
          onSaved();
        });
      }}
    >
      <Field label="添加申请笔记">
        <textarea
          required
          maxLength={20000}
          className={control}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setDone(false);
          }}
        />
      </Field>
      <Button type="submit" disabled={action.busy || attempted}>
        追加申请笔记
      </Button>
      <ErrorNotice code={action.error} />
      {action.error && (
        <>
          <p className="text-sm">请先刷新记录，确认笔记没有保存成功，再重试。</p>
          <Button onClick={() => setAttempted(false)}>已核对事件，重新启用追加</Button>
        </>
      )}
      {done && <p role="status">笔记已保存。</p>}
    </form>
  );
}
