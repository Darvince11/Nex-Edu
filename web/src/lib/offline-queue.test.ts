import { describe, expect, it } from "vitest";
import { enqueue, flush, type QueuedRegister, readQueue } from "./offline-queue";

function memoryStore() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
  };
}

const register = (overrides: Partial<QueuedRegister> = {}): QueuedRegister => ({
  batch_id: crypto.randomUUID(),
  school: "greenfield",
  arm: "arm-1",
  date: "2026-10-19",
  recorded_at: "2026-10-19T08:00:00Z",
  entries: [{ student: "s1", status: "present" }],
  ...overrides,
});

describe("offline attendance queue", () => {
  it("keeps only the newest register per class and day", () => {
    const store = memoryStore();
    enqueue(register({ batch_id: "old" }), store);
    enqueue(register({ batch_id: "new" }), store);
    enqueue(register({ batch_id: "other-day", date: "2026-10-20" }), store);
    expect(readQueue(store).map((q) => q.batch_id)).toEqual(["new", "other-day"]);
  });

  it("keeps items while offline and clears them once sent", async () => {
    const store = memoryStore();
    enqueue(register(), store);
    const offline = await flush(() => Promise.reject(new TypeError("Failed to fetch")), store);
    expect(offline).toMatchObject({ sent: 0, pending: 1 });
    const online = await flush(() => Promise.resolve(new Response("{}", { status: 200 })), store);
    expect(online).toMatchObject({ sent: 1, pending: 0 });
  });

  it("drops and reports registers the server rejects", async () => {
    const store = memoryStore();
    enqueue(register(), store);
    const result = await flush(() => Promise.resolve(new Response("{}", { status: 403 })), store);
    expect(result.failed).toHaveLength(1);
    expect(result.pending).toBe(0);
  });

  it("keeps items when the server has a temporary error", async () => {
    const store = memoryStore();
    enqueue(register(), store);
    const result = await flush(() => Promise.resolve(new Response("", { status: 503 })), store);
    expect(result.pending).toBe(1);
  });
});
