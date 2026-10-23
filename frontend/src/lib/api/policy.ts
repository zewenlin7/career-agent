/** Transport validation only. No backend field names or business endpoint assumptions. */
export function backendUrl(origin: string, path: string): URL {
  const base = new URL(origin);
  if (
    !["http:", "https:"].includes(base.protocol) ||
    base.username ||
    base.password ||
    base.pathname !== "/" ||
    base.search ||
    base.hash
  ) {
    throw new Error("invalid_backend_origin");
  }
  if (!/^\/api\/v1\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(path)) {
    throw new Error("invalid_backend_path");
  }
  return new URL(path, base);
}
