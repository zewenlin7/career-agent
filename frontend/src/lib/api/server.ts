import "server-only";
import { backendUrl } from "./policy";

import { BackendError } from "./error";

/**
 * Product-only server reader. No Internal endpoints or Ops credential handling.
 * Future BFF routes must allowlist their resource and validate browser inputs, never
 * expose this transport as a generic forwarding endpoint. No implicit retry or cache.
 */
export async function readBackend<T>({
  path,
  query,
  decode,
}: {
  path: string;
  query?: URLSearchParams;
  decode: (value: unknown) => T;
}): Promise<T> {
  let url: URL;
  const headers = new Headers({ Accept: "application/json" });
  try {
    const origin = process.env.CAREER_AGENT_API_ORIGIN;
    if (!origin) throw new Error();
    url = backendUrl(origin, path);
    if (query) url.search = query.toString();
  } catch {
    throw new BackendError("configuration");
  }
  let response: Response;
  try {
    response = await fetch(url, {
      headers,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    // Do not return connection URLs, headers, raw exceptions or backend error bodies.
    throw new BackendError("unavailable");
  }
  if (!response.ok) throw new BackendError("response", response.status);
  try {
    return decode(await response.json());
  } catch {
    throw new BackendError("contract");
  }
}
