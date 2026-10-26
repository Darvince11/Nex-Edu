"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { BarList, ChartCard, compact, Meter, SERIES_1, TrendChart } from "@/components/charts";
import { LifecycleCard, SchoolBillingCard, SupportAccessCard } from "@/components/console-lifecycle";
import { TenantModulesCard } from "@/components/console-modules";
import { Alert, Badge, Button, Card, Empty, ErrorText, Loading, PageHeader, Stat } from "@/components/ui";
import { apiFetch, type PlatformSchool } from "@/lib/api";
import { SCHOOL_DOMAIN } from "@/lib/auth";
import { cedis, formatDate, timeAgo } from "@/lib/format";
import { PLATFORM_ACTIONS, TENANT_STATUS } from "@/lib/platform";
import { ROLE_LABELS, type Role } from "@/lib/roles";

const day = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
const number = (v: number) => v.toLocaleString("en-GB");

/**
 * One school as Nex Edu staff see it: who runs it, how big it is, how it uses
 * Nex Edu, its price band and what Nex Edu staff have done to it. Totals only:
 * no pupil, parent or staff record is shown here.
 */
export default function PlatformSchoolPage() {
  const { slug } = useParams<{ slug: string }>();
  const client = useQueryClient();
  const path = `/api/v1/platform/tenants/${slug}`;
  const school = useQuery({
    queryKey: ["platform", "tenant", slug],
    queryFn: () => apiFetch<PlatformSchool>(path, { school: false }),
  });
  const refresh = useMutation({
    mutationFn: () => apiFetch<PlatformSchool>(path, { method: "POST", school: false }),
    onSuccess: (data) => client.setQueryData(["platform", "tenant", slug], data),
  });

  if (school.isPending) return <Loading />;
  if (school.error) return <ErrorText error={school.error} />;
  const s = school.data;
  const u = s.usage;
  const status = TENANT_STATUS[s.status];

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 text-sm text-neutral-500">
        <Link href="/platform/schools" className="text-link underline hover:text-link-hover">
          Schools
        </Link>{" "}
        › <span aria-current="page">{s.name}</span>
      </nav>
      <PageHeader
        title={s.name}
        description={
          <>
            <span className="font-mono">
              {s.slug}.{SCHOOL_DOMAIN}
            </span>{" "}
            · on Nex Edu since {formatDate(s.created_at)}
          </>
        }
        actions={
          <>
            <Badge tone={status.tone}>{status.label}</Badge>
            {s.status === "active" && (
              <Button variant="secondary" busy={refresh.isPending} onClick={() => refresh.mutate()}>
                Refresh figures
              </Button>
            )}
          </>
        }
      />
      <ErrorText error={refresh.error} />

      {s.attention.length > 0 && (
        <div className="mb-4">
          <Alert tone="warning">Needs attention: {s.attention.join(" · ")}.</Alert>
        </div>
      )}

      {u ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Pupils" value={number(u.pupils)} hint={`${u.classes} classes`} />
          <Stat
            label="Staff"
            value={number(u.staff)}
            hint={`${s.people.staff_with_app} with an authenticator app`}
          />
          <Stat label="Parents" value={number(u.parents)} />
          <Stat
            label="Signed in this week"
            value={number(u.active_users_7d)}
            hint={`${number(u.active_users_30d)} in the last 30 days`}
          />
        </div>
      ) : (
        <Empty>No figures for this school{s.status === "active" ? " yet" : " while it isn't active"}.</Empty>
      )}

      {u && u.setup_total > 0 && (
        <div className="mt-6">
          <Card title="School set-up">
            <div className="mb-2 flex items-baseline justify-between gap-3 text-sm">
              <span>
                {u.setup_done === u.setup_total
                  ? "Every set-up step is done."
                  : `${u.setup_done} of ${u.setup_total} set-up steps done.`}
              </span>
            </div>
            <Meter value={u.setup_done} max={u.setup_total} label="School set-up steps done" />
            {u.setup_left.length > 0 && (
              <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
                Still to do: {u.setup_left.join(" · ")}
              </p>
            )}
          </Card>
        </div>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="Subscription">
          {s.band ? (
            <>
              <p className="text-3xl font-semibold">{cedis(s.band.price_pesewas)}</p>
              <p className="mt-1 text-sm font-medium">{s.band.label}</p>
              <p className="mt-2 text-xs text-neutral-500">
                A month, from the school's {number(u?.pupils ?? 0)} active pupils. No free trial. Invoiced on
                the 1st; suspended if unpaid 30 days after the due date.
              </p>
            </>
          ) : (
            <Empty>No price band until the school has figures.</Empty>
          )}
        </Card>

        <Card title="Proprietor">
          {s.owner ? (
            <Details
              rows={[
                ["Name", s.owner.name || "—"],
                [
                  "Email",
                  <a key="email" href={`mailto:${s.owner.email}`} className="text-link hover:text-link-hover">
                    {s.owner.email}
                  </a>,
                ],
                ["Phone", s.owner.phone || "—"],
                ["Last sign-in", timeAgo(s.owner.last_login)],
              ]}
            />
          ) : (
            <Empty>No proprietor recorded.</Empty>
          )}
        </Card>

        <Card title="School">
          <Details
            rows={[
              ["Type", s.registration?.school_type ?? "—"],
              ["Location", [s.registration?.town, s.registration?.region].filter(Boolean).join(", ") || "—"],
              ["School phone", s.registration?.phone || "—"],
              ["Expected pupils", s.registration ? number(s.registration.expected_pupils) : "—"],
              [
                "Approved",
                s.registration?.approved_at
                  ? `${formatDate(s.registration.approved_at)}${s.registration.approved_by ? ` by ${s.registration.approved_by}` : ""}`
                  : "—",
              ],
              ["Last activity", timeAgo(u?.last_activity_at)],
            ]}
          />
        </Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <LifecycleCard school={s} />
        <SchoolBillingCard school={s} />
        <SupportAccessCard school={s} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Pupils over time"
          description="Active pupils, counted each day."
          table={{
            head: ["Day", "Pupils", "Signed in (7 days)", "Register marks (7 days)"],
            rows: s.history.map((h) => [
              day(h.day, { day: "numeric", month: "short" }),
              number(h.pupils),
              number(h.active_users_7d),
              number(h.registers_7d),
            ]),
          }}
        >
          {s.history.length ? (
            <TrendChart
              name="Pupils"
              format={(v) => compact(v)}
              points={s.history.map((h) => ({
                label: day(h.day, { day: "numeric", month: "short" }),
                title: day(h.day, { weekday: "long", day: "numeric", month: "long" }),
                value: h.pupils,
                detail: [
                  { name: "Signed in (7 days)", value: number(h.active_users_7d) },
                  { name: "Register marks (7 days)", value: number(h.registers_7d) },
                ],
              }))}
            />
          ) : (
            <Empty>No history yet.</Empty>
          )}
        </ChartCard>

        <ChartCard
          title="People by role"
          description={`Active logins at this school. ${s.people.not_joined} invited but not yet signed up.`}
          table={{
            head: ["Role", "People"],
            rows: s.people.by_role.map((r) => [ROLE_LABELS[r.role as Role] ?? r.label, r.count]),
          }}
        >
          {s.people.by_role.length ? (
            <BarList
              series={[{ name: "People", color: SERIES_1 }]}
              format={(v) => number(v)}
              rows={s.people.by_role.map((r) => ({
                label: ROLE_LABELS[r.role as Role] ?? r.label,
                values: [r.count],
              }))}
            />
          ) : (
            <Empty>Nobody has access yet.</Empty>
          )}
        </ChartCard>
      </div>

      {u && (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card title="Use of Nex Edu">
            <div className="mb-4">
              <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                <span>SMS this month</span>
                <span className="tabular-nums text-neutral-600 dark:text-neutral-300">
                  {number(u.sms_sent_month)} of {number(u.sms_monthly_limit)}
                </span>
              </div>
              <Meter
                value={u.sms_sent_month}
                max={u.sms_monthly_limit}
                label="SMS allowance used this month"
              />
            </div>
            <Details
              rows={[
                ["Register marks, last 7 days", number(u.registers_7d)],
                ["Report cards published", number(u.report_cards_published)],
                ["Admission applications waiting", number(u.applications_pending)],
                ["Figures counted", timeAgo(u.collected_at)],
              ]}
            />
          </Card>
          <Card title="School fees through Nex Edu">
            <Details
              rows={[
                ["Paid, last 30 days", cedis(u.payments_30d_pesewas)],
                ["Paid, all time", cedis(u.payments_total_pesewas)],
                ["Still owed this term", cedis(u.outstanding_pesewas)],
              ]}
            />
            <p className="mt-3 text-xs text-neutral-500">
              Money parents pay the school. It goes to the school's own account, not to Nex Edu.
            </p>
          </Card>
        </div>
      )}

      {s.status === "active" && (
        <div className="mt-6">
          <TenantModulesCard slug={s.slug} />
        </div>
      )}

      <div className="mt-6">
        <Card title="Nex Edu staff actions on this school">
          {s.platform_events.length ? (
            <ol className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
              {s.platform_events.map((e) => (
                <li
                  key={`${e.occurred_at}-${e.action}`}
                  className="flex flex-wrap justify-between gap-x-4 py-2"
                >
                  <span>
                    <span className="font-medium">{PLATFORM_ACTIONS[e.action] ?? e.action}</span>
                    {e.reason && (
                      <span className="text-neutral-600 dark:text-neutral-300"> · {e.reason}</span>
                    )}
                  </span>
                  <span className="text-neutral-500">
                    {e.actor_email || "System"} · {formatDate(e.occurred_at)}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <Empty>No actions recorded.</Empty>
          )}
        </Card>
      </div>

      <p className="mt-6 text-xs text-neutral-500">
        Database version {s.schema_version || "—"}
        {s.migrated_at ? `, updated ${formatDate(s.migrated_at)}` : ""}
        {s.cell ? ` · cell ${s.cell}` : ""}
      </p>
    </>
  );
}

function Details({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-3">
          <dt className="text-neutral-500">{label}</dt>
          <dd className="min-w-0 text-right wrap-break-word">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
