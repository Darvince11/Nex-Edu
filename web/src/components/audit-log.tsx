"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Empty, ErrorText, Field, Input, Loading, Select, Table, Td } from "@/components/ui";
import { type AuditEntry, type AuditPage, apiFetch } from "@/lib/api";
import { AUDIT_ACTIONS } from "@/lib/platform";

const CATEGORIES: [string, string][] = [
  ["", "All activity"],
  ["auth.", "Sign-ins and passwords"],
  ["registration.", "Registrations"],
  ["billing.", "Pricing and payments"],
  ["announcement.", "Announcements"],
  ["problem.", "Problems"],
  ["platform_staff.", "Platform staff"],
  ["tenant.", "Schools"],
  ["system.", "System"],
];

const when = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Africa/Accra",
});

function details(e: AuditEntry): string {
  const parts: string[] = [];
  if (e.action === "auth.sign_in_failed" && typeof e.data.email === "string")
    parts.push(`tried ${e.data.email}`);
  if (e.action === "billing.price_changed")
    parts.push(
      `${(Number(e.data.before_pesewas) / 100).toFixed(2)} → ${(Number(e.data.after_pesewas) / 100).toFixed(2)} GH₵`,
    );
  if (e.action === "billing.payment_recorded")
    parts.push(`GH₵${(Number(e.data.amount_pesewas) / 100).toFixed(2)} for ${String(e.data.period ?? "")}`);
  if (typeof e.data.title === "string") parts.push(String(e.data.title));
  if (e.reason) parts.push(`“${e.reason}”`);
  return parts.join(" · ");
}

type Group = { slug: string; name: string; events: number };

/**
 * The platform audit log as a table. ``mine`` shows only the signed-in staff
 * member's own actions; otherwise a school list files events by school.
 */
export function AuditLog({ mine = false }: { mine?: boolean }) {
  const [school, setSchool] = useState("");
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [days, setDays] = useState("30");
  const base = mine ? "/api/v1/platform/audit/mine" : "/api/v1/platform/audit";
  const params = new URLSearchParams();
  if (school) params.set("school", school);
  if (action) params.set("action", action);
  if (actor.trim() && !mine) params.set("actor", actor.trim());
  if (days) params.set("days", days);

  const groups = useQuery({
    queryKey: ["platform", "audit-groups"],
    queryFn: () => apiFetch<Group[]>("/api/v1/platform/audit/groups", { school: false }),
    enabled: !mine,
  });
  const integrity = useQuery({
    queryKey: ["platform", "audit-verify"],
    queryFn: () =>
      apiFetch<{ valid: boolean; checked: number; first_bad_seq: number | null; reason: string }>(
        "/api/v1/platform/audit/verify",
        { school: false },
      ),
    enabled: !mine,
  });
  const log = useInfiniteQuery({
    queryKey: ["platform", "audit", mine, school, action, actor.trim(), days],
    queryFn: ({ pageParam }) =>
      apiFetch<AuditPage>(`${base}?${params}${pageParam ? `&before=${pageParam}` : ""}`, { school: false }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
  const events = log.data?.pages.flatMap((p) => p.events) ?? [];

  return (
    <div className={mine ? "" : "grid gap-4 lg:grid-cols-[15rem_1fr]"}>
      {!mine && (
        <aside aria-label="Schools" className="lg:sticky lg:top-4 lg:self-start">
          <p className="mb-2 text-xs font-medium tracking-wide text-neutral-500 uppercase">
            By school (30 days)
          </p>
          <ul className="flex flex-wrap gap-1 lg:flex-col">
            {[{ slug: "", name: "All schools and platform", events: -1 }, ...(groups.data ?? [])].map((g) => (
              <li key={g.slug || "all"}>
                <button
                  type="button"
                  aria-pressed={school === g.slug}
                  onClick={() => setSchool(g.slug)}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-1.5 text-left text-sm ${
                    school === g.slug
                      ? "bg-brand/10 font-medium text-brand-strong dark:bg-brand/20 dark:text-brand-bright"
                      : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
                  }`}
                >
                  <span className="truncate">{g.name}</span>
                  {g.events >= 0 && <span className="text-xs text-neutral-500 tabular-nums">{g.events}</span>}
                </button>
              </li>
            ))}
          </ul>
          {integrity.data && (
            <p className="mt-4 text-xs">
              {integrity.data.valid ? (
                <Badge tone="green">Log intact</Badge>
              ) : (
                <Badge tone="red">Log tampered</Badge>
              )}{" "}
              <span className="text-neutral-500">
                {integrity.data.valid
                  ? `${integrity.data.checked.toLocaleString("en-GB")} entries checked`
                  : `${integrity.data.reason} at entry ${integrity.data.first_bad_seq}`}
              </span>
            </p>
          )}
        </aside>
      )}

      <div className="min-w-0">
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Field label="Activity">
            <Select value={action} onChange={(e) => setAction(e.target.value)}>
              {CATEGORIES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          {!mine && (
            <Field label="Done by">
              <Input
                type="search"
                placeholder="Staff email…"
                value={actor}
                onChange={(e) => setActor(e.target.value)}
              />
            </Field>
          )}
          <Field label="Period">
            <Select value={days} onChange={(e) => setDays(e.target.value)}>
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="365">Last year</option>
              <option value="">Everything</option>
            </Select>
          </Field>
        </div>

        {log.isPending ? (
          <Loading />
        ) : log.error ? (
          <ErrorText error={log.error} />
        ) : !events.length ? (
          <Empty>Nothing recorded for this selection.</Empty>
        ) : (
          <>
            <Table head={["When", "What", "Who", ...(mine ? [] : ["School"]), "Details"]}>
              {events.map((e) => (
                <tr key={e.seq}>
                  <Td className="whitespace-nowrap tabular-nums">{when.format(new Date(e.occurred_at))}</Td>
                  <Td>
                    <span
                      className={e.action === "auth.sign_in_failed" ? "text-red-700 dark:text-red-400" : ""}
                    >
                      {AUDIT_ACTIONS[e.action] ?? e.action}
                    </span>
                  </Td>
                  <Td className="text-xs">
                    {e.actor_email || "—"}
                    {e.ip && <div className="text-neutral-500">{e.ip}</div>}
                  </Td>
                  {!mine && (
                    <Td className="text-xs">
                      {e.schools.length
                        ? e.schools.map((s) => (
                            <Link
                              key={s.slug}
                              href={`/platform/schools/${s.slug}`}
                              className="block hover:underline"
                            >
                              {s.name}
                            </Link>
                          ))
                        : "Platform"}
                    </Td>
                  )}
                  <Td className="text-xs text-neutral-600 dark:text-neutral-300">{details(e) || "—"}</Td>
                </tr>
              ))}
            </Table>
            {log.hasNextPage && (
              <div className="mt-3 flex justify-center">
                <Button variant="secondary" busy={log.isFetchingNextPage} onClick={() => log.fetchNextPage()}>
                  Show older entries
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
