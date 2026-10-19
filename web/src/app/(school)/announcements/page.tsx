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
import { type Announcement, api, type Level, type Paged } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useArms, useSchool } from "@/lib/hooks";
import { hasAny, isLeader } from "@/lib/roles";

const AUDIENCES: Record<string, string> = {
  everyone: "Everyone",
  staff: "All staff",
  parents: "All parents",
  students: "All students",
  level_parents: "Parents of one class level",
  arm_parents: "Parents of one class",
};

export default function AnnouncementsPage() {
  const { roles } = useSchool();
  const canSend = hasAny(roles, ["owner", "principal", "admin", "teacher", "form_teacher"]);
  const [creating, setCreating] = useState(false);
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["announcements"],
    queryFn: () => api.get<Paged<Announcement>>("/api/v1/communication/announcements?page_size=50"),
  });
  const publish = useMutation({
    mutationFn: (id: string) => api.post<Announcement>(`/api/v1/communication/announcements/${id}/publish`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["announcements"] }),
  });

  return (
    <>
      <PageHeader
        title="Announcements"
        actions={canSend && <Button onClick={() => setCreating(true)}>New announcement</Button>}
      />
      <ErrorText error={list.error ?? publish.error} />
      {publish.isSuccess && (
        <div className="mb-3">
          <Alert tone="success">Sent to {publish.data.recipient_count} recipient(s).</Alert>
        </div>
      )}
      {list.isPending ? (
        <Loading />
      ) : list.data?.results.length ? (
        <div className="flex flex-col gap-3">
          {list.data.results.map((a) => (
            <Card
              key={a.id}
              title={a.title}
              actions={
                a.status === "draft" ? (
                  <Button
                    busy={publish.isPending && publish.variables === a.id}
                    onClick={() => publish.mutate(a.id)}
                  >
                    Send now
                  </Button>
                ) : (
                  <Badge>{a.status}</Badge>
                )
              }
            >
              <p className="whitespace-pre-line text-sm">{a.body}</p>
              <p className="mt-2 text-xs text-neutral-500">
                {AUDIENCES[a.audience]}
                {a.channels.length > 0 && ` · also by ${a.channels.join(", ")}`} ·{" "}
                {formatDate(a.published_at ?? a.created_at)}
                {a.status === "published" && ` · ${a.recipient_count} recipients`}
              </p>
            </Card>
          ))}
        </div>
      ) : (
        <Empty>No announcements yet.</Empty>
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title="New announcement">
        <Compose leader={isLeader(roles)} onDone={() => setCreating(false)} />
      </Modal>
    </>
  );
}

function Compose({ leader, onDone }: { leader: boolean; onDone: () => void }) {
  const client = useQueryClient();
  const arms = useArms(!leader);
  const levels = useQuery({
    queryKey: ["levels"],
    queryFn: () => api.get<Level[]>("/api/v1/academics/levels"),
    enabled: leader,
  });
  const [audience, setAudience] = useState(leader ? "everyone" : "arm_parents");
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/communication/announcements", body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["announcements"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    create.mutate({
      title: form.get("title"),
      body: form.get("body"),
      audience,
      arm: audience === "arm_parents" ? form.get("arm") : null,
      level: audience === "level_parents" ? Number(form.get("level")) : null,
      channels: form.getAll("channels"),
    });
  };
  const options = leader ? Object.entries(AUDIENCES) : [["arm_parents", AUDIENCES.arm_parents]];
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Title">
        <Input name="title" required maxLength={140} />
      </Field>
      <Field label="Message">
        <Textarea name="body" required maxLength={5000} />
      </Field>
      <Field label="Send to">
        <Select value={audience} onChange={(e) => setAudience(e.target.value)}>
          {options.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      {audience === "arm_parents" && (
        <Field label="Class">
          <Select name="arm" required>
            {arms.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {audience === "level_parents" && (
        <Field label="Level">
          <Select name="level" required>
            {levels.data
              ?.filter((l) => l.is_active)
              .map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
          </Select>
        </Field>
      )}
      <fieldset className="flex flex-wrap gap-4 text-sm">
        <legend className="mb-1 font-medium">Also send by</legend>
        {[
          ["sms", "SMS"],
          ["whatsapp", "WhatsApp"],
          ["email", "Email"],
        ].map(([value, label]) => (
          <label key={value} className="flex items-center gap-2">
            <input type="checkbox" name="channels" value={value} /> {label}
          </label>
        ))}
      </fieldset>
      <p className="text-xs text-neutral-500">
        Everyone with a login also gets it in their Nex Edu inbox. SMS counts toward the school's monthly
        limit.
      </p>
      <ErrorText error={create.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={create.isPending}>
          Save draft
        </Button>
      </div>
    </form>
  );
}
