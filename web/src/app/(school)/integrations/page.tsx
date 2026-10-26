"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";

type Option = { code: string; label: string };
type Key = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};
type Hook = {
  id: string;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
  last_delivery: { status: string; at: string; error: string } | null;
};
type Delivery = {
  id: string;
  event: string;
  status: string;
  attempts: number;
  response_code: number | null;
  error: string;
  created_at: string;
};

/** API keys and webhooks for other systems (the proprietor only). */
export default function IntegrationsPage() {
  const options = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.get<{ scopes: Option[]; events: Option[] }>("/api/v1/integrations"),
  });
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Let another system (an accounting package, a parent app, a district dashboard) read your school's data or hear when things happen. Read-only, one school, and you can switch any key off."
      />
      <ErrorText error={options.error} />
      {options.data ? (
        <div className="flex flex-col gap-6">
          <Keys scopes={options.data.scopes} />
          <Webhooks events={options.data.events} />
          <Guide />
        </div>
      ) : (
        !options.error && <Loading />
      )}
    </>
  );
}

function Checkboxes({ name, options }: { name: string; options: Option[] }) {
  return (
    <fieldset className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
      <legend className="px-1 text-sm font-medium">
        {name === "scopes" ? "It may read" : "Send these events"}
      </legend>
      <div className="flex flex-col gap-1">
        {options.map((o) => (
          <label key={o.code} className="flex items-start gap-2 text-sm">
            <input type="checkbox" name={name} value={o.code} className="mt-0.5 size-4 accent-brand" />
            <span>
              <span className="font-mono text-xs">{o.code}</span> · {o.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Secret({ label, value, note }: { label: string; value: string; note: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <Alert tone="warning">{note}</Alert>
      <label className="text-sm font-medium" htmlFor="secret-value">
        {label}
      </label>
      <Input
        id="secret-value"
        readOnly
        value={value}
        onFocus={(e) => e.currentTarget.select()}
        className="font-mono"
      />
      <div>
        <Button
          variant="secondary"
          onClick={() => void navigator.clipboard?.writeText(value).then(() => setCopied(true))}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

function Keys({ scopes }: { scopes: Option[] }) {
  const client = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [made, setMade] = useState<string | null>(null);
  const keys = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.get<Key[]>("/api/v1/integrations/keys"),
  });
  const create = useMutation({
    mutationFn: (body: { name: string; scopes: string[] }) =>
      api.post<Key & { key: string }>("/api/v1/integrations/keys", body),
    onSuccess: (data) => {
      setMade(data.key);
      void client.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/integrations/keys/${id}/revoke`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["api-keys"] }),
  });
  return (
    <Card
      title="API keys"
      actions={
        <Button
          variant="secondary"
          onClick={() => {
            setMade(null);
            create.reset();
            setAdding(true);
          }}
        >
          New key
        </Button>
      }
    >
      <ErrorText error={keys.error ?? revoke.error} />
      {keys.data?.length ? (
        <Table head={["Name", "Key", "Can read", "Last used", ""]}>
          {keys.data.map((k) => (
            <tr key={k.id}>
              <Td className="font-medium">{k.name}</Td>
              <Td className="font-mono text-xs">nxk_{k.prefix}_…</Td>
              <Td className="text-xs">{k.scopes.join(", ")}</Td>
              <Td>{k.revoked_at ? <Badge tone="grey">Switched off</Badge> : timeAgo(k.last_used_at)}</Td>
              <Td className="text-right">
                {!k.revoked_at && (
                  <Button
                    variant="ghost"
                    busy={revoke.isPending && revoke.variables === k.id}
                    onClick={() => revoke.mutate(k.id)}
                    aria-label={`Switch off ${k.name}`}
                  >
                    Switch off
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        keys.data && <Empty>No keys yet.</Empty>
      )}
      <Modal open={adding} onClose={() => setAdding(false)} title={made ? "Your new key" : "New API key"}>
        {made ? (
          <Secret
            label="API key"
            value={made}
            note="Copy it now and give it only to the system that needs it. It won't be shown again."
          />
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              create.mutate({ name: String(f.get("name") ?? ""), scopes: f.getAll("scopes").map(String) });
            }}
          >
            <Field label="What it's for">
              <Input name="name" required maxLength={80} placeholder="e.g. Accountant's software" />
            </Field>
            <Checkboxes name="scopes" options={scopes} />
            <ErrorText error={create.error} />
            <div className="flex justify-end">
              <Button type="submit" busy={create.isPending}>
                Make the key
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </Card>
  );
}

function Webhooks({ events }: { events: Option[] }) {
  const client = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const hooks = useQuery({
    queryKey: ["webhooks"],
    queryFn: () => api.get<Hook[]>("/api/v1/integrations/webhooks"),
  });
  const create = useMutation({
    mutationFn: (body: { url: string; events: string[] }) =>
      api.post<Hook & { secret: string }>("/api/v1/integrations/webhooks", body),
    onSuccess: (data) => {
      setSecret(data.secret);
      void client.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });
  return (
    <Card
      title="Webhooks"
      actions={
        <Button
          variant="secondary"
          onClick={() => {
            setSecret(null);
            create.reset();
            setAdding(true);
          }}
        >
          Add a webhook
        </Button>
      }
    >
      <ErrorText error={hooks.error} />
      {hooks.data?.length ? (
        <Table head={["Address", "Events", "Last sent", ""]}>
          {hooks.data.map((h) => (
            <tr key={h.id}>
              <Td className="max-w-xs break-all font-mono text-xs">{h.url}</Td>
              <Td className="text-xs">{h.events.join(", ")}</Td>
              <Td>
                {h.last_delivery ? (
                  <Badge
                    tone={
                      h.last_delivery.status === "sent"
                        ? "green"
                        : h.last_delivery.status === "failed"
                          ? "red"
                          : "amber"
                    }
                  >
                    {h.last_delivery.status} {timeAgo(h.last_delivery.at)}
                  </Badge>
                ) : (
                  "Not yet"
                )}
              </Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(h.id)} aria-label={`Open webhook ${h.url}`}>
                  Open
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        hooks.data && <Empty>No webhooks yet.</Empty>
      )}
      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title={secret ? "Your signing secret" : "Add a webhook"}
      >
        {secret ? (
          <Secret
            label="Signing secret"
            value={secret}
            note="Use it to check each request really comes from Nex Edu. It won't be shown again."
          />
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              create.mutate({ url: String(f.get("url") ?? ""), events: f.getAll("events").map(String) });
            }}
          >
            <Field label="Address (https)" hint="Nex Edu sends a POST here for each event.">
              <Input name="url" type="url" required maxLength={500} pattern="https://.*" />
            </Field>
            <Checkboxes name="events" options={events} />
            <ErrorText error={create.error} />
            <div className="flex justify-end">
              <Button type="submit" busy={create.isPending}>
                Add webhook
              </Button>
            </div>
          </form>
        )}
      </Modal>
      <Modal open={open !== null} onClose={() => setOpen(null)} title="Webhook">
        {open && <HookDetail id={open} onDone={() => setOpen(null)} />}
      </Modal>
    </Card>
  );
}

function HookDetail({ id, onDone }: { id: string; onDone: () => void }) {
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: ["webhook", id],
    queryFn: () => api.get<Hook & { deliveries: Delivery[] }>(`/api/v1/integrations/webhooks/${id}`),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/integrations/webhooks/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["webhooks"] });
      onDone();
    },
  });
  if (!detail.data) return detail.error ? <ErrorText error={detail.error} /> : <Loading />;
  const d = detail.data;
  return (
    <div className="flex flex-col gap-4">
      <p className="break-all font-mono text-sm">{d.url}</p>
      {d.deliveries.length ? (
        <Table head={["Event", "When", "Result", "Tries"]}>
          {d.deliveries.map((x) => (
            <tr key={x.id}>
              <Td className="font-mono text-xs">{x.event}</Td>
              <Td>{formatDate(x.created_at)}</Td>
              <Td>
                {x.status}
                {x.response_code ? ` (${x.response_code})` : ""}
                {x.error && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">{x.error}</span>
                )}
              </Td>
              <Td className="tabular-nums">{x.attempts}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Nothing sent yet.</Empty>
      )}
      <ErrorText error={remove.error} />
      <div>
        <Button variant="danger" busy={remove.isPending} onClick={() => remove.mutate()}>
          Remove this webhook
        </Button>
      </div>
    </div>
  );
}

function Guide() {
  return (
    <Card title="For developers">
      <div className="flex flex-col gap-3 text-sm">
        <p>
          Read with the key in the Authorization header. Results are JSON, oldest first, up to 200 at a time.
        </p>
        <pre className="overflow-x-auto rounded-control bg-neutral-100 p-3 text-xs dark:bg-neutral-900">
          {`curl -H "Authorization: Bearer nxk_..." \\
  "https://api.nexedu.com.gh/api/v1/developer/students/?since=2026-09-01T00:00:00Z"`}
        </pre>
        <p>
          Addresses: <code>/developer/students/</code>, <code>/developer/classes/</code>,{" "}
          <code>/developer/attendance/?date=</code>, <code>/developer/invoices/</code>,{" "}
          <code>/developer/payments/?since=</code>. A key works only while the Developer API module is on.
        </p>
        <p>
          Each webhook request carries <code>X-NexEdu-Signature: t=…,v1=…</code>: the HMAC-SHA256 of{" "}
          <code>&lt;t&gt;.&lt;body&gt;</code> with your signing secret. Reply 2xx within 10 seconds; failed
          deliveries are tried again after 1, 5 and 30 minutes, then 2 and 6 hours.
        </p>
      </div>
    </Card>
  );
}
