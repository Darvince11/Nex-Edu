"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Button, ErrorText, Field, Input, Select } from "@/components/ui";
import { api, type Level } from "@/lib/api";

/** Used by staff (office applications) and by the public /apply page. */
export function ApplicationForm({
  onDone,
  levels,
  submit,
}: {
  onDone: (reference?: string) => void;
  levels?: { id: number; name: string }[];
  submit?: (body: Record<string, unknown>) => Promise<{ reference?: string }>;
}) {
  const client = useQueryClient();
  const staffLevels = useQuery({
    queryKey: ["levels"],
    queryFn: () => api.get<Level[]>("/api/v1/academics/levels"),
    enabled: !levels,
  });
  const options = levels ?? (staffLevels.data ?? []).filter((l) => l.is_active);
  const send = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      submit ? submit(body) : api.post<{ reference: string }>("/api/v1/admissions/applications", body),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["applications"] });
      onDone(data?.reference);
    },
  });
  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    send.mutate({ ...f, desired_level: Number(f.desired_level) });
  };
  return (
    <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2">
      <Field label="Pupil's first name">
        <Input name="first_name" required />
      </Field>
      <Field label="Pupil's last name">
        <Input name="last_name" required />
      </Field>
      <Field label="Date of birth">
        <Input name="date_of_birth" type="date" required />
      </Field>
      <Field label="Gender">
        <Select name="gender">
          <option value="female">Female</option>
          <option value="male">Male</option>
        </Select>
      </Field>
      <Field label="Class applying for">
        <Select name="desired_level" required>
          {options.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Previous school">
        <Input name="previous_school" />
      </Field>
      <Field label="Parent / guardian name">
        <Input name="guardian_name" required />
      </Field>
      <Field label="Parent's mobile number" hint="e.g. 024 412 3456">
        <Input name="guardian_phone" inputMode="tel" required />
      </Field>
      <Field label="Parent's email (optional)">
        <Input name="guardian_email" type="email" />
      </Field>
      <Field label="Relationship">
        <Input name="guardian_relationship" defaultValue="parent" />
      </Field>
      {/* Honeypot: hidden from people, often filled by bots. */}
      <input name="website" tabIndex={-1} autoComplete="off" className="hidden" aria-hidden="true" />
      <div className="sm:col-span-2">
        <ErrorText error={send.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={send.isPending}>
          Submit application
        </Button>
      </div>
    </form>
  );
}
