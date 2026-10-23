import { createServer } from "node:http";
import { fixtureResponse } from "./fixtures/product-api.ts";
const requests: { method: string; path: string; hasOpsToken: boolean }[] = [];
createServer((req, res) => {
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
  requests.push({
    method: req.method || "",
    path: url.pathname + url.search,
    hasOpsToken: Boolean(req.headers["x-ops-token"]),
  });
  if (req.method !== "GET") {
    res.statusCode = 405;
    res.end("{}");
    return;
  }
  const result = fixtureResponse(url);
  res.statusCode = result.status;
  res.end(JSON.stringify(result.body));
}).listen(3111, "127.0.0.1");
