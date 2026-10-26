"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useState } from "react";
import { ChartCard, ColumnChart } from "@/components/charts";
import {
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
  Textarea,
} from "@/components/ui";
import { apiFetch, type BillingHistory, type Pricing } from "@/lib/api";
import { cedis, formatDate, todayInAccra, toPesewas } from "@/lib/format";

const PATH = "/api/v1/platform/billing/payments";
const month = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));

/** Subscription payments schools have made to Nex Edu. */
export default function BillingHistoryPage() {
  const [school, setSchool] = useState("");
  const [earlierOnly, setEarlierOnly] = useState(false);
  const [recording, setRecording] = useState(false);
  const schools = useSchoolOptions();
  const params = new URLSearchParams();
  if (school) params.set("school", school);
  if (earlierOnly) params.set("before_month", "1");
  const history = useQuery({
    queryKey: ["platform", "billing-history", school, earlierOnly],
    queryFn: () => apiFetch<BillingHistory>(`${PATH}?${params}`, { school: false }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Billing history"
        description="Subscription payments schools have made to Nex Edu."
        actions={<Button onClick={() => setRecording(true)}>Record a payment</Button>}
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Field label="School">
            <Select value={school} onChange={(e) => setSchool(e.target.value)}>
              <option value="">All schools</option>
              {schools.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            checked={earlierOnly}
            onChange={(e) => setEarlierOnly(e.target.checked)}
            className="size-4 accent-brand"
          />
          Only payments before this month
        </label>
      </div>

      {history.isPending ? (
        <Loading />
      ) : history.error ? (
        <ErrorText error={history.error} />
      ) : (
        <div className={history.isPlaceholderData ? "opacity-60" : ""}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Received this month" value={cedis(history.data.this_month_pesewas)} />
            <Stat label="Received before this month" value={cedis(history.data.before_this_month_pesewas)} />
            <Stat
              label={earlierOnly ? "Shown below" : "All payments"}
              value={cedis(history.data.total_pesewas)}
              hint={`${history.data.payments_count} payment${history.data.payments_count === 1 ? "" : "s"}`}
            />
          </div>
          <div className="mt-6">
            <ChartCard
              title="Received each month"
              description="Subscription payments by the month they were received, last 12 months."
              table={{
                head: ["Month", "Received", "Payments"],
                rows: history.data.by_month.map((m) => [
                  month(m.month, { month: "long", year: "numeric" }),
                  cedis(m.total_pesewas),
                  m.payments,
                ]),
              }}
            >
              <ColumnChart
                name="Received"
                format={(v) => `GH₵${Math.round(v / 100).toLocaleString("en-GB")}`}
                columns={history.data.by_month.map((m) => ({
                  label: month(m.month, { month: "short" }),
                  title: month(m.month, { month: "long", year: "numeric" }),
                  value: m.total_pesewas,
                }))}
              />
            </ChartCard>
          </div>
          <div className="mt-6">
            {history.data.payments.length ? (
              <Table head={["Received", "School", "For", "Amount", "Method", "Reference", "Recorded by"]}>
                {history.data.payments.map((p) => (
                  <tr key={p.id}>
                    <Td className="whitespace-nowrap">{formatDate(p.received_on)}</Td>
                    <Td>
                      <Link href={`/platform/schools/${p.slug}`} className="font-medium hover:underline">
                        {p.school}
                      </Link>
                      {p.pupils != null && (
                        <div className="text-xs text-neutral-500">
                          {p.pupils.toLocaleString("en-GB")} pupils then
                        </div>
                      )}
                    </Td>
                    <Td>{p.period_label}</Td>
                    <Td className="tabular-nums">{cedis(p.amount_pesewas)}</Td>
                    <Td>{p.method_label}</Td>
                    <Td className="font-mono text-xs">{p.reference || "—"}</Td>
                    <Td className="text-xs text-neutral-500">{p.recorded_by}</Td>
                  </tr>
                ))}
              </Table>
            ) : (
              <Empty>No payments recorded{earlierOnly ? " before this month" : ""}.</Empty>
            )}
          </div>
        </div>
      )}

      <Modal open={recording} onClose={() => setRecording(false)} title="Record a payment">
        <RecordPayment schools={schools} onDone={() => setRecording(false)} />
      </Modal>
    </>
  );
}

type SchoolOption = { slug: string; name: string };

/** Active schools, from the pricing list (billing staff can read it; the schools list is for support). */
function useSchoolOptions(): SchoolOption[] {
  const pricing = useQuery({
    queryKey: ["platform", "pricing"],
    queryFn: () => apiFetch<Pricing>("/api/v1/platform/billing/pricing", { school: false }),
  });
  return pricing.data?.schools ?? [];
}

function RecordPayment({ schools, onDone }: { schools: SchoolOption[]; onDone: () => void }) {
  const client = useQueryClient();
  const [amount, setAmount] = useState("");
  const pesewas = toPesewas(amount);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => apiFetch(PATH, { method: "POST", school: false, body }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["platform", "billing-history"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    save.mutate({ ...f, amount_pesewas: pesewas });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="School">
        <Select name="school" required defaultValue="">
          <option value="" disabled>
            Choose a school
          </option>
          {schools.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Amount (GH₵)">
        <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
      </Field>
      <Field label="Paying for" hint='e.g. "October 2026" or "First term 2026/27"'>
        <Input name="period_label" required maxLength={60} />
      </Field>
      <Field label="Received on">
        <Input name="received_on" type="date" required max={todayInAccra()} defaultValue={todayInAccra()} />
      </Field>
      <Field label="Method">
        <Select name="method" defaultValue="momo">
          <option value="momo">Mobile money</option>
          <option value="bank">Bank transfer</option>
          <option value="card">Card</option>
          <option value="cash">Cash</option>
          <option value="cheque">Cheque</option>
        </Select>
      </Field>
      <Field label="Reference" hint="Transaction ID or receipt number">
        <Input name="reference" maxLength={80} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Note (optional)">
          <Textarea name="note" rows={2} maxLength={300} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending} disabled={pesewas === null}>
          Save payment
        </Button>
      </div>
    </form>
  );
}
