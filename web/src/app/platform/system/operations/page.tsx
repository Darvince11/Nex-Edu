"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, Card, Empty, ErrorText, Loading, PageHeader, Stat, Table, Td } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";

type Operations = {
  jobs: {
    name: string;
    key: string;
    every_seconds: number | null;
    last_started_at: string | null;
    last_finished_at: string | null;
    last_succeeded: boolean | null;
    last_result: string;
    last_error: string;
    failures_recent: number;
    late: boolean;
  }[];
  cells: { name: string; region: string; schools: number; capacity: number; accepting: boolean }[];
  migrations: {
    school: string;
    slug: string;
    started_at: string;
    finished_at: string;
    succeeded: boolean;
    schema_version: string;
    error: string;
  }[];
  migration_failures_7d: number;
  lifecycle: { suspended: number; closing: number };
};

const every = (seconds: number | null) => {
  if (!seconds) return "—";
  if (seconds % 86400 === 0) return seconds === 86400 ? "Daily" : `Every ${seconds / 86400} days`;
  if (seconds % 3600 === 0) return seconds === 3600 ? "Hourly" : `Every ${seconds / 3600} hours`;
  return `Every ${Math.round(seconds / 60)} min`;
};

/** Background jobs, database groups and school database updates. No school records here. */
export default function OperationsPage() {
  const ops = useQuery({
    queryKey: ["platform", "operations"],
    queryFn: () => apiFetch<Operations>("/api/v1/platform/system/operations", { school: false }),
    refetchInterval: 60_000,
  });
  if (ops.isPending) return <Loading />;
  if (ops.error) return <ErrorText error={ops.error} />;
  const o = ops.data;
  const failing = o.jobs.filter((j) => j.last_succeeded === false || j.late).length;
  return (
    <>
      <PageHeader
        title="Jobs and databases"
        description="Scheduled background jobs, database groups (cells) and updates to school databases."
      />
      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Jobs failing or late" value={failing} />
        <Stat label="Database updates failed (7 days)" value={o.migration_failures_7d} />
        <Stat label="Schools suspended" value={o.lifecycle.suspended} />
        <Stat label="Closed, waiting to be destroyed" value={o.lifecycle.closing} hint="Kept 90 days" />
      </div>
      <Card title="Scheduled jobs">
        <Table head={["Job", "How often", "Last run", "Result", ""]}>
          {o.jobs.map((j) => (
            <tr key={j.name}>
              <Td>
                <span className="font-medium">{j.key}</span>
                <span className="block font-mono text-xs text-neutral-500">{j.name}</span>
              </Td>
              <Td>{every(j.every_seconds)}</Td>
              <Td>{j.last_started_at ? timeAgo(j.last_started_at) : "Never"}</Td>
              <Td className="max-w-xs wrap-break-word text-xs">{j.last_error || j.last_result || "—"}</Td>
              <Td>
                {j.last_succeeded === false ? (
                  <Badge tone="red">Failed</Badge>
                ) : j.late ? (
                  <Badge tone="amber">Late</Badge>
                ) : j.last_succeeded ? (
                  <Badge tone="green">OK</Badge>
                ) : (
                  <Badge tone="grey">Not run yet</Badge>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_2fr]">
        <Card title="Database groups (cells)">
          {o.cells.length ? (
            <ul className="flex flex-col gap-2 text-sm">
              {o.cells.map((c) => (
                <li key={c.name} className="flex flex-wrap justify-between gap-2">
                  <span>
                    <span className="font-medium">{c.name}</span>{" "}
                    <span className="text-neutral-500">{c.region}</span>
                  </span>
                  <span className="tabular-nums">
                    {c.schools} of {c.capacity} schools{c.accepting ? "" : " · full"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No cells (local databases).</Empty>
          )}
        </Card>
        <Card title="Recent school database updates">
          {o.migrations.length ? (
            <Table head={["School", "When", "Version", ""]}>
              {o.migrations.map((m) => (
                <tr key={`${m.slug}-${m.started_at}`}>
                  <Td>
                    <Link href={`/platform/schools/${m.slug}`} className="hover:underline">
                      {m.school}
                    </Link>
                  </Td>
                  <Td>{formatDate(m.started_at)}</Td>
                  <Td className="font-mono text-xs">{m.schema_version || "—"}</Td>
                  <Td>
                    {m.succeeded ? (
                      <Badge tone="green">Done</Badge>
                    ) : (
                      <span title={m.error}>
                        <Badge tone="red">Failed</Badge>
                      </span>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No database updates recorded yet.</Empty>
          )}
        </Card>
      </div>
    </>
  );
}
