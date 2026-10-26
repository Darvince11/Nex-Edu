"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Evidence = { id: string; name: string; size: number; uploaded_at: string };
type Item = {
  id: string;
  area: string;
  area_label: string;
  title: string;
  authority: string;
  notes: string;
  due_on: string | null;
  renew_every_months: number | null;
  status: "open" | "done";
  completed_on: string | null;
  state: "open" | "done" | "due_soon" | "overdue";
  evidence: Evidence[];
};

const AREAS: [string, string][] = [
  ["licence", "Licence and registration"],
  ["safety", "Safety and premises"],
  ["staff", "Staff"],
  ["health", "Health and food"],
  ["safeguarding", "Child protection"],
  ["data", "Data protection"],
  ["finance", "Tax and statutory payments"],
  ["other", "Other"],
];
const STATE: Record<Item["state"], { label: string; tone: "green" | "amber" | "red" | "grey" }> = {
  done: { label: "Done", tone: "green" },
  open: { label: "To do", tone: "grey" },
  due_soon: { label: "Due soon", tone: "amber" },
  overdue: { label: "Overdue", tone: "red" },
};

/** Licences, certificates and inspections the school must keep up, with the evidence. */
export default function CompliancePage() {
  const client = useQueryClient();
  const [open, setOpen] = useState<string | "new" | null>(null);
  const items = useQuery({
    queryKey: ["compliance"],
    queryFn: () => api.get<Item[]>("/api/v1/compliance/items"),
  });
  const starter = useMutation({
    mutationFn: () => api.post<{ added: number }>("/api/v1/compliance/items/starter", {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["compliance"] }),
  });
  const count = (state: Item["state"]) => items.data?.filter((i) => i.state === state).length ?? 0;
  const current = items.data?.find((i) => i.id === open) ?? null;
  return (
    <>
      <PageHeader
        title="Compliance"
        description="Licences, certificates and inspections, with the evidence. You're reminded 30 days before anything is due."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" busy={starter.isPending} onClick={() => starter.mutate()}>
              Add the usual checklist
            </Button>
            <Button onClick={() => setOpen("new")}>Add an item</Button>
          </div>
        }
      />
      {starter.data && (
        <Alert tone="success">
          {starter.data.added
            ? `${starter.data.added} items added. Fill in the due dates from your certificates.`
            : "You already have every item on the usual checklist."}
        </Alert>
      )}
      <ErrorText error={items.error ?? starter.error} />
      {items.data && items.data.length > 0 && (
        <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Overdue" value={count("overdue")} />
          <Stat label="Due in 30 days" value={count("due_soon")} />
          <Stat label="To do" value={count("open")} />
          <Stat label="Done" value={count("done")} />
        </div>
      )}
      {items.isPending ? (
        <Loading />
      ) : items.data?.length ? (
        <Table head={["Item", "Area", "Due", "Evidence", "Status", ""]}>
          {items.data.map((i) => (
            <tr key={i.id}>
              <Td>
                <span className="font-medium">{i.title}</span>
                {i.authority && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">{i.authority}</span>
                )}
              </Td>
              <Td>{i.area_label}</Td>
              <Td>
                {i.due_on ? formatDate(i.due_on) : "—"}
                {i.renew_every_months && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    Renews every {i.renew_every_months} month{i.renew_every_months === 1 ? "" : "s"}
                  </span>
                )}
              </Td>
              <Td>{i.evidence.length || "—"}</Td>
              <Td>
                <Badge tone={STATE[i.state].tone}>{STATE[i.state].label}</Badge>
              </Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(i.id)} aria-label={`Open ${i.title}`}>
                  Open
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Nothing on the checklist yet. Start with the usual checklist for a basic school.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "Add an item" : (current?.title ?? "Item")}
      >
        {open === "new" && <ItemForm item={null} onDone={() => setOpen(null)} />}
        {current && <ItemDetail item={current} onDone={() => setOpen(null)} />}
      </Modal>
    </>
  );
}

function ItemForm({ item, onDone }: { item: Item | null; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      item
        ? api.patch(`/api/v1/compliance/items/${item.id}`, body)
        : api.post("/api/v1/compliance/items", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["compliance"] });
      if (!item) onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          title: f.title,
          area: f.area,
          authority: f.authority,
          due_on: f.due_on || null,
          renew_every_months: f.renew ? Number(f.renew) : null,
          notes: f.notes,
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="What">
          <Input name="title" required maxLength={150} defaultValue={item?.title} />
        </Field>
        <Field label="Area">
          <Select name="area" defaultValue={item?.area ?? "other"}>
            {AREAS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Issued or inspected by">
          <Input name="authority" maxLength={120} defaultValue={item?.authority} />
        </Field>
        <Field label="Due on" hint="The deadline or the next renewal">
          <Input name="due_on" type="date" defaultValue={item?.due_on ?? ""} />
        </Field>
        <Field label="Renews every (months)" hint="Leave empty if it doesn't renew">
          <Input name="renew" type="number" min={1} max={120} defaultValue={item?.renew_every_months ?? ""} />
        </Field>
      </div>
      <Field label="Notes">
        <Textarea name="notes" rows={2} maxLength={2000} defaultValue={item?.notes} />
      </Field>
      <ErrorText error={save.error} />
      {item && save.isSuccess && <Alert tone="success">Saved.</Alert>}
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function ItemDetail({ item, onDone }: { item: Item; onDone: () => void }) {
  const client = useQueryClient();
  const refresh = () => void client.invalidateQueries({ queryKey: ["compliance"] });
  const complete = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/compliance/items/${item.id}/${item.status === "done" ? "reopen" : "complete"}`, {}),
    onSuccess: refresh,
  });
  const upload = useMutation({
    mutationFn: (form: FormData) => api.post(`/api/v1/compliance/items/${item.id}/upload`, form),
    onSuccess: refresh,
  });
  const removeFile = useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/compliance/items/${item.id}/evidence/${id}/remove`),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/compliance/items/${item.id}`),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={STATE[item.state].tone}>{STATE[item.state].label}</Badge>
        {item.completed_on && (
          <span className="text-sm text-neutral-600 dark:text-neutral-300">
            Last done {formatDate(item.completed_on)}
          </span>
        )}
        <div className="ml-auto">
          <Button
            variant={item.status === "done" ? "secondary" : "primary"}
            busy={complete.isPending}
            onClick={() => complete.mutate()}
          >
            {item.status === "done" ? "Reopen" : item.renew_every_months ? "Mark renewed" : "Mark done"}
          </Button>
        </div>
      </div>
      <ErrorText error={complete.error} />
      {/* Fresh form after "Mark done/renewed" (new due date), not after its own Save. */}
      <ItemForm key={`${item.status}-${item.completed_on}`} item={item} onDone={onDone} />
      <section
        aria-labelledby="evidence-title"
        className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
      >
        <h3 id="evidence-title" className="mb-2 font-medium">
          Evidence
        </h3>
        {item.evidence.length ? (
          <ul className="mb-3 flex flex-col gap-1 text-sm">
            {item.evidence.map((ev) => (
              <li key={ev.id} className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="text-link hover:underline"
                  onClick={() =>
                    void download(`/api/v1/compliance/items/${item.id}/evidence/${ev.id}`, ev.name)
                  }
                >
                  {ev.name}
                </button>
                <span className="text-xs text-neutral-600 dark:text-neutral-400">
                  {formatDate(ev.uploaded_at)}
                </span>
                <Button
                  variant="ghost"
                  busy={removeFile.isPending && removeFile.variables === ev.id}
                  onClick={() => removeFile.mutate(ev.id)}
                  aria-label={`Remove ${ev.name}`}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
            No evidence yet. Add a scan or photo of the certificate.
          </p>
        )}
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            upload.mutate(new FormData(form), { onSuccess: () => form.reset() });
          }}
        >
          <Field label="Add a file" hint="PDF, Word, picture: 5 MB at most.">
            <Input name="file" type="file" required />
          </Field>
          <Button type="submit" variant="secondary" busy={upload.isPending}>
            Upload
          </Button>
        </form>
        <ErrorText error={upload.error ?? removeFile.error} />
      </section>
      <div>
        <Button variant="ghost" busy={remove.isPending} onClick={() => remove.mutate()}>
          Delete this item
        </Button>
        <ErrorText error={remove.error} />
      </div>
    </div>
  );
}
