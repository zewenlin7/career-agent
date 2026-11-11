"use client";
import { useCallback, useState } from "react";
import { useRead } from "./client";
import { readHistory } from "./history";
import type { Page } from "./contracts";

/** Keep known rows on a failed refresh, scoped to this exact history request. */
export function useResultHistory<T>(path: string | null, identify: (row: T) => string | null) {
  const [last, setLast] = useState<{ path: string; data: Page<T> }>();
  const [removed, setRemoved] = useState<{ path: string | null; ids: string[] }>({
    path: null,
    ids: [],
  });
  const loader = useCallback(async (requested: string, signal: AbortSignal) => {
    const data = await readHistory<T>(requested, signal);
    if (!signal.aborted) setLast({ path: requested, data });
    return data;
  }, []);
  const read = useRead(path, loader);
  const known = last?.path === path ? last.data : read.data;
  const ids = removed.path === path ? removed.ids : [];
  const isRemoved = (id: string | null | undefined) => !!id && ids.includes(id);
  return {
    ...read,
    data: known
      ? { ...known, items: known.items.filter((row) => !isRemoved(identify(row))) }
      : undefined,
    isRemoved,
    hasRemoved: ids.length > 0,
    exclude: (id: string) =>
      setRemoved((current) => ({
        path,
        ids: current.path === path ? [...current.ids, id] : [id],
      })),
  };
}
