"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Alert, Badge, Button, Card, ErrorText, Field, Input, Loading, Modal } from "@/components/ui";
import { ApiError, apiFetch, type Me } from "@/lib/api";
import { cedis, toPesewas } from "@/lib/format";

type ConsoleModule = {
  code: string;
  name: string;
  description: string;
  core: boolean;
  available: boolean;
  price_pesewas: number;
  entitled: boolean;
  active: boolean;
};
type ModuleHistory = {
  code: string;
  module: string;
  action_label: string;
  actor_email: string;
  by_platform: boolean;
  at: string;
};
type Action = "grant" | "revoke" | "activate" | "deactivate";

const ACTION_LABEL: Record<Action, string> = {
  grant: "Grant add-on",
  revoke: "Remove add-on",
  activate: "Switch on",
  deactivate: "Switch off",
};

function useIsSuperAdmin() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }) });
  return Boolean(me.data?.platform_roles.includes("super_admin"));
}

/** A school's optional modules on its console page. Super admins can act; every action needs a reason. */
export function TenantModulesCard({ slug }: { slug: string }) {
  const client = useQueryClient();
  const superAdmin = useIsSuperAdmin();
  const path = `/api/v1/platform/tenants/${slug}/modules`;
  const data = useQuery({
    queryKey: ["platform", "tenant-modules", slug],
    queryFn: () => apiFetch<{ modules: ConsoleModule[]; history: ModuleHistory[] }>(path, { school: false }),
  });
  const [pending, setPending] = useState<{ module: ConsoleModule; action: Action } | null>(null);

  if (data.isPending) return <Loading />;
  if (data.error) return <ErrorText error={data.error} />;
  const optional = data.data.modules.filter((m) => !m.core && m.available);

  return (
    <Card title="Modules">
      <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
        {optional.map((m) => (
          <li key={m.code} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{m.name}</span>
              {m.active ? <Badge tone="green">On</Badge> : <Badge tone="grey">Off</Badge>}
              {m.price_pesewas > 0 &&
                (m.entitled ? (
                  <Badge tone="blue">Add-on granted</Badge>
                ) : (
                  <Badge tone="amber">Add-on not paid</Badge>
                ))}
            </span>
            {superAdmin && (
              <span className="flex flex-wrap gap-1">
                {m.price_pesewas > 0 && (
                  <Button
                    variant="ghost"
                    onClick={() => setPending({ module: m, action: m.entitled ? "revoke" : "grant" })}
                  >
                    {m.entitled ? "Remove add-on" : "Grant add-on"}
                  </Button>
                )}
                {m.entitled && (
                  <Button
                    variant="ghost"
                    onClick={() => setPending({ module: m, action: m.active ? "deactivate" : "activate" })}
                  >
                    {m.active ? "Switch off" : "Switch on"}
                  </Button>
                )}
              </span>
            )}
          </li>
        ))}
      </ul>
      {data.data.history.length > 0 && (
        <p className="mt-3 text-xs text-neutral-500">
          Last change: {data.data.history[0]?.action_label} {data.data.history[0]?.module} by{" "}
          {data.data.history[0]?.by_platform ? "Nex Edu" : "the school"} ({data.data.history[0]?.actor_email})
        </p>
      )}
      <Modal
        open={Boolean(pending)}
        onClose={() => setPending(null)}
        title={pending ? `${ACTION_LABEL[pending.action]}: ${pending.module.name}` : ""}
      >
        {pending && (
          <ModuleActionForm
            path={path}
            module={pending.module}
            action={pending.action}
            onDone={() => {
              setPending(null);
              void client.invalidateQueries({ queryKey: ["platform", "tenant-modules", slug] });
            }}
          />
        )}
      </Modal>
    </Card>
  );
}

function ModuleActionForm({
  path,
  module,
  action,
  onDone,
}: {
  path: string;
  module: ConsoleModule;
  action: Action;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [records, setRecords] = useState<string[] | null>(null);
  const save = useMutation({
    mutationFn: (confirm: boolean) =>
      apiFetch(path, { method: "POST", school: false, body: { code: module.code, action, reason, confirm } }),
    onSuccess: onDone,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        setRecords((error.body as { open_records?: string[] }).open_records ?? []);
      }
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(records !== null);
  };
  return (
    <form onSubmit={submit} className="grid gap-3">
      <Field
        label="Reason"
        hint={
          action === "grant"
            ? "For example the payment reference."
            : "Kept in the audit log and shown to the school."
        }
      >
        <Input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
      </Field>
      {records && (
        <Alert tone="warning">
          The school still has {records.join(", ")}. Nothing is deleted. Press the button again to go ahead.
        </Alert>
      )}
      {!(save.error instanceof ApiError && save.error.status === 409) && <ErrorText error={save.error} />}
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending} disabled={!reason.trim()}>
          {ACTION_LABEL[action]}
        </Button>
      </div>
    </form>
  );
}

type ModulePrice = {
  code: string;
  name: string;
  description: string;
  available: boolean;
  price_pesewas: number;
};

/** Optional module prices on the Pricing and billing page. GH₵0 means included in every band. */
export function ModulePricesCard() {
  const client = useQueryClient();
  const superAdmin = useIsSuperAdmin();
  const prices = useQuery({
    queryKey: ["platform", "module-prices"],
    queryFn: () => apiFetch<ModulePrice[]>("/api/v1/platform/billing/modules", { school: false }),
  });
  const [editing, setEditing] = useState<ModulePrice | null>(null);
  if (prices.isPending) return <Loading />;
  if (prices.error) return <ErrorText error={prices.error} />;
  return (
    <Card title="Optional modules">
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
        GH₵0 means the module is included in every price band. A price makes it a paid add-on that you grant
        to a school once it pays (on the school's page).
      </p>
      <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
        {prices.data.map((m) => (
          <li key={m.code} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              <span className="font-medium">{m.name}</span>{" "}
              {!m.available && <Badge tone="grey">Coming soon</Badge>}
            </span>
            <span className="flex items-center gap-2">
              <span className="tabular-nums">{m.price_pesewas ? cedis(m.price_pesewas) : "Included"}</span>
              {superAdmin && m.available && (
                <Button
                  variant="ghost"
                  onClick={() => setEditing(m)}
                  aria-label={`Change price for ${m.name}`}
                >
                  Change
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={`Price for ${editing?.name ?? ""}`}
      >
        {editing && (
          <ModulePriceForm
            module={editing}
            onDone={(data) => {
              client.setQueryData(["platform", "module-prices"], data);
              setEditing(null);
            }}
          />
        )}
      </Modal>
    </Card>
  );
}

function ModulePriceForm({ module, onDone }: { module: ModulePrice; onDone: (data: ModulePrice[]) => void }) {
  const [price, setPrice] = useState((module.price_pesewas / 100).toFixed(2));
  const [reason, setReason] = useState("");
  const pesewas = toPesewas(price);
  const save = useMutation({
    mutationFn: () =>
      apiFetch<ModulePrice[]>(`/api/v1/platform/billing/modules/${module.code}`, {
        method: "POST",
        school: false,
        body: { price_pesewas: pesewas, reason },
      }),
    onSuccess: onDone,
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
      className="grid gap-3"
    >
      <Field label="Price per billing period (GH₵)" hint="0 means included in every band.">
        <Input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" required />
      </Field>
      <Field label="Reason" hint="Kept in the audit log.">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={300} />
      </Field>
      {pesewas !== null && pesewas > 0 && module.price_pesewas === 0 && (
        <Alert tone="warning">
          Schools that haven't paid for it lose {module.name} until you grant it on their page.
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
