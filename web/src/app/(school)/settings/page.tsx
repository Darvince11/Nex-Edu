"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, type FormEvent, type ReactNode, useRef, useState } from "react";
import { useSetupAction, useSetupChecklist } from "@/components/setup-checklist";
import { Alert, Button, Card, ErrorText, Field, Input, Loading, PageHeader, Textarea } from "@/components/ui";
import { ApiError, api, apiFetch } from "@/lib/api";
import { cedis, toPesewas } from "@/lib/format";
import { SCHOOL_LOGO, useSchool, useSchoolLogo } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

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
  const { can } = useSchool();
  const leader = can(PERM.SCHOOL_MANAGE);
  const finance = can(PERM.FINANCE_MANAGE);
  return (
    <>
      <PageHeader title="School settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        {leader && <SetupCard />}
        {leader && <ProfileSettings />}
        {can(PERM.SCHOOL_BRANDING) && <LogoCard />}
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

const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];

/** The school's own logo: top bar, admission page, report cards and receipts. */
function LogoCard() {
  const { slug } = useSchool();
  const client = useQueryClient();
  const logo = useSchoolLogo(SCHOOL_LOGO, slug ?? undefined);
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  const refresh = () => client.invalidateQueries({ queryKey: ["school-logo"] });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("logo", file);
      return apiFetch(SCHOOL_LOGO, { method: "PUT", body });
    },
    onSuccess: refresh,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Upload failed. Try again."),
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(SCHOOL_LOGO, { method: "DELETE" }),
    onSuccess: refresh,
  });

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(undefined);
    // Quick checks for a friendly message; the server decodes and re-encodes every upload.
    if (!LOGO_TYPES.includes(file.type)) return setError("Choose a PNG, JPG or WebP image.");
    if (file.size > 1024 * 1024) return setError("The logo must be 1 MB or smaller.");
    upload.mutate(file);
  }

  return (
    <Card title="School logo">
      <div className="flex items-center gap-4">
        <div className="grid size-20 shrink-0 place-items-center overflow-hidden rounded-lg border border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
          {logo ? (
            // biome-ignore lint/performance/noImgElement: a local blob URL; next/image can't optimise it.
            <img src={logo} alt="Current school logo" className="size-full object-contain p-1" />
          ) : (
            <span className="text-xs text-neutral-500">No logo</span>
          )}
        </div>
        <div className="flex flex-col gap-2 text-sm">
          <p className="text-neutral-500">
            Shown in your school's workspace, on the admission page, and on report cards and receipts. PNG,
            JPG or WebP, up to 1 MB. We resize it and remove hidden photo data.
          </p>
          <div className="flex flex-wrap gap-2">
            <input
              ref={input}
              type="file"
              accept={LOGO_TYPES.join(",")}
              onChange={onFile}
              className="sr-only"
              aria-label="Choose a logo file"
            />
            <Button onClick={() => input.current?.click()} busy={upload.isPending}>
              {logo ? "Replace logo" : "Upload logo"}
            </Button>
            {logo && (
              <Button variant="secondary" onClick={() => remove.mutate()} busy={remove.isPending}>
                Remove
              </Button>
            )}
          </div>
        </div>
      </div>
      {error && (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      )}
    </Card>
  );
}

/** The set-up checklist's progress, terms acceptance, and a way to bring the list back. */
function SetupCard() {
  const checklist = useSetupChecklist(true);
  const act = useSetupAction();
  if (!checklist.data) return null;
  const c = checklist.data;
  return (
    <Card title="Set-up checklist">
      <p className="text-sm">
        {c.complete ? "All set-up steps are done." : `${c.done} of ${c.total} steps done.`}
      </p>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
        {c.terms_accepted_at
          ? `Terms accepted for the school by ${c.terms_accepted_by} on ${new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" }).format(new Date(c.terms_accepted_at))}.`
          : "The proprietor hasn't accepted the terms for the school yet."}
      </p>
      <ErrorText error={act.error} />
      {c.hidden && !c.complete && (
        <Button className="mt-3" variant="secondary" busy={act.isPending} onClick={() => act.mutate("show")}>
          Show the checklist on the dashboard
        </Button>
      )}
    </Card>
  );
}
