"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Button, ErrorText, Field, Input, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";

export type Club = {
  id: string;
  name: string;
  kind: string;
  kind_label: string;
  description: string;
  meets: string;
  capacity: number | null;
  is_active: boolean;
  member_count: number;
  patrons: { id: string; name: string }[];
  i_run: boolean;
  my_children: string[];
};
export type Activity = {
  id: string;
  club: string;
  club_name: string;
  title: string;
  kind: string;
  kind_label: string;
  date: string;
  starts_at: string | null;
  venue: string;
  opponent: string;
  result: string;
  notes: string;
};
export const CLUB_KINDS: [string, string][] = [
  ["club", "Club or society"],
  ["sport", "Sports team"],
  ["arts", "Music, drama or cultural group"],
  ["uniformed", "Uniformed group (Scouts, Guides, Cadets)"],
  ["other", "Other"],
];

/** Add or change a club (school leaders). */
export function ClubForm({ club, onDone }: { club: Club | null; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      club ? api.patch(`/api/v1/clubs/${club.id}`, body) : api.post("/api/v1/clubs", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["clubs"] });
      void client.invalidateQueries({ queryKey: ["club"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      name: f.name,
      kind: f.kind,
      description: f.description,
      meets: f.meets,
      capacity: f.capacity ? Number(f.capacity) : null,
      ...(club ? { is_active: f.is_active === "on" } : {}),
    });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Name">
        <Input name="name" required maxLength={80} defaultValue={club?.name} />
      </Field>
      <Field label="Kind">
        <Select name="kind" defaultValue={club?.kind ?? "club"}>
          {CLUB_KINDS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="When and where it meets (optional)" hint='For example "Wednesdays 2:30pm, Science lab".'>
        <Input name="meets" maxLength={120} defaultValue={club?.meets} />
      </Field>
      <Field label="Most members (optional)">
        <Input name="capacity" type="number" min={1} max={500} defaultValue={club?.capacity ?? ""} />
      </Field>
      <Field label="About it (optional)">
        <Textarea name="description" maxLength={300} rows={3} defaultValue={club?.description} />
      </Field>
      {club && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="is_active"
            defaultChecked={club.is_active}
            className="size-4 accent-brand"
          />
          Running this year
        </label>
      )}
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          {club ? "Save changes" : "Add club"}
        </Button>
      </div>
    </form>
  );
}
