import { UUID_PATTERN } from "../applications/contracts";
const key = "career-job-create-v1";
export function pendingJobRequest(): { id: string; fingerprint: string } | null {
  const raw = sessionStorage.getItem(key);
  if (!raw) return null;
  const value = JSON.parse(raw);
  if (!UUID_PATTERN.test(value.id) || !/^[a-f0-9]{64}$/.test(value.fingerprint))
    throw new Error("invalid_request_identity");
  return value;
}
export function clearJobRequest() {
  sessionStorage.removeItem(key);
}
export async function jobRequest(payload: unknown): Promise<string> {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(payload)),
  );
  const fingerprint = Array.from(new Uint8Array(bytes), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  const old = pendingJobRequest();
  if (old) {
    if (old.fingerprint !== fingerprint) throw new Error("request_identity_conflict");
    return old.id;
  }
  const id = crypto.randomUUID();
  sessionStorage.setItem(key, JSON.stringify({ id, fingerprint }));
  return id;
}
