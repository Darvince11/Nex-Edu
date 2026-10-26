"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  Table,
  Td,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { cedis, toPesewas } from "@/lib/format";

type Rules = { due_days: number; sms_included_monthly: number };
type Bundle = {
  code: string;
  label: string;
  sms: number;
  price_pesewas: number;
  is_active: boolean;
  position: number;
};

/** Monthly billing, days to pay, and the SMS every school gets each month (super admins change them). */
export function BillingRulesCard({ canEdit }: { canEdit: boolean }) {
  const client = useQueryClient();
  const path = "/api/v1/platform/billing/rules";
  const rules = useQuery({
    queryKey: ["platform", "billing-rules"],
    queryFn: () => apiFetch<Rules>(path, { school: false }),
  });
  const save = useMutation({
    mutationFn: (body: Rules) => apiFetch<Rules>(path, { method: "PATCH", school: false, body }),
    onSuccess: (data) => client.setQueryData(["platform", "billing-rules"], data),
  });
  if (!rules.data) return rules.error ? <ErrorText error={rules.error} /> : <Loading />;
  return (
    <Card title="Billing rules">
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
        Schools are billed <strong>monthly</strong>, on the 1st. Reminders go out 7 and 14 days after the due
        date; 30 days after it the school is suspended until it pays.
      </p>
      <form
        key={`${rules.data.due_days}-${rules.data.sms_included_monthly}`}
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          save.mutate({ due_days: Number(f.get("due_days")), sms_included_monthly: Number(f.get("sms")) });
        }}
      >
        <Field label="Days to pay" hint="From the invoice to its due date">
          <Input
            name="due_days"
            type="number"
            min={1}
            max={60}
            defaultValue={rules.data.due_days}
            disabled={!canEdit}
          />
        </Field>
        <Field label="SMS included each month" hint="Beyond this, schools use SMS bundles they buy">
          <Input
            name="sms"
            type="number"
            min={0}
            max={1000000}
            defaultValue={rules.data.sms_included_monthly}
            disabled={!canEdit}
          />
        </Field>
        <ErrorText error={save.error} />
        {canEdit ? (
          <div className="flex justify-end">
            <Button type="submit" variant="secondary" busy={save.isPending}>
              Save rules
            </Button>
          </div>
        ) : (
          <p className="text-xs text-neutral-500">Only a super admin can change these.</p>
        )}
      </form>
    </Card>
  );
}

/** The SMS bundles schools can buy through Paystack. */
export function SmsBundlesCard({ canEdit }: { canEdit: boolean }) {
  const [open, setOpen] = useState<Bundle | "new" | null>(null);
  const bundles = useQuery({
    queryKey: ["platform", "sms-bundles"],
    queryFn: () => apiFetch<Bundle[]>("/api/v1/platform/billing/sms-bundles", { school: false }),
  });
  return (
    <Card
      title="SMS bundles"
      actions={
        canEdit && (
          <Button variant="secondary" onClick={() => setOpen("new")}>
            Add a bundle
          </Button>
        )
      }
    >
      {bundles.isPending ? (
        <Loading />
      ) : bundles.error ? (
        <ErrorText error={bundles.error} />
      ) : bundles.data.length ? (
        <Table head={["Bundle", "SMS", "Price", "On sale", ""]}>
          {bundles.data.map((b) => (
            <tr key={b.code}>
              <Td className="font-medium">{b.label}</Td>
              <Td className="tabular-nums">{b.sms.toLocaleString("en-GB")}</Td>
              <Td className="tabular-nums">{cedis(b.price_pesewas)}</Td>
              <Td>{b.is_active ? <Badge tone="green">On sale</Badge> : <Badge tone="grey">Off</Badge>}</Td>
              <Td className="text-right">
                {canEdit && (
                  <Button variant="ghost" onClick={() => setOpen(b)} aria-label={`Change ${b.label}`}>
                    Change
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No bundles yet, so schools can't buy extra SMS. Add one with its price.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "Add an SMS bundle" : "Change a bundle"}
      >
        {open !== null && <BundleForm bundle={open === "new" ? null : open} onDone={() => setOpen(null)} />}
      </Modal>
    </Card>
  );
}

function BundleForm({ bundle, onDone }: { bundle: Bundle | null; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Partial<Bundle>) =>
      bundle
        ? apiFetch(`/api/v1/platform/billing/sms-bundles/${bundle.code}`, {
            method: "PATCH",
            school: false,
            body,
          })
        : apiFetch("/api/v1/platform/billing/sms-bundles", { method: "POST", school: false, body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["platform", "sms-bundles"] });
      onDone();
    },
  });
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        const sms = Number(f.sms);
        save.mutate({
          ...(bundle ? {} : { code: `sms-${sms}` }),
          label: f.label || `${sms.toLocaleString("en-GB")} SMS`,
          sms,
          price_pesewas: toPesewas(f.price ?? "") ?? 0,
          is_active: f.active === "on",
        });
      }}
    >
      <Field label="Number of SMS">
        <Input
          name="sms"
          type="number"
          min={1}
          max={1000000}
          required
          defaultValue={bundle?.sms}
          disabled={Boolean(bundle)}
        />
      </Field>
      <Field label="Name" hint="Leave blank for “1,000 SMS”">
        <Input name="label" maxLength={60} defaultValue={bundle?.label} />
      </Field>
      <Field label="Price (GH₵)">
        <Input
          name="price"
          required
          inputMode="decimal"
          defaultValue={bundle ? (bundle.price_pesewas / 100).toFixed(2) : ""}
        />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="active"
          defaultChecked={bundle?.is_active ?? true}
          className="size-4 accent-brand"
        />
        On sale to schools
      </label>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save bundle
        </Button>
      </div>
    </form>
  );
}
