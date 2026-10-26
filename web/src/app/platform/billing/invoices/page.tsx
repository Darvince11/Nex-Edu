"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import {
  Alert,
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
import { apiFetch } from "@/lib/api";
import { cedis, formatDate, todayInAccra } from "@/lib/format";

type Invoice = {
  id: string;
  number: string;
  school: string;
  slug: string;
  month: string;
  lines: { description: string; amount_pesewas: number }[];
  total_pesewas: number;
  issued_on: string;
  due_on: string;
  status: "open" | "paid" | "void";
  status_label: string;
  overdue_days: number;
  paid_on: string | null;
  void_reason: string;
};
type Invoices = { open_pesewas: number; overdue: number; invoices: Invoice[] };

const month = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );

export default function InvoicesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <InvoiceList />
    </Suspense>
  );
}

/** Every school's monthly invoices: record bank or cash payments, cancel, or make the month's now. */
function InvoiceList() {
  const client = useQueryClient();
  const router = useRouter();
  const params = useSearchParams();
  const school = params.get("school") ?? "";
  const status = params.get("status") ?? "";
  const [acting, setActing] = useState<{ invoice: Invoice; action: "mark_paid" | "void" } | null>(null);
  const query = new URLSearchParams({ ...(school && { school }), ...(status && { status }) }).toString();
  const data = useQuery({
    queryKey: ["platform", "invoices", query],
    queryFn: () =>
      apiFetch<Invoices>(`/api/v1/platform/billing/invoices${query ? `?${query}` : ""}`, { school: false }),
  });
  const run = useMutation({
    mutationFn: () =>
      apiFetch<{ made: number }>("/api/v1/platform/billing/invoices", { method: "POST", school: false }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["platform", "invoices"] }),
  });
  const setStatus = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set("status", value);
    else next.delete("status");
    router.replace(`/platform/billing/invoices${next.size ? `?${next}` : ""}`);
  };
  return (
    <>
      <PageHeader
        title="Invoices"
        description="Each school is invoiced on the 1st for its band and any paid add-ons. Proprietors pay by mobile money or card; record other payments here."
        actions={
          <Button variant="secondary" busy={run.isPending} onClick={() => run.mutate()}>
            Make this month's invoices
          </Button>
        }
      />
      {run.data && (
        <Alert tone="success">
          {run.data.made
            ? `${run.data.made} invoice${run.data.made === 1 ? "" : "s"} made.`
            : "Every active school already has this month's invoice."}
        </Alert>
      )}
      <ErrorText error={data.error ?? run.error} />
      {data.data && (
        <div className="mb-5 grid gap-3 sm:grid-cols-2">
          <Stat label="Unpaid" value={cedis(data.data.open_pesewas)} />
          <Stat
            label="Overdue invoices"
            value={data.data.overdue}
            hint="Suspended 30 days after the due date"
          />
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Field label="Show">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All invoices</option>
              <option value="open">Unpaid</option>
              <option value="paid">Paid</option>
              <option value="void">Cancelled</option>
            </Select>
          </Field>
        </div>
        {school && (
          <p className="pb-2 text-sm">
            One school only ·{" "}
            <Link href="/platform/billing/invoices" className="text-link underline">
              show all
            </Link>
          </p>
        )}
      </div>
      {data.isPending ? (
        <Loading />
      ) : data.data?.invoices.length ? (
        <Table head={["Invoice", "School", "Month", "Amount", "Due", "Status", ""]}>
          {data.data.invoices.map((i) => (
            <tr key={i.id}>
              <Td className="font-mono text-xs">{i.number}</Td>
              <Td>
                <Link href={`/platform/schools/${i.slug}`} className="font-medium hover:underline">
                  {i.school}
                </Link>
              </Td>
              <Td>{month(i.month)}</Td>
              <Td className="tabular-nums">{cedis(i.total_pesewas)}</Td>
              <Td>{formatDate(i.due_on)}</Td>
              <Td>
                {i.status === "paid" ? (
                  <Badge tone="green">Paid {i.paid_on ? formatDate(i.paid_on) : ""}</Badge>
                ) : i.status === "void" ? (
                  <Badge tone="grey">Cancelled</Badge>
                ) : i.overdue_days ? (
                  <Badge tone={i.overdue_days >= 14 ? "red" : "amber"}>{i.overdue_days} days overdue</Badge>
                ) : (
                  <Badge tone="blue">Unpaid</Badge>
                )}
              </Td>
              <Td className="text-right">
                {i.status === "open" && (
                  <span className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      onClick={() => setActing({ invoice: i, action: "mark_paid" })}
                      aria-label={`Record payment for ${i.number}`}
                    >
                      Record payment
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setActing({ invoice: i, action: "void" })}
                      aria-label={`Cancel ${i.number}`}
                    >
                      Cancel
                    </Button>
                  </span>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No invoices.</Empty>
      )}
      <Modal
        open={acting !== null}
        onClose={() => setActing(null)}
        title={acting?.action === "void" ? "Cancel an invoice" : "Record a payment"}
      >
        {acting && <InvoiceAction {...acting} onDone={() => setActing(null)} />}
      </Modal>
    </>
  );
}

function InvoiceAction({
  invoice,
  action,
  onDone,
}: {
  invoice: Invoice;
  action: "mark_paid" | "void";
  onDone: () => void;
}) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, string>) =>
      apiFetch(`/api/v1/platform/billing/invoices/${invoice.id}`, {
        method: "POST",
        school: false,
        body: { action, ...body },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["platform", "invoices"] });
      onDone();
    },
  });
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>);
      }}
    >
      <p className="text-sm">
        <span className="font-medium">{invoice.school}</span>, {month(invoice.month)}:{" "}
        {cedis(invoice.total_pesewas)}
      </p>
      <ul className="text-sm text-neutral-600 dark:text-neutral-300">
        {invoice.lines.map((l) => (
          <li key={l.description}>
            {l.description}: {cedis(l.amount_pesewas)}
          </li>
        ))}
      </ul>
      {action === "mark_paid" ? (
        <>
          <Field label="Paid by">
            <Select name="method" defaultValue="bank">
              <option value="bank">Bank transfer</option>
              <option value="momo">Mobile money</option>
              <option value="cash">Cash</option>
              <option value="cheque">Cheque</option>
              <option value="card">Card</option>
            </Select>
          </Field>
          <Field label="Reference (optional)">
            <Input name="reference" maxLength={80} />
          </Field>
          <Field label="Received on">
            <Input
              name="received_on"
              type="date"
              required
              defaultValue={todayInAccra()}
              max={todayInAccra()}
            />
          </Field>
        </>
      ) : (
        <Field label="Reason" hint="Kept in the audit log.">
          <Input name="reason" required maxLength={300} />
        </Field>
      )}
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" variant={action === "void" ? "danger" : "primary"} busy={save.isPending}>
          {action === "void" ? "Cancel invoice" : "Record payment"}
        </Button>
      </div>
    </form>
  );
}
