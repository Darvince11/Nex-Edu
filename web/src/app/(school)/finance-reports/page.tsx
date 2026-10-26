"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useState } from "react";
import { BarList, ChartCard, ColumnChart, compact, SERIES_1 } from "@/components/charts";
import {
  Badge,
  Button,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { cedis, formatDate, toPesewas } from "@/lib/format";
import { useArms, useCurrentTerm, useSchool, useTerms } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Tab = "balances" | "collections" | "scholarships";
type Balances = {
  pupils: number;
  outstanding_pesewas: number;
  rows: {
    invoice: string;
    student: string;
    name: string;
    admission_number: string;
    class: string;
    billed_pesewas: number;
    paid_pesewas: number;
    balance_pesewas: number;
    guardian_phone: string;
    last_payment: string | null;
  }[];
};
type Collections = {
  total_pesewas: number;
  payments: number;
  by_day: { day: string; total_pesewas: number; payments: number }[];
  by_method: { method: string; total_pesewas: number; payments: number }[];
  by_class: { class: string; total_pesewas: number; payments: number }[];
};
type ScholarshipRow = {
  id: string;
  student: string;
  student_name: string;
  student_class: string;
  name: string;
  percent: string | null;
  amount_pesewas: number | null;
  item: number | null;
  item_name: string;
  is_active: boolean;
  note: string;
};
const METHODS: Record<string, string> = {
  cash: "Cash",
  bank_transfer: "Bank transfer",
  pos: "POS",
  paystack: "Online (Paystack)",
  flutterwave: "Online (Flutterwave)",
};
const shortDay = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));

/** Who owes, what came in, and standing scholarships. Staff with finance access only. */
export default function FinanceReportsPage() {
  const [tab, setTab] = useState<Tab>("balances");
  return (
    <>
      <PageHeader
        title="Finance reports"
        description="Outstanding fees, money collected, and scholarships."
      />
      <div
        role="tablist"
        aria-label="Reports"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["balances", "Outstanding balances"],
            ["collections", "Collections"],
            ["scholarships", "Scholarships"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === key ? "border-brand font-medium" : "border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "balances" && <BalancesTab />}
        {tab === "collections" && <CollectionsTab />}
        {tab === "scholarships" && <ScholarshipsTab />}
      </div>
    </>
  );
}

function BalancesTab() {
  const terms = useTerms();
  const current = useCurrentTerm();
  const arms = useArms();
  const [term, setTerm] = useState("");
  const [arm, setArm] = useState("");
  const chosen = term || (current.data ? String(current.data.id) : "");
  const params = new URLSearchParams();
  if (chosen) params.set("term", chosen);
  if (arm) params.set("arm", arm);
  const report = useQuery({
    queryKey: ["finance-balances", chosen, arm],
    queryFn: () => api.get<Balances>(`/api/v1/finance/reports/balances?${params}`),
    enabled: Boolean(chosen),
    placeholderData: keepPreviousData,
  });
  const exporting = useMutation({
    mutationFn: () =>
      download(`/api/v1/finance/reports/balances?${params}&export=csv`, "outstanding-fees.csv"),
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Field label="Term">
            <Select value={chosen} onChange={(e) => setTerm(e.target.value)}>
              {terms.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="w-48">
          <Field label="Class">
            <Select value={arm} onChange={(e) => setArm(e.target.value)}>
              <option value="">All classes</option>
              {arms.data?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button
          variant="secondary"
          busy={exporting.isPending}
          onClick={() => exporting.mutate()}
          disabled={!report.data?.rows.length}
        >
          Download spreadsheet
        </Button>
      </div>
      <ErrorText error={exporting.error} />
      {!chosen ? (
        <Empty>Set a current term first.</Empty>
      ) : report.isPending ? (
        <Loading />
      ) : report.error ? (
        <ErrorText error={report.error} />
      ) : (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <Stat label="Still owed" value={cedis(report.data.outstanding_pesewas)} />
            <Stat label="Pupils owing" value={report.data.pupils} />
          </div>
          {report.data.rows.length ? (
            <Table head={["Pupil", "Class", "Billed", "Paid", "Owes", "Guardian", "Last payment"]}>
              {report.data.rows.map((r) => (
                <tr key={r.invoice}>
                  <Td>
                    <Link href={`/students/${r.student}`} className="font-medium hover:underline">
                      {r.name}
                    </Link>
                    <span className="block font-mono text-xs text-neutral-500">{r.admission_number}</span>
                  </Td>
                  <Td>{r.class || "—"}</Td>
                  <Td className="tabular-nums">{cedis(r.billed_pesewas)}</Td>
                  <Td className="tabular-nums">{cedis(r.paid_pesewas)}</Td>
                  <Td className="font-medium tabular-nums">{cedis(r.balance_pesewas)}</Td>
                  <Td className="text-xs">{r.guardian_phone || "—"}</Td>
                  <Td className="whitespace-nowrap">{formatDate(r.last_payment)}</Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>Nobody owes anything for this term.</Empty>
          )}
        </>
      )}
    </>
  );
}

function CollectionsTab() {
  const today = new Date().toISOString().slice(0, 10);
  const [start, setStart] = useState(`${today.slice(0, 8)}01`);
  const [end, setEnd] = useState(today);
  const report = useQuery({
    queryKey: ["finance-collections", start, end],
    queryFn: () => api.get<Collections>(`/api/v1/finance/reports/collections?start=${start}&end=${end}`),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="From">
            <Input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          </Field>
        </div>
        <div className="w-44">
          <Field label="To">
            <Input type="date" value={end} min={start} max={today} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>
      </div>
      {report.isPending ? (
        <Loading />
      ) : report.error ? (
        <ErrorText error={report.error} />
      ) : (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <Stat label="Collected" value={cedis(report.data.total_pesewas)} />
            <Stat label="Payments" value={report.data.payments} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard
              className="lg:col-span-2"
              title="Collected each day"
              table={{
                head: ["Day", "Collected", "Payments"],
                rows: report.data.by_day.map((d) => [
                  shortDay(d.day, { day: "numeric", month: "short" }),
                  cedis(d.total_pesewas),
                  d.payments,
                ]),
              }}
            >
              <ColumnChart
                name="Collected"
                format={(v) => `GH₵${compact(v / 100)}`}
                columns={report.data.by_day.map((d) => ({
                  label: shortDay(d.day, { day: "numeric" }),
                  title: shortDay(d.day, { weekday: "long", day: "numeric", month: "long" }),
                  value: d.total_pesewas,
                }))}
              />
            </ChartCard>
            <ChartCard
              title="By payment method"
              table={{
                head: ["Method", "Collected", "Payments"],
                rows: report.data.by_method.map((m) => [
                  METHODS[m.method] ?? m.method,
                  cedis(m.total_pesewas),
                  m.payments,
                ]),
              }}
            >
              {report.data.by_method.length ? (
                <BarList
                  series={[{ name: "Collected", color: SERIES_1 }]}
                  format={(v) => cedis(v)}
                  rows={report.data.by_method.map((m) => ({
                    label: METHODS[m.method] ?? m.method,
                    values: [m.total_pesewas],
                  }))}
                />
              ) : (
                <Empty>No payments in this period.</Empty>
              )}
            </ChartCard>
            <ChartCard
              title="By class"
              table={{
                head: ["Class", "Collected", "Payments"],
                rows: report.data.by_class.map((c) => [c.class, cedis(c.total_pesewas), c.payments]),
              }}
            >
              {report.data.by_class.length ? (
                <BarList
                  series={[{ name: "Collected", color: SERIES_1 }]}
                  format={(v) => cedis(v)}
                  rows={report.data.by_class.map((c) => ({ label: c.class, values: [c.total_pesewas] }))}
                />
              ) : (
                <Empty>No payments in this period.</Empty>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </>
  );
}

function ScholarshipsTab() {
  const client = useQueryClient();
  const { can } = useSchool();
  const manage = can(PERM.FINANCE_MANAGE);
  const list = useQuery({
    queryKey: ["scholarships"],
    queryFn: () => api.get<ScholarshipRow[]>("/api/v1/finance/scholarships"),
  });
  const [adding, setAdding] = useState(false);
  const toggle = useMutation({
    mutationFn: (s: ScholarshipRow) =>
      api.patch(`/api/v1/finance/scholarships/${s.id}`, { is_active: !s.is_active }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["scholarships"] }),
  });
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Scholarships come off a pupil's bill automatically whenever invoices are made.
        </p>
        {manage && <Button onClick={() => setAdding(true)}>Add scholarship</Button>}
      </div>
      <ErrorText error={toggle.error} />
      {list.isPending ? (
        <Loading />
      ) : list.error ? (
        <ErrorText error={list.error} />
      ) : list.data.length ? (
        <Table head={["Pupil", "Scholarship", "Off", "On", "Status", ""]}>
          {list.data.map((s) => (
            <tr key={s.id} className={s.is_active ? "" : "opacity-60"}>
              <Td>
                <Link href={`/students/${s.student}`} className="font-medium hover:underline">
                  {s.student_name}
                </Link>
                <span className="block text-xs text-neutral-500">{s.student_class}</span>
              </Td>
              <Td>{s.name}</Td>
              <Td className="tabular-nums">
                {s.percent ? `${Number(s.percent)}%` : cedis(s.amount_pesewas)}
              </Td>
              <Td>{s.item_name || "Whole bill"}</Td>
              <Td>{s.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="grey">Stopped</Badge>}</Td>
              <Td>
                {manage && (
                  <Button variant="ghost" onClick={() => toggle.mutate(s)}>
                    {s.is_active ? "Stop" : "Restart"}
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No scholarships yet.</Empty>
      )}
      <Modal open={adding} onClose={() => setAdding(false)} title="Add a scholarship">
        <AddScholarship onDone={() => setAdding(false)} />
      </Modal>
    </>
  );
}

function AddScholarship({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<"percent" | "amount">("percent");
  const pupils = useQuery({
    queryKey: ["students", "scholarship-search", q],
    queryFn: () =>
      api.get<{ results: { id: string; first_name: string; last_name: string; arm_name: string | null }[] }>(
        `/api/v1/students?page_size=20&q=${encodeURIComponent(q)}`,
      ),
    enabled: q.trim().length >= 2,
  });
  const items = useQuery({
    queryKey: ["fee-items"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/api/v1/finance/fee-items"),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/finance/scholarships", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scholarships"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      student: f.student,
      name: f.name,
      item: f.item || null,
      percent: kind === "percent" ? f.value : null,
      amount_pesewas: kind === "amount" ? toPesewas(f.value ?? "") : null,
      note: f.note,
      apply_now: f.apply_now === "on",
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field label="Find the pupil" hint="Type at least two letters of their name or admission number.">
          <Input value={q} onChange={(e) => setQ(e.target.value)} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label="Pupil">
          <Select name="student" required defaultValue="">
            <option value="" disabled>
              {q.trim().length >= 2 ? "Choose a pupil" : "Search above first"}
            </option>
            {pupils.data?.results.map((p) => (
              <option key={p.id} value={p.id}>
                {p.last_name} {p.first_name} {p.arm_name ? `(${p.arm_name})` : ""}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Name" hint='e.g. "Staff child", "Sibling discount"'>
        <Input name="name" required maxLength={80} />
      </Field>
      <Field label="Applies to">
        <Select name="item" defaultValue="">
          <option value="">The whole bill</option>
          {items.data?.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name} only
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Kind">
        <Select value={kind} onChange={(e) => setKind(e.target.value as "percent" | "amount")}>
          <option value="percent">A percentage</option>
          <option value="amount">A fixed amount</option>
        </Select>
      </Field>
      <Field label={kind === "percent" ? "Percentage off" : "Amount off (GH₵)"}>
        <Input name="value" required inputMode="decimal" />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Note (optional)">
          <Input name="note" maxLength={200} />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input type="checkbox" name="apply_now" defaultChecked className="size-4 accent-brand" />
        Also take it off this term's bill if it's already been made
      </label>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Save scholarship
        </Button>
      </div>
    </form>
  );
}
