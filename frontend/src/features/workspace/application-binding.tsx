"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useAction, useRead } from "./client";
import { resumeChoices, resolveResume, type ResumeChoice } from "../profile-area/library";
import { ErrorNotice, Panel, ReadState, Select } from "./ui";

export type ApplicationBinding = {
  application_id: string;
  revision: number;
  profile_id: string | null;
  resume_revision_id: string | null;
  job_revision_id: string;
  profile_name: string | null;
  profile_revision: number | null;
  resume_name: string | null;
  resume_revision: number | null;
  job_revision: number;
};
export function ApplicationMaterials({ applicationId }: { applicationId: string }) {
  const path = `applications/${applicationId}/context`;
  const binding = useRead<ApplicationBinding>(path);
  const [editing, setEditing] = useState(false);
  return (
    <Panel title="当前使用简历">
      <ReadState loaded={!!binding.data} error={binding.error} />
      {binding.data && !editing && (
        <>
          <p>
            简历：
            {binding.data.resume_name ||
              (binding.data.resume_revision_id ? "已绑定简历" : "尚未选择")}
          </p>
          <Button onClick={() => setEditing(true)}>更换</Button>
        </>
      )}
      {binding.data && editing && (
        <BindingEditor
          binding={binding.data}
          onDone={() => {
            setEditing(false);
            binding.reload();
          }}
        />
      )}
    </Panel>
  );
}
function BindingEditor({ binding, onDone }: { binding: ApplicationBinding; onDone: () => void }) {
  const [resume, setResume] = useState(binding.resume_revision_id || "");
  const resumes = useRead<{ items: ResumeChoice[] }>(
    "resume-library/versions?limit=100",
    resumeChoices,
  );
  const action = useAction();
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          const choice = resumes.data?.items.find((r) => r.id === resume);
          const resolved = choice ? await resolveResume(choice) : null;
          await api(`applications/${binding.application_id}/context`, "PUT", {
            expected_revision: binding.revision,
            profile_id: null,
            resume_revision_id: resolved?.id || null,
            job_revision_id: binding.job_revision_id,
          });
          onDone();
        });
      }}
    >
      <Select label="简历" value={resume} onChange={(e) => setResume(e.target.value)}>
        <option value="">暂不选择</option>
        {resumes.data?.items.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </Select>
      <ErrorNotice code={resumes.error || action.error} />
      <div className="flex gap-3">
        <Button type="submit" disabled={action.busy} variant="primary">
          保存
        </Button>
        <Button onClick={onDone}>取消</Button>
      </div>
    </form>
  );
}
