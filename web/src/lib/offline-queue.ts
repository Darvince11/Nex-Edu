/**
 * Offline attendance registers.
 *
 * Connectivity in many schools is patchy. A register that can't be sent is kept
 * in localStorage with a batch id and the time it was taken, then retried when
 * the browser comes back online. The server treats a repeated batch id as a
 * no-op, so retrying is always safe.
 */

export type RegisterEntry = { student: string; status: string; note?: string };
export type QueuedRegister = {
  batch_id: string;
  school: string;
  arm: string;
  date: string;
  recorded_at: string;
  entries: RegisterEntry[];
};

const KEY = "nexedu:attendance-queue";

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readQueue(store: Storage | null = storage()): QueuedRegister[] {
  try {
    const raw = store?.getItem(KEY);
    return raw ? (JSON.parse(raw) as QueuedRegister[]) : [];
  } catch {
    return [];
  }
}

function writeQueue(items: QueuedRegister[], store: Storage | null = storage()): void {
  try {
    store?.setItem(KEY, JSON.stringify(items));
  } catch {
    // Storage full or blocked: the teacher sees the unsent state and can retry.
  }
}

/** Add or replace (same school, class and date: the newer register wins). */
export function enqueue(item: QueuedRegister, store: Storage | null = storage()): void {
  const others = readQueue(store).filter(
    (q) => !(q.school === item.school && q.arm === item.arm && q.date === item.date),
  );
  writeQueue([...others, item], store);
}

export function remove(batchId: string, store: Storage | null = storage()): void {
  writeQueue(
    readQueue(store).filter((q) => q.batch_id !== batchId),
    store,
  );
}

/**
 * Try to send every queued register. Network failures leave items queued;
 * a rejection from the server (4xx) drops the item and reports it.
 */
export async function flush(
  send: (item: QueuedRegister) => Promise<Response>,
  store: Storage | null = storage(),
): Promise<{ sent: number; failed: QueuedRegister[]; pending: number }> {
  let sent = 0;
  const failed: QueuedRegister[] = [];
  for (const item of readQueue(store)) {
    try {
      const response = await send(item);
      if (response.ok) {
        sent += 1;
        remove(item.batch_id, store);
      } else if (response.status >= 400 && response.status < 500) {
        failed.push(item);
        remove(item.batch_id, store);
      }
    } catch {
      // Still offline; keep it for next time.
    }
  }
  return { sent, failed, pending: readQueue(store).length };
}
