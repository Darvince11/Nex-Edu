/**
 * Sends screen errors to the console's Problems list so Nex Edu staff see them
 * before a school calls. Messages are scrubbed again on the server. At most a
 * few reports per page load, each message once; failures are silent.
 */
import { apiFetch, getSelectedSchool } from "./api";

const MAX_PER_PAGE = 5;
const sent = new Set<string>();

export function reportError(error: unknown, source = ""): void {
  if (typeof window === "undefined" || sent.size >= MAX_PER_PAGE) return;
  const err = error instanceof Error ? error : new Error(String(error));
  const key = `${err.message}|${source}`;
  if (sent.has(key)) return;
  sent.add(key);
  void apiFetch("/api/v1/problems/browser", {
    method: "POST",
    school: false,
    body: {
      message: `${err.name}: ${err.message}`.slice(0, 500),
      source: source.slice(0, 300),
      stack: (err.stack ?? "").slice(0, 6000),
      page: window.location.pathname.slice(0, 300),
      school: getSelectedSchool() ?? "",
    },
  }).catch(() => {
    // Not signed in, offline or throttled: nothing more to do.
  });
}

/** Catch errors React doesn't see: event handlers, timers, rejected promises. */
export function listenForErrors(): () => void {
  const onError = (e: ErrorEvent) => reportError(e.error ?? e.message, e.filename);
  const onRejection = (e: PromiseRejectionEvent) => reportError(e.reason, "unhandled promise");
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
