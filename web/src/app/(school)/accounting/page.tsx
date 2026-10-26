"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  Select,
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { cedis, formatDate, todayInAccra, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Account = { id: number; code: string; name: string; type: string };
type Txn = {
  id: string;
  kind: "expense" | "income";
  date: string;
  account: number;
  account_name: string;
  amount_pesewas: number;
  method: string;
  method_label: string;
  party: string;
  reference: string;
  description: string;
  voided: boolean;
  void_reason: string;
};
type BudgetRow = {
  account: number;
  code: string;
  name: string;
  budget_pesewas: number;
  actual_pesewas: number;
  left_pesewas: number;
  used_percent: number | null;
};
type Budgets = { session: number; session_name: string; rows: BudgetRow[] };
type Line = { code: string; name: string; amount_pesewas: number };
type IE = {
  income: Line[];
  expenditure: Line[];
  income_total_pesewas: number;
  expenditure_total_pesewas: number;
  surplus_pesewas: number;
};
type TB = {
  rows: { code: string; name: string; debit_pesewas: number; credit_pesewas: number }[];
  debit_total_pesewas: number;
  credit_total_pesewas: number;
};
type CashBook = {
  opening_pesewas: number;
  closing_pesewas: number;
  rows: { date: string; memo: string; in_pesewas: number; out_pesewas: number; balance_pesewas: number }[];
};
type Tab = "money" | "budgets" | "reports" | "accounts";

const monthStart = () => `${todayInAccra().slice(0, 8)}01`;

/** The school's accounts: spending, other income, budgets and the reports. */
export default function AccountingPage() {
  const { can } = useSchool();
  const manage = can(PERM.ACCOUNTING_MANAGE);
  const [tab, setTab] = useState<Tab>("money");
  return (
    <>
      <PageHeader
        title="Accounting"
        description="Spending and other income, budgets, and the school's books."
      />
      <div
        role="tablist"
        aria-label="Accounting"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["money", "Money in and out"],
            ["budgets", "Budgets"],
            ["reports", "Reports"],
            ["accounts", "Accounts"],
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
        {tab === "money" && <Money manage={manage} />}
        {tab === "budgets" && <BudgetsTab manage={manage} />}
        {tab === "reports" && <Reports />}
        {tab === "accounts" && <Accounts manage={manage} />}
      </div>
    </>
  );
}

function useAccounts(type?: string) {
  return useQuery({
    queryKey: ["ledger-accounts", type ?? "all"],
    queryFn: () => api.get<Account[]>(`/api/v1/accounting/accounts${type ? `?type=${type}` : ""}`),
  });
}

function Money({ manage }: { manage: boolean }) {
  const client = useQueryClient();
  const [kind, setKind] = useState("");
  const [recording, setRecording] = useState<"expense" | "income" | null>(null);
  const [voiding, setVoiding] = useState<Txn | null>(null);
  const txns = useQuery({
    queryKey: ["transactions", kind],
    queryFn: () => api.get<Txn[]>(`/api/v1/accounting/transactions${kind ? `?kind=${kind}` : ""}`),
    placeholderData: keepPreviousData,
  });
  const refresh = () => {
    for (const key of ["transactions", "budgets", "acc-report"])
      void client.invalidateQueries({ queryKey: [key] });
  };
  const voidIt = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post(`/api/v1/accounting/transactions/${id}/void`, { reason }),
    onSuccess: () => {
      refresh();
      setVoiding(null);
    },
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="Show">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Everything</option>
              <option value="expense">Money spent</option>
              <option value="income">Money received</option>
            </Select>
          </Field>
        </div>
        {manage && (
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" onClick={() => setRecording("income")}>
              Record money received
            </Button>
            <Button onClick={() => setRecording("expense")}>Record spending</Button>
          </div>
        )}
      </div>
      <ErrorText error={txns.error} />
      {txns.isPending ? (
        <Loading />
      ) : txns.data?.length ? (
        <Table head={["Date", "What", "To or from", "Amount", ""]}>
          {txns.data.map((t) => (
            <tr key={t.id} className={t.voided ? "opacity-60" : ""}>
              <Td className="whitespace-nowrap">{formatDate(t.date)}</Td>
              <Td>
                {t.account_name}
                {t.description && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {t.description}
                  </span>
                )}
              </Td>
              <Td>
                {t.party}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {t.method_label}
                  {t.reference ? ` · ${t.reference}` : ""}
                </span>
              </Td>
              <Td className="whitespace-nowrap tabular-nums">
                {t.kind === "expense" ? "−" : "+"}
                {cedis(t.amount_pesewas)} {t.voided && <Badge tone="grey">Voided</Badge>}
              </Td>
              <Td className="text-right">
                {manage && !t.voided && (
                  <Button
                    variant="ghost"
                    onClick={() => setVoiding(t)}
                    aria-label={`Void ${t.account_name} ${formatDate(t.date)}`}
                  >
                    Void
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Nothing recorded yet.</Empty>
      )}
      <Modal
        open={recording !== null}
        onClose={() => setRecording(null)}
        title={recording === "income" ? "Record money received" : "Record spending"}
      >
        {recording && (
          <RecordForm
            kind={recording}
            onDone={() => {
              refresh();
              setRecording(null);
            }}
          />
        )}
      </Modal>
      <Modal open={voiding !== null} onClose={() => setVoiding(null)} title="Void this entry?">
        {voiding && (
          <form
            className="flex flex-col gap-3 text-sm"
            onSubmit={(e) => {
              e.preventDefault();
              voidIt.mutate({
                id: voiding.id,
                reason: String(new FormData(e.currentTarget).get("reason") ?? ""),
              });
            }}
          >
            <p>
              {voiding.account_name}, {cedis(voiding.amount_pesewas)} on {formatDate(voiding.date)}. The
              reverse is posted today; the original stays in the books.
            </p>
            <Field label="Why">
              <Input name="reason" required maxLength={200} />
            </Field>
            <ErrorText error={voidIt.error} />
            <div className="flex justify-end">
              <Button type="submit" variant="danger" busy={voidIt.isPending}>
                Void
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}

function RecordForm({ kind, onDone }: { kind: "expense" | "income"; onDone: () => void }) {
  const accounts = useAccounts(kind);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/accounting/transactions", body),
    onSuccess: onDone,
  });
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          kind,
          date: f.date,
          account: Number(f.account),
          amount_pesewas: toPesewas(f.amount ?? ""),
          method: f.method,
          party: f.party,
          reference: f.reference,
          description: f.description,
        });
      }}
    >
      <Field label={kind === "expense" ? "Spent on" : "Received for"}>
        <Select name="account" required defaultValue="">
          <option value="" disabled>
            Choose
          </option>
          {accounts.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Amount (GH₵)">
        <Input name="amount" inputMode="decimal" required />
      </Field>
      <Field label="Date">
        <Input name="date" type="date" required defaultValue={todayInAccra()} max={todayInAccra()} />
      </Field>
      <Field label="How">
        <Select name="method" defaultValue="cash">
          <option value="cash">Cash</option>
          <option value="bank">Bank transfer or cheque</option>
          <option value="momo">Mobile money</option>
        </Select>
      </Field>
      <Field label={kind === "expense" ? "Paid to" : "Received from"}>
        <Input name="party" required maxLength={120} />
      </Field>
      <Field label="Receipt or cheque number (optional)">
        <Input name="reference" maxLength={60} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Details (optional)">
          <Input name="description" maxLength={300} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function BudgetsTab({ manage }: { manage: boolean }) {
  const client = useQueryClient();
  const budgets = useQuery({
    queryKey: ["budgets"],
    queryFn: () => api.get<Budgets>("/api/v1/accounting/budgets"),
  });
  const accounts = useAccounts("expense");
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put("/api/v1/accounting/budgets", body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["budgets"] }),
  });
  const b = budgets.data;
  return (
    <>
      <ErrorText error={budgets.error ?? save.error} />
      {budgets.isPending ? (
        <Loading />
      ) : b ? (
        <>
          <h2 className="mb-2 font-medium">Budget for {b.session_name}</h2>
          {b.rows.length ? (
            <Table head={["Account", "Budget", "Spent", "Left", "Used"]}>
              {b.rows.map((r) => (
                <tr key={r.account}>
                  <Td>{r.name}</Td>
                  <Td className="tabular-nums">{cedis(r.budget_pesewas)}</Td>
                  <Td className="tabular-nums">{cedis(r.actual_pesewas)}</Td>
                  <Td className="tabular-nums">{cedis(r.left_pesewas)}</Td>
                  <Td className="tabular-nums">
                    {r.used_percent === null ? "No budget" : `${r.used_percent}%`}{" "}
                    {r.used_percent !== null && r.used_percent > 100 && <Badge tone="red">Over</Badge>}
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No budget set and nothing spent yet.</Empty>
          )}
          {manage && (
            <form
              className="mt-4 grid max-w-2xl gap-2 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
                save.mutate({
                  session: b.session,
                  account: Number(f.account),
                  amount_pesewas: toPesewas(f.amount ?? ""),
                });
              }}
            >
              <Field label="Account">
                <Select name="account" required defaultValue="">
                  <option value="" disabled>
                    Choose
                  </option>
                  {accounts.data?.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Budget (GH₵)">
                <Input name="amount" inputMode="decimal" required />
              </Field>
              <Button type="submit" variant="secondary" busy={save.isPending}>
                Set budget
              </Button>
            </form>
          )}
        </>
      ) : null}
    </>
  );
}

function Reports() {
  const [kind, setKind] = useState<"income-expenditure" | "trial-balance" | "cash-book">(
    "income-expenditure",
  );
  const [start, setStart] = useState(monthStart());
  const [end, setEnd] = useState(todayInAccra());
  const query = `start=${start}&end=${end}`;
  const report = useQuery({
    queryKey: ["acc-report", kind, start, end],
    queryFn: () => api.get<IE | TB | CashBook>(`/api/v1/accounting/reports/${kind}?${query}`),
    placeholderData: keepPreviousData,
  });
  const exporting = useMutation({
    mutationFn: () => download(`/api/v1/accounting/reports/${kind}?${query}&export=csv`, `${kind}.csv`),
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-56">
          <Field label="Report">
            <Select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="income-expenditure">Income and expenditure</option>
              <option value="cash-book">Cash book</option>
              <option value="trial-balance">Trial balance</option>
            </Select>
          </Field>
        </div>
        {kind !== "trial-balance" && (
          <div className="w-44">
            <Field label="From">
              <Input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
            </Field>
          </div>
        )}
        <div className="w-44">
          <Field label={kind === "trial-balance" ? "As at" : "To"}>
            <Input type="date" value={end} max={todayInAccra()} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>
        <Button variant="secondary" busy={exporting.isPending} onClick={() => exporting.mutate()}>
          Download spreadsheet
        </Button>
      </div>
      <ErrorText error={report.error ?? exporting.error} />
      <ExportForSoftware start={start} end={end} />
      {report.isPending ? (
        <Loading />
      ) : kind === "income-expenditure" ? (
        <IEView r={report.data as IE} />
      ) : kind === "trial-balance" ? (
        <TBView r={report.data as TB} />
      ) : (
        <CashView r={report.data as CashBook} />
      )}
    </>
  );
}

/** The books for QuickBooks, Xero, Sage or Tally: one standard CSV journal plus the accounts. */
function ExportForSoftware({ start, end }: { start: string; end: string }) {
  const journal = useMutation({
    mutationFn: () =>
      download(
        `/api/v1/accounting/export/journal?start=${start}&end=${end}`,
        `journal-${start}-to-${end}.csv`,
      ),
  });
  const accounts = useMutation({
    mutationFn: () => download("/api/v1/accounting/export/accounts", "chart-of-accounts.csv"),
  });
  return (
    <div className="mb-4 rounded-card border border-neutral-200 p-4 dark:border-neutral-800">
      <h3 className="font-medium">For your accountant's software</h3>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
        A journal of every entry in these dates, in a CSV that QuickBooks, Xero, Sage and Tally can import,
        and the list of accounts to match them to. Amounts are in cedis.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" busy={journal.isPending} onClick={() => journal.mutate()}>
          Download journal (CSV)
        </Button>
        <Button variant="ghost" busy={accounts.isPending} onClick={() => accounts.mutate()}>
          Download chart of accounts
        </Button>
      </div>
      <ErrorText error={journal.error ?? accounts.error} />
    </div>
  );
}

function IEView({ r }: { r: IE }) {
  if (!r?.income) return null;
  return (
    <>
      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <Stat label="Income" value={cedis(r.income_total_pesewas)} />
        <Stat label="Spending" value={cedis(r.expenditure_total_pesewas)} />
        <Stat
          label={r.surplus_pesewas >= 0 ? "Surplus" : "Deficit"}
          value={cedis(Math.abs(r.surplus_pesewas))}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Income">
          <Lines rows={r.income} />
        </Card>
        <Card title="Spending">
          <Lines rows={r.expenditure} />
        </Card>
      </div>
    </>
  );
}

function Lines({ rows }: { rows: Line[] }) {
  return rows.length ? (
    <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
      {rows.map((l) => (
        <li key={l.code} className="flex justify-between gap-2 py-1.5">
          {l.name} <span className="tabular-nums">{cedis(l.amount_pesewas)}</span>
        </li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-neutral-600 dark:text-neutral-300">None in this period.</p>
  );
}

function TBView({ r }: { r: TB }) {
  if (!r?.rows) return null;
  return (
    <>
      {r.debit_total_pesewas === r.credit_total_pesewas ? (
        <div className="mb-3">
          <Alert tone="success">The books balance.</Alert>
        </div>
      ) : (
        <div className="mb-3">
          <Alert tone="error">Debits and credits don't match. Contact Nex Edu.</Alert>
        </div>
      )}
      <Table head={["Code", "Account", "Debit", "Credit"]}>
        {r.rows.map((row) => (
          <tr key={row.code}>
            <Td className="font-mono text-xs">{row.code}</Td>
            <Td>{row.name}</Td>
            <Td className="tabular-nums">{row.debit_pesewas ? cedis(row.debit_pesewas) : ""}</Td>
            <Td className="tabular-nums">{row.credit_pesewas ? cedis(row.credit_pesewas) : ""}</Td>
          </tr>
        ))}
        <tr>
          <Td>{""}</Td>
          <Td className="font-medium">Total</Td>
          <Td className="font-medium tabular-nums">{cedis(r.debit_total_pesewas)}</Td>
          <Td className="font-medium tabular-nums">{cedis(r.credit_total_pesewas)}</Td>
        </tr>
      </Table>
    </>
  );
}

function CashView({ r }: { r: CashBook }) {
  if (!r?.rows) return null;
  return (
    <>
      <div className="mb-4 grid gap-4 sm:grid-cols-2">
        <Stat label="Opening balance" value={cedis(r.opening_pesewas)} />
        <Stat label="Closing balance" value={cedis(r.closing_pesewas)} />
      </div>
      {r.rows.length ? (
        <Table head={["Date", "Details", "In", "Out", "Balance"]}>
          {r.rows.map((row, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: cash book lines have no id of their own.
            <tr key={i}>
              <Td className="whitespace-nowrap">{formatDate(row.date)}</Td>
              <Td>{row.memo}</Td>
              <Td className="tabular-nums">{row.in_pesewas ? cedis(row.in_pesewas) : ""}</Td>
              <Td className="tabular-nums">{row.out_pesewas ? cedis(row.out_pesewas) : ""}</Td>
              <Td className="tabular-nums">{cedis(row.balance_pesewas)}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No money in or out in this period.</Empty>
      )}
    </>
  );
}

function Accounts({ manage }: { manage: boolean }) {
  const client = useQueryClient();
  const accounts = useAccounts();
  const add = useMutation({
    mutationFn: (body: Record<string, string>) => api.post("/api/v1/accounting/accounts", body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["ledger-accounts"] }),
  });
  return (
    <>
      {manage && (
        <form
          className="mb-4 grid max-w-2xl gap-2 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            add.mutate(Object.fromEntries(new FormData(form)) as Record<string, string>, {
              onSuccess: () => form.reset(),
            });
          }}
        >
          <Field label="New account">
            <Input name="name" required maxLength={80} />
          </Field>
          <Field label="For">
            <Select name="type" defaultValue="expense">
              <option value="expense">Spending</option>
              <option value="income">Income</option>
            </Select>
          </Field>
          <Button type="submit" variant="secondary" busy={add.isPending}>
            Add account
          </Button>
        </form>
      )}
      <ErrorText error={accounts.error ?? add.error} />
      {accounts.data?.length ? (
        <Table head={["Code", "Account", "Kind"]}>
          {accounts.data.map((a) => (
            <tr key={a.id}>
              <Td className="font-mono text-xs">{a.code}</Td>
              <Td>{a.name}</Td>
              <Td className="capitalize">{a.type}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Loading />
      )}
    </>
  );
}
