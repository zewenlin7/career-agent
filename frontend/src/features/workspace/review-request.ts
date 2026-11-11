/** Keep only a payload fingerprint and request ID across uncertain responses. */
export async function reviewRequest(key: string, payload: unknown): Promise<string> {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(payload)),
  );
  const fingerprint = Array.from(new Uint8Array(bytes), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  const saved = JSON.parse(sessionStorage.getItem(key) || "null") as {
    fingerprint: string;
    id: string;
  } | null;
  if (saved?.fingerprint === fingerprint) return saved.id;
  const id = crypto.randomUUID();
  sessionStorage.setItem(key, JSON.stringify({ fingerprint, id }));
  return id;
}
