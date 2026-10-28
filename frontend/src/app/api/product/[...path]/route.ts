import { safeResumeFields } from "@/features/profile-area/short-text";
import { backendUrl } from "@/lib/api/policy";
import {
  productRule,
  projectResponse,
  validateBody,
  sameOriginWrite,
} from "@/features/workspace/transport-policy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
function failure(code: string, status: number) {
  return Response.json({ error: { code } }, { status, headers: { "Cache-Control": "no-store" } });
}
async function handle(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.join("/");
  const incoming = new URL(request.url);
  let body: string | ArrayBuffer | undefined;
  const photoUpload = path === "profile-photos" && request.method === "POST";
  try {
    const rule = productRule(path, request.method, incoming.searchParams);
    if (request.method !== "GET") {
      // Same-origin JSON writes only; no credentials/headers from the browser are forwarded.
      if (photoUpload) {
        if (
          !sameOriginWrite(request) ||
          !["image/jpeg", "image/png", "image/webp"].includes(
            request.headers.get("content-type") || "",
          )
        )
          return failure("invalid_photo", 422);
        const reader = request.body?.getReader();
        if (!reader) return failure("invalid_photo", 422);
        const chunks: Uint8Array[] = [];
        let size = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > 5_000_000) {
            await reader.cancel();
            return failure("photo_too_large", 413);
          }
          chunks.push(value);
        }
        const bytes = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) {
          bytes.set(chunk, offset);
          offset += chunk.length;
        }
        body = bytes.buffer;
      } else {
        if (
          !sameOriginWrite(request) ||
          !request.headers.get("content-type")?.startsWith("application/json")
        )
          return failure("invalid_origin", 403);
        const raw = await request.text();
        if (new TextEncoder().encode(raw).length > 1_000_000)
          return failure("input_too_large", 413);
        body = JSON.stringify(validateBody(JSON.parse(raw || "{}"), rule.body));
      }
    }
  } catch {
    return failure("invalid_request", 422);
  }
  const origin = process.env.CAREER_AGENT_API_ORIGIN;
  if (!origin) return failure("backend_not_configured", 503);
  try {
    const url = backendUrl(origin, `/api/v1/${path}`);
    const query = new URLSearchParams(incoming.searchParams);
    query.delete("inline");
    url.search = query.toString();
    const upstream = await fetch(url, {
      method: request.method,
      body,
      headers: {
        Accept: "application/json, text/event-stream, application/pdf",
        "Content-Type": photoUpload ? request.headers.get("content-type")! : "application/json",
      },
      cache: "no-store",
      redirect: "error",
      signal: request.signal,
    });
    if (!upstream.ok) {
      let code = "request_failed";
      let fields: ReturnType<typeof safeResumeFields> = [];
      try {
        const data = await upstream.json();
        if (typeof data?.error?.code === "string" && /^[a-z][a-z0-9_]{0,79}$/.test(data.error.code))
          code = data.error.code;
        if (code === "resume_field_validation") fields = safeResumeFields(data?.error?.fields);
      } catch {
        /* Never forward raw upstream errors. */
      }
      if (fields.length)
        return Response.json(
          { error: { code, fields } },
          {
            status: upstream.status,
            headers: { "Cache-Control": "no-store" },
          },
        );
      return failure(code, upstream.status);
    }
    if (/^profile-photos\/[0-9a-f-]{36}$/.test(path)) {
      if (!upstream.headers.get("content-type")?.startsWith("image/jpeg"))
        return failure("invalid_photo", 502);
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "image/jpeg",
          "Cache-Control": "private, no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    if (path.endsWith("/download")) {
      if (!upstream.headers.get("content-type")?.startsWith("application/pdf"))
        return failure("invalid_pdf_response", 502);
      const artifact = path.split("/")[1];
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "application/pdf",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          "Content-Disposition": `${incoming.searchParams.get("inline") === "true" ? "inline" : "attachment"}; filename="resume-${artifact}.pdf"`,
        },
      });
    }
    if (path.startsWith("interview-debriefs/") && path.endsWith("/execute")) {
      if (!upstream.headers.get("content-type")?.startsWith("text/event-stream"))
        return failure("invalid_event_response", 502);
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-store",
          "X-Accel-Buffering": "no",
        },
      });
    }
    return Response.json(projectResponse(path, await upstream.json()), {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return failure("connection_interrupted", 502);
  }
}
export { handle as GET, handle as POST, handle as PATCH, handle as PUT, handle as DELETE };
