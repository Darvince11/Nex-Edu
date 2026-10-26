"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Badge, Empty, ErrorText, Loading, PageHeader, Table, Td } from "@/components/ui";
import { apiFetch, type Paged, type PlatformRegistration } from "@/lib/api";
import { SCHOOL_DOMAIN } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { REGISTRATION_STATUSES as STATUS_TABS } from "@/lib/registration";

export default function RegistrationsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Registrations />
    </Suspense>
  );
}

function Registrations() {
  const router = useRouter();
  const requested = useSearchParams().get("status");
  const status = STATUS_TABS.find((t) => t.value === requested)?.value ?? "pending";
  const list = useQuery({
    queryKey: ["platform", "registrations", status],
    queryFn: () =>
      apiFetch<Paged<PlatformRegistration>>(`/api/v1/platform/registrations?status=${status}`, {
        school: false,
      }),
  });

  return (
    <>
      <PageHeader
        title="School registrations"
        description="Every school is checked by a person before its workspace is created."
      />
      <div
        role="tablist"
        aria-label="Status"
        className="mb-4 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={status === tab.value}
            onClick={() => router.replace(`/platform/registrations?status=${tab.value}`)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              status === tab.value
                ? "border-brand font-medium text-brand-strong dark:text-brand-bright"
                : "border-transparent text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {list.isPending ? (
        <Loading />
      ) : list.error ? (
        <ErrorText error={list.error} />
      ) : !list.data.results.length ? (
        <Empty>{status === "pending" ? "Nothing waiting for review." : "No registrations here yet."}</Empty>
      ) : (
        <>
          <Table head={["School", "Location", "Pupils", "Owner", "Submitted", ""]}>
            {list.data.results.map((r) => (
              <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900">
                <Td>
                  <Link
                    href={`/platform/registrations/${r.id}`}
                    className="font-medium text-link hover:text-link-hover"
                  >
                    {r.school_name}
                  </Link>
                  <div className="font-mono text-xs text-neutral-500">
                    {r.slug}.{SCHOOL_DOMAIN}
                  </div>
                </Td>
                <Td>
                  {r.town}
                  <div className="text-xs text-neutral-500">{r.region_label}</div>
                </Td>
                <Td className="tabular-nums">{r.expected_pupils}</Td>
                <Td>
                  {r.owner_name || "—"}
                  <div className="text-xs text-neutral-500">{r.owner_email}</div>
                </Td>
                <Td className="whitespace-nowrap">{formatDate(r.created_at)}</Td>
                <Td>{r.possible_duplicate && <Badge tone="amber">Possible duplicate</Badge>}</Td>
              </tr>
            ))}
          </Table>
          {list.data.next && (
            <p className="mt-3 text-sm text-neutral-500">
              Showing the newest 50. Older ones aren't listed yet.
            </p>
          )}
        </>
      )}
    </>
  );
}
