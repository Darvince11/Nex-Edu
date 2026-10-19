"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Alert, Card, Empty, PageHeader, Stat } from "@/components/ui";
import { type Announcement, api, type Invoice, type Paged, type ReportCard, type Student } from "@/lib/api";
import { cedis, formatDate } from "@/lib/format";
import { useCurrentTerm, useSchool } from "@/lib/hooks";
import { isFinance, isLeader, isParentOnly, isTeacher } from "@/lib/roles";

type Summary = {
  billed_pesewas: number;
  collected_pesewas: number;
  outstanding_pesewas: number;
  invoices: Record<string, number>;
};

export default function DashboardPage() {
  const { me, school, roles } = useSchool();
  const term = useCurrentTerm();
  const parent = isParentOnly(roles);

  const students = useQuery({
    queryKey: ["students", "dashboard"],
    queryFn: () => api.get<Paged<Student>>("/api/v1/students?page_size=200"),
  });
  const finance = useQuery({
    queryKey: ["finance-summary", term.data?.id],
    queryFn: () => api.get<Summary>(`/api/v1/finance/summary?term=${term.data?.id}`),
    enabled: Boolean(term.data) && roles.some((r) => r === "owner" || r === "bursar"),
  });
  const invoices = useQuery({
    queryKey: ["invoices", "mine"],
    queryFn: () => api.get<Invoice[]>("/api/v1/finance/invoices"),
    enabled: parent,
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

  const firstName = me.data?.first_name || me.data?.email;
  const count = students.data?.results.length ?? 0;
  const owed = (invoices.data ?? []).reduce((sum, i) => sum + i.balance_pesewas, 0);

  return (
    <>
      <PageHeader
        title={`Welcome${firstName ? `, ${firstName}` : ""}`}
        description={
          term.data ? `${school?.name} · ${term.data.label}` : `${school?.name} · no current term set`
        }
      />

      {!term.data && isLeader(roles) && (
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

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {parent ? (
          <>
            <Stat label="Children" value={count} />
            <Stat label="Fees outstanding" value={cedis(owed)} />
            <Stat label="Report cards" value={reports.data?.length ?? 0} hint="Published results" />
          </>
        ) : (
          <>
            <Stat label={isTeacher(roles) && !isLeader(roles) ? "My students" : "Students"} value={count} />
            {finance.data && (
              <>
                <Stat label="Billed this term" value={cedis(finance.data.billed_pesewas)} />
                <Stat label="Collected" value={cedis(finance.data.collected_pesewas)} />
                <Stat
                  label="Outstanding"
                  value={cedis(finance.data.outstanding_pesewas)}
                  hint={`${finance.data.invoices.paid ?? 0} invoices fully paid`}
                />
              </>
            )}
          </>
        )}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card
          title="Announcements"
          actions={
            <Link href="/announcements" className="text-sm underline">
              All
            </Link>
          }
        >
          {news.data?.results.length ? (
            <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {news.data.results.map((a) => (
                <li key={a.id} className="py-2">
                  <div className="font-medium">{a.title}</div>
                  <div className="text-sm text-neutral-600 dark:text-neutral-400">{a.body}</div>
                  <div className="text-xs text-neutral-500">{formatDate(a.published_at ?? a.created_at)}</div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No announcements yet.</Empty>
          )}
        </Card>

        <Card title="Quick links">
          <div className="grid gap-2 sm:grid-cols-2">
            {parent && <QuickLink href="/children" label="My children" />}
            {parent && <QuickLink href="/fees" label="Pay school fees" />}
            {parent && <QuickLink href="/results" label="Report cards" />}
            {isTeacher(roles) && <QuickLink href="/attendance" label="Take today's register" />}
            {(isTeacher(roles) || isLeader(roles)) && <QuickLink href="/scores" label="Enter scores" />}
            {isLeader(roles) && <QuickLink href="/admissions" label="Review admissions" />}
            {isLeader(roles) && <QuickLink href="/results" label="Compute & publish results" />}
            {isFinance(roles) && !parent && <QuickLink href="/fees" label="Fees and payments" />}
            {isLeader(roles) && <QuickLink href="/people" label="Invite staff and parents" />}
          </div>
        </Card>
      </div>
    </>
  );
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-neutral-200 px-3 py-2 text-sm hover:border-brand dark:border-neutral-800"
    >
      {label} →
    </Link>
  );
}
