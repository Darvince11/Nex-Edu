"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { BarList, ChartCard, ColumnChart, compact, SERIES_1, TrendChart } from "@/components/charts";
import { Alert, Card, Empty, ErrorText, Loading, PageHeader, Stat } from "@/components/ui";
import { apiFetch, type PlatformOverview } from "@/lib/api";
import { cedis, timeAgo } from "@/lib/format";

const day = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
const number = (v: number) => v.toLocaleString("en-GB");

/** The console's front page: totals and trends across every school. Counts only. */
export default function PlatformDashboardPage() {
  const overview = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => apiFetch<PlatformOverview>("/api/v1/platform/overview", { school: false }),
    refetchInterval: 5 * 60_000,
  });

  if (overview.isPending) return <Loading />;
  if (overview.error) return <ErrorText error={overview.error} />;
  const d = overview.data;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Every school on Nex Edu, in numbers. Updated ${timeAgo(d.generated_at)}; school figures refresh hourly.`}
      />

      {d.registrations_pending > 0 && (
        <div className="mb-4">
          <Alert tone="info">
            {d.registrations_pending} school registration{d.registrations_pending === 1 ? " is" : "s are"}{" "}
            waiting for review.{" "}
            <Link href="/platform/registrations" className="font-medium underline">
              Review now
            </Link>
          </Alert>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Active schools"
          value={number(d.schools.active)}
          hint={`${d.schools.active_7d} used Nex Edu this week${d.schools.setting_up ? ` · ${d.schools.setting_up} setting up` : ""}`}
        />
        <Stat label="Pupils" value={number(d.people.pupils)} hint="Active pupils in all schools" />
        <Stat
          label="Staff and parents"
          value={number(d.people.staff + d.people.parents)}
          hint={`${number(d.people.staff)} staff · ${number(d.people.parents)} parents`}
        />
        <Stat
          label="Signed in this week"
          value={number(d.people.active_users_7d)}
          hint={`${number(d.people.active_users_30d)} in the last 30 days`}
        />
        <Stat
          label="Subscription value"
          value={cedis(d.money.expected_subscriptions_pesewas)}
          hint="Per billing period, from each school's price band"
        />
        <Stat
          label="School fees paid through Nex Edu"
          value={cedis(d.money.fees_processed_30d_pesewas)}
          hint={`Last 30 days · ${cedis(d.money.fees_processed_total_pesewas)} in total`}
        />
        <Stat
          label="Fees still owed to schools"
          value={cedis(d.money.fees_outstanding_pesewas)}
          hint="Current term, all schools"
        />
        <Stat label="SMS sent this month" value={number(d.messages.sms_sent_month)} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Pupils on Nex Edu"
          description="Active pupils across all schools, by day."
          table={{
            head: ["Day", "Pupils", "Schools counted", "Signed in (7 days)"],
            rows: d.history.map((h) => [
              day(h.day, { day: "numeric", month: "short" }),
              number(h.pupils),
              h.schools,
              number(h.active_users),
            ]),
          }}
        >
          {d.history.length ? (
            <TrendChart
              name="Pupils"
              format={(v) => compact(v)}
              points={d.history.map((h) => ({
                label: day(h.day, { day: "numeric", month: "short" }),
                title: day(h.day, { weekday: "long", day: "numeric", month: "long" }),
                value: h.pupils,
                detail: [
                  { name: "Schools", value: String(h.schools) },
                  { name: "Signed in (7 days)", value: number(h.active_users) },
                ],
              }))}
            />
          ) : (
            <Empty>Figures appear once schools are counted.</Empty>
          )}
        </ChartCard>

        <ChartCard
          title="People signing in"
          description="Staff, parents and pupils who signed in during the 7 days before each day."
          table={{
            head: ["Day", "Signed in"],
            rows: d.history.map((h) => [
              day(h.day, { day: "numeric", month: "short" }),
              number(h.active_users),
            ]),
          }}
        >
          {d.history.length ? (
            <TrendChart
              name="Signed in (7 days)"
              format={(v) => compact(v)}
              points={d.history.map((h) => ({
                label: day(h.day, { day: "numeric", month: "short" }),
                title: day(h.day, { weekday: "long", day: "numeric", month: "long" }),
                value: h.active_users,
              }))}
            />
          ) : (
            <Empty>No sign-ins counted yet.</Empty>
          )}
        </ChartCard>

        <ChartCard
          title="New schools"
          description="Schools that went live each month."
          table={{
            head: ["Month", "Schools"],
            rows: d.schools_by_month.map((m) => [day(m.month, { month: "long", year: "numeric" }), m.count]),
          }}
        >
          <ColumnChart
            name="New schools"
            format={(v) => compact(v)}
            columns={d.schools_by_month.map((m) => ({
              label: day(m.month, { month: "short" }),
              title: day(m.month, { month: "long", year: "numeric" }),
              value: m.count,
            }))}
          />
        </ChartCard>

        <ChartCard
          title="Registrations received"
          description="Schools that asked to join each month, approved or not."
          table={{
            head: ["Month", "Registrations"],
            rows: d.registrations_by_month.map((m) => [
              day(m.month, { month: "long", year: "numeric" }),
              m.count,
            ]),
          }}
        >
          <ColumnChart
            name="Registrations received"
            format={(v) => compact(v)}
            columns={d.registrations_by_month.map((m) => ({
              label: day(m.month, { month: "short" }),
              title: day(m.month, { month: "long", year: "numeric" }),
              value: m.count,
            }))}
          />
        </ChartCard>

        <ChartCard
          title="Schools by price band"
          description="Which band each active school's pupil numbers put it in."
          table={{
            head: ["Band", "Price", "Schools"],
            rows: d.bands.map((b) => [b.label, cedis(b.price_pesewas), b.schools]),
          }}
        >
          <BarList
            series={[{ name: "Schools", color: SERIES_1 }]}
            format={(v) => number(v)}
            rows={d.bands.map((b) => ({
              label: `${b.label} · ${cedis(b.price_pesewas)}`,
              values: [b.schools],
            }))}
          />
        </ChartCard>

        <ChartCard
          title="Schools by region"
          description="Where active schools are."
          table={{ head: ["Region", "Schools"], rows: d.by_region.map((r) => [r.region, r.schools]) }}
        >
          {d.by_region.length ? (
            <BarList
              series={[{ name: "Schools", color: SERIES_1 }]}
              format={(v) => number(v)}
              rows={d.by_region.map((r) => ({ label: r.region, values: [r.schools] }))}
            />
          ) : (
            <Empty>No regions recorded yet.</Empty>
          )}
        </ChartCard>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="Largest schools">
          {d.top_schools.length ? (
            <ol className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {d.top_schools.map((s, i) => (
                <li key={s.slug} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="w-4 text-right text-xs text-neutral-500 tabular-nums">{i + 1}</span>
                    <Link
                      href={`/platform/schools/${s.slug}`}
                      className="truncate font-medium hover:underline"
                    >
                      {s.name}
                    </Link>
                  </span>
                  <span className="shrink-0 text-neutral-600 tabular-nums dark:text-neutral-300">
                    {number(s.pupils)} pupils · {number(s.staff)} staff
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <Empty>No schools yet.</Empty>
          )}
        </Card>

        <Card title="Needs attention">
          {d.attention.length ? (
            <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {d.attention.map((s) => (
                <li key={s.slug} className="py-2 text-sm">
                  <Link href={`/platform/schools/${s.slug}`} className="font-medium hover:underline">
                    {s.name}
                  </Link>
                  <p className="text-neutral-600 dark:text-neutral-300">{s.reasons.join(" · ")}</p>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Every school is active and within its limits.</Empty>
          )}
        </Card>
      </div>
    </>
  );
}
