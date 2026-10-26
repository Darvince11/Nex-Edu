"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useState } from "react";
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
import { api, download, type Invoice, type Level, type Payment } from "@/lib/api";
import { cedis, formatDate, toPesewas } from "@/lib/format";
import { useCurrentTerm, useSchool, useTerms } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";
import { isParentOnly } from "@/lib/roles";

type Summary = {
  billed_pesewas: number;
  collected_pesewas: number;
  outstanding_pesewas: number;
  invoices: Record<string, number>;
  online_payments: number;
};

export default function FeesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Fees />
    </Suspense>
  );
}

function Fees() {
  const { roles, can } = useSchool();
  return isParentOnly(roles) ? <ParentFees /> : <BursarFees canManage={can(PERM.FINANCE_MANAGE)} />;
}

// --- Parents ---------------------------------------------------------------------

function ParentFees() {
  const invoices = useQuery({
    queryKey: ["invoices", "mine"],
    queryFn: () => api.get<Invoice[]>("/api/v1/finance/invoices"),
  });
  const [paying, setPaying] = useState<Invoice | null>(null);
  return (
    <>
      <PageHeader
        title="School fees"
        description="Pay with MTN MoMo, Telecel Cash, AirtelTigo Money or a bank card."
      />
      <ErrorText error={invoices.error} />
      {invoices.isPending ? (
        <Loading />
      ) : invoices.data?.length ? (
        <div className="grid gap-4">
          {invoices.data.map((inv) => (
            <Card
              key={inv.id}
              title={`${inv.student_name} · ${inv.term_label}`}
              actions={<Badge>{inv.status}</Badge>}
            >
              <InvoiceLines invoice={inv} />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm">
                  Balance: <strong className="text-lg">{cedis(inv.balance_pesewas)}</strong>
                  {inv.due_date && (
                    <span className="text-neutral-500"> · due {formatDate(inv.due_date)}</span>
                  )}
                </div>
                {inv.balance_pesewas > 0 && <Button onClick={() => setPaying(inv)}>Pay now</Button>}
              </div>
              <Receipts payments={inv.payments} />
            </Card>
          ))}
        </div>
      ) : (
        <Empty>No fees have been billed yet.</Empty>
      )}
      <Modal open={Boolean(paying)} onClose={() => setPaying(null)} title="Pay school fees">
        {paying && <PayOnline invoice={paying} />}
      </Modal>
    </>
  );
}

function PayOnline({ invoice }: { invoice: Invoice }) {
  const [amount, setAmount] = useState((invoice.balance_pesewas / 100).toFixed(2));
  const [key] = useState(() => crypto.randomUUID()); // one key per attempt: double-clicks can't double-charge
  const pay = useMutation({
    mutationFn: (provider: string) => {
      const pesewas = toPesewas(amount);
      if (pesewas === null) throw new Error("Enter a valid amount, e.g. 450.00");
      return api.post<Payment>(
        `/api/v1/finance/invoices/${invoice.id}/pay`,
        { provider, amount_pesewas: pesewas },
        { "Idempotency-Key": `${key}-${provider}` },
      );
    },
    onSuccess: (payment) => window.location.assign(payment.authorization_url),
  });
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        {invoice.student_name} · {invoice.number} · balance {cedis(invoice.balance_pesewas)}
      </p>
      <Field label="Amount (GH₵)" hint="You can pay part of the balance if the school allows it.">
        <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <ErrorText error={pay.error} />
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="secondary"
          busy={pay.isPending && pay.variables === "flutterwave"}
          onClick={() => pay.mutate("flutterwave")}
        >
          Pay with Flutterwave
        </Button>
        <Button busy={pay.isPending && pay.variables === "paystack"} onClick={() => pay.mutate("paystack")}>
          Pay with Paystack
        </Button>
      </div>
      <p className="text-xs text-neutral-500">
        You'll be taken to a secure payment page. Nex Edu never sees your card or mobile money PIN.
      </p>
    </div>
  );
}

function InvoiceLines({ invoice }: { invoice: Invoice }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {invoice.lines.map((l) => (
          <tr key={l.id}>
            <td className="py-0.5">{l.description}</td>
            <td className="py-0.5 text-right tabular-nums">{cedis(l.amount_pesewas)}</td>
          </tr>
        ))}
        <tr className="border-t border-neutral-200 font-medium dark:border-neutral-800">
          <td className="pt-1">Total</td>
          <td className="pt-1 text-right tabular-nums">{cedis(invoice.total_pesewas)}</td>
        </tr>
        <tr>
          <td>Paid</td>
          <td className="text-right tabular-nums">{cedis(invoice.paid_pesewas)}</td>
        </tr>
      </tbody>
    </table>
  );
}

function Receipts({ payments }: { payments: Payment[] }) {
  if (!payments.length) return null;
  return (
    <div className="mt-3 border-t border-neutral-200 pt-2 text-sm dark:border-neutral-800">
      {payments.map((p) => (
        <div key={p.id} className="flex items-center justify-between gap-2 py-1">
          <span>
            {formatDate(p.paid_at)} · {cedis(p.amount_received_pesewas)} · {p.method.replace("_", " ")}
          </span>
          <Button
            variant="ghost"
            onClick={() => download(`/api/v1/finance/payments/${p.id}/receipt`, `${p.receipt_number}.pdf`)}
          >
            Receipt {p.receipt_number}
          </Button>
        </div>
      ))}
    </div>
  );
}

// --- Bursar / head teacher -------------------------------------------------------

function BursarFees({ canManage }: { canManage: boolean }) {
  const params = useSearchParams();
  const terms = useTerms();
  const current = useCurrentTerm();
  const [term, setTerm] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string | null>(params.get("invoice"));
  const [tab, setTab] = useState<"invoices" | "setup">("invoices");

  useEffect(() => {
    if (!term && current.data) setTerm(String(current.data.id));
  }, [current.data, term]);

  const summary = useQuery({
    queryKey: ["finance-summary", term],
    queryFn: () => api.get<Summary>(`/api/v1/finance/summary?term=${term}`),
    enabled: Boolean(term) && canManage,
  });
  const invoices = useQuery({
    queryKey: ["invoices", term, status],
    queryFn: () =>
      api.get<Invoice[]>(`/api/v1/finance/invoices?term=${term}${status ? `&status=${status}` : ""}`),
    enabled: Boolean(term),
  });
  const selectedInvoice = invoices.data?.find((i) => i.id === selected) ?? null;

  return (
    <>
      <PageHeader
        title="Fees"
        description="Bill each term, record payments, and track what's outstanding."
        actions={
          canManage && (
            <div className="flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
              {(["invoices", "setup"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`rounded px-3 py-1.5 text-sm ${tab === t ? "bg-brand text-white" : ""}`}
                >
                  {t === "invoices" ? "Invoices" : "Fee setup"}
                </button>
              ))}
            </div>
          )
        }
      />
      <div className="mb-4 max-w-xs">
        <Field label="Term">
          <Select value={term} onChange={(e) => setTerm(e.target.value)}>
            {terms.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {tab === "setup" && term ? (
        <FeeSetup term={Number(term)} />
      ) : (
        <>
          {summary.data && (
            <div className="mb-6 grid gap-4 sm:grid-cols-4">
              <Stat label="Billed" value={cedis(summary.data.billed_pesewas)} />
              <Stat label="Collected" value={cedis(summary.data.collected_pesewas)} />
              <Stat label="Outstanding" value={cedis(summary.data.outstanding_pesewas)} />
              <Stat
                label="Fully paid"
                value={summary.data.invoices.paid ?? 0}
                hint={`${summary.data.online_payments} paid online`}
              />
            </div>
          )}
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div className="w-48">
              <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
                <option value="">All invoices</option>
                <option value="issued">Unpaid</option>
                <option value="part_paid">Part paid</option>
                <option value="paid">Paid</option>
                <option value="void">Void</option>
              </Select>
            </div>
            {canManage && term && <GenerateInvoices term={Number(term)} />}
          </div>
          <ErrorText error={invoices.error} />
          {invoices.isPending && term ? (
            <Loading />
          ) : invoices.data?.length ? (
            <Table head={["Invoice", "Pupil", "Total", "Paid", "Balance", "Status"]}>
              {invoices.data.map((i) => (
                <tr
                  key={i.id}
                  className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-900"
                  onClick={() => setSelected(i.id)}
                >
                  <Td className="font-mono text-xs">{i.number}</Td>
                  <Td>
                    {i.student_name}
                    <div className="text-xs text-neutral-500">{i.admission_number}</div>
                  </Td>
                  <Td className="tabular-nums">{cedis(i.total_pesewas)}</Td>
                  <Td className="tabular-nums">{cedis(i.paid_pesewas)}</Td>
                  <Td className="tabular-nums font-medium">{cedis(i.balance_pesewas)}</Td>
                  <Td>
                    <Badge>{i.status}</Badge>
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            term &&
            !invoices.isPending && (
              <Empty>No invoices for this term. Set up fees, then generate invoices.</Empty>
            )
          )}
        </>
      )}

      <Modal
        open={Boolean(selectedInvoice)}
        onClose={() => setSelected(null)}
        title={selectedInvoice?.number ?? ""}
      >
        {selectedInvoice && <InvoiceAdmin invoice={selectedInvoice} canManage={canManage} />}
      </Modal>
    </>
  );
}

function GenerateInvoices({ term }: { term: number }) {
  const client = useQueryClient();
  const generate = useMutation({
    mutationFn: () =>
      api.post<{ created: number; skipped: number }>("/api/v1/finance/invoices/generate", { term }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["invoices"] });
      client.invalidateQueries({ queryKey: ["finance-summary"] });
    },
  });
  return (
    <div className="flex items-center gap-3">
      {generate.isSuccess && (
        <span className="text-sm text-neutral-600">
          {generate.data.created} created, {generate.data.skipped} already billed
        </span>
      )}
      <ErrorText error={generate.error} />
      <Button busy={generate.isPending} onClick={() => generate.mutate()}>
        Generate invoices
      </Button>
    </div>
  );
}

function InvoiceAdmin({ invoice, canManage }: { invoice: Invoice; canManage: boolean }) {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["invoices"] });
    client.invalidateQueries({ queryKey: ["finance-summary"] });
  };
  const record = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/finance/invoices/${invoice.id}/record_payment`, body),
    onSuccess: refresh,
  });
  const discount = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/finance/invoices/${invoice.id}/discount`, body),
    onSuccess: refresh,
  });
  const voidIt = useMutation({
    mutationFn: (reason: string) => api.post(`/api/v1/finance/invoices/${invoice.id}/void`, { reason }),
    onSuccess: refresh,
  });

  const submitPayment = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const pesewas = toPesewas(f.amount ?? "");
    if (pesewas === null) return;
    record.mutate({ amount_pesewas: pesewas, method: f.method, reference: f.reference, note: f.note });
    e.currentTarget.reset();
  };
  const submitDiscount = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const pesewas = toPesewas(f.amount ?? "");
    if (pesewas === null) return;
    discount.mutate({ description: f.description, amount_pesewas: pesewas });
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        {invoice.student_name} · {invoice.term_label} · <Badge>{invoice.status}</Badge>
      </p>
      <InvoiceLines invoice={invoice} />
      <p className="text-sm">
        Balance: <strong>{cedis(invoice.balance_pesewas)}</strong>
      </p>
      <Receipts payments={invoice.payments} />
      {canManage && invoice.status !== "void" && (
        <>
          {invoice.balance_pesewas > 0 && (
            <Card title="Record a payment">
              <form onSubmit={submitPayment} className="grid gap-3 sm:grid-cols-2">
                <Field label="Amount (GH₵)">
                  <Input name="amount" inputMode="decimal" required />
                </Field>
                <Field label="Method">
                  <Select name="method">
                    <option value="cash">Cash</option>
                    <option value="bank_transfer">Bank transfer / deposit</option>
                    <option value="pos">POS / card machine</option>
                  </Select>
                </Field>
                <Field label="Reference (optional)">
                  <Input name="reference" />
                </Field>
                <Field label="Note (optional)">
                  <Input name="note" />
                </Field>
                <div className="sm:col-span-2">
                  <ErrorText error={record.error} />
                  {record.isSuccess && <Alert tone="success">Payment recorded and receipt issued.</Alert>}
                </div>
                <div className="flex justify-end sm:col-span-2">
                  <Button type="submit" busy={record.isPending}>
                    Record payment
                  </Button>
                </div>
              </form>
            </Card>
          )}
          <details className="text-sm">
            <summary className="cursor-pointer font-medium">Discount or void</summary>
            <form
              onSubmit={submitDiscount}
              className="mt-3 grid gap-3 sm:grid-cols-[1fr_8rem_auto] sm:items-end"
            >
              <Field label="Discount reason">
                <Input name="description" placeholder="Sibling discount" required />
              </Field>
              <Field label="GH₵">
                <Input name="amount" inputMode="decimal" required />
              </Field>
              <Button type="submit" variant="secondary" busy={discount.isPending}>
                Apply
              </Button>
            </form>
            <ErrorText error={discount.error} />
            {invoice.paid_pesewas === 0 && (
              <div className="mt-3 flex justify-end">
                <Button
                  variant="danger"
                  busy={voidIt.isPending}
                  onClick={() => {
                    const reason = window.prompt("Why is this invoice being voided?");
                    if (reason) voidIt.mutate(reason);
                  }}
                >
                  Void invoice
                </Button>
              </div>
            )}
            <ErrorText error={voidIt.error} />
          </details>
        </>
      )}
    </div>
  );
}

type FeeItem = { id: number; name: string; description: string; is_active: boolean };
type Schedule = {
  id: number;
  term: number;
  level: number | null;
  level_name: string | null;
  item: number;
  item_name: string;
  amount_pesewas: number;
  is_optional: boolean;
};

function FeeSetup({ term }: { term: number }) {
  const client = useQueryClient();
  const items = useQuery({
    queryKey: ["fee-items"],
    queryFn: () => api.get<FeeItem[]>("/api/v1/finance/fee-items"),
  });
  const levels = useQuery({
    queryKey: ["levels"],
    queryFn: () => api.get<Level[]>("/api/v1/academics/levels"),
  });
  const schedules = useQuery({
    queryKey: ["fee-schedules", term],
    queryFn: () => api.get<Schedule[]>(`/api/v1/finance/fee-schedules?term=${term}`),
  });
  const addItem = useMutation({
    mutationFn: (name: string) => api.post("/api/v1/finance/fee-items", { name }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["fee-items"] }),
  });
  const addSchedule = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/finance/fee-schedules", body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["fee-schedules", term] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/finance/fee-schedules/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["fee-schedules", term] }),
  });

  const submitSchedule = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const pesewas = toPesewas(f.amount ?? "");
    if (pesewas === null) return;
    addSchedule.mutate({
      term,
      item: Number(f.item),
      level: f.level ? Number(f.level) : null,
      amount_pesewas: pesewas,
    });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <Card title="This term's fees">
        {schedules.data?.length ? (
          <Table head={["Fee", "Applies to", "Amount", ""]}>
            {schedules.data.map((s) => (
              <tr key={s.id}>
                <Td>{s.item_name}</Td>
                <Td>{s.level_name ?? "All classes"}</Td>
                <Td className="tabular-nums">{cedis(s.amount_pesewas)}</Td>
                <Td>
                  <Button variant="ghost" onClick={() => remove.mutate(s.id)}>
                    Remove
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No fees set for this term.</Empty>
        )}
        <form onSubmit={submitSchedule} className="mt-4 grid gap-3 sm:grid-cols-4 sm:items-end">
          <Field label="Fee">
            <Select name="item" required>
              {items.data?.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Class level">
            <Select name="level">
              <option value="">All classes</option>
              {levels.data
                ?.filter((l) => l.is_active)
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
            </Select>
          </Field>
          <Field label="Amount (GH₵)">
            <Input name="amount" inputMode="decimal" required />
          </Field>
          <Button type="submit" busy={addSchedule.isPending}>
            Add
          </Button>
        </form>
        <ErrorText error={addSchedule.error ?? remove.error} />
      </Card>
      <Card title="Fee types">
        <ul className="mb-3 text-sm">
          {items.data?.map((i) => (
            <li key={i.id} className="py-0.5">
              {i.name}
            </li>
          ))}
        </ul>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const name = String(new FormData(e.currentTarget).get("name") ?? "").trim();
            if (name) addItem.mutate(name);
            e.currentTarget.reset();
          }}
          className="flex gap-2"
        >
          <Input name="name" placeholder="e.g. Feeding fee" />
          <Button type="submit" variant="secondary" busy={addItem.isPending}>
            Add
          </Button>
        </form>
        <ErrorText error={addItem.error} />
      </Card>
    </div>
  );
}
