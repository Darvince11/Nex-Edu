"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Badge,
  Button,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";

type AuditEvent = {
  seq: number;
  occurred_at: string;
  actor_email: string;
  action: string;
  target_type: string;
  target_id: string;
  ip: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string;
};
type Page = { next: string | null; results: AuditEvent[] };

const CATEGORIES: [string, string][] = [
  ["", "Everything"],
  ["students.", "Pupils and guardians"],
  ["admissions.", "Admissions"],
  ["attendance.", "Registers"],
  ["assessments.", "Scores and report cards"],
  ["academics.", "Classes and timetable"],
  ["finance.", "Fees and payments"],
  ["staff.", "Staff and leave"],
  ["members.", "Access"],
  ["school.", "School settings"],
  ["communication.", "Messages"],
];

const when = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Africa/Accra",
});

/** "assessments.score_amended" → "Assessments: score amended". */
function describe(action: string): string {
  const [area = "", what = ""] = action.split(".", 2);
  const label = area.charAt(0).toUpperCase() + area.slice(1);
  return what ? `${label}: ${what.replace(/_/g, " ")}` : label;
}

function changes(e: AuditEvent): string {
  if (!e.before && !e.after) return "";
  const keys = new Set([...Object.keys(e.before ?? {}), ...Object.keys(e.after ?? {})]);
  const parts: string[] = [];
  for (const key of keys) {
    const was = e.before?.[key];
    const now = e.after?.[key];
    if (JSON.stringify(was) === JSON.stringify(now)) continue;
    parts.push(e.before ? `${key}: ${String(was ?? "—")} → ${String(now ?? "—")}` : `${key}: ${String(now)}`);
    if (parts.length >= 4) break;
  }
  return parts.join("; ");
}

/**
 * Everything done in this school: who, what and when. Entries can't be edited or
 * deleted, and the chain check shows none has been tampered with.
 */
export default function SchoolAuditPage() {
  const [category, setCategory] = useState("");
  const [actor, setActor] = useState("");
  const [days, setDays] = useState("30");
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (actor.trim()) params.set("actor", actor.trim());
  if (days) params.set("days", days);
  const verify = useQuery({
    queryKey: ["audit-verify"],
    queryFn: () => api.get<{ valid: boolean; checked: number; reason: string }>("/api/v1/audit/verify"),
  });
  const log = useInfiniteQuery({
    queryKey: ["audit", category, actor.trim(), days],
    queryFn: ({ pageParam }) => api.get<Page>(pageParam || `/api/v1/audit/events?${params}`),
    initialPageParam: "",
    // The server's link is absolute and ends in "/"; the API helper takes a path without it.
    getNextPageParam: (last) => {
      if (!last.next) return undefined;
      const next = new URL(last.next);
      return next.pathname.replace(/\/$/, "") + next.search;
    },
  });
  const events = log.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Everything done in this school, by whom and when. Entries can't be changed or deleted."
        actions={
          verify.data &&
          (verify.data.valid ? (
            <Badge tone="green">
              Log intact · {verify.data.checked.toLocaleString("en-GB")} entries checked
            </Badge>
          ) : (
            <Badge tone="red">Log tampered: {verify.data.reason}</Badge>
          ))
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Activity">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Done by">
          <Input
            type="search"
            placeholder="Email…"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
          />
        </Field>
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
          <Table head={["When", "What", "Who", "Details"]}>
            {events.map((e) => (
              <tr key={e.seq}>
                <Td className="whitespace-nowrap tabular-nums">{when.format(new Date(e.occurred_at))}</Td>
                <Td>{describe(e.action)}</Td>
                <Td className="text-xs">
                  {e.actor_email || "System"}
                  {e.ip && <span className="block text-neutral-500">{e.ip}</span>}
                </Td>
                <Td className="text-xs wrap-break-word text-neutral-600 dark:text-neutral-300">
                  {[changes(e), e.reason && `“${e.reason}”`].filter(Boolean).join(" · ") || "—"}
                </Td>
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
    </>
  );
}
