"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Badge, Empty, ErrorText, Input, Loading, PageHeader, Select, Table, Td } from "@/components/ui";
import { apiFetch, type Paged, type PlatformTenant } from "@/lib/api";
import { SCHOOL_DOMAIN } from "@/lib/auth";
import { cedis, timeAgo } from "@/lib/format";
import { TENANT_STATUS as STATUS } from "@/lib/platform";

/** Every school on the platform, with its size and price band. Open one for its details. */
export default function PlatformSchoolsPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (status) params.set("status", status);
  const schools = useQuery({
    queryKey: ["platform", "tenants", q.trim(), status],
    queryFn: () => apiFetch<Paged<PlatformTenant>>(`/api/v1/platform/tenants?${params}`, { school: false }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Schools"
        description="Every school on Nex Edu with its size, price band and last activity. School records stay private to each school."
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_12rem]">
        <Input
          type="search"
          placeholder="Search by name or web address…"
          aria-label="Search schools"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          {Object.entries(STATUS).map(([value, s]) => (
            <option key={value} value={value}>
              {s.label}
            </option>
          ))}
        </Select>
      </div>
      {schools.isPending ? (
        <Loading />
      ) : schools.error ? (
        <ErrorText error={schools.error} />
      ) : !schools.data.results.length ? (
        <Empty>{q || status ? "No schools match." : "No schools yet."}</Empty>
      ) : (
        <Table head={["School", "Location", "Pupils", "Staff", "Price band", "Last active", "Status"]}>
          {schools.data.results.map((t) => (
            <tr key={t.id}>
              <Td>
                <Link href={`/platform/schools/${t.slug}`} className="font-medium hover:underline">
                  {t.name}
                </Link>
                {t.is_canary && (
                  <span className="ml-2">
                    <Badge tone="blue">Canary</Badge>
                  </span>
                )}
                <div className="font-mono text-xs text-neutral-500">
                  {t.slug}.{SCHOOL_DOMAIN}
                </div>
              </Td>
              <Td>{[t.town, t.region].filter(Boolean).join(", ") || "—"}</Td>
              <Td className="tabular-nums">{t.pupils?.toLocaleString("en-GB") ?? "—"}</Td>
              <Td className="tabular-nums">{t.staff?.toLocaleString("en-GB") ?? "—"}</Td>
              <Td className="whitespace-nowrap">
                {t.band ? (
                  <>
                    {cedis(t.band.price_pesewas)}
                    <div className="text-xs text-neutral-500">{t.band.label}</div>
                  </>
                ) : (
                  "—"
                )}
              </Td>
              <Td className="whitespace-nowrap">{timeAgo(t.last_activity_at)}</Td>
              <Td>
                <div className="flex flex-col items-start gap-1">
                  <Badge tone={STATUS[t.status].tone}>{STATUS[t.status].label}</Badge>
                  {t.attention.length > 0 && <Badge tone="amber">Needs attention</Badge>}
                </div>
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
