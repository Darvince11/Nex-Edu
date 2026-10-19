"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent, ReactNode } from "react";
import { Alert, Button, Card, ErrorText, Field, Input, Loading, PageHeader, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { cedis, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { hasAny } from "@/lib/roles";

type Profile = Record<string, string>;
type PaymentSettings = {
  online_payments_enabled: boolean;
  paystack_subaccount_code: string;
  flutterwave_subaccount_id: string;
  allow_part_payment: boolean;
  minimum_part_payment_pesewas: number;
  bank_transfer_instructions: string;
};
type MessagingSettings = {
  sms_sender_id: string;
  sms_monthly_limit: number;
  notify_absence_by_sms: boolean;
  notify_results_by_sms: boolean;
  whatsapp_enabled: boolean;
};

export default function SettingsPage() {
  const { roles } = useSchool();
  const leader = hasAny(roles, ["owner", "principal", "admin"]);
  const finance = hasAny(roles, ["owner", "bursar"]);
  return (
    <>
      <PageHeader title="School settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        {leader && <ProfileSettings />}
        {finance && <PaymentSettingsCard />}
        {leader && <MessagingSettingsCard />}
      </div>
    </>
  );
}

function useSettings<T>(path: string) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: [path], queryFn: () => api.get<T>(path) });
  const save = useMutation({
    mutationFn: (body: Partial<T>) => api.patch<T>(path, body),
    onSuccess: (data) => client.setQueryData([path], data),
  });
  return { query, save };
}

function SaveRow({ save }: { save: { isPending: boolean; isSuccess: boolean; error: unknown } }): ReactNode {
  return (
    <div className="flex items-center justify-end gap-3 sm:col-span-2">
      {save.isSuccess && <span className="text-sm text-emerald-700">Saved</span>}
      <ErrorText error={save.error} />
      <Button type="submit" busy={save.isPending}>
        Save
      </Button>
    </div>
  );
}

function ProfileSettings() {
  const { query, save } = useSettings<Profile>("/api/v1/school/profile");
  if (!query.data) return <Loading />;
  const p = query.data;
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    save.mutate(Object.fromEntries(new FormData(e.currentTarget)) as Profile);
  };
  return (
    <Card title="School profile (shown on report cards and receipts)">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="School name">
          <Input name="name" defaultValue={p.name} required />
        </Field>
        <Field label="Motto">
          <Input name="motto" defaultValue={p.motto} />
        </Field>
        <Field label="Phone">
          <Input name="phone" defaultValue={p.phone} />
        </Field>
        <Field label="Email">
          <Input name="email" type="email" defaultValue={p.email} />
        </Field>
        <Field label="Head teacher's name">
          <Input name="principal_name" defaultValue={p.principal_name} />
        </Field>
        <Field label="Admission number prefix" hint="e.g. GFA → GFA/2026/0001">
          <Input name="admission_prefix" defaultValue={p.admission_prefix} maxLength={10} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Address">
            <Textarea name="address" defaultValue={p.address} rows={2} />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Report card footer">
            <Input name="report_card_footer" defaultValue={p.report_card_footer} />
          </Field>
        </div>
        <SaveRow save={save} />
      </form>
    </Card>
  );
}

function PaymentSettingsCard() {
  const { query, save } = useSettings<PaymentSettings>("/api/v1/school/payment-settings");
  if (!query.data) return <Loading />;
  const s = query.data;
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    save.mutate({
      online_payments_enabled: f.get("online_payments_enabled") === "on",
      allow_part_payment: f.get("allow_part_payment") === "on",
      paystack_subaccount_code: String(f.get("paystack_subaccount_code") ?? ""),
      flutterwave_subaccount_id: String(f.get("flutterwave_subaccount_id") ?? ""),
      minimum_part_payment_pesewas: toPesewas(String(f.get("minimum") ?? "0")) ?? 0,
      bank_transfer_instructions: String(f.get("bank_transfer_instructions") ?? ""),
    });
  };
  return (
    <Card title="Online fee payments">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" name="online_payments_enabled" defaultChecked={s.online_payments_enabled} />{" "}
          Accept mobile money and card payments
        </label>
        <Field label="Paystack subaccount code" hint="Money settles straight to the school's bank account.">
          <Input name="paystack_subaccount_code" defaultValue={s.paystack_subaccount_code} />
        </Field>
        <Field label="Flutterwave subaccount ID">
          <Input name="flutterwave_subaccount_id" defaultValue={s.flutterwave_subaccount_id} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="allow_part_payment" defaultChecked={s.allow_part_payment} /> Allow part
          payments
        </label>
        <Field label={`Minimum part payment (now ${cedis(s.minimum_part_payment_pesewas)})`}>
          <Input
            name="minimum"
            inputMode="decimal"
            defaultValue={(s.minimum_part_payment_pesewas / 100).toFixed(2)}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Bank transfer instructions for parents">
            <Textarea
              name="bank_transfer_instructions"
              defaultValue={s.bank_transfer_instructions}
              rows={2}
            />
          </Field>
        </div>
        <SaveRow save={save} />
      </form>
    </Card>
  );
}

function MessagingSettingsCard() {
  const { query, save } = useSettings<MessagingSettings>("/api/v1/school/messaging-settings");
  const usage = useQuery({
    queryKey: ["sms-usage"],
    queryFn: () =>
      api.get<{ sms_sent_this_month: number; sms_monthly_limit: number }>(
        "/api/v1/communication/deliveries/usage",
      ),
  });
  if (!query.data) return <Loading />;
  const s = query.data;
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    save.mutate({
      sms_sender_id: String(f.get("sms_sender_id") ?? ""),
      sms_monthly_limit: Number(f.get("sms_monthly_limit")),
      notify_absence_by_sms: f.get("notify_absence_by_sms") === "on",
      notify_results_by_sms: f.get("notify_results_by_sms") === "on",
      whatsapp_enabled: f.get("whatsapp_enabled") === "on",
    });
  };
  return (
    <Card title="SMS and WhatsApp">
      {usage.data && (
        <div className="mb-3">
          <Alert tone="info">
            {usage.data.sms_sent_this_month} of {usage.data.sms_monthly_limit} SMS used this month.
          </Alert>
        </div>
      )}
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="SMS sender ID" hint="Up to 11 characters, registered with the SMS provider">
          <Input name="sms_sender_id" defaultValue={s.sms_sender_id} maxLength={11} />
        </Field>
        <Field label="Monthly SMS limit">
          <Input name="sms_monthly_limit" type="number" min={0} defaultValue={s.sms_monthly_limit} />
        </Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" name="notify_absence_by_sms" defaultChecked={s.notify_absence_by_sms} /> Text
          parents when a child is marked absent
        </label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" name="notify_results_by_sms" defaultChecked={s.notify_results_by_sms} /> Text
          parents when results are published
        </label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" name="whatsapp_enabled" defaultChecked={s.whatsapp_enabled} /> Allow WhatsApp
          messages
        </label>
        <SaveRow save={save} />
      </form>
    </Card>
  );
}
