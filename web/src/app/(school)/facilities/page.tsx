"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { cedis, formatDate, todayInAccra, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Room = {
  id: number;
  name: string;
  kind: string;
  kind_label: string;
  capacity: number | null;
  bookable: boolean;
  notes: string;
};
type Booking = {
  id: string;
  room: number;
  room_name: string;
  date: string;
  starts_at: string;
  ends_at: string;
  purpose: string;
  booked_by_name: string;
  mine: boolean;
};
type Repair = {
  id: string;
  room: number | null;
  room_name: string;
  where: string;
  title: string;
  details: string;
  priority: string;
  priority_label: string;
  status: string;
  status_label: string;
  reported_by_name: string;
  assigned_to: string;
  cost_pesewas: number | null;
  outcome: string;
  created_at: string;
  closed_at: string | null;
};
type Tab = "bookings" | "repairs" | "rooms";

const hhmm = (t: string) => t.slice(0, 5);
const STATUS_TONE: Record<string, "amber" | "blue" | "green" | "grey"> = {
  reported: "amber",
  in_progress: "blue",
  done: "green",
  wont_fix: "grey",
};
const ROOM_KINDS: [string, string][] = [
  ["classroom", "Classroom"],
  ["hall", "Hall"],
  ["lab", "Laboratory or ICT lab"],
  ["field", "Field or court"],
  ["office", "Office"],
  ["other", "Other"],
];

/** Facilities: book rooms, report repairs; leaders keep the room list and follow repairs. */
export default function FacilitiesPage() {
  const { can } = useSchool();
  const manage = can(PERM.FACILITIES_MANAGE);
  const [tab, setTab] = useState<Tab>("bookings");
  const tabs: [Tab, string][] = [
    ["bookings", "Room bookings"],
    ["repairs", "Repairs"],
    ...(manage ? ([["rooms", "Rooms"]] as [Tab, string][]) : []),
  ];
  return (
    <>
      <PageHeader
        title="Facilities"
        description="Book the hall, labs and other rooms, and report anything that needs fixing."
      />
      <div
        role="tablist"
        aria-label="Facilities"
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
        {tab === "bookings" && <Bookings manage={manage} />}
        {tab === "repairs" && <Repairs manage={manage} />}
        {tab === "rooms" && manage && <Rooms />}
      </div>
    </>
  );
}

function useRooms() {
  return useQuery({ queryKey: ["rooms"], queryFn: () => api.get<Room[]>("/api/v1/facilities/rooms") });
}

function Bookings({ manage }: { manage: boolean }) {
  const client = useQueryClient();
  const rooms = useRooms();
  const [day, setDay] = useState(todayInAccra());
  const [booking, setBooking] = useState(false);
  const bookings = useQuery({
    queryKey: ["bookings", day],
    queryFn: () => api.get<Booking[]>(`/api/v1/facilities/bookings?date=${day}`),
    placeholderData: keepPreviousData,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/facilities/bookings/${id}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["bookings"] }),
  });
  const bookable = rooms.data?.filter((r) => r.bookable) ?? [];
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="Day">
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value || todayInAccra())} />
          </Field>
        </div>
        <div className="ml-auto">
          <Button onClick={() => setBooking(true)} disabled={!bookable.length}>
            Book a room
          </Button>
        </div>
      </div>
      <ErrorText error={bookings.error ?? cancel.error} />
      {!bookable.length && rooms.isFetched ? (
        <Empty>{manage ? "Add rooms on the Rooms tab first." : "No rooms can be booked yet."}</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {bookable.map((r) => {
            const mine = bookings.data?.filter((b) => b.room === r.id) ?? [];
            return (
              <Card key={r.id} title={r.name}>
                {mine.length ? (
                  <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
                    {mine.map((b) => (
                      <li key={b.id} className="flex items-center justify-between gap-2 py-1.5">
                        <span>
                          <span className="tabular-nums">
                            {hhmm(b.starts_at)} to {hhmm(b.ends_at)}
                          </span>{" "}
                          · {b.purpose}
                          <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                            {b.booked_by_name}
                          </span>
                        </span>
                        {(b.mine || manage) && (
                          <Button
                            variant="ghost"
                            onClick={() => cancel.mutate(b.id)}
                            aria-label={`Cancel ${r.name} at ${hhmm(b.starts_at)}`}
                          >
                            Cancel
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">Free all day.</p>
                )}
              </Card>
            );
          })}
        </div>
      )}
      <Modal open={booking} onClose={() => setBooking(false)} title="Book a room">
        {booking && <BookingForm rooms={bookable} day={day} onDone={() => setBooking(false)} />}
      </Modal>
    </>
  );
}

function BookingForm({ rooms, day, onDone }: { rooms: Room[]; day: string; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/facilities/bookings", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["bookings"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      room: Number(f.room),
      date: f.date,
      starts_at: f.starts_at,
      ends_at: f.ends_at,
      purpose: f.purpose,
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="Room">
        <Select name="room" required defaultValue={String(rooms[0]?.id ?? "")}>
          {rooms.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Day">
        <Input name="date" type="date" required defaultValue={day} min={todayInAccra()} />
      </Field>
      <Field label="From">
        <Input name="starts_at" type="time" required />
      </Field>
      <Field label="Until">
        <Input name="ends_at" type="time" required />
      </Field>
      <div className="sm:col-span-2">
        <Field label="What for">
          <Input name="purpose" required maxLength={120} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Book
        </Button>
      </div>
    </form>
  );
}

function Repairs({ manage }: { manage: boolean }) {
  const client = useQueryClient();
  const rooms = useRooms();
  const [status, setStatus] = useState(manage ? "open" : "");
  const [reporting, setReporting] = useState(false);
  const [editing, setEditing] = useState<Repair | null>(null);
  const repairs = useQuery({
    queryKey: ["repairs", status],
    queryFn: () => api.get<Repair[]>(`/api/v1/facilities/repairs${status ? `?status=${status}` : ""}`),
    placeholderData: keepPreviousData,
  });
  const report = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/facilities/repairs", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["repairs"] });
      setReporting(false);
    },
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="Show">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="open">Still to fix</option>
              <option value="done">Fixed</option>
              <option value="">All</option>
            </Select>
          </Field>
        </div>
        <div className="ml-auto">
          <Button onClick={() => setReporting(true)}>Report a repair</Button>
        </div>
      </div>
      <ErrorText error={repairs.error} />
      {repairs.isPending ? (
        <Loading />
      ) : repairs.data?.length ? (
        <Table head={["Reported", "What", "Where", "Status", ""]}>
          {repairs.data.map((r) => (
            <tr key={r.id}>
              <Td className="whitespace-nowrap">{formatDate(r.created_at)}</Td>
              <Td>
                <span className="font-medium">{r.title}</span>{" "}
                {r.priority === "urgent" && <Badge tone="red">Urgent</Badge>}
                {manage && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {r.reported_by_name}
                  </span>
                )}
              </Td>
              <Td>{r.room_name || r.where}</Td>
              <Td>
                <Badge tone={STATUS_TONE[r.status] ?? "grey"}>{r.status_label}</Badge>
                {r.assigned_to && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {r.assigned_to}
                  </span>
                )}
                {r.outcome && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">{r.outcome}</span>
                )}
              </Td>
              <Td className="text-right">
                {manage && (
                  <Button variant="ghost" onClick={() => setEditing(r)} aria-label={`Update ${r.title}`}>
                    Update
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Nothing to show.</Empty>
      )}
      <Modal open={reporting} onClose={() => setReporting(false)} title="Report a repair">
        {reporting && (
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
              report.mutate({
                title: f.title,
                room: f.room ? Number(f.room) : null,
                where: f.where,
                details: f.details,
                priority: f.priority,
              });
            }}
          >
            <div className="sm:col-span-2">
              <Field label="What needs fixing">
                <Input name="title" required maxLength={120} />
              </Field>
            </div>
            <Field label="Room">
              <Select name="room" defaultValue="">
                <option value="">Not a listed room</option>
                {rooms.data?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Or where">
              <Input name="where" maxLength={120} />
            </Field>
            <Field label="How urgent">
              <Select name="priority" defaultValue="normal">
                <option value="low">Can wait</option>
                <option value="normal">Normal</option>
                <option value="urgent">Urgent (safety)</option>
              </Select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Details (optional)">
                <Textarea name="details" maxLength={1000} rows={3} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <ErrorText error={report.error} />
            </div>
            <div className="flex justify-end sm:col-span-2">
              <Button type="submit" busy={report.isPending}>
                Report
              </Button>
            </div>
          </form>
        )}
      </Modal>
      <Modal open={editing !== null} onClose={() => setEditing(null)} title="Update repair">
        {editing && <RepairUpdate repair={editing} onDone={() => setEditing(null)} />}
      </Modal>
    </>
  );
}

function RepairUpdate({ repair, onDone }: { repair: Repair; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/api/v1/facilities/repairs/${repair.id}`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["repairs"] });
      onDone();
    },
  });
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          status: f.status,
          assigned_to: f.assigned_to,
          cost_pesewas: f.cost ? toPesewas(f.cost) : null,
          outcome: f.outcome,
        });
      }}
    >
      <p className="text-sm sm:col-span-2">
        <span className="font-medium">{repair.title}</span> · {repair.room_name || repair.where}
        {repair.details && (
          <span className="block text-neutral-600 dark:text-neutral-300">{repair.details}</span>
        )}
      </p>
      <Field label="Status">
        <Select name="status" defaultValue={repair.status}>
          <option value="reported">Reported</option>
          <option value="in_progress">Being fixed</option>
          <option value="done">Fixed</option>
          <option value="wont_fix">Won't be fixed</option>
        </Select>
      </Field>
      <Field label="Who is fixing it">
        <Input name="assigned_to" maxLength={120} defaultValue={repair.assigned_to} />
      </Field>
      <Field label="Cost (GH₵, optional)">
        <Input
          name="cost"
          inputMode="decimal"
          defaultValue={repair.cost_pesewas ? (repair.cost_pesewas / 100).toFixed(2) : ""}
        />
      </Field>
      <div className="sm:col-span-2">
        <Field label="What was done (the reporter is told when it's closed)">
          <Input name="outcome" maxLength={300} defaultValue={repair.outcome} />
        </Field>
      </div>
      {repair.cost_pesewas ? <Alert>Recorded cost: {cedis(repair.cost_pesewas)}</Alert> : null}
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function Rooms() {
  const client = useQueryClient();
  const rooms = useRooms();
  const [editing, setEditing] = useState<Room | "new" | null>(null);
  const save = useMutation({
    mutationFn: ({ room, body }: { room: Room | null; body: Record<string, unknown> }) =>
      room
        ? api.patch(`/api/v1/facilities/rooms/${room.id}`, body)
        : api.post("/api/v1/facilities/rooms", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["rooms"] });
      setEditing(null);
    },
  });
  const room = editing === "new" ? null : editing;
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setEditing("new")}>Add a room</Button>
      </div>
      <ErrorText error={rooms.error} />
      {rooms.data?.length ? (
        <Table head={["Room", "Kind", "Seats", "Can be booked", ""]}>
          {rooms.data.map((r) => (
            <tr key={r.id}>
              <Td className="font-medium">{r.name}</Td>
              <Td>{r.kind_label}</Td>
              <Td className="tabular-nums">{r.capacity ?? "—"}</Td>
              <Td>{r.bookable ? "Yes" : "No"}</Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setEditing(r)} aria-label={`Change ${r.name}`}>
                  Change
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No rooms yet.</Empty>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={room ? `Change ${room.name}` : "Add a room"}
      >
        {editing !== null && (
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
              save.mutate({
                room,
                body: {
                  name: f.name,
                  kind: f.kind,
                  capacity: f.capacity ? Number(f.capacity) : null,
                  bookable: f.bookable === "on",
                },
              });
            }}
          >
            <Field label="Name">
              <Input name="name" required maxLength={80} defaultValue={room?.name} />
            </Field>
            <Field label="Kind">
              <Select name="kind" defaultValue={room?.kind ?? "classroom"}>
                {ROOM_KINDS.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Seats (optional)">
              <Input name="capacity" type="number" min={1} max={5000} defaultValue={room?.capacity ?? ""} />
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input
                type="checkbox"
                name="bookable"
                defaultChecked={room?.bookable ?? true}
                className="size-4 accent-brand"
              />{" "}
              Staff can book it
            </label>
            <div className="sm:col-span-2">
              <ErrorText error={save.error} />
            </div>
            <div className="flex justify-end sm:col-span-2">
              <Button type="submit" busy={save.isPending}>
                Save
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
