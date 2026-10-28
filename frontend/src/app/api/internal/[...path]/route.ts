import { backendUrl } from "@/lib/api/policy";
import { sameOriginWrite } from "@/features/workspace/transport-policy";
import { internalRule, internalBody, internalProjection } from "@/features/internal/policy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const failure = (code: string, status: number) =>
  Response.json({ error: { code } }, { status, headers: { "Cache-Control": "no-store" } });
async function handle(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.join("/");
  const incoming = new URL(request.url);
  let body: string | undefined;
  try {
    const rule = internalRule(path, request.method, incoming.searchParams);
    // Custom header is required even for private GETs: cross-origin forms/images cannot invoke this BFF.
    if (
      request.headers.get("x-internal-request") !== "1" ||
      (request.headers.get("sec-fetch-site") &&
        request.headers.get("sec-fetch-site") !== "same-origin")
    )
      return failure("invalid_origin", 403);
    if (request.method !== "GET") {
      if (
        !sameOriginWrite(request) ||
        !request.headers.get("content-type")?.startsWith("application/json")
      )
        return failure("invalid_origin", 403);
      const raw = await request.text();
      if (new TextEncoder().encode(raw).length > 1_000_000) return failure("input_too_large", 413);
      body = JSON.stringify(internalBody(JSON.parse(raw || "{}"), rule.body));
    }
  } catch {
    return failure("invalid_request", 422);
  }
  const origin = process.env.CAREER_AGENT_API_ORIGIN,
    token = process.env.CAREER_AGENT_OPS_TOKEN;
  if (!origin || !token) return failure("internal_not_configured", 503);
  try {
    const url = backendUrl(origin, `/api/v1/${path}`);
    const query = new URLSearchParams(incoming.searchParams);
    query.delete("private");
    url.search = query.toString();
    const response = await fetch(url, {
      method: request.method,
      body,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Ops-Token": token,
      },
      cache: "no-store",
      redirect: "error",
      signal: request.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const code = data?.error?.code;
      return failure(
        typeof code === "string" && /^[a-z][a-z0-9_]{0,79}$/.test(code) ? code : "request_failed",
        response.status,
      );
    }
    return Response.json(
      internalProjection(
        path,
        await response.json(),
        incoming.searchParams.get("private") === "confirmed",
      ),
      {
        status: response.status,
        headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
      },
    );
  } catch {
    return failure("connection_interrupted", 502);
  }
}
export { handle as GET, handle as POST };
