import { onboardingResponse, resetOnboarding } from "./fixtures/onboarding-api.ts";
import { internalResponse, resetInternal } from "./fixtures/internal-api.ts";
import { createServer } from "node:http";
import { workspaceResponse, resetWorkspace } from "./fixtures/workspace-api.ts";
import { fixtureResponse } from "./fixtures/product-api.ts";
const requests: { method: string; path: string; hasOpsToken: boolean }[] = [];
createServer(async (req, res) => {
  const url = new URL(req.url || "/", "http://127.0.0.1:3111");
  res.setHeader("Content-Type", "application/json");
  if (url.pathname === "/__ready") {
    res.end("{}");
    return;
  }
  if (url.pathname === "/__requests") {
    res.end(JSON.stringify(requests));
    return;
  }
  if (url.pathname === "/__reset") {
    resetWorkspace();
    resetInternal();
    resetOnboarding(url.searchParams.get("empty") === "true");
    requests.length = 0;
    res.end("{}");
    return;
  }
  requests.push({
    method: req.method || "",
    path: url.pathname + url.search,
    hasOpsToken: Boolean(req.headers["x-ops-token"]),
  });
  let raw = "";
  for await (const chunk of req) raw += chunk;
  const payload = raw ? JSON.parse(raw) : {};
  const result =
    internalResponse(
      url,
      req.method || "GET",
      payload,
      req.headers["x-ops-token"] === "synthetic-never-forward",
    ) ||
    onboardingResponse(url, req.method || "GET", payload) ||
    workspaceResponse(url, req.method || "GET", payload) ||
    fixtureResponse(url);
  if ("sse" in result && result.sse) {
    res.setHeader("Content-Type", "text/event-stream");
    res.end(result.sse);
    return;
  }
  if ("pdf" in result && result.pdf) {
    res.setHeader("Content-Type", "application/pdf");
    res.end("%PDF-1.4\n%%EOF");
    return;
  }
  res.statusCode = result.status;
  res.end(JSON.stringify(result.body));
}).listen(3111, "127.0.0.1");
