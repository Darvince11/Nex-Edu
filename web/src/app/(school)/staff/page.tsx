"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
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
import { api, type Department, type StaffMember } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

/**
 * Everyone who works at the school. Staff with a login appear automatically;
 * staff without one (cooks, cleaners, security) are added here.
 */
export default function StaffPage() {
  const { can } = useSchool();
  const manage = can(PERM.STAFF_MANAGE);
  const [q, setQ] = useState("");
  const [department, setDepartment] = useState("");
  const [editing, setEditing] = useState<StaffMember | "new" | null>(null);
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (department) params.set("department", department);
  const staff = useQuery({
    queryKey: ["staff", q.trim(), department],
    queryFn: () => api.get<StaffMember[]>(`/api/v1/staff?${params}`),
    placeholderData: keepPreviousData,
  });
  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.get<Department[]>("/api/v1/staff/departments"),
  });

  return (
    <>
      <PageHeader
        title="Staff"
        description="Everyone who works at the school. Staff with a Nex Edu login are listed automatically."
        actions={manage && <Button onClick={() => setEditing("new")}>Add staff member</Button>}
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_14rem]">
        <Input
          type="search"
          placeholder="Search by name, staff number or job…"
          aria-label="Search staff"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select value={department} onChange={(e) => setDepartment(e.target.value)} aria-label="Department">
          <option value="">All departments</option>
          {departments.data?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
        <div className="min-w-0">
          {staff.isPending ? (
            <Loading />
          ) : staff.error ? (
            <ErrorText error={staff.error} />
          ) : !staff.data.length ? (
            <Empty>No staff found.</Empty>
          ) : (
            <Table head={["Name", "Staff no.", "Job", "Department", "Contact", "Started", ""]}>
              {staff.data.map((s) => (
                <tr key={s.id} className={s.is_active ? "" : "opacity-60"}>
                  <Td>
                    <span className="font-medium">
                      {s.first_name} {s.last_name}
                    </span>
                    <span className="mt-0.5 block">
                      {s.user_id ? (
                        <Badge tone="blue">Has a login</Badge>
                      ) : (
                        <Badge tone="grey">No login</Badge>
                      )}
                      {!s.is_active && (
                        <span className="ml-1">
                          <Badge tone="red">Left</Badge>
                        </span>
                      )}
                    </span>
                  </Td>
                  <Td className="font-mono text-xs">{s.staff_number}</Td>
                  <Td>{s.job_title || "—"}</Td>
                  <Td>{s.department_name || "—"}</Td>
                  <Td className="text-xs">
                    {s.phone || "—"}
                    {s.email && <span className="block text-neutral-500">{s.email}</span>}
                  </Td>
                  <Td className="whitespace-nowrap">{formatDate(s.employment_date)}</Td>
                  <Td>
                    {manage && (
                      <Button
                        variant="ghost"
                        onClick={() => setEditing(s)}
                        aria-label={`Edit ${s.first_name} ${s.last_name}`}
                      >
                        Edit
                      </Button>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
        <Departments manage={manage} departments={departments.data ?? []} />
      </div>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add a staff member" : "Edit staff member"}
      >
        {editing && (
          <StaffForm
            member={editing === "new" ? null : editing}
            departments={departments.data ?? []}
            onDone={() => setEditing(null)}
          />
        )}
      </Modal>
    </>
  );
}

function Departments({ manage, departments }: { manage: boolean; departments: Department[] }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const add = useMutation({
    mutationFn: () => api.post("/api/v1/staff/departments", { name: name.trim() }),
    onSuccess: () => {
      setName("");
      void client.invalidateQueries({ queryKey: ["departments"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/staff/departments/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["departments"] });
      void client.invalidateQueries({ queryKey: ["staff"] });
    },
  });
  return (
    <Card title="Departments">
      {departments.length ? (
        <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
          {departments.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 py-1.5">
              <span>
                {d.name} <span className="text-xs text-neutral-500">· {d.staff_count}</span>
              </span>
              {manage && d.staff_count === 0 && (
                <Button variant="ghost" onClick={() => remove.mutate(d.id)} aria-label={`Delete ${d.name}`}>
                  Delete
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-neutral-500">No departments yet.</p>
      )}
      {manage && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (name.trim()) add.mutate();
          }}
        >
          <Input
            aria-label="New department"
            placeholder="e.g. JHS Science"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
          />
          <Button type="submit" variant="secondary" busy={add.isPending}>
            Add
          </Button>
        </form>
      )}
      <ErrorText error={add.error ?? remove.error} />
    </Card>
  );
}

function StaffForm({
  member,
  departments,
  onDone,
}: {
  member: StaffMember | null;
  departments: Department[];
  onDone: () => void;
}) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      member ? api.patch(`/api/v1/staff/${member.id}`, body) : api.post("/api/v1/staff", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["staff"] });
      void client.invalidateQueries({ queryKey: ["departments"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      ...f,
      department: f.department || null,
      employment_date: f.employment_date || null,
      is_active: f.is_active === "on",
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="First name">
        <Input name="first_name" required defaultValue={member?.first_name} maxLength={80} />
      </Field>
      <Field label="Last name">
        <Input name="last_name" required defaultValue={member?.last_name} maxLength={80} />
      </Field>
      <Field label="Job title">
        <Input
          name="job_title"
          defaultValue={member?.job_title}
          placeholder="e.g. Science teacher"
          maxLength={80}
        />
      </Field>
      <Field label="Department">
        <Select name="department" defaultValue={member?.department ?? ""}>
          <option value="">None</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Phone">
        <Input name="phone" type="tel" defaultValue={member?.phone} maxLength={20} />
      </Field>
      <Field label="Email">
        <Input name="email" type="email" defaultValue={member?.email} />
      </Field>
      <Field label="Gender">
        <Select name="gender" defaultValue={member?.gender ?? ""}>
          <option value="">Not given</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
        </Select>
      </Field>
      <Field label="Started on">
        <Input name="employment_date" type="date" defaultValue={member?.employment_date ?? ""} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Qualification">
          <Input
            name="qualification"
            defaultValue={member?.qualification}
            placeholder="e.g. B.Ed. Mathematics"
          />
        </Field>
      </div>
      <Field label="Bank" hint="For payroll. Only leaders see this.">
        <Input name="bank_name" defaultValue={member?.bank_name} />
      </Field>
      <Field label="Account number" hint="Stored encrypted.">
        <Input name="bank_account_number" defaultValue={member?.bank_account_number} inputMode="numeric" />
      </Field>
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input
          type="checkbox"
          name="is_active"
          defaultChecked={member?.is_active ?? true}
          className="size-4 accent-brand"
        />
        Works at the school now (untick when someone leaves)
      </label>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          {member ? "Save changes" : "Add staff member"}
        </Button>
      </div>
    </form>
  );
}
