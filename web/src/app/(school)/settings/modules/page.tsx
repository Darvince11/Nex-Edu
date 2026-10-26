"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert, Badge, Button, Card, ErrorText, Loading, Modal, PageHeader } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { cedis } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type SchoolModule = {
  code: string;
  name: string;
  description: string;
  core: boolean;
  available: boolean;
  depends: { code: string; name: string }[];
  price_pesewas: number;
  entitled: boolean;
  active: boolean;
};

type ModulesData = {
  modules: SchoolModule[];
  history: {
    code: string;
    module: string;
    action_label: string;
    actor_email: string;
    by_platform: boolean;
    at: string;
  }[];
  confirmed: boolean;
};

const PATH = "/api/v1/school/modules";
const when = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Africa/Accra",
});

/**
 * The school's features. Core ones are always on; the proprietor switches the
 * optional ones. Switching off hides a feature everywhere but deletes nothing.
 */
export default function ModulesPage() {
  const client = useQueryClient();
  const { can } = useSchool();
  const canSwitch = can(PERM.SCHOOL_MODULES);
  const data = useQuery({ queryKey: ["school-modules"], queryFn: () => api.get<ModulesData>(PATH) });
  const [confirming, setConfirming] = useState<{ module: SchoolModule; records: string[] } | null>(null);

  const done = (next: ModulesData) => {
    client.setQueryData(["school-modules"], next);
    // The menu, dashboard and checklist all follow the switches.
    void client.invalidateQueries({ queryKey: ["me"] });
    void client.invalidateQueries({ queryKey: ["school-setup"] });
    void client.invalidateQueries({ queryKey: ["insights"] });
  };
  const toggle = useMutation({
    mutationFn: (vars: { code: string; active: boolean; confirm?: boolean }) =>
      api.post<ModulesData>(PATH, vars),
    onSuccess: (next) => {
      setConfirming(null);
      done(next);
    },
    onError: (error, vars) => {
      if (error instanceof ApiError && error.status === 409) {
        const body = error.body as { open_records?: string[] };
        const module = data.data?.modules.find((m) => m.code === vars.code);
        if (module) setConfirming({ module, records: body.open_records ?? [] });
      }
    },
  });
  const confirm = useMutation({
    mutationFn: () => api.post<ModulesData>(PATH, { action: "confirm_choices" }),
    onSuccess: done,
  });

  if (data.isPending) return <Loading />;
  if (data.error) return <ErrorText error={data.error} />;
  const modules = data.data.modules;
  const optional = modules.filter((m) => !m.core && m.available);
  const core = modules.filter((m) => m.core);
  const coming = modules.filter((m) => !m.available);
  const conflict = toggle.error instanceof ApiError && toggle.error.status === 409;

  return (
    <>
      <PageHeader
        title="Modules"
        description="The features your school uses. Switching one off hides it for everyone but deletes nothing; switch it back on and everything is still there."
        actions={
          canSwitch && (
            <Button
              variant={data.data.confirmed ? "secondary" : "primary"}
              busy={confirm.isPending}
              onClick={() => confirm.mutate()}
            >
              {data.data.confirmed ? "Choices saved" : "Save my choices"}
            </Button>
          )
        }
      />
      {!canSwitch && (
        <div className="mb-4">
          <Alert tone="info">Only the proprietor switches modules on and off.</Alert>
        </div>
      )}
      {!conflict && <ErrorText error={toggle.error ?? confirm.error} />}

      <Card title="Optional modules">
        <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
          {optional.map((m) => (
            <li key={m.code} className="flex flex-wrap items-start justify-between gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {m.name}
                  {m.active ? <Badge tone="green">On</Badge> : <Badge tone="grey">Off</Badge>}
                  {m.price_pesewas > 0 ? (
                    <Badge tone="amber">Add-on: {cedis(m.price_pesewas)}</Badge>
                  ) : (
                    <Badge tone="blue">Included</Badge>
                  )}
                </p>
                <p className="text-sm text-neutral-600 dark:text-neutral-300">{m.description}</p>
                {m.depends.length > 0 && (
                  <p className="text-xs text-neutral-500">Needs: {m.depends.map((d) => d.name).join(", ")}</p>
                )}
                {!m.entitled && (
                  <p className="mt-1 text-xs text-neutral-500">
                    A paid add-on. Ask Nex Edu to add it to your subscription.
                  </p>
                )}
              </div>
              {canSwitch && (
                <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm">
                  <span className="sr-only">{m.name}</span>
                  <input
                    type="checkbox"
                    role="switch"
                    aria-checked={m.active}
                    checked={m.active}
                    disabled={!m.entitled || toggle.isPending}
                    onChange={(e) => toggle.mutate({ code: m.code, active: e.target.checked })}
                    className="peer sr-only"
                  />
                  <span
                    aria-hidden="true"
                    className="relative h-6 w-11 rounded-full bg-neutral-300 transition-colors peer-checked:bg-brand peer-disabled:opacity-50 peer-focus-visible:outline-2 peer-focus-visible:outline-brand after:absolute after:top-0.5 after:left-0.5 after:size-5 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-5 dark:bg-neutral-700"
                  />
                  <span className="w-6 text-neutral-600 dark:text-neutral-300">
                    {m.active ? "On" : "Off"}
                  </span>
                </label>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Always included">
          <ul className="grid gap-2 text-sm">
            {core.map((m) => (
              <li key={m.code}>
                <span className="font-medium">{m.name}</span>
                <span className="text-neutral-600 dark:text-neutral-300"> · {m.description}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Coming soon">
          <ul className="grid gap-2 text-sm">
            {coming.map((m) => (
              <li key={m.code}>
                <span className="font-medium">{m.name}</span>
                <span className="text-neutral-600 dark:text-neutral-300"> · {m.description}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mt-4">
        <Card title="History">
          {data.data.history.length ? (
            <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
              {data.data.history.map((h) => (
                <li
                  key={`${h.at}-${h.code}-${h.action_label}`}
                  className="flex flex-wrap justify-between gap-2 py-2"
                >
                  <span>
                    <span className="font-medium">{h.action_label}</span>
                    {h.module && ` · ${h.module}`}
                  </span>
                  <span className="text-xs text-neutral-500">
                    {h.by_platform ? `Nex Edu (${h.actor_email})` : h.actor_email} ·{" "}
                    {when.format(new Date(h.at))}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-500">No changes yet.</p>
          )}
        </Card>
      </div>

      <Modal
        open={Boolean(confirming)}
        onClose={() => setConfirming(null)}
        title={`Switch off ${confirming?.module.name ?? ""}?`}
      >
        {confirming && (
          <div className="grid gap-3 text-sm">
            <p>
              {confirming.module.name} still has {confirming.records.join(", ")}. Switching it off hides it
              for everyone, but nothing is deleted: switch it back on and it's all still there.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirming(null)}>
                Keep it on
              </Button>
              <Button
                variant="danger"
                busy={toggle.isPending}
                onClick={() => toggle.mutate({ code: confirming.module.code, active: false, confirm: true })}
              >
                Switch off anyway
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
