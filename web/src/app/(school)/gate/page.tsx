"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  PageHeader,
  Select,
  Table,
  Td,
} from "@/components/ui";
import { api, type Paged, type Student } from "@/lib/api";
import { formatDate, todayInAccra } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Visit = {
  id: string;
  name: string;
  phone: string;
  organisation: string;
  purpose: string;
  to_see: string;
  badge: string;
  arrived_at: string;
  left_at: string | null;
};
type Collector = {
  id: string;
  student: string;
  name: string;
  relationship: string;
  phone: string;
  notes: string;
};
type CheckRow = {
  student: string;
  name: string;
  class: string;
  admission_number: string;
  collected_today: boolean;
  collectors: Collector[];
};
type Pickup = {
  id: string;
  student: string;
  student_name: string;
  collected_by_name: string;
  authorised: boolean;
  reason: string;
  at: string;
};

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

/** The gate: visitors in and out, and who collects each pupil. Families keep their list. */
export default function GatePage() {
  const { can } = useSchool();
  return can(PERM.GATE_RECORD) ? <Guard /> : <Family />;
}

function Family() {
  const client = useQueryClient();
  const children = useQuery({
    queryKey: ["students", "mine"],
    queryFn: () => api.get<Paged<Student>>("/api/v1/students?page_size=20"),
  });
  const collectors = useQuery({
    queryKey: ["collectors"],
    queryFn: () => api.get<Collector[]>("/api/v1/gate/collectors"),
  });
  const pickups = useQuery({
    queryKey: ["pickups"],
    queryFn: () => api.get<Pickup[]>("/api/v1/gate/pickups"),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["collectors"] });
  const add = useMutation({
    mutationFn: (body: Record<string, string>) => api.post("/api/v1/gate/collectors", body),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/gate/collectors/${id}`),
    onSuccess: refresh,
  });
  const kids = children.data?.results ?? [];
  return (
    <>
      <PageHeader title="Pick-up" description="Who may collect your children from school, and who did." />
      <ErrorText error={collectors.error ?? add.error ?? remove.error} />
      <div className="grid gap-4 lg:grid-cols-2">
        {kids.map((kid) => {
          const list = collectors.data?.filter((c) => c.student === kid.id) ?? [];
          return (
            <Card key={kid.id} title={`${kid.first_name} may be collected by`}>
              {list.length ? (
                <ul className="mb-3 divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
                  {list.map((c) => (
                    <li key={c.id} className="flex items-center justify-between gap-2 py-1.5">
                      <span>
                        <span className="font-medium">{c.name}</span> · {c.relationship}
                        {c.phone && (
                          <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                            {c.phone}
                          </span>
                        )}
                      </span>
                      <Button
                        variant="ghost"
                        onClick={() => remove.mutate(c.id)}
                        aria-label={`Remove ${c.name}`}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
                  Nobody yet. The gate will ask the office before letting anyone take {kid.first_name}.
                </p>
              )}
              <form
                className="grid gap-2 sm:grid-cols-3 sm:items-end"
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
                  add.mutate(
                    {
                      student: kid.id,
                      name: f.name ?? "",
                      relationship: f.relationship ?? "",
                      phone: f.phone ?? "",
                    },
                    { onSuccess: () => form.reset() },
                  );
                }}
              >
                <Field label="Name">
                  <Input name="name" required maxLength={120} />
                </Field>
                <Field label="Relationship">
                  <Input name="relationship" required maxLength={40} placeholder="Aunt, driver…" />
                </Field>
                <Field label="Phone (optional)">
                  <Input name="phone" maxLength={20} />
                </Field>
                <div className="flex justify-end sm:col-span-3">
                  <Button type="submit" variant="secondary" busy={add.isPending}>
                    Add person
                  </Button>
                </div>
              </form>
            </Card>
          );
        })}
      </div>
      <section aria-labelledby="pickups-title" className="mt-6">
        <h2 id="pickups-title" className="mb-2 font-medium">
          Recent pick-ups
        </h2>
        {pickups.data?.length ? (
          <Table head={["When", "Child", "Collected by"]}>
            {pickups.data.map((p) => (
              <tr key={p.id}>
                <Td className="whitespace-nowrap">
                  {formatDate(p.at)}, {time(p.at)}
                </Td>
                <Td>{p.student_name}</Td>
                <Td>
                  {p.collected_by_name} {!p.authorised && <Badge tone="amber">Not on your list</Badge>}
                  {p.reason && (
                    <span className="block text-xs text-neutral-600 dark:text-neutral-400">{p.reason}</span>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No pick-ups recorded yet.</Empty>
        )}
      </section>
    </>
  );
}

function Guard() {
  return (
    <>
      <PageHeader title="Gate" description="Sign visitors in and out, and check who collects each pupil." />
      <div className="grid gap-4 lg:grid-cols-2">
        <PickupDesk />
        <Visitors />
      </div>
      <TodaysPickups />
    </>
  );
}

function PickupDesk() {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [chosen, setChosen] = useState<CheckRow | null>(null);
  const [who, setWho] = useState("");
  const [done, setDone] = useState<Pickup | null>(null);
  const found = useQuery({
    queryKey: ["gate-check", q],
    queryFn: () => api.get<CheckRow[]>(`/api/v1/gate/check?q=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2,
  });
  const record = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Pickup>("/api/v1/gate/pickups", body),
    onSuccess: (p) => {
      setDone(p);
      setChosen(null);
      setWho("");
      setQ("");
      void client.invalidateQueries({ queryKey: ["pickups"] });
    },
  });
  return (
    <Card title="Pick-up check">
      <Field label="Pupil" hint="Name or admission number.">
        <Input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setChosen(null);
          }}
          autoComplete="off"
        />
      </Field>
      {!chosen && found.data && found.data.length > 0 && (
        <ul
          aria-label="Matching pupils"
          className="mt-2 divide-y divide-neutral-100 text-sm dark:divide-neutral-800"
        >
          {found.data.map((r) => (
            <li key={r.student}>
              <button
                type="button"
                className="flex w-full justify-between gap-2 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800"
                onClick={() => setChosen(r)}
              >
                <span>
                  <span className="font-medium">{r.name}</span>
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {r.class} · {r.admission_number}
                  </span>
                </span>
                {r.collected_today && <Badge tone="grey">Collected today</Badge>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {chosen && (
        <form
          className="mt-3 flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
            record.mutate(
              who === "other"
                ? { student: chosen.student, collected_by_name: f.name, reason: f.reason }
                : { student: chosen.student, collector: who },
            );
          }}
        >
          <p className="text-sm font-medium">{chosen.name}</p>
          <Field label="Who is collecting?">
            <Select value={who} onChange={(e) => setWho(e.target.value)} required>
              <option value="" disabled>
                Choose
              </option>
              {chosen.collectors.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.relationship})
                </option>
              ))}
              <option value="other">Someone not on the list</option>
            </Select>
          </Field>
          {chosen.collectors.length === 0 && (
            <Alert tone="warning">The family hasn't listed anyone. Check with the office first.</Alert>
          )}
          {who === "other" && (
            <>
              <Alert tone="warning">Not on the family's list. The parents will be told.</Alert>
              <Field label="Their name">
                <Input name="name" required maxLength={120} />
              </Field>
              <Field label="Why they may take the pupil">
                <Input name="reason" required maxLength={200} placeholder="e.g. Mother phoned the office" />
              </Field>
            </>
          )}
          <ErrorText error={record.error} />
          <div className="flex justify-end">
            <Button type="submit" busy={record.isPending} disabled={!who}>
              Record pick-up
            </Button>
          </div>
        </form>
      )}
      {done && !chosen && (
        <div className="mt-3">
          <Alert tone="success">
            {done.student_name} left with {done.collected_by_name} at {time(done.at)}. The parents have been
            told.
          </Alert>
        </div>
      )}
    </Card>
  );
}

function Visitors() {
  const client = useQueryClient();
  const onSite = useQuery({
    queryKey: ["gate-visits", "now"],
    queryFn: () => api.get<Visit[]>("/api/v1/gate/visits?now=1"),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["gate-visits"] });
  const signIn = useMutation({
    mutationFn: (body: Record<string, string>) => api.post("/api/v1/gate/visits", body),
    onSuccess: refresh,
  });
  const signOut = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/gate/visits/${id}/sign_out`),
    onSuccess: refresh,
  });
  return (
    <Card title="Visitors">
      <form
        className="grid gap-2 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          signIn.mutate(Object.fromEntries(new FormData(form)) as Record<string, string>, {
            onSuccess: () => form.reset(),
          });
        }}
      >
        <Field label="Visitor's name">
          <Input name="name" required maxLength={120} />
        </Field>
        <Field label="Phone (optional)">
          <Input name="phone" maxLength={20} />
        </Field>
        <Field label="Here to">
          <Input name="purpose" required maxLength={200} />
        </Field>
        <Field label="To see (optional)">
          <Input name="to_see" maxLength={120} />
        </Field>
        <Field label="ID number (optional)" hint="Kept encrypted.">
          <Input name="id_number" maxLength={40} />
        </Field>
        <Field label="Badge (optional)">
          <Input name="badge" maxLength={20} />
        </Field>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" variant="secondary" busy={signIn.isPending}>
            Sign in
          </Button>
        </div>
      </form>
      <ErrorText error={signIn.error ?? signOut.error ?? onSite.error} />
      <h3 className="mt-4 mb-1 text-sm font-medium">On site now</h3>
      {onSite.data?.length ? (
        <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
          {onSite.data.map((v) => (
            <li key={v.id} className="flex items-center justify-between gap-2 py-1.5">
              <span>
                <span className="font-medium">{v.name}</span> since {time(v.arrived_at)}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {v.purpose}
                  {v.to_see ? ` · to see ${v.to_see}` : ""}
                  {v.badge ? ` · badge ${v.badge}` : ""}
                </span>
              </span>
              <Button variant="ghost" onClick={() => signOut.mutate(v.id)} aria-label={`Sign out ${v.name}`}>
                Sign out
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">No visitors on site.</p>
      )}
    </Card>
  );
}

function TodaysPickups() {
  const [day, setDay] = useState(todayInAccra());
  const pickups = useQuery({
    queryKey: ["pickups", day],
    queryFn: () => api.get<Pickup[]>(`/api/v1/gate/pickups?date=${day}`),
    placeholderData: keepPreviousData,
  });
  return (
    <section aria-labelledby="day-pickups" className="mt-6">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-3">
        <h2 id="day-pickups" className="font-medium">
          Pick-ups on {formatDate(day)}
        </h2>
        <div className="w-44">
          <Field label="Day">
            <Input
              type="date"
              value={day}
              max={todayInAccra()}
              onChange={(e) => setDay(e.target.value || todayInAccra())}
            />
          </Field>
        </div>
      </div>
      {pickups.isPending ? (
        <Loading />
      ) : pickups.data?.length ? (
        <Table head={["Time", "Pupil", "Collected by"]}>
          {pickups.data.map((p) => (
            <tr key={p.id}>
              <Td className="tabular-nums">{time(p.at)}</Td>
              <Td className="font-medium">{p.student_name}</Td>
              <Td>
                {p.collected_by_name} {!p.authorised && <Badge tone="amber">Not on the list</Badge>}
                {p.reason && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">{p.reason}</span>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No pick-ups recorded.</Empty>
      )}
    </section>
  );
}
