"use client";
import { safeResumeFields, type ResumeFieldError } from "../profile-area/short-text";
import { useCallback, useEffect, useRef, useState } from "react";
export class ApiError extends Error {
  constructor(
    public code: string,
    public status = 0,
    public fields: ResumeFieldError[] = [],
  ) {
    super(code);
  }
}
export const endpoint = (path: string) => `/api/product/${path}`;
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(endpoint(path), {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal,
    });
  } catch {
    throw new ApiError("connection_interrupted");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(
      error?.error?.code || "request_failed",
      response.status,
      safeResumeFields(error?.error?.fields),
    );
  }
  return response.json() as Promise<T>;
}
export function useRead<T>(
  path: string | null,
  loader?: (path: string, signal: AbortSignal) => Promise<T>,
) {
  const [state, setState] = useState<{ path: string | null; data?: T; error?: string }>({
    path: null,
  });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  useEffect(() => {
    if (!path) return;
    const abort = new AbortController();
    let active = true;
    (loader ? loader(path, abort.signal) : api<T>(path, "GET", undefined, abort.signal))
      .then((data) => {
        if (active) setState({ path, data });
      })
      .catch((e) => {
        if (active) setState({ path, error: e instanceof ApiError ? e.code : "invalid_response" });
      });
    return () => {
      active = false;
      abort.abort();
    };
  }, [path, nonce, loader]);
  return {
    data: state.path === path ? state.data : undefined,
    error: state.path === path ? state.error : undefined,
    loading: !!path && state.path !== path,
    reload,
  };
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<string>();
  const active = useRef(false);
  const run = async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (active.current) return;
    active.current = true;
    setBusy(true);
    setError(undefined);
    try {
      return await fn();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.code
          : e instanceof DOMException && e.name === "AbortError"
            ? "connection_interrupted"
            : "invalid_request",
      );
    } finally {
      active.current = false;
      setBusy(false);
    }
  };
  return { busy, error, run };
}
/** Reuse the same UUID for an identical manual retry, never silently repeat a mutation. */
export function useRequestId() {
  const last = useRef<{ key: string; id: string } | null>(null);
  return (payload: unknown) => {
    const key = JSON.stringify(payload);
    if (last.current?.key !== key) last.current = { key, id: crypto.randomUUID() };
    return last.current.id;
  };
}
