import assert from "node:assert/strict";
import { test } from "node:test";
import { backendUrl } from "../src/lib/api/policy.ts";
import { applicationNavigation, sectionNavigation, isActivePath } from "../src/lib/navigation.ts";

test("active navigation respects path segments", () => {
  const item = { href: "/applications", label: "Applications" };
  assert.ok(isActivePath("/applications/a/summary", item));
  assert.ok(!isActivePath("/applications-old", item));
  assert.ok(!isActivePath("/applications/a", { ...item, exact: true }));
});
test("application navigation preserves the explicit route context", () => {
  assert.equal(applicationNavigation("a/b")[0].href, "/applications/a%2Fb/summary");
  assert.deepEqual(
    sectionNavigation("synthetic-id", "apply").map((x) => x.label),
    ["简历", "招呼语", "投递记录"],
  );
});
test("transport stays on the configured origin and versioned relative path", () => {
  assert.equal(
    backendUrl("http://127.0.0.1:8000", "/api/v1/synthetic-resource").origin,
    "http://127.0.0.1:8000",
  );
  for (const path of [
    "https://other.test",
    "//other.test",
    "/api/v1/../ops",
    "/api/v1/%2e%2e",
    "/api/v1/a?url=x",
    "/api/v1/a//b",
  ]) {
    assert.throws(() => backendUrl("https://backend.test", path));
  }
  for (const origin of [
    "file:///tmp",
    "https://user:secret@backend.test",
    "https://backend.test/private",
    "https://backend.test?token=x",
  ]) {
    assert.throws(() => backendUrl(origin, "/api/v1/synthetic-resource"));
  }
});
