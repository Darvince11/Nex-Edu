"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { type Activity, type Club, ClubForm } from "@/components/clubs";
import {
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
  Table,
  Td,
} from "@/components/ui";
import { api, type Paged, type StaffMember, type Student } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Detail = Club & {
  upcoming: Activity[];
  past: Activity[];
  members?: { student: string; name: string; class: string; title: string; joined_on: string }[];
  can_run?: boolean;
};

const ACTIVITY_KINDS: [string, string][] = [
  ["meeting", "Meeting"],
  ["practice", "Practice"],
  ["match", "Match or competition"],
  ["outing", "Trip or outing"],
  ["event", "Event or performance"],
];

/** One club: what's coming up, results, members and patrons. */
export default function ClubPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSchool();
  const manage = can(PERM.CLUBS_MANAGE);
  const [editing, setEditing] = useState(false);
  const club = useQuery({ queryKey: ["club", id], queryFn: () => api.get<Detail>(`/api/v1/clubs/${id}`) });

  if (club.isPending) return <Loading />;
  if (club.error) return <ErrorText error={club.error} />;
  const c = club.data;
  return (
    <>
      <PageHeader
        title={c.name}
        description={[c.kind_label, c.meets].filter(Boolean).join(" · ")}
        actions={
          manage && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Change details
            </Button>
          )
        }
      />
      <p className="mb-4 text-sm">
        <Link href="/clubs" className="text-brand-strong hover:underline dark:text-brand-sky">
          ← All clubs
        </Link>
      </p>
      {c.description && <p className="mb-4 max-w-prose text-sm">{c.description}</p>}
      {c.my_children.length > 0 && (
        <p className="mb-4 text-sm">
          <Badge tone="green">{`${c.my_children.join(" and ")} ${c.my_children.length > 1 ? "are members" : "is a member"}`}</Badge>
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Activities club={c} />
        {c.members && <Members club={c} />}
        <Patrons club={c} manage={manage} />
      </div>
      <Modal open={editing} onClose={() => setEditing(false)} title="Change club details">
        {editing && <ClubForm club={c} onDone={() => setEditing(false)} />}
      </Modal>
    </>
  );
}

function Activities({ club }: { club: Detail }) {
  const client = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [scoring, setScoring] = useState<Activity | null>(null);
  const refresh = () => void client.invalidateQueries({ queryKey: ["club", club.id] });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post(`/api/v1/clubs/${club.id}/add_activity`, body),
    onSuccess: () => {
      setAdding(false);
      refresh();
    },
  });
  const result = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) =>
      api.patch(`/api/v1/clubs/activities/${id}`, { result: value }),
    onSuccess: () => {
      setScoring(null);
      refresh();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    add.mutate({
      title: f.title,
      kind: f.kind,
      date: f.date,
      starts_at: f.starts_at || null,
      venue: f.venue,
      opponent: f.opponent,
    });
  };
  const row = (a: Activity) => (
    <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
      <span>
        <span className="font-medium">{a.title}</span>
        {a.opponent ? ` vs ${a.opponent}` : ""}
        <span className="block text-neutral-600 dark:text-neutral-300">
          {a.kind_label} · {formatDate(a.date)}
          {a.starts_at ? `, ${a.starts_at.slice(0, 5)}` : ""}
          {a.venue ? ` · ${a.venue}` : ""}
        </span>
      </span>
      <span className="flex items-center gap-2">
        {a.result && <Badge tone="blue">{a.result}</Badge>}
        {club.can_run && a.kind === "match" && (
          <Button variant="ghost" onClick={() => setScoring(a)}>
            {a.result ? "Change result" : "Add result"}
          </Button>
        )}
      </span>
    </li>
  );
  return (
    <Card
      title="Coming up"
      actions={
        club.can_run && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Add
          </Button>
        )
      }
    >
      {club.upcoming.length ? (
        <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">{club.upcoming.map(row)}</ul>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">Nothing planned yet.</p>
      )}
      {club.past.length > 0 && (
        <>
          <h3 className="mt-4 mb-1 text-sm font-medium">Earlier</h3>
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">{club.past.map(row)}</ul>
        </>
      )}
      <Modal open={adding} onClose={() => setAdding(false)} title="Add to the club's calendar">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="What">
              <Input name="title" required maxLength={120} />
            </Field>
          </div>
          <Field label="Kind">
            <Select name="kind" defaultValue="meeting">
              {ACTIVITY_KINDS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Date">
            <Input name="date" type="date" required />
          </Field>
          <Field label="Time (optional)">
            <Input name="starts_at" type="time" />
          </Field>
          <Field label="Where (optional)">
            <Input name="venue" maxLength={120} />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Against (matches only)">
              <Input name="opponent" maxLength={120} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <ErrorText error={add.error} />
          </div>
          <div className="flex justify-end sm:col-span-2">
            <Button type="submit" busy={add.isPending}>
              Add
            </Button>
          </div>
        </form>
      </Modal>
      <Modal open={scoring !== null} onClose={() => setScoring(null)} title="Result">
        {scoring && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const value = String(new FormData(e.currentTarget).get("result") ?? "");
              result.mutate({ id: scoring.id, value });
            }}
            className="flex flex-col gap-3"
          >
            <Field
              label={`${scoring.title}${scoring.opponent ? ` vs ${scoring.opponent}` : ""}`}
              hint='For example "Won 2-1".'
            >
              <Input name="result" maxLength={120} defaultValue={scoring.result} required />
            </Field>
            <ErrorText error={result.error} />
            <div className="flex justify-end">
              <Button type="submit" busy={result.isPending}>
                Save result
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </Card>
  );
}

function Members({ club }: { club: Detail }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [student, setStudent] = useState("");
  const [title, setTitle] = useState("");
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["club", club.id] });
    void client.invalidateQueries({ queryKey: ["clubs"] });
  };
  const pupils = useQuery({
    queryKey: ["students", "club-search", q],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?page_size=20&q=${encodeURIComponent(q.trim())}`),
    enabled: Boolean(club.can_run) && q.trim().length >= 2,
  });
  const add = useMutation({
    mutationFn: () => api.post(`/api/v1/clubs/${club.id}/add_member`, { student, title }),
    onSuccess: () => {
      setStudent("");
      setTitle("");
      setQ("");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/clubs/${club.id}/remove_member`, { student: id }),
    onSuccess: refresh,
  });
  const members = club.members ?? [];
  return (
    <Card title={`Members (${members.length}${club.capacity ? ` of ${club.capacity}` : ""})`}>
      {members.length ? (
        <Table head={["Name", "Class", "Role", ""]}>
          {members.map((m) => (
            <tr key={m.student}>
              <Td className="font-medium">{m.name}</Td>
              <Td>{m.class}</Td>
              <Td>{m.title || "Member"}</Td>
              <Td className="text-right">
                {club.can_run && (
                  <Button
                    variant="ghost"
                    busy={remove.isPending && remove.variables === m.student}
                    onClick={() => remove.mutate(m.student)}
                    aria-label={`Remove ${m.name}`}
                  >
                    Remove
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No members yet.</Empty>
      )}
      {club.can_run && (
        <form
          className="mt-4 grid gap-2 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (student) add.mutate();
          }}
        >
          <Field label="Find a pupil">
            <Input value={q} onChange={(e) => setQ(e.target.value)} />
          </Field>
          <Field label="Pupil">
            <Select value={student} onChange={(e) => setStudent(e.target.value)}>
              <option value="">{q.trim().length >= 2 ? "Choose" : "Search first"}</option>
              {pupils.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.first_name} {p.last_name} {p.arm_name ? `(${p.arm_name})` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Role (optional)" hint='e.g. "Captain"'>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={40} />
          </Field>
          <div className="flex items-end justify-end">
            <Button type="submit" variant="secondary" busy={add.isPending} disabled={!student}>
              Add member
            </Button>
          </div>
          <div className="sm:col-span-2">
            <ErrorText error={add.error ?? remove.error} />
          </div>
        </form>
      )}
    </Card>
  );
}

function Patrons({ club, manage }: { club: Detail; manage: boolean }) {
  const client = useQueryClient();
  const [person, setPerson] = useState("");
  const staff = useQuery({
    queryKey: ["staff", "patrons"],
    queryFn: () => api.get<StaffMember[]>("/api/v1/staff"),
    enabled: manage,
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["club", club.id] });
    void client.invalidateQueries({ queryKey: ["clubs"] });
  };
  const add = useMutation({
    mutationFn: () => api.post(`/api/v1/clubs/${club.id}/add_patron`, { user: person }),
    onSuccess: () => {
      setPerson("");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (user: string) => api.post(`/api/v1/clubs/${club.id}/remove_patron`, { user }),
    onSuccess: refresh,
  });
  const current = new Set(club.patrons.map((p) => p.id));
  const options = (staff.data ?? []).filter((s) => s.user_id && s.is_active && !current.has(s.user_id));
  return (
    <Card title="Patrons">
      {club.patrons.length ? (
        <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
          {club.patrons.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-1.5">
              {p.name}
              {manage && (
                <Button
                  variant="ghost"
                  onClick={() => remove.mutate(p.id)}
                  aria-label={`Remove ${p.name} as patron`}
                >
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">No patron yet.</p>
      )}
      {manage && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (person) add.mutate();
          }}
        >
          <div className="min-w-48 flex-1">
            <Field label="Add a patron">
              <Select value={person} onChange={(e) => setPerson(e.target.value)}>
                <option value="">Choose a member of staff</option>
                {options.map((s) => (
                  <option key={s.id} value={s.user_id ?? ""}>
                    {s.first_name} {s.last_name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Button type="submit" variant="secondary" busy={add.isPending} disabled={!person}>
            Add
          </Button>
        </form>
      )}
      <ErrorText error={add.error ?? remove.error} />
    </Card>
  );
}
