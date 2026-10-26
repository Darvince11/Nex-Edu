"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  BarList,
  ChartCard,
  ColumnChart,
  compact,
  Meter,
  SERIES_1,
  SERIES_2,
  type Series,
  TrendChart,
} from "@/components/charts";
import { SetupChecklistCard } from "@/components/setup-checklist";
import { Alert, Card, Empty, Field, PageHeader, Select, Stat } from "@/components/ui";
import { type Announcement, api, type Invoice, type Paged, type ReportCard, type Student } from "@/lib/api";
import { cedis, formatDate } from "@/lib/format";
import { useArms, useCurrentTerm, useSchool, useTerms } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import { isParentOnly, isTeacher } from "@/lib/roles";

type Insights = {
  term: number | null;
  enrolment?: { arm: string; label: string; pupils: number; girls: number; boys: number }[];
  attendance?: {
    date: string;
    present: number;
    late: number;
    absent: number;
    excused: number;
    marked: number;
    rate: number | null;
  }[];
  fees?: {
    billed_pesewas: number;
    collected_pesewas: number;
    outstanding_pesewas: number;
    collection_rate: number | null;
    by_class: {
      label: string;
      billed_pesewas: number;
      collected_pesewas: number;
      outstanding_pesewas: number;
    }[];
    weekly: { week: string; amount_pesewas: number; payments: number }[];
  };
  results?: {
    report_cards: number;
    subjects: { code: string; subject: string; average: number; pupils: number }[];
    grades: { grade: string; count: number }[];
  };
};

const GENDER: Series[] = [
  { name: "Girls", color: SERIES_1 },
  { name: "Boys", color: SERIES_2 },
];
const day = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
const pct = (v: number) => `${Math.round(v)}%`;
const ghs = (pesewas: number) => `GH₵${compact(pesewas / 100)}`;

export default function DashboardPage() {
  const { me, school, roles, can, hasModule } = useSchool();
  const parent = isParentOnly(roles);
  const current = useCurrentTerm();
  const terms = useTerms();
  // Empty until someone picks a term: then the current term is used.
  const [chosenTerm, setTerm] = useState("");
  const [arm, setArm] = useState("");
  const wholeSchool = can(PERM.STUDENTS_MANAGE) || can(PERM.ASSESSMENTS_PUBLISH);
  const arms = useArms(!wholeSchool, !parent);

  const term = chosenTerm || (current.data ? String(current.data.id) : "");

  const params = new URLSearchParams();
  if (term) params.set("term", term);
  if (arm) params.set("arm", arm);
  const insights = useQuery({
    queryKey: ["insights", term, arm],
    queryFn: () => api.get<Insights>(`/api/v1/school/insights?${params}`),
    placeholderData: keepPreviousData,
    // Wait for the current term, so the figures load once instead of twice.
    enabled: current.isFetched,
  });
  const children = useQuery({
    queryKey: ["students", "mine"],
    queryFn: () => api.get<Paged<Student>>("/api/v1/students?page_size=50"),
    enabled: parent,
  });
  const invoices = useQuery({
    queryKey: ["invoices", "mine"],
    queryFn: () => api.get<Invoice[]>("/api/v1/finance/invoices"),
    enabled: parent && hasModule("fees"),
  });
  const reports = useQuery({
    queryKey: ["report-cards", "mine"],
    queryFn: () => api.get<ReportCard[]>("/api/v1/assessments/report-cards"),
    enabled: parent,
  });
  const news = useQuery({
    queryKey: ["announcements", "latest"],
    queryFn: () => api.get<Paged<Announcement>>("/api/v1/communication/announcements?page_size=5"),
  });

  const data = insights.data;
  const firstName = me.data?.first_name || me.data?.email;
  const termLabel = terms.data?.find((t) => String(t.id) === term)?.label ?? current.data?.label;
  const pupils = data?.enrolment?.reduce((sum, r) => sum + r.pupils, 0) ?? 0;
  const latestDay = data?.attendance?.at(-1);
  const owed = (invoices.data ?? []).reduce((sum, i) => sum + i.balance_pesewas, 0);

  return (
    <>
      <PageHeader
        title={`Welcome${firstName ? `, ${firstName}` : ""}`}
        description={
          current.data ? `${school?.name} · ${current.data.label}` : `${school?.name} · no current term set`
        }
      />

      {can(PERM.SCHOOL_MANAGE) && <SetupChecklistCard />}

      {!current.data && can(PERM.ACADEMICS_MANAGE) && (
        <div className="mb-6">
          <Alert tone="warning">
            Set up the academic year and current term in{" "}
            <Link href="/academics" className="font-medium underline">
              Classes &amp; timetable
            </Link>{" "}
            before taking registers or billing fees.
          </Alert>
        </div>
      )}

      {/* One filter row; it scopes every figure below it. */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Field label="Term">
            <Select value={term} onChange={(e) => setTerm(e.target.value)}>
              {!term && <option value="">No term</option>}
              {terms.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {!parent && Boolean(arms.data?.length) && (
          <div className="w-48">
            <Field label="Class">
              <Select value={arm} onChange={(e) => setArm(e.target.value)}>
                <option value="">{wholeSchool ? "Whole school" : "All my classes"}</option>
                {arms.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {parent ? (
          <>
            <Stat label="Children" value={children.data?.results.length ?? 0} />
            {hasModule("fees") && <Stat label="Fees outstanding" value={cedis(owed)} />}
            <Stat label="Report cards" value={reports.data?.length ?? 0} hint="Published results" />
            <Stat
              label="Attendance, latest day"
              value={latestDay?.rate != null ? pct(latestDay.rate) : "—"}
              hint={
                latestDay
                  ? day(latestDay.date, { weekday: "short", day: "numeric", month: "short" })
                  : undefined
              }
            />
          </>
        ) : (
          <>
            {data?.enrolment && (
              <Stat
                label={isTeacher(roles) && !wholeSchool ? "My pupils" : "Pupils"}
                value={pupils.toLocaleString("en-GB")}
                hint={`${data.enrolment.length} classes`}
              />
            )}
            {data?.attendance && (
              <Stat
                label="Attendance, latest register"
                value={latestDay?.rate != null ? pct(latestDay.rate) : "—"}
                hint={
                  latestDay
                    ? `${latestDay.absent} absent · ${day(latestDay.date, { weekday: "short", day: "numeric", month: "short" })}`
                    : "No registers yet"
                }
              />
            )}
            {data?.fees && (
              <Stat
                label="Fees collected"
                value={cedis(data.fees.collected_pesewas)}
                hint={`${data.fees.collection_rate ?? 0}% of ${cedis(data.fees.billed_pesewas)} billed`}
              />
            )}
            {data?.results && (
              <Stat
                label="Report cards"
                value={data.results.report_cards.toLocaleString("en-GB")}
                hint={termLabel ? `Computed for ${termLabel}` : undefined}
              />
            )}
          </>
        )}
      </div>

      <div
        className={`mt-6 grid gap-4 transition-opacity lg:grid-cols-2 ${insights.isFetching && insights.isPlaceholderData ? "opacity-60" : ""}`}
        aria-busy={insights.isFetching}
      >
        {data?.attendance && <AttendanceCard rows={data.attendance} parent={parent} />}
        {data?.enrolment && <EnrolmentCard rows={data.enrolment} />}
        {data?.fees && <FeesCard fees={data.fees} termLabel={termLabel} />}
        {data?.results && <ResultsCard results={data.results} parent={parent} termLabel={termLabel} />}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card
          title="Announcements"
          actions={
            <Link href="/announcements" className="text-sm text-link hover:text-link-hover">
              All
            </Link>
          }
        >
          {news.data?.results.length ? (
            <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {news.data.results.map((a) => (
                <li key={a.id} className="py-2">
                  <div className="font-medium">{a.title}</div>
                  <div className="line-clamp-2 text-sm text-neutral-600 dark:text-neutral-400">{a.body}</div>
                  <div className="text-xs text-neutral-500">{formatDate(a.published_at ?? a.created_at)}</div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No announcements yet.</Empty>
          )}
        </Card>
        <QuickLinks parent={parent} />
      </div>
    </>
  );
}

function AttendanceCard({ rows, parent }: { rows: NonNullable<Insights["attendance"]>; parent: boolean }) {
  return (
    <ChartCard
      title="Attendance"
      description={`Share of pupils in school (present or late), last ${rows.length || 20} register days${parent ? ", your children" : ""}.`}
      table={{
        head: ["Day", "In school", "Present", "Late", "Absent", "Excused"],
        rows: rows.map((r) => [
          day(r.date, { weekday: "short", day: "numeric", month: "short" }),
          r.rate != null ? pct(r.rate) : "—",
          r.present,
          r.late,
          r.absent,
          r.excused,
        ]),
      }}
    >
      {rows.length ? (
        <TrendChart
          name="Attendance"
          max={100}
          format={pct}
          points={rows.map((r) => ({
            label: day(r.date, { day: "numeric", month: "short" }),
            title: day(r.date, { weekday: "long", day: "numeric", month: "long" }),
            value: r.rate,
            detail: [
              { name: "Present", value: String(r.present) },
              { name: "Late", value: String(r.late) },
              { name: "Absent", value: String(r.absent) },
            ],
          }))}
        />
      ) : (
        <Empty>No registers taken yet.</Empty>
      )}
    </ChartCard>
  );
}

function EnrolmentCard({ rows }: { rows: NonNullable<Insights["enrolment"]> }) {
  return (
    <ChartCard
      title="Pupils by class"
      description="Active pupils in each class. New pupils appear here as soon as they're added to a class."
      legend={GENDER}
      table={{
        head: ["Class", "Girls", "Boys", "Total"],
        rows: rows.map((r) => [r.label, r.girls, r.boys, r.pupils]),
      }}
    >
      {rows.length ? (
        <BarList
          series={GENDER}
          format={(v) => v.toLocaleString("en-GB")}
          rows={rows.map((r) => ({ label: r.label, values: [r.girls, r.boys] }))}
        />
      ) : (
        <Empty>No pupils in a class yet.</Empty>
      )}
    </ChartCard>
  );
}

function FeesCard({ fees, termLabel }: { fees: NonNullable<Insights["fees"]>; termLabel?: string }) {
  const owing = fees.by_class.filter((c) => c.outstanding_pesewas > 0);
  return (
    <ChartCard
      className="lg:col-span-2"
      title="Fees"
      description={`Collected against billed${termLabel ? ` for ${termLabel}` : ""}, payments by week, and what each class still owes.`}
      table={{
        head: ["Class", "Billed", "Collected", "Outstanding"],
        rows: fees.by_class.map((c) => [
          c.label,
          cedis(c.billed_pesewas),
          cedis(c.collected_pesewas),
          cedis(c.outstanding_pesewas),
        ]),
      }}
    >
      {fees.billed_pesewas ? (
        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex flex-col gap-4">
            <div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-3xl font-semibold">{fees.collection_rate ?? 0}%</span>
                <span className="text-right text-xs text-neutral-500">
                  {cedis(fees.collected_pesewas)} of {cedis(fees.billed_pesewas)}
                </span>
              </div>
              <div className="mt-2">
                <Meter
                  value={fees.collected_pesewas}
                  max={fees.billed_pesewas}
                  label="Share of fees collected"
                />
              </div>
              <p className="mt-1 text-xs text-neutral-500">{cedis(fees.outstanding_pesewas)} outstanding</p>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-medium text-neutral-600 dark:text-neutral-300">
                Collected each week
              </h3>
              {fees.weekly.length ? (
                <ColumnChart
                  name="Fees collected"
                  format={ghs}
                  columns={fees.weekly.map((w) => ({
                    label: day(w.week, { day: "numeric", month: "short" }),
                    title: `Week of ${day(w.week, { day: "numeric", month: "long" })} · ${w.payments} payment${w.payments === 1 ? "" : "s"}`,
                    value: w.amount_pesewas,
                  }))}
                />
              ) : (
                <Empty>No payments yet this term.</Empty>
              )}
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium text-neutral-600 dark:text-neutral-300">
              Outstanding by class
            </h3>
            {owing.length ? (
              <BarList
                series={[{ name: "Outstanding", color: SERIES_1 }]}
                format={(v) => cedis(v)}
                rows={owing.map((c) => ({ label: c.label, values: [c.outstanding_pesewas] }))}
              />
            ) : (
              <Empty>Every class is fully paid.</Empty>
            )}
          </div>
        </div>
      ) : (
        <Empty>No invoices for this term yet.</Empty>
      )}
    </ChartCard>
  );
}

function ResultsCard({
  results,
  parent,
  termLabel,
}: {
  results: NonNullable<Insights["results"]>;
  parent: boolean;
  termLabel?: string;
}) {
  return (
    <ChartCard
      className="lg:col-span-2"
      title="Results"
      description={`Average total score per subject${parent ? " for your children" : ""}${termLabel ? `, ${termLabel}` : ""}, and how the grades spread.`}
      table={{
        head: ["Subject", "Average", "Pupils"],
        rows: results.subjects.map((s) => [s.subject, `${s.average}`, s.pupils]),
      }}
    >
      {results.subjects.length ? (
        <div className="grid gap-6 md:grid-cols-[3fr_2fr]">
          <div>
            <h3 className="mb-2 text-xs font-medium text-neutral-600 dark:text-neutral-300">
              Average by subject (out of 100)
            </h3>
            <BarList
              series={[{ name: "Average", color: SERIES_1 }]}
              max={100}
              format={(v) => v.toFixed(1)}
              rows={results.subjects.map((s) => ({ label: s.subject, values: [s.average] }))}
            />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium text-neutral-600 dark:text-neutral-300">
              Grades awarded
            </h3>
            <ColumnChart
              name="Grades awarded"
              format={(v) => compact(v)}
              columns={results.grades.map((g) => ({
                label: g.grade,
                title: `Grade ${g.grade}`,
                value: g.count,
              }))}
            />
          </div>
        </div>
      ) : (
        <Empty>
          {parent ? "No published report cards for this term." : "No results computed for this term yet."}
        </Empty>
      )}
    </ChartCard>
  );
}

function QuickLinks({ parent }: { parent: boolean }) {
  const { roles, can, hasModule } = useSchool();
  const fees = hasModule("fees");
  const links: [boolean, string, string][] = [
    [parent, "/children", "My children"],
    [parent && fees, "/fees", "Pay school fees"],
    [parent, "/results", "Report cards"],
    [isTeacher(roles) && can(PERM.ATTENDANCE_RECORD), "/attendance", "Take today's register"],
    [!can(PERM.STUDENTS_MANAGE) && can(PERM.STUDENTS_ADD_OWN_CLASS), "/students", "Add a pupil to my class"],
    [can(PERM.ASSESSMENTS_RECORD, PERM.ASSESSMENTS_MANAGE), "/scores", "Enter scores"],
    [can(PERM.ADMISSIONS_MANAGE) && hasModule("admissions"), "/admissions", "Review admissions"],
    [
      can(PERM.ASSESSMENTS_PUBLISH, PERM.ASSESSMENTS_PUBLISH_OWN_CLASS),
      "/results",
      can(PERM.ASSESSMENTS_PUBLISH) ? "Compute & publish results" : "Prepare my class's report cards",
    ],
    [!parent && fees && can(PERM.FINANCE_VIEW), "/fees", "Fees and payments"],
    [can(PERM.MEMBERS_MANAGE), "/people", "Give staff access"],
    [!can(PERM.MEMBERS_MANAGE) && can(PERM.MEMBERS_VIEW), "/people", "See staff and access"],
  ];
  const shown = links.filter(([ok]) => ok);
  return (
    <Card title="Quick links">
      <div className="grid gap-2 sm:grid-cols-2">
        {shown.map(([, href, label]) => (
          <Link
            key={label}
            href={href}
            className="rounded-control border border-neutral-200 px-3 py-2 text-sm hover:border-brand hover:bg-brand/5 dark:border-neutral-800"
          >
            {label} →
          </Link>
        ))}
      </div>
    </Card>
  );
}
