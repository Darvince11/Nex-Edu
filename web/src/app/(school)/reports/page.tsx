"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Badge,
  Button,
  Empty,
  ErrorText,
  Field,
  Loading,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { useArms, useCurrentTerm, useSchool, useTerms } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Kind = "class-list" | "attendance" | "results";
type Column = { key: string; label: string; numeric: boolean; wide: boolean };
type Row = Record<string, string | number | null>;
type Report = {
  title: string;
  subtitle: string;
  summary: { label: string; value: string | number }[];
  tables: { title: string; columns: Column[]; rows: Row[] }[];
};

const KINDS: [Kind, string][] = [
  ["class-list", "Class lists"],
  ["attendance", "Attendance"],
  ["results", "Results"],
];
const LOW_ATTENDANCE = 80;

/** Class lists, attendance and results, on screen or as a spreadsheet or PDF. */
export default function ReportsPage() {
  const { can } = useSchool();
  const wholeSchool = can(PERM.REPORTS_VIEW);
  const arms = useArms(wholeSchool ? false : "form");
  const terms = useTerms();
  const current = useCurrentTerm();
  const [kind, setKind] = useState<Kind>("class-list");
  const [arm, setArm] = useState("");
  const [term, setTerm] = useState("");
  const chosenTerm = term || (current.data ? String(current.data.id) : "");

  const params = new URLSearchParams();
  if (arm) params.set("arm", arm);
  if (kind !== "class-list" && chosenTerm) params.set("term", chosenTerm);
  const path = `/api/v1/reports/${kind}?${params}`;
  const report = useQuery({
    queryKey: ["report", kind, arm, kind === "class-list" ? "" : chosenTerm],
    queryFn: () => api.get<Report>(path),
    enabled: current.isFetched,
    placeholderData: keepPreviousData,
  });
  const exporting = useMutation({
    mutationFn: (format: "csv" | "pdf") => download(`${path}&export=${format}`, `${kind}.${format}`),
  });

  return (
    <>
      <PageHeader
        title="Reports"
        description="Class lists, attendance and results to view, download or print."
      />
      <div
        role="tablist"
        aria-label="Reports"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {KINDS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={kind === key}
            onClick={() => setKind(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${kind === key ? "border-brand font-medium" : "border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="w-48">
            <Field label="Class">
              <Select value={arm} onChange={(e) => setArm(e.target.value)}>
                {(wholeSchool || (arms.data?.length ?? 0) > 1) && (
                  <option value="">{wholeSchool ? "All classes" : "All my classes"}</option>
                )}
                {arms.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {kind !== "class-list" && (
            <div className="w-48">
              <Field label="Term">
                <Select value={chosenTerm} onChange={(e) => setTerm(e.target.value)}>
                  {terms.data?.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              variant="secondary"
              busy={exporting.isPending && exporting.variables === "csv"}
              disabled={!report.data}
              onClick={() => exporting.mutate("csv")}
            >
              Download spreadsheet
            </Button>
            <Button
              variant="secondary"
              busy={exporting.isPending && exporting.variables === "pdf"}
              disabled={!report.data}
              onClick={() => exporting.mutate("pdf")}
            >
              Download PDF
            </Button>
          </div>
        </div>
        <ErrorText error={exporting.error} />
        {report.isPending ? (
          <Loading />
        ) : report.error ? (
          <ErrorText error={report.error} />
        ) : (
          <ReportView report={report.data} onClass={setArm} kind={kind} />
        )}
      </div>
    </>
  );
}

function ReportView({
  report,
  kind,
  onClass,
}: {
  report: Report;
  kind: Kind;
  onClass: (arm: string) => void;
}) {
  return (
    <section aria-labelledby="report-title" className="flex flex-col gap-5">
      <div>
        <h2 id="report-title" className="text-lg font-medium">
          {report.title}
        </h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">{report.subtitle}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {report.summary.map((s) => (
          <Stat key={s.label} label={s.label} value={s.value} />
        ))}
      </div>
      {report.tables.map((table) => (
        <div key={table.title || "main"}>
          {table.title && <h3 className="mb-2 font-medium">{table.title}</h3>}
          {table.rows.length ? (
            <Table
              head={table.columns.map((c) =>
                c.numeric ? (
                  <span key={c.key} className="block text-right">
                    {c.label}
                  </span>
                ) : (
                  c.label
                ),
              )}
            >
              {table.rows.map((row, i) => (
                <tr key={String(row.student ?? row.arm ?? row.subject ?? i)}>
                  {table.columns.map((c) => (
                    <Td
                      key={c.key}
                      className={c.numeric ? "text-right tabular-nums" : c.wide ? "font-medium" : ""}
                    >
                      <Cell column={c} row={row} kind={kind} onClass={onClass} />
                    </Td>
                  ))}
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>
              {kind === "results"
                ? "No results worked out for this term yet."
                : kind === "attendance"
                  ? "Nothing to show yet."
                  : "No pupils in this class."}
            </Empty>
          )}
        </div>
      ))}
    </section>
  );
}

function Cell({
  column,
  row,
  kind,
  onClass,
}: {
  column: Column;
  row: Row;
  kind: Kind;
  onClass: (arm: string) => void;
}) {
  const value = row[column.key];
  if (value === null || value === undefined || value === "") return <>—</>;
  // In a whole-school report, a class name opens that class's report.
  if (column.key === "class" && row.arm && !row.student) {
    return (
      <button
        type="button"
        onClick={() => onClass(String(row.arm))}
        className="font-medium text-brand-strong hover:underline dark:text-brand-sky"
      >
        {value}
      </button>
    );
  }
  if (kind === "attendance" && column.key === "rate") {
    const low = Number(value) < LOW_ATTENDANCE;
    return (
      <span className="inline-flex items-center justify-end gap-2">
        {low && <Badge tone="red">Low</Badge>}
        {value}%
      </span>
    );
  }
  return <>{value}</>;
}
