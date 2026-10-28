"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useAction, useRead } from "../workspace/client";
import { Field, control } from "../workspace/ui";
import type { Fact } from "../onboarding/contracts";
import { InlineError, dateLabel } from "./common";
import { Extraction } from "./extraction";
const categories: Record<string, string> = {
  education: "教育",
  experience: "工作",
  project: "项目",
  skill: "技能",
  general: "其他",
};
const states: Record<string, string> = {
  proposed: "待审核",
  verified: "已确认",
  rejected: "已拒绝",
  superseded: "已替代",
};
type Row = Fact & { source_label: string; updated_at: string | null };
export function FactsPage() {
  const [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<string[]>([]),
    [editing, setEditing] = useState(""),
    [statement, setStatement] = useState(""),
    [category, setCategory] = useState("general"),
    [adding, setAdding] = useState(false),
    [menu, setMenu] = useState(""),
    [invalid, setInvalid] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null),
    anchor = useRef<number | null>(null);
  const list = useRead<{ items: Row[]; has_more: boolean }>(
      `fact-library?limit=30&offset=${offset}`,
    ),
    action = useAction();
  const rows = list.data?.items || [];
  useEffect(() => {
    if (adding) dialog.current?.show();
    else dialog.current?.close();
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setAdding(false);
    }
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [adding]);
  function edit(row: Row) {
    setEditing(row.id);
    setStatement(row.statement);
    setCategory(row.category in categories ? row.category : "general");
    setInvalid(false);
    setMenu("");
  }
  async function save(row?: Row, nextCategory = category) {
    if (!statement.trim()) {
      setInvalid(true);
      return;
    }
    await action.run(async () => {
      if (row)
        await api(`fact-library/${row.id}`, "PATCH", {
          expected_revision: row.revision,
          statement: statement.trim(),
          category: nextCategory,
        });
      else await api("facts", "POST", { statement: statement.trim(), category: nextCategory });
      setEditing("");
      setAdding(false);
      setSelected(selected.filter((id) => id !== row?.id));
      list.reload();
    });
  }
  async function batch(kind: string, ids = selected) {
    const chosen = rows.filter((r) => ids.includes(r.id));
    const changes = chosen.filter(
      (r) =>
        kind === "archive" ||
        (kind === "verify" ? r.status === "proposed" : ["proposed", "verified"].includes(r.status)),
    ).length;
    const verb = kind === "archive" ? "删除" : kind === "verify" ? "确认" : "拒绝";
    if (
      !confirm(
        `${changes} 条事实将被${verb}。${chosen.length - changes ? `\n${chosen.length - changes} 条将保持不变。` : ""}${kind === "archive" ? "\n历史记录将保留。" : ""}`,
      )
    )
      return;
    await action.run(async () => {
      await api("fact-library/actions", "POST", { ids, action: kind });
      setSelected(selected.filter((id) => !ids.includes(id)));
      setMenu("");
      list.reload();
    });
  }
  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-serif text-3xl">事实库</h1>
        <Button
          variant="primary"
          onClick={() => {
            setAdding(!adding);
            setStatement("");
            setCategory("general");
            setInvalid(false);
          }}
        >
          添加
        </Button>
      </div>
      <Extraction onAdded={list.reload} existing={rows.map((r) => r.statement)} />
      <div className="my-4 flex flex-wrap items-center gap-3">
        <select
          aria-label="快速选择"
          className={control + " !w-auto"}
          value=""
          onChange={(e) => {
            const v = e.target.value;
            setSelected(
              rows
                .filter(
                  (r) =>
                    v === "all" ||
                    (v === "reviewed"
                      ? ["verified", "rejected"].includes(r.status)
                      : r.status === v),
                )
                .map((r) => r.id),
            );
          }}
        >
          <option value="">快速选择</option>
          <option value="all">本页全部</option>
          <option value="proposed">待审核</option>
          <option value="verified">已确认</option>
          <option value="rejected">已拒绝</option>
          <option value="reviewed">已审核</option>
          <option value="none">清除选择</option>
        </select>
        {!!selected.length && (
          <div role="region" aria-label="批量操作" className="flex flex-wrap items-center gap-3">
            <span>已选 {selected.length} 条</span>
            <Button disabled={action.busy} onClick={() => void batch("verify")}>
              确认
            </Button>
            <Button disabled={action.busy} onClick={() => void batch("reject")}>
              拒绝
            </Button>
            <Button disabled={action.busy} onClick={() => void batch("archive")}>
              删除
            </Button>
            <Button onClick={() => setSelected([])}>清除选择</Button>
          </div>
        )}
      </div>
      <InlineError code={list.error || action.error} />
      <div className="relative max-w-full overflow-x-auto">
        <table
          aria-label="事实列表"
          className="w-full min-w-[650px] border-collapse text-left text-sm"
        >
          <thead className="border-y border-line text-secondary">
            <tr>
              <th className="p-3">
                <input
                  type="checkbox"
                  aria-label="选择本页全部事实"
                  checked={!!rows.length && rows.every((r) => selected.includes(r.id))}
                  onChange={(e) => setSelected(e.target.checked ? rows.map((r) => r.id) : [])}
                />
              </th>
              <th className="py-3">内容</th>
              <th>类别</th>
              <th>状态</th>
              <th>来源</th>
              <th>更新时间</th>
              <th>
                <span className="sr-only">操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={r.id}
                className="group border-b border-line"
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu(r.id);
                }}
              >
                <td className="p-3 align-top">
                  <input
                    type="checkbox"
                    aria-label={`选择事实：${r.statement}`}
                    checked={selected.includes(r.id)}
                    onClick={(e) => {
                      if (e.shiftKey && anchor.current !== null) {
                        const range = rows
                          .slice(Math.min(i, anchor.current), Math.max(i, anchor.current) + 1)
                          .map((r) => r.id);
                        setSelected([...new Set([...selected, ...range])]);
                      } else {
                        setSelected(
                          selected.includes(r.id)
                            ? selected.filter((id) => id !== r.id)
                            : [...selected, r.id],
                        );
                      }
                      anchor.current = i;
                    }}
                    onChange={() => {}}
                  />
                </td>
                <td className="max-w-lg py-3 pr-4 align-top" onDoubleClick={() => edit(r)}>
                  {editing === r.id ? (
                    <div className="space-y-2">
                      <textarea
                        autoFocus
                        aria-label="事实内容"
                        className={control}
                        value={statement}
                        onChange={(e) => setStatement(e.target.value)}
                      />
                      {invalid && !statement.trim() && <InlineError message="请输入内容。" />}
                      <div className="flex gap-2">
                        <Button disabled={action.busy} onClick={() => void save(r)}>
                          保存
                        </Button>
                        <Button onClick={() => setEditing("")}>取消</Button>
                      </div>
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap break-words">{r.statement}</p>
                  )}
                </td>
                <td className="align-top py-3 pr-3">
                  <select
                    aria-label={`类别：${r.statement}`}
                    className="max-w-24 bg-transparent"
                    value={r.category in categories ? r.category : "general"}
                    disabled={action.busy}
                    onChange={(e) => {
                      const value = e.target.value;
                      void action.run(async () => {
                        await api(`fact-library/${r.id}`, "PATCH", {
                          expected_revision: r.revision,
                          statement: r.statement,
                          category: value,
                        });
                        list.reload();
                      });
                    }}
                  >
                    {Object.entries(categories).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="align-top py-3 pr-3">
                  <details>
                    <summary className="cursor-pointer whitespace-nowrap">
                      {states[r.status]}
                    </summary>
                    <div className="flex flex-col gap-2 pt-2">
                      <button onClick={() => void batch("verify", [r.id])}>确认</button>
                      <button onClick={() => void batch("reject", [r.id])}>拒绝</button>
                    </div>
                  </details>
                </td>
                <td className="align-top py-3 pr-3 text-secondary">{r.source_label}</td>
                <td className="align-top py-3 pr-3 text-secondary">
                  {r.updated_at ? dateLabel(r.updated_at) : "—"}
                </td>
                <td className="relative align-top py-3">
                  <button
                    aria-label={`操作：${r.statement}`}
                    onClick={() => setMenu(menu === r.id ? "" : r.id)}
                  >
                    ⋯
                  </button>
                  {menu === r.id && (
                    <div className="absolute right-0 z-10 min-w-24 border border-line bg-paper p-2 shadow-soft">
                      <button className="block w-full p-2" onClick={() => edit(r)}>
                        编辑
                      </button>
                      <button
                        className="block w-full p-2"
                        onClick={() => void batch("archive", [r.id])}
                      >
                        删除
                      </button>
                      <button className="block w-full p-2" onClick={() => setMenu("")}>
                        取消
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!list.data ? (
        <p className="py-5">正在读取…</p>
      ) : (
        !rows.length && <p className="py-5">尚无事实</p>
      )}
      <div className="mt-5 flex gap-3">
        <Button
          disabled={!offset}
          onClick={() => {
            setOffset(offset - 30);
            setSelected([]);
          }}
        >
          上一页
        </Button>
        <Button
          disabled={!list.data?.has_more}
          onClick={() => {
            setOffset(offset + 30);
            setSelected([]);
          }}
        >
          下一页
        </Button>
      </div>
      <dialog
        ref={dialog}
        onCancel={() => setAdding(false)}
        onClose={() => setAdding(false)}
        className="fixed left-1/2 top-1/2 z-50 m-0 -translate-x-1/2 -translate-y-1/2 shadow-soft w-[min(90vw,32rem)] rounded-control bg-paper p-6 text-ink backdrop:bg-ink/30"
      >
        <div className="mb-4 flex justify-between">
          <h2 className="font-serif text-xl">添加事实</h2>
          <button aria-label="关闭添加" onClick={() => setAdding(false)}>
            ×
          </button>
        </div>
        <div className="space-y-4">
          <Field label="内容">
            <textarea
              autoFocus
              className={control}
              rows={4}
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
            />
          </Field>
          {invalid && !statement.trim() && <InlineError message="请输入内容。" />}
          <Field label="类别">
            <select
              className={control}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {Object.entries(categories).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <InlineError code={action.error} />
          <div className="flex gap-3">
            <Button disabled={action.busy} onClick={() => void save()}>
              保存
            </Button>
            <Button onClick={() => setAdding(false)}>取消</Button>
          </div>
        </div>
      </dialog>
    </>
  );
}
