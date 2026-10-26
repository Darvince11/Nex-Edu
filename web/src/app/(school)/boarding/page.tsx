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
  PageHeader,
  Select,
  Table,
  Td,
} from "@/components/ui";
import { api, type Paged, type StaffMember, type Student } from "@/lib/api";
import { formatDate, todayInAccra } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type House = {
  id: number;
  name: string;
  gender: string;
  gender_label: string;
  warden_user_id: string | null;
  warden_name: string;
  beds: number;
  boarders: number;
};
type Room = { id: number; house: number; name: string; beds: number; occupied: number };
type BoarderRow = {
  student: string;
  name: string;
  class: string;
  house: number;
  room: number;
  room_name: string;
  since: string;
};
type RollRow = { student: string; name: string; room: string; status: string; on_exeat: boolean };
type Roll = {
  house: number;
  house_name: string;
  date: string;
  session: string;
  taken: boolean;
  rows: RollRow[];
};
type Exeat = {
  id: string;
  student: string;
  student_name: string;
  leaves_on: string;
  returns_on: string;
  reason: string;
  collected_by: string;
  status: string;
  status_label: string;
  decision_note: string;
};
type Mine = {
  student: string;
  name: string;
  house: string;
  room: string;
  roll_calls: { date: string; session: string; status: string }[];
};
type Tab = "roll" | "beds" | "exeats" | "houses";

const ROLL_STATUSES: [string, string][] = [
  ["present", "Present"],
  ["absent", "Absent"],
  ["exeat", "On exeat"],
  ["sick_bay", "Sick bay"],
];
const EXEAT_TONE: Record<string, "amber" | "green" | "grey" | "blue"> = {
  requested: "amber",
  approved: "green",
  declined: "grey",
  out: "blue",
  returned: "grey",
};

/** Boarding: roll call, beds and exeats for wardens; houses for leaders; parents follow and ask for exeats. */
export default function BoardingPage() {
  const { can } = useSchool();
  return can(PERM.HOSTEL_RECORD, PERM.HOSTEL_MANAGE) ? <Staff /> : <Family />;
}

function useHouses() {
  return useQuery({ queryKey: ["houses"], queryFn: () => api.get<House[]>("/api/v1/hostel/houses") });
}

function Staff() {
  const { can } = useSchool();
  const manage = can(PERM.HOSTEL_MANAGE);
  const [tab, setTab] = useState<Tab>("roll");
  const houses = useHouses();
  const [house, setHouse] = useState("");
  const chosen = house || String(houses.data?.[0]?.id ?? "");
  const tabs: [Tab, string][] = [
    ["roll", "Roll call"],
    ["beds", "Beds"],
    ["exeats", "Exeats"],
    ...(manage ? ([["houses", "Houses and rooms"]] as [Tab, string][]) : []),
  ];
  return (
    <>
      <PageHeader title="Boarding" description="Roll call, beds and exeats for the boarding houses." />
      <div
        role="tablist"
        aria-label="Boarding"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {tabs.map(([key, label]) => (
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
      <div role="tabpanel">
        {(tab === "roll" || tab === "beds") && (houses.data?.length ?? 0) > 1 && (
          <div className="mb-4 w-56">
            <Field label="House">
              <Select value={chosen} onChange={(e) => setHouse(e.target.value)}>
                {houses.data?.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        )}
        {(tab === "roll" || tab === "beds") && !chosen && (
          <Empty>{manage ? "Add a boarding house first." : "You aren't the warden of a house yet."}</Empty>
        )}
        {tab === "roll" && chosen && <RollCallTab house={chosen} />}
        {tab === "beds" && chosen && <BedsTab house={chosen} />}
        {tab === "exeats" && <ExeatsTab />}
        {tab === "houses" && manage && <HousesTab />}
      </div>
    </>
  );
}

function RollCallTab({ house }: { house: string }) {
  const client = useQueryClient();
  const [day, setDay] = useState(todayInAccra());
  const [session, setSession] = useState(new Date().getHours() < 12 ? "morning" : "evening");
  const [marks, setMarks] = useState<Record<string, string>>({});
  const roll = useQuery({
    queryKey: ["roll-call", house, day, session],
    queryFn: () => api.get<Roll>(`/api/v1/hostel/roll-call?house=${house}&date=${day}&session=${session}`),
  });
  const save = useMutation({
    mutationFn: () =>
      api.post<{ saved: number; absent: number }>("/api/v1/hostel/roll-call", {
        house: Number(house),
        date: day,
        session,
        marks: (roll.data?.rows ?? []).map((r) => ({
          student: r.student,
          status: marks[r.student] ?? (r.status || "present"),
        })),
      }),
    onSuccess: () => {
      setMarks({});
      void client.invalidateQueries({ queryKey: ["roll-call", house] });
    },
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
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
        <div className="w-40">
          <Field label="Session">
            <Select value={session} onChange={(e) => setSession(e.target.value)}>
              <option value="morning">Morning</option>
              <option value="evening">Evening</option>
            </Select>
          </Field>
        </div>
      </div>
      <ErrorText error={roll.error ?? save.error} />
      {save.data && (
        <div className="mb-3">
          <Alert tone={save.data.absent ? "warning" : "success"}>
            Saved {save.data.saved}.{" "}
            {save.data.absent
              ? `${save.data.absent} missing: the head teacher has been told.`
              : "Everyone accounted for."}
          </Alert>
        </div>
      )}
      {roll.isPending ? (
        <Loading />
      ) : roll.data?.rows.length ? (
        <>
          <Table head={["Pupil", "Room", "Status"]}>
            {roll.data.rows.map((r) => {
              const value = marks[r.student] ?? (r.status || "present");
              return (
                <tr key={r.student}>
                  <Td className="font-medium">
                    {r.name} {r.on_exeat && <Badge tone="blue">On exeat</Badge>}
                  </Td>
                  <Td>{r.room}</Td>
                  <Td>
                    <Select
                      aria-label={`Status for ${r.name}`}
                      value={value}
                      onChange={(e) => setMarks((m) => ({ ...m, [r.student]: e.target.value }))}
                    >
                      {ROLL_STATUSES.map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </Select>
                  </Td>
                </tr>
              );
            })}
          </Table>
          <div className="mt-3 flex justify-end">
            <Button busy={save.isPending} onClick={() => save.mutate()}>
              {roll.data.taken ? "Update roll call" : "Save roll call"}
            </Button>
          </div>
        </>
      ) : (
        <Empty>No boarders in this house yet.</Empty>
      )}
    </>
  );
}

function BedsTab({ house }: { house: string }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const boarders = useQuery({
    queryKey: ["boarders", house],
    queryFn: () => api.get<BoarderRow[]>(`/api/v1/hostel/boarders?house=${house}`),
  });
  const rooms = useQuery({
    queryKey: ["hostel-rooms", house],
    queryFn: () => api.get<Room[]>(`/api/v1/hostel/rooms?house=${house}`),
  });
  const pupils = useQuery({
    queryKey: ["students", "bed-search", q],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?page_size=20&q=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2,
  });
  const refresh = () => {
    for (const key of ["boarders", "hostel-rooms", "houses"])
      void client.invalidateQueries({ queryKey: [key] });
  };
  const give = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/hostel/boarders", body),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (student: string) => api.del(`/api/v1/hostel/boarders?student=${student}`),
    onSuccess: refresh,
  });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <div>
        <ErrorText error={boarders.error ?? remove.error} />
        {boarders.data?.length ? (
          <Table head={["Pupil", "Class", "Room", ""]}>
            {boarders.data.map((b) => (
              <tr key={b.student}>
                <Td className="font-medium">{b.name}</Td>
                <Td>{b.class}</Td>
                <Td>{b.room_name}</Td>
                <Td className="text-right">
                  <Button
                    variant="ghost"
                    onClick={() => remove.mutate(b.student)}
                    aria-label={`${b.name} no longer boards`}
                  >
                    Remove
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No boarders yet.</Empty>
        )}
      </div>
      <Card title="Give a bed">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
            give.mutate(
              { student: f.student, room: Number(f.room) },
              {
                onSuccess: () => {
                  form.reset();
                  setQ("");
                },
              },
            );
          }}
        >
          <Field label="Find the pupil">
            <Input value={q} onChange={(e) => setQ(e.target.value)} />
          </Field>
          <Field label="Pupil">
            <Select name="student" required defaultValue="">
              <option value="" disabled>
                {q.trim().length >= 2 ? "Choose" : "Search first"}
              </option>
              {pupils.data?.results.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.first_name} {p.last_name} {p.arm_name ? `(${p.arm_name})` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Room">
            <Select name="room" required defaultValue="">
              <option value="" disabled>
                Choose
              </option>
              {rooms.data?.map((r) => (
                <option key={r.id} value={r.id} disabled={r.occupied >= r.beds}>
                  {r.name} ({r.occupied} of {r.beds})
                </option>
              ))}
            </Select>
          </Field>
          <ErrorText error={give.error} />
          <Button type="submit" busy={give.isPending}>
            Give bed
          </Button>
        </form>
      </Card>
    </div>
  );
}

function ExeatsTab() {
  const client = useQueryClient();
  const [status, setStatus] = useState("requested");
  const exeats = useQuery({
    queryKey: ["exeats", status],
    queryFn: () => api.get<Exeat[]>(`/api/v1/hostel/exeats${status ? `?status=${status}` : ""}`),
  });
  const act = useMutation({
    mutationFn: ({ id, what }: { id: string; what: string }) =>
      api.post(`/api/v1/hostel/exeats/${id}/${what}`, {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["exeats"] }),
  });
  return (
    <>
      <div className="mb-4 w-48">
        <Field label="Show">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="requested">Waiting for approval</option>
            <option value="approved">Approved</option>
            <option value="out">Away now</option>
            <option value="">All</option>
          </Select>
        </Field>
      </div>
      <ErrorText error={exeats.error ?? act.error} />
      {exeats.data?.length ? (
        <Table head={["Pupil", "Away", "Why", "Status", ""]}>
          {exeats.data.map((x) => (
            <tr key={x.id}>
              <Td className="font-medium">{x.student_name}</Td>
              <Td className="whitespace-nowrap">
                {formatDate(x.leaves_on)} to {formatDate(x.returns_on)}
              </Td>
              <Td>
                {x.reason}
                {x.collected_by && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    With {x.collected_by}
                  </span>
                )}
              </Td>
              <Td>
                <Badge tone={EXEAT_TONE[x.status] ?? "grey"}>{x.status_label}</Badge>
              </Td>
              <Td className="whitespace-nowrap text-right">
                {x.status === "requested" && (
                  <>
                    <Button
                      variant="secondary"
                      onClick={() => act.mutate({ id: x.id, what: "approve" })}
                      aria-label={`Approve exeat for ${x.student_name}`}
                    >
                      Approve
                    </Button>{" "}
                    <Button
                      variant="ghost"
                      onClick={() => act.mutate({ id: x.id, what: "decline" })}
                      aria-label={`Decline exeat for ${x.student_name}`}
                    >
                      Decline
                    </Button>
                  </>
                )}
                {x.status === "approved" && (
                  <Button
                    variant="secondary"
                    onClick={() => act.mutate({ id: x.id, what: "depart" })}
                    aria-label={`${x.student_name} has left`}
                  >
                    Has left
                  </Button>
                )}
                {(x.status === "out" || x.status === "approved") && (
                  <Button
                    variant="ghost"
                    onClick={() => act.mutate({ id: x.id, what: "back" })}
                    aria-label={`${x.student_name} is back`}
                  >
                    Is back
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No exeats to show.</Empty>
      )}
    </>
  );
}

function HousesTab() {
  const client = useQueryClient();
  const houses = useHouses();
  const staff = useQuery({
    queryKey: ["staff", "wardens"],
    queryFn: () => api.get<StaffMember[]>("/api/v1/staff"),
  });
  const refresh = () => {
    for (const key of ["houses", "hostel-rooms"]) void client.invalidateQueries({ queryKey: [key] });
  };
  const addHouse = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/hostel/houses", body),
    onSuccess: refresh,
  });
  const addRoom = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/hostel/rooms", body),
    onSuccess: refresh,
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Houses">
        {houses.data?.length ? (
          <ul className="mb-4 divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
            {houses.data.map((h) => (
              <li key={h.id} className="py-1.5">
                <span className="font-medium">{h.name}</span> · {h.gender_label} · {h.boarders} of{" "}
                {h.beds ?? 0} beds used
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  Warden: {h.warden_name || "none yet"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mb-4 text-sm text-neutral-600 dark:text-neutral-300">No houses yet.</p>
        )}
        <form
          className="grid gap-2 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
            addHouse.mutate(
              { name: f.name, gender: f.gender, warden_user_id: f.warden || null },
              { onSuccess: () => form.reset() },
            );
          }}
        >
          <Field label="House name">
            <Input name="name" required maxLength={80} />
          </Field>
          <Field label="For">
            <Select name="gender" defaultValue="mixed">
              <option value="girls">Girls</option>
              <option value="boys">Boys</option>
              <option value="mixed">Mixed</option>
            </Select>
          </Field>
          <Field label="Warden">
            <Select name="warden" defaultValue="">
              <option value="">Choose later</option>
              {staff.data
                ?.filter((s) => s.user_id && s.is_active)
                .map((s) => (
                  <option key={s.id} value={s.user_id ?? ""}>
                    {s.first_name} {s.last_name}
                  </option>
                ))}
            </Select>
          </Field>
          <div className="flex items-end justify-end">
            <Button type="submit" variant="secondary" busy={addHouse.isPending}>
              Add house
            </Button>
          </div>
        </form>
        <ErrorText error={addHouse.error} />
      </Card>
      <Card title="Add a room">
        <form
          className="grid gap-2 sm:grid-cols-3 sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
            addRoom.mutate(
              { house: Number(f.house), name: f.name, beds: Number(f.beds) },
              { onSuccess: () => form.reset() },
            );
          }}
        >
          <Field label="House">
            <Select name="house" required defaultValue="">
              <option value="" disabled>
                Choose
              </option>
              {houses.data?.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Room">
            <Input name="name" required maxLength={40} />
          </Field>
          <Field label="Beds">
            <Input name="beds" type="number" min={1} max={100} required defaultValue={4} />
          </Field>
          <div className="flex justify-end sm:col-span-3">
            <Button type="submit" variant="secondary" busy={addRoom.isPending}>
              Add room
            </Button>
          </div>
        </form>
        <ErrorText error={addRoom.error} />
      </Card>
    </div>
  );
}

function Family() {
  const client = useQueryClient();
  const mine = useQuery({
    queryKey: ["boarding-mine"],
    queryFn: () => api.get<Mine[]>("/api/v1/hostel/mine"),
  });
  const exeats = useQuery({
    queryKey: ["exeats", "mine"],
    queryFn: () => api.get<Exeat[]>("/api/v1/hostel/exeats"),
  });
  const ask = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/hostel/exeats", body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["exeats"] }),
  });
  return (
    <>
      <PageHeader title="Boarding" description="Your child's house and room, roll calls, and exeats." />
      <ErrorText error={mine.error ?? exeats.error} />
      {mine.isPending ? (
        <Loading />
      ) : mine.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {mine.data.map((m) => (
            <Card key={m.student} title={`${m.name}: ${m.house}, ${m.room}`}>
              <h3 className="mb-1 text-sm font-medium">Recent roll calls</h3>
              {m.roll_calls.length ? (
                <ul className="mb-4 text-sm">
                  {m.roll_calls.map((r) => (
                    <li key={`${r.date}-${r.session}`}>
                      {formatDate(r.date)} {r.session.toLowerCase()}: {r.status}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mb-4 text-sm text-neutral-600 dark:text-neutral-300">None yet.</p>
              )}
              <form
                className="grid gap-2 sm:grid-cols-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
                  ask.mutate(
                    {
                      student: m.student,
                      leaves_on: f.leaves_on,
                      returns_on: f.returns_on,
                      reason: f.reason,
                      collected_by: f.collected_by,
                    },
                    { onSuccess: () => form.reset() },
                  );
                }}
              >
                <h3 className="text-sm font-medium sm:col-span-2">Ask for an exeat</h3>
                <Field label="Leaving on">
                  <Input name="leaves_on" type="date" required min={todayInAccra()} />
                </Field>
                <Field label="Back on">
                  <Input name="returns_on" type="date" required min={todayInAccra()} />
                </Field>
                <Field label="Why">
                  <Input name="reason" required maxLength={200} />
                </Field>
                <Field label="Who will collect">
                  <Input name="collected_by" maxLength={120} />
                </Field>
                <div className="flex justify-end sm:col-span-2">
                  <Button type="submit" variant="secondary" busy={ask.isPending}>
                    Ask
                  </Button>
                </div>
              </form>
            </Card>
          ))}
        </div>
      ) : (
        <Empty>Your children don't board.</Empty>
      )}
      <ErrorText error={ask.error} />
      {exeats.data && exeats.data.length > 0 && (
        <section aria-labelledby="exeats-title" className="mt-6">
          <h2 id="exeats-title" className="mb-2 font-medium">
            Exeats
          </h2>
          <Table head={["Child", "Away", "Why", "Status"]}>
            {exeats.data.map((x) => (
              <tr key={x.id}>
                <Td>{x.student_name}</Td>
                <Td className="whitespace-nowrap">
                  {formatDate(x.leaves_on)} to {formatDate(x.returns_on)}
                </Td>
                <Td>{x.reason}</Td>
                <Td>
                  <Badge tone={EXEAT_TONE[x.status] ?? "grey"}>{x.status_label}</Badge>
                  {x.decision_note && (
                    <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                      {x.decision_note}
                    </span>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        </section>
      )}
    </>
  );
}
