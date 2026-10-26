"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
} from "@/components/ui";
import { api, download } from "@/lib/api";
import { cedis, formatDate, todayInAccra, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";

type Person = {
  id: string;
  first_name: string;
  last_name: string;
  class_of: number;
  phone: string;
  email: string;
  occupation: string;
  lives_in: string;
  may_contact: boolean;
  consent_recorded_at: string | null;
  notes: string;
  given_pesewas: number | null;
};
type Gift = {
  id: string;
  alumnus: string | null;
  alumnus_name: string;
  donor: string;
  amount_pesewas: number;
  kind: "pledge" | "received";
  date: string;
  purpose: string;
  in_books: boolean;
};
type Summary = {
  received_pesewas: number;
  pledged_pesewas: number;
  alumni: number;
  may_contact: number;
  by_purpose: { purpose: string; total_pesewas: number; gifts: number }[];
};
type Tab = "people" | "gifts";

/** Past pupils who keep in touch, and what old pupils and friends give the school. */
export default function AlumniPage() {
  const [tab, setTab] = useState<Tab>("people");
  return (
    <>
      <PageHeader
        title="Alumni"
        description="Past pupils, who to contact (only those who agreed), and gifts and pledges."
      />
      <div
        role="tablist"
        aria-label="Alumni"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["people", "Past pupils"],
            ["gifts", "Gifts and pledges"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === key ? "border-brand font-medium" : "border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">{tab === "people" ? <People /> : <Gifts />}</div>
    </>
  );
}

function People() {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Person | "new" | null>(null);
  const people = useQuery({
    queryKey: ["alumni", q],
    queryFn: () => api.get<Person[]>(`/api/v1/alumni/people?q=${encodeURIComponent(q.trim())}`),
    placeholderData: keepPreviousData,
  });
  const imported = useMutation({
    mutationFn: () => api.post<{ added: number }>("/api/v1/alumni/people/import_graduates", {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["alumni"] }),
  });
  const [exporting, setExporting] = useState(false);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Field label="Search">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or work" />
          </Field>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button variant="secondary" busy={imported.isPending} onClick={() => imported.mutate()}>
            Add this year's graduates
          </Button>
          <Button
            variant="secondary"
            busy={exporting}
            onClick={() => {
              setExporting(true);
              void download("/api/v1/alumni/people/mailing_list", "alumni-mailing-list.csv").finally(() =>
                setExporting(false),
              );
            }}
          >
            Mailing list (CSV)
          </Button>
          <Button onClick={() => setOpen("new")}>Add a past pupil</Button>
        </div>
      </div>
      {imported.data && (
        <Alert tone="success">
          {imported.data.added
            ? `${imported.data.added} graduate${imported.data.added === 1 ? "" : "s"} added. Ask each one before contacting them.`
            : "Every graduate is already on the list."}
        </Alert>
      )}
      <ErrorText error={people.error ?? imported.error} />
      {people.isPending ? (
        <Loading />
      ) : people.data?.length ? (
        <Table head={["Name", "Class of", "Work and town", "Contact", "Given", ""]}>
          {people.data.map((p) => (
            <tr key={p.id}>
              <Td className="font-medium">
                {p.first_name} {p.last_name}
              </Td>
              <Td>{p.class_of}</Td>
              <Td>{[p.occupation, p.lives_in].filter(Boolean).join(", ") || "—"}</Td>
              <Td>
                {p.may_contact ? (
                  <Badge tone="green">Agreed</Badge>
                ) : (
                  <Badge tone="grey">Not asked or declined</Badge>
                )}
              </Td>
              <Td className="tabular-nums">{p.given_pesewas ? cedis(p.given_pesewas) : "—"}</Td>
              <Td className="text-right">
                <Button
                  variant="ghost"
                  onClick={() => setOpen(p)}
                  aria-label={`Edit ${p.first_name} ${p.last_name}`}
                >
                  Edit
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No past pupils yet. Add this year's graduates, or add old pupils one by one.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "Add a past pupil" : "Past pupil"}
      >
        {open !== null && <PersonForm person={open === "new" ? null : open} onDone={() => setOpen(null)} />}
      </Modal>
    </>
  );
}

function PersonForm({ person, onDone }: { person: Person | null; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      person
        ? api.patch(`/api/v1/alumni/people/${person.id}`, body)
        : api.post("/api/v1/alumni/people", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["alumni"] });
      onDone();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/alumni/people/${person?.id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["alumni"] });
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          first_name: f.first_name,
          last_name: f.last_name,
          class_of: Number(f.class_of),
          phone: f.phone,
          email: f.email,
          occupation: f.occupation,
          lives_in: f.lives_in,
          notes: f.notes,
          may_contact: f.may_contact === "on",
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="First name">
          <Input name="first_name" required maxLength={80} defaultValue={person?.first_name} />
        </Field>
        <Field label="Last name">
          <Input name="last_name" required maxLength={80} defaultValue={person?.last_name} />
        </Field>
        <Field label="Class of" hint="The year they left">
          <Input
            name="class_of"
            type="number"
            required
            min={1950}
            max={2100}
            defaultValue={person?.class_of ?? Number(todayInAccra().slice(0, 4))}
          />
        </Field>
        <Field label="Phone">
          <Input name="phone" type="tel" maxLength={20} defaultValue={person?.phone} />
        </Field>
        <Field label="Email">
          <Input name="email" type="email" defaultValue={person?.email} />
        </Field>
        <Field label="Work">
          <Input name="occupation" maxLength={120} defaultValue={person?.occupation} />
        </Field>
        <Field label="Lives in">
          <Input name="lives_in" maxLength={120} defaultValue={person?.lives_in} />
        </Field>
        <Field label="Notes">
          <Input name="notes" maxLength={300} defaultValue={person?.notes} />
        </Field>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          name="may_contact"
          defaultChecked={person?.may_contact ?? false}
          className="mt-0.5 size-4 accent-brand"
        />
        <span>
          They agreed to hear from the school
          {person?.consent_recorded_at && (
            <span className="block text-xs text-neutral-600 dark:text-neutral-400">
              Recorded {formatDate(person.consent_recorded_at)}
            </span>
          )}
        </span>
      </label>
      <ErrorText error={save.error ?? remove.error} />
      <div className="flex justify-between gap-2">
        {person ? (
          <Button type="button" variant="ghost" busy={remove.isPending} onClick={() => remove.mutate()}>
            Remove from the list
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function Gifts() {
  const client = useQueryClient();
  const { hasModule } = useSchool();
  const [adding, setAdding] = useState(false);
  const gifts = useQuery({ queryKey: ["gifts"], queryFn: () => api.get<Gift[]>("/api/v1/alumni/gifts") });
  const summary = useQuery({
    queryKey: ["gifts", "summary"],
    queryFn: () => api.get<Summary>("/api/v1/alumni/gifts/summary"),
  });
  const received = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/alumni/gifts/${id}/received`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["gifts"] });
      void client.invalidateQueries({ queryKey: ["alumni"] });
    },
  });
  return (
    <>
      {summary.data && (
        <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Received" value={cedis(summary.data.received_pesewas)} />
          <Stat label="Still pledged" value={cedis(summary.data.pledged_pesewas)} />
          <Stat label="Past pupils" value={summary.data.alumni} />
          <Stat label="Agreed to contact" value={summary.data.may_contact} />
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          {hasModule("accounting")
            ? "Money received goes into the books as donation income."
            : "Switch on Accounting to put money received into the books."}
        </p>
        <div className="ml-auto">
          <Button onClick={() => setAdding(true)}>Record a gift</Button>
        </div>
      </div>
      <ErrorText error={gifts.error ?? summary.error ?? received.error} />
      {gifts.isPending ? (
        <Loading />
      ) : gifts.data?.length ? (
        <Table head={["Date", "From", "For", "Amount", "Status", ""]}>
          {gifts.data.map((g) => (
            <tr key={g.id}>
              <Td>{formatDate(g.date)}</Td>
              <Td className="font-medium">{g.donor}</Td>
              <Td>{g.purpose || "General"}</Td>
              <Td className="tabular-nums">{cedis(g.amount_pesewas)}</Td>
              <Td>
                {g.kind === "pledge" ? (
                  <Badge tone="amber">Pledged</Badge>
                ) : (
                  <Badge tone="green">{g.in_books ? "Received, in the books" : "Received"}</Badge>
                )}
              </Td>
              <Td className="text-right">
                {g.kind === "pledge" && (
                  <Button
                    variant="ghost"
                    busy={received.isPending && received.variables === g.id}
                    onClick={() => received.mutate(g.id)}
                    aria-label={`Mark the pledge from ${g.donor} as paid`}
                  >
                    Mark paid
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No gifts recorded yet.</Empty>
      )}
      <Modal open={adding} onClose={() => setAdding(false)} title="Record a gift">
        {adding && <GiftForm onDone={() => setAdding(false)} />}
      </Modal>
    </>
  );
}

function GiftForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const people = useQuery({
    queryKey: ["alumni", ""],
    queryFn: () => api.get<Person[]>("/api/v1/alumni/people?q="),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/alumni/gifts", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["gifts"] });
      void client.invalidateQueries({ queryKey: ["alumni"] });
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          alumnus: f.alumnus || null,
          donor: f.donor,
          amount_pesewas: toPesewas(f.amount ?? ""),
          kind: f.kind,
          date: f.date,
          purpose: f.purpose,
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Past pupil (optional)">
          <Select name="alumnus" defaultValue="">
            <option value="">Not a past pupil</option>
            {people.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.first_name} {p.last_name} ({p.class_of})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="From" hint="Leave blank to use the past pupil's name">
          <Input name="donor" maxLength={120} placeholder="e.g. Class of 2010" />
        </Field>
        <Field label="Amount (GH₵)">
          <Input name="amount" required inputMode="decimal" pattern="[0-9]+(\.[0-9]{1,2})?" />
        </Field>
        <Field label="Status">
          <Select name="kind" defaultValue="received">
            <option value="received">Received</option>
            <option value="pledge">Pledged, not yet paid</option>
          </Select>
        </Field>
        <Field label="Date">
          <Input name="date" type="date" required defaultValue={todayInAccra()} />
        </Field>
        <Field label="For">
          <Input name="purpose" maxLength={200} placeholder="e.g. New library roof" />
        </Field>
      </div>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save gift
        </Button>
      </div>
    </form>
  );
}
