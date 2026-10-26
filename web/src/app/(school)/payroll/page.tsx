"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { cedis, formatDate, todayInAccra, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Line = { name: string; amount_pesewas: number; taxable?: boolean };
type Payslip = {
  id: string;
  month: string;
  staff: string;
  staff_name: string;
  basic_pesewas: number;
  allowances: Line[];
  gross_pesewas: number;
  ssnit_employee_pesewas: number;
  ssnit_employer_pesewas: number;
  taxable_pesewas: number;
  paye_pesewas: number;
  deductions: Line[];
  deductions_pesewas: number;
  net_pesewas: number;
};
type Run = {
  id: string;
  month: string;
  status: "draft" | "approved" | "paid";
  status_label: string;
  gross_pesewas: number;
  paye_pesewas: number;
  ssnit_employee_pesewas: number;
  ssnit_employer_pesewas: number;
  other_deductions_pesewas: number;
  net_pesewas: number;
};
type Salary = {
  basic_pesewas: number;
  allowances: Line[];
  deductions: Line[];
  ssnit_number: string;
  tin: string;
  on_payroll: boolean;
};
type StaffPay = {
  staff: string;
  name: string;
  job_title: string;
  salary: Salary | null;
  figures: Payslip | null;
};
type Rules = {
  paye_bands: [number | null, string][];
  ssnit_employee_percent: string;
  ssnit_employer_percent: string;
  tier2_percent: string;
  ssnit_cap_pesewas: number;
  rates_confirmed_at: string | null;
};
type Tab = "runs" | "salaries" | "rules" | "mine";

const monthLabel = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );
const STATUS_TONE = { draft: "amber", approved: "blue", paid: "green" } as const;

/** Payroll: the bursar keeps salaries and prepares pay; the proprietor approves; everyone sees their own payslips. */
export default function PayrollPage() {
  const { can } = useSchool();
  const manage = can(PERM.PAYROLL_MANAGE, PERM.PAYROLL_APPROVE);
  const [tab, setTab] = useState<Tab>(manage ? "runs" : "mine");
  if (!manage) {
    return (
      <>
        <PageHeader title="My payslips" description="Your pay, PAYE and SSNIT for each month." />
        <MyPayslips />
      </>
    );
  }
  return (
    <>
      <PageHeader title="Payroll" description="Salaries, PAYE and SSNIT each month, and payslips." />
      <div
        role="tablist"
        aria-label="Payroll"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["runs", "Monthly pay"],
            ["salaries", "Salaries"],
            ["rules", "Tax and SSNIT rules"],
            ["mine", "My payslips"],
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
        {tab === "runs" && <Runs />}
        {tab === "salaries" && <Salaries />}
        {tab === "rules" && <RulesTab />}
        {tab === "mine" && <MyPayslips />}
      </div>
    </>
  );
}

function MyPayslips() {
  const slips = useQuery({
    queryKey: ["my-payslips"],
    queryFn: () => api.get<Payslip[]>("/api/v1/payroll/mine"),
  });
  const pdf = useMutation({
    mutationFn: (s: Payslip) =>
      download(`/api/v1/payroll/payslips/${s.id}/pdf`, `payslip-${s.month.slice(0, 7)}.pdf`),
  });
  return (
    <>
      <ErrorText error={slips.error ?? pdf.error} />
      {slips.isPending ? (
        <Loading />
      ) : slips.data?.length ? (
        <Table head={["Month", "Gross", "SSNIT", "PAYE", "Other", "Net pay", ""]}>
          {slips.data.map((s) => (
            <tr key={s.id}>
              <Td className="font-medium">{monthLabel(s.month)}</Td>
              <Td className="tabular-nums">{cedis(s.gross_pesewas)}</Td>
              <Td className="tabular-nums">{cedis(s.ssnit_employee_pesewas)}</Td>
              <Td className="tabular-nums">{cedis(s.paye_pesewas)}</Td>
              <Td className="tabular-nums">{cedis(s.deductions_pesewas)}</Td>
              <Td className="font-medium tabular-nums">{cedis(s.net_pesewas)}</Td>
              <Td className="text-right">
                <Button
                  variant="ghost"
                  onClick={() => pdf.mutate(s)}
                  aria-label={`Download payslip for ${monthLabel(s.month)}`}
                >
                  PDF
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No payslips yet.</Empty>
      )}
    </>
  );
}

function Runs() {
  const client = useQueryClient();
  const { can } = useSchool();
  const [month, setMonth] = useState(todayInAccra().slice(0, 7));
  const [open, setOpen] = useState<string | null>(null);
  const runs = useQuery({ queryKey: ["pay-runs"], queryFn: () => api.get<Run[]>("/api/v1/payroll/runs") });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["pay-runs"] });
    void client.invalidateQueries({ queryKey: ["pay-run"] });
  };
  const prepare = useMutation({
    mutationFn: () => api.post<Run>("/api/v1/payroll/runs/prepare", { month: `${month}-01` }),
    onSuccess: (run) => {
      refresh();
      setOpen(run.id);
    },
  });
  return (
    <>
      {can(PERM.PAYROLL_MANAGE) && (
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="w-44">
            <Field label="Month">
              <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
            </Field>
          </div>
          <Button busy={prepare.isPending} onClick={() => prepare.mutate()}>
            Work out this month's pay
          </Button>
        </div>
      )}
      <ErrorText error={prepare.error ?? runs.error} />
      {runs.isPending ? (
        <Loading />
      ) : runs.data?.length ? (
        <Table head={["Month", "Gross", "PAYE", "SSNIT (both)", "Net pay", "Status", ""]}>
          {runs.data.map((r) => (
            <tr key={r.id}>
              <Td className="font-medium">{monthLabel(r.month)}</Td>
              <Td className="tabular-nums">{cedis(r.gross_pesewas)}</Td>
              <Td className="tabular-nums">{cedis(r.paye_pesewas)}</Td>
              <Td className="tabular-nums">{cedis(r.ssnit_employee_pesewas + r.ssnit_employer_pesewas)}</Td>
              <Td className="tabular-nums">{cedis(r.net_pesewas)}</Td>
              <Td>
                <Badge tone={STATUS_TONE[r.status]}>{r.status_label}</Badge>
              </Td>
              <Td className="text-right">
                <Button
                  variant="ghost"
                  onClick={() => setOpen(r.id)}
                  aria-label={`Open pay for ${monthLabel(r.month)}`}
                >
                  Open
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No pay runs yet.</Empty>
      )}
      <Modal open={open !== null} onClose={() => setOpen(null)} title="Monthly pay">
        {open && <RunDetail id={open} onChange={refresh} />}
      </Modal>
    </>
  );
}

function RunDetail({ id, onChange }: { id: string; onChange: () => void }) {
  const { can } = useSchool();
  const run = useQuery({
    queryKey: ["pay-run", id],
    queryFn: () => api.get<Run & { payslips: Payslip[] }>(`/api/v1/payroll/runs/${id}`),
  });
  const act = useMutation({
    mutationFn: (what: "approve" | "paid") => api.post(`/api/v1/payroll/runs/${id}/${what}`),
    onSuccess: onChange,
  });
  const schedule = useMutation({
    mutationFn: (kind: "paye" | "ssnit") =>
      download(
        `/api/v1/payroll/runs/${id}/schedule?kind=${kind}`,
        `${kind}-${run.data?.month.slice(0, 7)}.csv`,
      ),
  });
  if (run.isPending) return <Loading />;
  if (!run.data) return <ErrorText error={run.error} />;
  const r = run.data;
  return (
    <div className="flex flex-col gap-4 text-sm">
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Gross pay" value={cedis(r.gross_pesewas)} />
        <Stat label="PAYE to GRA" value={cedis(r.paye_pesewas)} />
        <Stat label="Net to pay staff" value={cedis(r.net_pesewas)} />
      </div>
      <Table head={["Staff", "Gross", "SSNIT", "PAYE", "Other", "Net"]}>
        {r.payslips.map((s) => (
          <tr key={s.id}>
            <Td className="font-medium">{s.staff_name}</Td>
            <Td className="tabular-nums">{cedis(s.gross_pesewas)}</Td>
            <Td className="tabular-nums">{cedis(s.ssnit_employee_pesewas)}</Td>
            <Td className="tabular-nums">{cedis(s.paye_pesewas)}</Td>
            <Td className="tabular-nums">{cedis(s.deductions_pesewas)}</Td>
            <Td className="tabular-nums">{cedis(s.net_pesewas)}</Td>
          </tr>
        ))}
      </Table>
      <ErrorText error={act.error ?? schedule.error} />
      <div className="flex flex-wrap justify-between gap-2">
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => schedule.mutate("paye")}>
            PAYE schedule
          </Button>
          <Button variant="secondary" onClick={() => schedule.mutate("ssnit")}>
            SSNIT schedule
          </Button>
        </div>
        <div className="flex gap-2">
          {r.status === "draft" &&
            (can(PERM.PAYROLL_APPROVE) ? (
              <Button busy={act.isPending} onClick={() => act.mutate("approve")}>
                Approve this month's pay
              </Button>
            ) : (
              <Alert>Waiting for the proprietor to approve.</Alert>
            ))}
          {r.status === "approved" && can(PERM.PAYROLL_MANAGE) && (
            <Button busy={act.isPending} onClick={() => act.mutate("paid")}>
              Mark as paid
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function Salaries() {
  const staff = useQuery({
    queryKey: ["salaries"],
    queryFn: () => api.get<StaffPay[]>("/api/v1/payroll/salaries"),
  });
  const [editing, setEditing] = useState<StaffPay | null>(null);
  return (
    <>
      <ErrorText error={staff.error} />
      {staff.isPending ? (
        <Loading />
      ) : staff.data?.length ? (
        <Table head={["Staff", "Basic", "Gross", "PAYE", "Net", ""]}>
          {staff.data.map((s) => (
            <tr key={s.staff}>
              <Td>
                <span className="font-medium">{s.name}</span>
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">{s.job_title}</span>
              </Td>
              <Td className="tabular-nums">{s.salary ? cedis(s.salary.basic_pesewas) : "—"}</Td>
              <Td className="tabular-nums">{s.figures ? cedis(s.figures.gross_pesewas) : "—"}</Td>
              <Td className="tabular-nums">{s.figures ? cedis(s.figures.paye_pesewas) : "—"}</Td>
              <Td className="tabular-nums">{s.figures ? cedis(s.figures.net_pesewas) : "—"}</Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setEditing(s)} aria-label={`Set pay for ${s.name}`}>
                  Set pay
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Add staff records first (People, Staff).</Empty>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={`Pay for ${editing?.name ?? ""}`}
      >
        {editing && <SalaryForm person={editing} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function SalaryForm({ person, onDone }: { person: StaffPay; onDone: () => void }) {
  const client = useQueryClient();
  const s = person.salary;
  const [allowances, setAllowances] = useState<Line[]>(s?.allowances ?? []);
  const [deductions, setDeductions] = useState<Line[]>(s?.deductions ?? []);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.put(`/api/v1/payroll/salaries?staff=${person.staff}`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["salaries"] });
      onDone();
    },
  });
  const lines = (list: Line[], setList: (l: Line[]) => void, label: string, taxable: boolean) => (
    <fieldset className="flex flex-col gap-2 rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
      <legend className="px-1 text-sm font-medium">{label}</legend>
      {list.map((l, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: rows are edited in place; order is the identity.
        <div key={i} className="grid grid-cols-[1fr_7rem_auto] items-end gap-2">
          <Field label="Name">
            <Input
              value={l.name}
              onChange={(e) => setList(list.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
            />
          </Field>
          <Field label="GH₵ a month">
            <Input
              inputMode="decimal"
              defaultValue={(l.amount_pesewas / 100).toFixed(2)}
              onChange={(e) =>
                setList(
                  list.map((x, j) =>
                    j === i ? { ...x, amount_pesewas: toPesewas(e.target.value) ?? 0 } : x,
                  ),
                )
              }
            />
          </Field>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setList(list.filter((_, j) => j !== i))}
            aria-label={`Remove ${l.name || label}`}
          >
            Remove
          </Button>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            setList([...list, { name: "", amount_pesewas: 0, ...(taxable ? { taxable: true } : {}) }])
          }
        >
          Add
        </Button>
      </div>
    </fieldset>
  );
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          basic_pesewas: toPesewas(f.basic ?? "") ?? 0,
          ssnit_number: f.ssnit_number,
          tin: f.tin,
          on_payroll: f.on_payroll === "on",
          allowances: allowances.filter((a) => a.name.trim()),
          deductions: deductions.filter((d) => d.name.trim()),
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Basic salary (GH₵ a month)">
          <Input
            name="basic"
            inputMode="decimal"
            required
            defaultValue={s ? (s.basic_pesewas / 100).toFixed(2) : ""}
          />
        </Field>
        <Field label="SSNIT number">
          <Input name="ssnit_number" maxLength={30} defaultValue={s?.ssnit_number} />
        </Field>
        <Field label="Ghana Card / TIN">
          <Input name="tin" maxLength={30} defaultValue={s?.tin} />
        </Field>
      </div>
      {lines(allowances, setAllowances, "Allowances (taxed)", true)}
      {lines(deductions, setDeductions, "Other deductions (welfare, loans)", false)}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="on_payroll"
          defaultChecked={s?.on_payroll ?? true}
          className="size-4 accent-brand"
        />{" "}
        On the payroll
      </label>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save pay
        </Button>
      </div>
    </form>
  );
}

function RulesTab() {
  const client = useQueryClient();
  const rules = useQuery({
    queryKey: ["payroll-rules"],
    queryFn: () => api.get<Rules>("/api/v1/payroll/rules"),
  });
  const confirm = useMutation({
    mutationFn: () => api.post("/api/v1/payroll/rules"),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["payroll-rules"] }),
  });
  const r = rules.data;
  if (!r) return <Loading />;
  let from = 0;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Monthly PAYE bands">
        <Table head={["Chargeable income a month", "Rate"]}>
          {r.paye_bands.map(([width, rate]) => {
            const start = from;
            from += width ?? 0;
            return (
              <tr key={`${start}-${rate}`}>
                <Td className="tabular-nums">
                  {width === null ? `Above ${cedis(start)}` : `${cedis(start)} to ${cedis(start + width)}`}
                </Td>
                <Td className="tabular-nums">{Number(rate)}%</Td>
              </tr>
            );
          })}
        </Table>
        <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
          The default table is GRA's for resident individuals from 1 September 2026 (Act 1178). PAYE is
          charged after the employee's SSNIT.
        </p>
      </Card>
      <Card title="SSNIT">
        <ul className="text-sm">
          <li>Staff pay {Number(r.ssnit_employee_percent)}% of basic salary.</li>
          <li>The school pays {Number(r.ssnit_employer_percent)}% of basic salary.</li>
          <li>Charged on basic salary up to {cedis(r.ssnit_cap_pesewas)} a month.</li>
        </ul>
        <div className="mt-4">
          {r.rates_confirmed_at ? (
            <Alert tone="success">Confirmed on {formatDate(r.rates_confirmed_at)}.</Alert>
          ) : (
            <Alert tone="warning">
              Check these against GRA's and SSNIT's current tables before working out pay. Rates change, often
              in the budget.
            </Alert>
          )}
        </div>
        <ErrorText error={confirm.error} />
        {!r.rates_confirmed_at && (
          <div className="mt-3 flex justify-end">
            <Button busy={confirm.isPending} onClick={() => confirm.mutate()}>
              I've checked: use these rates
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
