"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
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
  Select,
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { ApiError, apiFetch, download, getSelectedSchool } from "@/lib/api";
import { loginPath } from "@/lib/auth";
import { cedis, formatDate, timeAgo } from "@/lib/format";

type Account = {
  school: string;
  slug: string;
  status: "active" | "suspended" | "offboarded";
  status_reason: string;
  purge_after: string | null;
  export_ready: boolean;
  band: { label: string; price_pesewas: number };
  outstanding_pesewas: number;
  invoices: {
    id: string;
    number: string;
    month: string;
    lines: { description: string; amount_pesewas: number }[];
    total_pesewas: number;
    issued_on: string;
    due_on: string;
    status: "open" | "paid";
    overdue_days: number;
    paid_on: string | null;
  }[];
  sms: { monthly: number; bought: number; sent_this_month: number };
  bundles: { code: string; label: string; sms: number; price_pesewas: number }[];
};
type Grant = {
  id: string;
  reason: string;
  granted_by: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  open: boolean;
  views: { staff: string; at: string }[];
};

const month = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );

export default function BillingPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Billing />
    </Suspense>
  );
}

/**
 * The proprietor's Nex Edu account for one school: invoices (paid by mobile money
 * or card through Paystack), SMS bundles, support access and, once closed, the
 * export. Outside the school's pages, so it works while the school is suspended.
 */
function Billing() {
  const router = useRouter();
  const params = useSearchParams();
  const slug = params.get("school") ?? getSelectedSchool() ?? "";
  const reference = params.get("reference");
  const base = `/api/v1/account/schools/${slug}`;
  const account = useQuery({
    queryKey: ["account-billing", slug],
    queryFn: () => apiFetch<Account>(`${base}/billing`, { school: false }),
    enabled: Boolean(slug),
    retry: false,
  });
  useEffect(() => {
    if (account.error instanceof ApiError && account.error.status === 401) router.replace(loginPath());
  }, [account.error, router]);

  if (!slug)
    return (
      <Shell>
        <Alert tone="error">Open this page from your school.</Alert>
      </Shell>
    );
  if (account.isPending)
    return (
      <Shell>
        <Loading />
      </Shell>
    );
  if (!account.data)
    return (
      <Shell>
        <ErrorText error={account.error} />
      </Shell>
    );
  const a = account.data;
  return (
    <Shell>
      <h1 className="text-2xl font-semibold">{a.school}: Nex Edu billing</h1>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
        {a.band.label}: {cedis(a.band.price_pesewas)} a month. Pay by mobile money or card.
      </p>
      {reference && <PaymentResult base={base} reference={reference} slug={slug} />}
      {a.status === "suspended" && (
        <div className="mt-4">
          <Alert tone="warning">
            {a.status_reason === "nonpayment"
              ? "The school is suspended because an invoice is more than 30 days overdue. Pay it and everyone can sign in again straight away."
              : "Nex Edu has suspended the school. Contact support@nexedu.com.gh."}
          </Alert>
        </div>
      )}
      {a.status === "offboarded" && <Closed account={a} base={base} />}
      {a.status === "active" && (
        <p className="mt-3 text-sm">
          <Link href="/dashboard" className="text-link underline">
            Back to the school
          </Link>
        </p>
      )}
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <Stat label="To pay" value={cedis(a.outstanding_pesewas)} />
        <Stat
          label="SMS this month"
          value={`${a.sms.sent_this_month.toLocaleString("en-GB")} of ${a.sms.monthly.toLocaleString("en-GB")}`}
        />
        <Stat label="Bought SMS left" value={a.sms.bought.toLocaleString("en-GB")} hint="They don't expire" />
      </div>
      <div className="mt-6 flex flex-col gap-6">
        <Invoices account={a} base={base} />
        {a.status === "active" && <Bundles account={a} base={base} />}
        {a.status === "active" && <SupportAccess base={base} slug={slug} />}
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between gap-4">
        <Logo className="h-10" />
        <ThemeToggle />
      </div>
      {children}
    </main>
  );
}

function PaymentResult({ base, reference, slug }: { base: string; reference: string; slug: string }) {
  const client = useQueryClient();
  const charge = useQuery({
    queryKey: ["account-charge", reference],
    queryFn: () =>
      apiFetch<{ status: string }>(`${base}/billing/charges/${encodeURIComponent(reference)}`, {
        school: false,
      }),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 4000 : false),
  });
  const status = charge.data?.status;
  useEffect(() => {
    if (status === "paid") void client.invalidateQueries({ queryKey: ["account-billing", slug] });
  }, [status, client, slug]);
  if (!status) return null;
  return (
    <div className="mt-4">
      {status === "paid" ? (
        <Alert tone="success">Payment received. Thank you.</Alert>
      ) : status === "pending" ? (
        <Alert>Waiting for the payment to come through…</Alert>
      ) : (
        <Alert tone="error">The payment didn't go through. You can try again.</Alert>
      )}
    </div>
  );
}

function usePay(base: string) {
  return useMutation({
    mutationFn: (body: { invoice?: string; bundle?: string }) =>
      apiFetch<{ authorization_url: string }>(`${base}/billing/pay`, { method: "POST", school: false, body }),
    onSuccess: (data) => window.location.assign(data.authorization_url),
  });
}

function Invoices({ account, base }: { account: Account; base: string }) {
  const pay = usePay(base);
  return (
    <Card title="Invoices">
      <ErrorText error={pay.error} />
      {account.invoices.length ? (
        <Table head={["Month", "Amount", "Due", "Status", ""]}>
          {account.invoices.map((i) => (
            <tr key={i.id}>
              <Td>
                <span className="font-medium">{month(i.month)}</span>
                <span className="block font-mono text-xs text-neutral-500">{i.number}</span>
              </Td>
              <Td className="tabular-nums">{cedis(i.total_pesewas)}</Td>
              <Td>{formatDate(i.due_on)}</Td>
              <Td>
                {i.status === "paid" ? (
                  <Badge tone="green">Paid</Badge>
                ) : i.overdue_days ? (
                  <Badge tone="red">{i.overdue_days} days overdue</Badge>
                ) : (
                  <Badge tone="blue">To pay</Badge>
                )}
              </Td>
              <Td className="text-right">
                {i.status === "open" && account.status !== "offboarded" && (
                  <Button
                    busy={pay.isPending && pay.variables?.invoice === i.id}
                    onClick={() => pay.mutate({ invoice: i.id })}
                    aria-label={`Pay ${month(i.month)}, ${cedis(i.total_pesewas)}`}
                  >
                    Pay
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No invoices yet. The first comes on the 1st of the month.</Empty>
      )}
    </Card>
  );
}

function Bundles({ account, base }: { account: Account; base: string }) {
  const pay = usePay(base);
  return (
    <Card title="Buy SMS">
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
        {account.sms.monthly.toLocaleString("en-GB")} SMS a month are included. When they run out, messages
        use the SMS you've bought.
      </p>
      <ErrorText error={pay.error} />
      {account.bundles.length ? (
        <ul className="grid gap-3 sm:grid-cols-3">
          {account.bundles.map((b) => (
            <li key={b.code} className="rounded-card border border-neutral-200 p-4 dark:border-neutral-800">
              <p className="font-medium">{b.label}</p>
              <p className="mt-1 text-xl font-semibold tabular-nums">{cedis(b.price_pesewas)}</p>
              <Button
                className="mt-3"
                variant="secondary"
                busy={pay.isPending && pay.variables?.bundle === b.code}
                onClick={() => pay.mutate({ bundle: b.code })}
                aria-label={`Buy ${b.label} for ${cedis(b.price_pesewas)}`}
              >
                Buy
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>No SMS bundles on sale yet.</Empty>
      )}
    </Card>
  );
}

function SupportAccess({ base, slug }: { base: string; slug: string }) {
  const client = useQueryClient();
  const [hours, setHours] = useState("24");
  const [reason, setReason] = useState("");
  const grants = useQuery({
    queryKey: ["account-support", slug],
    queryFn: () => apiFetch<{ grants: Grant[] }>(`${base}/support`, { school: false }),
  });
  const set = (data: { grants: Grant[] }) => client.setQueryData(["account-support", slug], data);
  const give = useMutation({
    mutationFn: () =>
      apiFetch<{ grants: Grant[] }>(`${base}/support`, {
        method: "POST",
        school: false,
        body: { hours: Number(hours), reason },
      }),
    onSuccess: (data) => {
      set(data);
      setReason("");
    },
  });
  const end = useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ grants: Grant[] }>(`${base}/support/${id}/revoke`, { method: "POST", school: false }),
    onSuccess: set,
  });
  const open = grants.data?.grants.find((g) => g.open);
  return (
    <Card title="Nex Edu support access">
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
        Let Nex Edu support see how the school is set up (classes, terms, modules, staff accounts) to help
        with a problem. They never see pupils, parents, scores or money. You see every time they look.
      </p>
      <ErrorText error={grants.error ?? give.error ?? end.error} />
      {open ? (
        <Alert tone="info">
          Support can look until {formatDate(open.expires_at)} ({open.reason}).{" "}
          <Button variant="ghost" busy={end.isPending} onClick={() => end.mutate(open.id)}>
            End access now
          </Button>
        </Alert>
      ) : (
        <form
          className="grid gap-3 sm:grid-cols-[10rem_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            give.mutate();
          }}
        >
          <Field label="For">
            <Select value={hours} onChange={(e) => setHours(e.target.value)}>
              <option value="2">2 hours</option>
              <option value="24">1 day</option>
              <option value="72">3 days</option>
              <option value="168">7 days</option>
            </Select>
          </Field>
          <Field label="What should they look at?">
            <Input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
          </Field>
          <Button type="submit" busy={give.isPending}>
            Allow access
          </Button>
        </form>
      )}
      {grants.data?.grants.some((g) => g.views.length) && (
        <section aria-labelledby="looks" className="mt-4">
          <h3 id="looks" className="mb-1 text-sm font-medium">
            When support looked
          </h3>
          <ul className="flex flex-col gap-1 text-sm">
            {grants.data.grants.flatMap((g) =>
              g.views.map((v) => (
                <li key={`${g.id}-${v.at}`}>
                  {v.staff} · {timeAgo(v.at)}
                </li>
              )),
            )}
          </ul>
        </section>
      )}
    </Card>
  );
}

function Closed({ account, base }: { account: Account; base: string }) {
  const [error, setError] = useState<unknown>(null);
  return (
    <div className="mt-4 flex flex-col gap-3">
      <Alert tone="warning">
        The school has left Nex Edu. Its data is kept locked until {formatDate(account.purge_after)}, then
        destroyed for good. To come back before then, contact support@nexedu.com.gh.
      </Alert>
      {account.export_ready && (
        <div>
          <Button
            onClick={() => {
              setError(null);
              download(`${base}/export`, `${account.slug}-nexedu-export.zip`, false).catch(setError);
            }}
          >
            Download all the school's data
          </Button>
          <ErrorText error={error} />
        </div>
      )}
    </div>
  );
}
