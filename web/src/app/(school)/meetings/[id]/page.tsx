"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { hhmm, type MeetingDay, MeetingDayForm } from "@/components/meetings";
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
} from "@/components/ui";
import { JoinLink } from "@/components/video-link";
import { api, type StaffMember } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type StaffSlot = {
  id: string;
  starts_at: string;
  ends_at: string;
  student: string | null;
  student_name: string;
  student_class: string;
  parent: string;
  note: string;
};
type Schedule = { user: string; name: string; room: string; booked: number; slots: StaffSlot[] }[];
type FreeSlot = { id: string; starts_at: string; ends_at: string; free: boolean; mine: boolean };
type ChildView = {
  student: string;
  name: string;
  class: string;
  teachers: {
    user: string;
    name: string;
    teaches: string;
    room: string;
    booking: (FreeSlot & { note: string }) | null;
    slots: FreeSlot[];
  }[];
};
type Detail = MeetingDay & { schedule?: Schedule; children?: ChildView[] };

/** One meeting day: book (parents), see your times (teachers), set it up (leaders). */
export default function MeetingDayPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSchool();
  const manage = can(PERM.MEETINGS_MANAGE);
  const [editing, setEditing] = useState(false);
  const day = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => api.get<Detail>(`/api/v1/meetings/${id}`),
  });

  if (day.isPending) return <Loading />;
  if (day.error) return <ErrorText error={day.error} />;
  const d = day.data;
  return (
    <>
      <PageHeader
        title={d.title}
        description={
          <>
            {`${formatDate(d.date)}, ${hhmm(d.starts_at)} to ${hhmm(d.ends_at)}${d.location ? ` · ${d.location}` : ""}`}{" "}
            <JoinLink url={d.video_url} label="Meeting" />
          </>
        }
        actions={
          manage && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Change details
            </Button>
          )
        }
      />
      <p className="mb-4 text-sm">
        <Link href="/meetings" className="text-brand-strong hover:underline dark:text-brand-sky">
          ← All meeting days
        </Link>
      </p>
      {d.notes && <p className="mb-4 max-w-prose text-sm">{d.notes}</p>}
      {manage && <Setup day={d} />}
      {d.children && <Booking day={d} />}
      {d.schedule && <ScheduleView day={d} manage={manage} />}
      <Modal open={editing} onClose={() => setEditing(false)} title="Change meeting day">
        {editing && <MeetingDayForm day={d} onDone={() => setEditing(false)} />}
      </Modal>
    </>
  );
}

function useRefresh(id: string) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["meeting", id] });
    void client.invalidateQueries({ queryKey: ["meetings"] });
  };
}

function Setup({ day }: { day: Detail }) {
  const refresh = useRefresh(day.id);
  const [person, setPerson] = useState("");
  const [room, setRoom] = useState("");
  const staff = useQuery({
    queryKey: ["staff", "meetings"],
    queryFn: () => api.get<StaffMember[]>("/api/v1/staff"),
  });
  const add = useMutation({
    mutationFn: () => api.post(`/api/v1/meetings/${day.id}/add_teacher`, { user: person, room }),
    onSuccess: () => {
      setPerson("");
      setRoom("");
      refresh();
    },
  });
  const open = useMutation({
    mutationFn: () => api.post<{ parents: number }>(`/api/v1/meetings/${day.id}/open`),
    onSuccess: refresh,
  });
  const close = useMutation({
    mutationFn: () => api.post(`/api/v1/meetings/${day.id}/close`),
    onSuccess: refresh,
  });
  const taking = new Set(day.schedule?.map((t) => t.user));
  const options = (staff.data ?? []).filter((s) => s.user_id && s.is_active && !taking.has(s.user_id));
  return (
    <Card
      title="Set-up"
      actions={
        day.is_open ? (
          <Button variant="secondary" busy={close.isPending} onClick={() => close.mutate()}>
            Stop bookings
          </Button>
        ) : (
          <Button busy={open.isPending} onClick={() => open.mutate()} disabled={!day.schedule?.length}>
            Open bookings and tell parents
          </Button>
        )
      }
    >
      {open.data && (
        <div className="mb-3">
          <Alert tone="success">
            Bookings are open. {open.data.parents} parent(s) were told in their inbox.
          </Alert>
        </div>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (person) add.mutate();
        }}
      >
        <div className="min-w-48 flex-1">
          <Field label="Teacher taking part">
            <Select value={person} onChange={(e) => setPerson(e.target.value)}>
              <option value="">Choose a member of staff</option>
              {options.map((s) => (
                <option key={s.id} value={s.user_id ?? ""}>
                  {s.first_name} {s.last_name}
                  {s.job_title ? ` (${s.job_title})` : ""}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="w-40">
          <Field label="Room (optional)">
            <Input value={room} onChange={(e) => setRoom(e.target.value)} maxLength={60} />
          </Field>
        </div>
        <Button type="submit" variant="secondary" busy={add.isPending} disabled={!person}>
          Add teacher
        </Button>
      </form>
      <ErrorText error={add.error ?? open.error ?? close.error} />
      <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
        Each teacher's time is split into {day.slot_minutes}-minute meetings. Parents can book teachers who
        teach their child's class, and the head teacher.
      </p>
    </Card>
  );
}

function ScheduleView({ day, manage }: { day: Detail; manage: boolean }) {
  const refresh = useRefresh(day.id);
  const cancel = useMutation({
    mutationFn: (slot: string) => api.post(`/api/v1/meetings/${day.id}/slots/${slot}/cancel`),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (user: string) => api.post(`/api/v1/meetings/${day.id}/remove_teacher`, { user }),
    onSuccess: refresh,
  });
  const schedule = day.schedule ?? [];
  return (
    <section aria-labelledby="schedule-title" className="mt-6">
      <h2 id="schedule-title" className="mb-2 font-medium">
        {manage ? "Teachers' times" : "Your times"}
      </h2>
      <ErrorText error={cancel.error ?? remove.error} />
      {schedule.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {schedule.map((t) => (
            <Card
              key={t.user}
              title={`${t.name}${t.room ? ` · ${t.room}` : ""} (${t.booked} booked)`}
              actions={
                manage && (
                  <Button
                    variant="ghost"
                    onClick={() => remove.mutate(t.user)}
                    aria-label={`Take ${t.name} off this day`}
                  >
                    Remove
                  </Button>
                )
              }
            >
              <Table head={["Time", "Pupil", "Parent", ""]}>
                {t.slots.map((s) => (
                  <tr key={s.id}>
                    <Td className="whitespace-nowrap tabular-nums">{hhmm(s.starts_at)}</Td>
                    <Td>
                      {s.student ? (
                        <>
                          {s.student_name}
                          <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                            {s.student_class}
                            {s.note ? ` · ${s.note}` : ""}
                          </span>
                        </>
                      ) : (
                        <span className="text-neutral-600 dark:text-neutral-400">Free</span>
                      )}
                    </Td>
                    <Td>{s.parent}</Td>
                    <Td className="text-right">
                      {s.student && (
                        <Button
                          variant="ghost"
                          onClick={() => cancel.mutate(s.id)}
                          aria-label={`Cancel ${hhmm(s.starts_at)}`}
                        >
                          Cancel
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
            </Card>
          ))}
        </div>
      ) : (
        <Empty>{manage ? "Add the teachers taking part." : "You aren't seeing parents on this day."}</Empty>
      )}
    </section>
  );
}

function Booking({ day }: { day: Detail }) {
  const refresh = useRefresh(day.id);
  const [note, setNote] = useState("");
  const book = useMutation({
    mutationFn: ({ slot, student }: { slot: string; student: string }) =>
      api.post(`/api/v1/meetings/${day.id}/slots/${slot}/book`, { student, note }),
    onSuccess: () => {
      setNote("");
      refresh();
    },
  });
  const cancel = useMutation({
    mutationFn: (slot: string) => api.post(`/api/v1/meetings/${day.id}/slots/${slot}/cancel`),
    onSuccess: refresh,
  });
  const children = day.children ?? [];
  if (!day.is_open)
    return <Alert>Booking hasn't opened yet. You'll get a message in your inbox when it does.</Alert>;
  return (
    <section aria-labelledby="booking-title" className="flex flex-col gap-4">
      <h2 id="booking-title" className="font-medium">
        Book your times
      </h2>
      <div className="max-w-md">
        <Field label="What would you like to talk about? (optional)" hint="Sent with your next booking.">
          <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
        </Field>
      </div>
      <ErrorText error={book.error ?? cancel.error} />
      {children.map((child) => (
        <Card key={child.student} title={`${child.name}${child.class ? ` (${child.class})` : ""}`}>
          {child.teachers.length ? (
            <ul className="flex flex-col gap-4">
              {child.teachers.map((t) => (
                <li key={t.user}>
                  <div className="mb-1 text-sm">
                    <span className="font-medium">{t.name}</span>{" "}
                    <span className="text-neutral-600 dark:text-neutral-300">
                      {t.teaches}
                      {t.room ? ` · ${t.room}` : ""}
                    </span>
                  </div>
                  {t.booking ? (
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Badge tone="green">{`Booked ${hhmm(t.booking.starts_at)}`}</Badge>
                      <Button
                        variant="ghost"
                        busy={cancel.isPending && cancel.variables === t.booking.id}
                        onClick={() => cancel.mutate(t.booking?.id ?? "")}
                      >
                        Cancel this time
                      </Button>
                    </div>
                  ) : t.slots.some((s) => s.free) ? (
                    <fieldset className="flex flex-wrap gap-2">
                      <legend className="sr-only">Free times with {t.name}</legend>
                      {t.slots
                        .filter((s) => s.free)
                        .map((s) => (
                          <Button
                            key={s.id}
                            variant="secondary"
                            busy={book.isPending && book.variables?.slot === s.id}
                            onClick={() => book.mutate({ slot: s.id, student: child.student })}
                            aria-label={`Book ${hhmm(s.starts_at)} with ${t.name} for ${child.name}`}
                          >
                            {hhmm(s.starts_at)}
                          </Button>
                        ))}
                    </fieldset>
                  ) : (
                    <p className="text-sm text-neutral-600 dark:text-neutral-300">Fully booked.</p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600 dark:text-neutral-300">
              None of {child.name}'s teachers is seeing parents this day.
            </p>
          )}
        </Card>
      ))}
    </section>
  );
}
