"use client";
import { useConfirmation } from "./confirmation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useAction, useRead, useRequestId } from "../workspace/client";
import { control, Field } from "../workspace/ui";
import { InlineName } from "./inline-name";
import { SavedAt, InlineError } from "./common";
import { ProfileEditor, ProfileView, type EditingProfile } from "./profile-editor";
import type { Data, Section } from "./contracts";
export type NamedProfile = {
  id: string;
  name: string;
  revision: number;
  data: Data;
  profile_id: string | null;
  section_revisions: Record<Section, number>;
  created_at: string;
  saved_at?: string | null;
};
export function PersonalPage() {
  const { confirm, confirmation } = useConfirmation();
  const list = useRead<{ items: NamedProfile[] }>("profile-library");
  const [selected, setSelected] = useState("");
  const [updated, setUpdated] = useState<NamedProfile>();
  const [editing, setEditing] = useState<EditingProfile>();
  const [intent, setIntent] = useState(0);
  const action = useAction(),
    requestId = useRequestId();
  const w = updated?.id === selected ? updated : list.data?.items.find((p) => p.id === selected);
  async function begin(p: NamedProfile) {
    setEditing(
      await api<EditingProfile>(`profile-library/${p.id}/editing`, "POST", {
        expected_revision: p.revision,
      }),
    );
  }
  function done(p: NamedProfile) {
    setUpdated(p);
    setEditing(undefined);
    list.reload();
  }
  return (
    <>
      {confirmation}
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="font-serif text-3xl">个人资料</h1>
        <Button
          disabled={action.busy || !!editing}
          onClick={() =>
            void action.run(async () => {
              const p = await api<NamedProfile>("profile-library", "POST", {
                request_id: requestId({ intent }),
              });
              setSelected(p.id);
              setUpdated(p);
              setIntent(intent + 1);
              list.reload();
              await begin(p);
            })
          }
        >
          {action.busy ? "正在准备…" : "新建"}
        </Button>
      </div>
      <InlineError code={action.error || list.error} />
      <Field label="个人资料">
        <select
          className={control}
          value={selected}
          disabled={action.busy || !!editing}
          onChange={(e) => {
            setSelected(e.target.value);
            setUpdated(undefined);
          }}
        >
          <option value="">请选择</option>
          {list.data?.items.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          {updated && !list.data?.items.some((p) => p.id === updated.id) && (
            <option value={updated.id}>{updated.name}</option>
          )}
        </select>
      </Field>
      {w && (
        <div key={w.id} className="mt-7 min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <InlineName
              value={w.name}
              label="修改资料名称"
              disabled={action.busy}
              save={async (name) => {
                setUpdated(
                  await api<NamedProfile>(`profile-library/${w.id}`, "PATCH", {
                    expected_revision: w.revision,
                    name,
                  }),
                );
                list.reload();
              }}
            />
            {!editing && (
              <div className="flex gap-3">
                <Button disabled={action.busy} onClick={() => void action.run(() => begin(w))}>
                  编辑
                </Button>
                <Button
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      if (!(await confirm(`删除“${w.name}”？`))) return;
                      await api(`profile-library/${w.id}`, "DELETE", {
                        expected_revision: w.revision,
                      });
                      setSelected("");
                      setUpdated(undefined);
                      list.reload();
                    })
                  }
                >
                  删除
                </Button>
              </div>
            )}
          </div>
          <SavedAt value={w.saved_at} />
          {editing ? (
            <ProfileEditor key={editing.id} record={w} initial={editing} done={done} />
          ) : (
            <ProfileView data={w.data} />
          )}
        </div>
      )}
    </>
  );
}
