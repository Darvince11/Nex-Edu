/**
 * Which school someone works in. People never choose: the school's own address
 * (greenfield.nexedu.com.gh) decides when it is one of theirs, then the school
 * they used last, then their first. The API re-checks membership on every request.
 */
import type { Me } from "./api";
import { SCHOOL_DOMAIN } from "./auth";

/** "greenfield" for greenfield.nexedu.com.gh; undefined on the main site or localhost. */
export function schoolFromHost(hostname: string, domain = SCHOOL_DOMAIN): string | undefined {
  const host = hostname.toLowerCase();
  const suffix = `.${domain.toLowerCase()}`;
  if (!host.endsWith(suffix)) return undefined;
  const sub = host.slice(0, -suffix.length);
  return sub && !sub.includes(".") && sub !== "www" ? sub : undefined;
}

export function pickSchool(
  me: Pick<Me, "schools">,
  saved: string | undefined,
  hostname = typeof window === "undefined" ? "" : window.location.hostname,
): string | undefined {
  const mine = new Set(me.schools.map((s) => s.slug));
  const fromHost = schoolFromHost(hostname);
  if (fromHost && mine.has(fromHost)) return fromHost;
  if (saved && mine.has(saved)) return saved;
  return me.schools[0]?.slug;
}
