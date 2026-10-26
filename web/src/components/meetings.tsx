"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Button, ErrorText, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";

export type MeetingDay = {
  id: string;
  title: string;
  date: string;
  starts_at: string;
  ends_at: string;
  slot_minutes: number;
  location: string;
  video_url: string;
  notes: string;
  is_open: boolean;
  teacher_count: number;
  booked_count: number;
};

export const hhmm = (t: string | null | undefined) => (t ? t.slice(0, 5) : "");

/** Set up a parent meeting day (school leaders). Times are fixed once teachers are added. */
export function MeetingDayForm({ day, onDone }: { day: MeetingDay | null; onDone: (id: string) => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      day
        ? api.patch<MeetingDay>(`/api/v1/meetings/${day.id}`, body)
        : api.post<MeetingDay>("/api/v1/meetings", body),
    onSuccess: (saved) => {
      void client.invalidateQueries({ queryKey: ["meetings"] });
      void client.invalidateQueries({ queryKey: ["meeting", saved.id] });
      onDone(saved.id);
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      title: f.title,
      date: f.date,
      starts_at: f.starts_at,
      ends_at: f.ends_at,
      slot_minutes: Number(f.slot_minutes),
      location: f.location,
      notes: f.notes,
      video_url: f.video_url ?? "",
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field label="Name" hint='For example "End of term parent meetings".'>
          <Input name="title" required maxLength={120} defaultValue={day?.title} />
        </Field>
      </div>
      <Field label="Date">
        <Input name="date" type="date" required defaultValue={day?.date} />
      </Field>
      <Field label="Each meeting lasts">
        <Select name="slot_minutes" defaultValue={String(day?.slot_minutes ?? 10)}>
          {[5, 10, 15, 20, 30].map((m) => (
            <option key={m} value={m}>
              {m} minutes
            </option>
          ))}
        </Select>
      </Field>
      <Field label="From">
        <Input name="starts_at" type="time" required defaultValue={hhmm(day?.starts_at) || "09:00"} />
      </Field>
      <Field label="Until">
        <Input name="ends_at" type="time" required defaultValue={hhmm(day?.ends_at) || "12:00"} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Where (optional)">
          <Input name="location" maxLength={120} defaultValue={day?.location} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field
          label="Online meeting link (optional)"
          hint="Google Meet, Zoom, Teams or WhatsApp; starts with https://"
        >
          <Input
            name="video_url"
            type="url"
            inputMode="url"
            maxLength={500}
            pattern="https://.*"
            defaultValue={day?.video_url}
          />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label="Note for parents (optional)">
          <Input name="notes" maxLength={500} defaultValue={day?.notes} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          {day ? "Save changes" : "Create meeting day"}
        </Button>
      </div>
    </form>
  );
}
