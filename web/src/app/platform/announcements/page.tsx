"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
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
  Select,
  Textarea,
} from "@/components/ui";
import { apiFetch, type Me, type PlatformAnnouncement, type Pricing } from "@/lib/api";
import { formatDate } from "@/lib/format";

const PATH = "/api/v1/platform/announcements";
const REGIONS: [string, string][] = [
  ["ahafo", "Ahafo"],
  ["ashanti", "Ashanti"],
  ["bono", "Bono"],
  ["bono_east", "Bono East"],
  ["central", "Central"],
  ["eastern", "Eastern"],
  ["greater_accra", "Greater Accra"],
  ["north_east", "North East"],
  ["northern", "Northern"],
  ["oti", "Oti"],
  ["savannah", "Savannah"],
  ["upper_east", "Upper East"],
  ["upper_west", "Upper West"],
  ["volta", "Volta"],
  ["western", "Western"],
  ["western_north", "Western North"],
];
const AUDIENCE: Record<PlatformAnnouncement["audience"], string> = {
  all: "Every proprietor",
  band: "One price band",
  region: "One region",
};

/** Updates from Nex Edu to school proprietors: shown on their dashboard, and emailed. */
export default function AnnouncementsPage() {
  const client = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }) });
  const canSend = Boolean(me.data?.platform_roles.includes("super_admin"));
  const list = useQuery({
    queryKey: ["platform", "announcements"],
    queryFn: () => apiFetch<PlatformAnnouncement[]>(PATH, { school: false }),
  });
  const [editing, setEditing] = useState<PlatformAnnouncement | "new" | null>(null);
  const [sending, setSending] = useState<PlatformAnnouncement | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: ["platform", "announcements"] });
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`${PATH}/${id}`, { method: "DELETE", school: false }),
    onSuccess: refresh,
  });

  return (
    <>
      <PageHeader
        title="Announcements"
        description="Tell proprietors about new features, maintenance and other news. They see it on their dashboard until they dismiss it."
        actions={canSend && <Button onClick={() => setEditing("new")}>New announcement</Button>}
      />
      <ErrorText error={remove.error} />
      {list.isPending ? (
        <Loading />
      ) : list.error ? (
        <ErrorText error={list.error} />
      ) : !list.data.length ? (
        <Empty>No announcements yet.</Empty>
      ) : (
        <div className="grid gap-3">
          {list.data.map((a) => (
            <Card key={a.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="font-medium">{a.title}</h2>
                  <p className="mt-1 line-clamp-3 text-sm whitespace-pre-line text-neutral-600 dark:text-neutral-300">
                    {a.body}
                  </p>
                  <p className="mt-2 text-xs text-neutral-500">
                    {AUDIENCE[a.audience]}
                    {a.audience === "region" &&
                      ` · ${REGIONS.find(([v]) => v === a.region)?.[1] ?? a.region}`}
                    {a.audience === "band" && ` · ${a.band_code.replace("band_", "Band ")}`}
                    {a.email ? " · also emailed" : ""} · by {a.created_by_email}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2 text-sm">
                  {a.status === "published" ? (
                    <>
                      <Badge tone="green">Sent {formatDate(a.published_at)}</Badge>
                      <span className="text-xs text-neutral-500 tabular-nums">
                        Read by {a.read_count} of {a.recipient_count}
                      </span>
                    </>
                  ) : (
                    <>
                      <Badge tone="grey">Draft</Badge>
                      {canSend && (
                        <div className="flex gap-1">
                          <Button variant="ghost" onClick={() => setEditing(a)}>
                            Edit
                          </Button>
                          <Button variant="ghost" onClick={() => remove.mutate(a.id)}>
                            Delete
                          </Button>
                          <Button onClick={() => setSending(a)}>Send</Button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New announcement" : "Edit announcement"}
      >
        {editing && (
          <Compose
            item={editing === "new" ? null : editing}
            onDone={() => {
              setEditing(null);
              refresh();
            }}
          />
        )}
      </Modal>
      <Modal open={Boolean(sending)} onClose={() => setSending(null)} title="Send this announcement?">
        {sending && (
          <ConfirmSend
            item={sending}
            onDone={() => {
              setSending(null);
              refresh();
            }}
          />
        )}
      </Modal>
    </>
  );
}

function Compose({ item, onDone }: { item: PlatformAnnouncement | null; onDone: () => void }) {
  const [audience, setAudience] = useState<PlatformAnnouncement["audience"]>(item?.audience ?? "all");
  const pricing = useQuery({
    queryKey: ["platform", "pricing"],
    queryFn: () => apiFetch<Pricing>("/api/v1/platform/billing/pricing", { school: false }),
    enabled: audience === "band",
    retry: false,
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch(item ? `${PATH}/${item.id}` : PATH, { method: item ? "PATCH" : "POST", school: false, body }),
    onSuccess: onDone,
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    save.mutate({
      title: f.title,
      body: f.body,
      audience,
      region: audience === "region" ? f.region : "",
      band_code: audience === "band" ? f.band_code : "",
      email: f.email === "on",
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-3">
      <Field label="Title">
        <Input name="title" required maxLength={140} defaultValue={item?.title} />
      </Field>
      <Field label="Message">
        <Textarea name="body" required rows={6} maxLength={5000} defaultValue={item?.body} />
      </Field>
      <Field label="Send to">
        <Select
          value={audience}
          onChange={(e) => setAudience(e.target.value as PlatformAnnouncement["audience"])}
        >
          <option value="all">Every proprietor</option>
          <option value="region">Proprietors in one region</option>
          <option value="band">Proprietors in one price band</option>
        </Select>
      </Field>
      {audience === "region" && (
        <Field label="Region">
          <Select name="region" required defaultValue={item?.region ?? ""}>
            <option value="" disabled>
              Choose a region
            </option>
            {REGIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {audience === "band" && (
        <Field label="Price band">
          <Select name="band_code" required defaultValue={item?.band_code ?? ""}>
            <option value="" disabled>
              Choose a band
            </option>
            {(pricing.data?.bands ?? []).map((b, i) => (
              <option key={b.code} value={b.code}>
                Band {i + 1}: {b.label}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="email"
          defaultChecked={item?.email ?? true}
          className="size-4 accent-brand"
        />
        Also email it to them
      </label>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save draft
        </Button>
      </div>
    </form>
  );
}

function ConfirmSend({ item, onDone }: { item: PlatformAnnouncement; onDone: () => void }) {
  const send = useMutation({
    mutationFn: () => apiFetch(`${PATH}/${item.id}/publish`, { method: "POST", school: false }),
    onSuccess: onDone,
  });
  return (
    <div className="grid gap-3">
      <p className="text-sm">
        <span className="font-medium">{item.title}</span> goes to {AUDIENCE[item.audience].toLowerCase()}
        {item.email ? " on their dashboard and by email" : " on their dashboard"}. It can't be changed once
        sent.
      </p>
      <Alert tone="info">Only proprietors of active schools receive it.</Alert>
      <ErrorText error={send.error} />
      <div className="flex justify-end">
        <Button busy={send.isPending} onClick={() => send.mutate()}>
          Send now
        </Button>
      </div>
    </div>
  );
}
