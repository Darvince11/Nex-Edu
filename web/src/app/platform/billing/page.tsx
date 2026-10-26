"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useState } from "react";
import { BillingRulesCard, SmsBundlesCard } from "@/components/console-billing";
import { ModulePricesCard } from "@/components/console-modules";
import {
  Alert,
  Button,
  Card,
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
import { apiFetch, type Me, type Pricing } from "@/lib/api";
import { cedis, toPesewas } from "@/lib/format";

const PATH = "/api/v1/platform/billing/pricing";

/** Price bands, the billing period, and what each school would pay. */
export default function PricingPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }) });
  const canEdit = Boolean(me.data?.platform_roles.includes("super_admin"));
  const pricing = useQuery({
    queryKey: ["platform", "pricing"],
    queryFn: () => apiFetch<Pricing>(PATH, { school: false }),
  });
  const [editing, setEditing] = useState<Pricing["bands"][number] | null>(null);

  if (pricing.isPending) return <Loading />;
  if (pricing.error) return <ErrorText error={pricing.error} />;
  const p = pricing.data;

  return (
    <>
      <PageHeader
        title="Pricing and billing"
        description="What schools pay Nex Edu. A school's band follows its number of active pupils. There is no free trial."
        actions={
          <>
            <Link href="/platform/billing/invoices" className="btn-secondary h-10 text-sm">
              Invoices
            </Link>
            <Link href="/platform/billing/history" className="btn-secondary h-10 text-sm">
              Billing history
            </Link>
          </>
        }
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat
          label="Subscription value"
          value={cedis(p.expected_pesewas)}
          hint="All active schools, each month"
        />
        <Stat label="Schools billed" value={p.schools.length} />
        <Stat label="Billing period" value={p.period_label} hint="Invoices on the 1st" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card title="Price bands">
          <Table head={["Band", "Pupils", "Price", "Schools", ""]}>
            {p.bands.map((band, i) => (
              <tr key={band.code}>
                <Td className="font-medium">Band {i + 1}</Td>
                <Td>{band.label}</Td>
                <Td className="tabular-nums">{cedis(band.price_pesewas)}</Td>
                <Td className="tabular-nums">{band.schools}</Td>
                <Td>
                  {canEdit && (
                    <Button
                      variant="ghost"
                      onClick={() => setEditing(band)}
                      aria-label={`Change price for ${band.label}`}
                    >
                      Change price
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
          <p className="mt-3 text-xs text-neutral-500">
            Every price change is kept in the general audit log with the old and new amounts and the reason.
          </p>
        </Card>

        <BillingRulesCard canEdit={canEdit} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ModulePricesCard />
        <SmsBundlesCard canEdit={canEdit} />
      </div>

      <div className="mt-6">
        <Card title="What each school pays">
          {p.schools.length ? (
            <Table head={["School", "Active pupils", "Band", "Amount"]}>
              {p.schools.map((s) => {
                const index = p.bands.findIndex((b) => b.code === s.band_code);
                return (
                  <tr key={s.slug}>
                    <Td>
                      <Link href={`/platform/schools/${s.slug}`} className="font-medium hover:underline">
                        {s.name}
                      </Link>
                    </Td>
                    <Td className="tabular-nums">{s.pupils?.toLocaleString("en-GB") ?? "—"}</Td>
                    <Td>{index >= 0 ? `Band ${index + 1}` : "—"}</Td>
                    <Td className="tabular-nums">
                      {s.amount_pesewas != null ? cedis(s.amount_pesewas) : "—"}
                    </Td>
                  </tr>
                );
              })}
            </Table>
          ) : (
            <p className="text-sm text-neutral-500">No active schools yet.</p>
          )}
        </Card>
      </div>

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title="Change a price">
        {editing && <ChangePrice band={editing} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function ChangePrice({ band, onDone }: { band: Pricing["bands"][number]; onDone: () => void }) {
  const client = useQueryClient();
  const [price, setPrice] = useState((band.price_pesewas / 100).toFixed(2));
  const [reason, setReason] = useState("");
  const pesewas = toPesewas(price);
  const save = useMutation({
    mutationFn: () =>
      apiFetch<Pricing>(`/api/v1/platform/billing/bands/${band.code}`, {
        method: "POST",
        school: false,
        body: { price_pesewas: pesewas, reason },
      }),
    onSuccess: (data) => {
      client.setQueryData(["platform", "pricing"], data);
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="grid gap-3">
      <p className="text-sm">
        <span className="font-medium">{band.label}</span>, now {cedis(band.price_pesewas)}. {band.schools}{" "}
        school{band.schools === 1 ? "" : "s"} in this band.
      </p>
      <Field label="New price (GH₵)">
        <Input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" required />
      </Field>
      <Field label="Reason" hint="Kept in the audit log, e.g. “New prices from January 2027”.">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
      </Field>
      {pesewas !== null && pesewas !== band.price_pesewas && (
        <Alert tone="info">
          Schools in this band will pay {cedis(pesewas)} instead of {cedis(band.price_pesewas)}.
        </Alert>
      )}
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending} disabled={pesewas === null || !reason.trim()}>
          Save price
        </Button>
      </div>
    </form>
  );
}
