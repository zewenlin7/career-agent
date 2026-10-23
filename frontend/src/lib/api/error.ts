export class BackendError extends Error {
  readonly kind: "configuration" | "unavailable" | "response" | "contract";
  readonly status?: number;
  constructor(kind: BackendError["kind"], status?: number) {
    super(`backend_${kind}`);
    this.name = "BackendError";
    this.kind = kind;
    this.status = status;
  }
}
