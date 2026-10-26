import { afterEach, describe, expect, it, vi } from "vitest";
import { login } from "./allauth";

const fakeDocument = { cookie: "" };

afterEach(() => {
  vi.unstubAllGlobals();
  fakeDocument.cookie = "";
});

describe("CSRF cookie before writes", () => {
  it("fetches the session first when the cookie isn't there yet (slow page load)", async () => {
    const calls: { url: string; method: string; csrf: string | null }[] = [];
    vi.stubGlobal("document", fakeDocument);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit = {}) => {
        const headers = new Headers(init.headers);
        calls.push({ url, method: init.method ?? "GET", csrf: headers.get("X-CSRFToken") });
        if (url.endsWith("/auth/session")) fakeDocument.cookie = "csrftoken=abc123";
        return new Response(JSON.stringify({ status: 200, meta: { is_authenticated: true } }));
      }),
    );

    await login("parent@example.test", "a-long-password-1");

    expect(calls.map((c) => [c.method, c.url.split("/v1")[1]])).toEqual([
      ["GET", "/auth/session"],
      ["POST", "/auth/login"],
    ]);
    expect(calls[1]?.csrf).toBe("abc123");
  });

  it("goes straight to the request when the cookie is already set", async () => {
    fakeDocument.cookie = "csrftoken=ready";
    vi.stubGlobal("document", fakeDocument);
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ status: 200 })));
    vi.stubGlobal("fetch", fetchMock);

    await login("parent@example.test", "a-long-password-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
