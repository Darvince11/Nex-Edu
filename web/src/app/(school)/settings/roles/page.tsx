"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Forbidden,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Person = { id: string; name: string; email: string };
type CustomRole = {
  id: string;
  name: string;
  description: string;
  permissions: string[];
  holders: Person[];
};
type Catalogue = { code: string; group: string; label: string }[];
type RolesData = { roles: CustomRole[]; catalogue: Catalogue; staff: Person[] };

const KEY = ["custom-roles"];

/** The school's own roles, such as Exams officer: extra permissions for staff. Proprietor only. */
export default function CustomRolesPage() {
  const { can } = useSchool();
  const data = useQuery({
    queryKey: KEY,
    queryFn: () => api.get<RolesData>("/api/v1/school/roles"),
    enabled: can(PERM.MEMBERS_MANAGE),
  });
  const [editing, setEditing] = useState<CustomRole | "new" | null>(null);

  if (!can(PERM.MEMBERS_MANAGE)) {
    return <Forbidden title="Custom roles">Only the proprietor sets up custom roles.</Forbidden>;
  }
  return (
    <>
      <PageHeader
        title="Custom roles"
        description="Give staff extra responsibilities, such as Exams officer or Head of year, on top of their own role."
        actions={<Button onClick={() => setEditing("new")}>New role</Button>}
      />
      <div className="mb-4">
        <Alert>
          A custom role adds to what someone can already do. It can't change the school's logo, terms or
          modules, give anyone access, or amend published scores; those stay with you.
        </Alert>
      </div>
      <ErrorText error={data.error} />
      {data.isPending ? (
        <Loading />
      ) : data.data?.roles.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.data.roles.map((role) => (
            <RoleCard
              key={role.id}
              role={role}
              catalogue={data.data.catalogue}
              staff={data.data.staff}
              onEdit={() => setEditing(role)}
            />
          ))}
        </div>
      ) : (
        <Empty>No custom roles yet. Make one for a job that doesn't fit the usual roles.</Empty>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New custom role" : "Change role"}
      >
        {editing !== null && data.data && (
          <RoleForm
            role={editing === "new" ? null : editing}
            catalogue={data.data.catalogue}
            onDone={() => setEditing(null)}
          />
        )}
      </Modal>
    </>
  );
}

function RoleCard({
  role,
  catalogue,
  staff,
  onEdit,
}: {
  role: CustomRole;
  catalogue: Catalogue;
  staff: Person[];
  onEdit: () => void;
}) {
  const client = useQueryClient();
  const [person, setPerson] = useState("");
  const refresh = () => void client.invalidateQueries({ queryKey: KEY });
  const give = useMutation({
    mutationFn: () => api.post(`/api/v1/school/roles/${role.id}/holders`, { user: person }),
    onSuccess: () => {
      setPerson("");
      refresh();
    },
  });
  const takeAway = useMutation({
    mutationFn: (user: string) => api.del(`/api/v1/school/roles/${role.id}/holders?user=${user}`),
    onSuccess: refresh,
  });
  const labels = catalogue.filter((c) => role.permissions.includes(c.code));
  const holderIds = new Set(role.holders.map((h) => h.id));
  const candidates = staff.filter((s) => !holderIds.has(s.id));

  return (
    <Card
      title={role.name}
      actions={
        <Button variant="secondary" onClick={onEdit}>
          Change
        </Button>
      }
    >
      {role.description && (
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">{role.description}</p>
      )}
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-neutral-600 dark:text-neutral-400">
        Can
      </h3>
      <ul className="mb-4 list-disc space-y-0.5 pl-5 text-sm">
        {labels.map((c) => (
          <li key={c.code}>{c.label}</li>
        ))}
      </ul>
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-neutral-600 dark:text-neutral-400">
        Held by
      </h3>
      {role.holders.length ? (
        <ul className="mb-3 divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
          {role.holders.map((h) => (
            <li key={h.id} className="flex items-center justify-between gap-2 py-1.5">
              <span>
                <span className="font-medium">{h.name}</span>{" "}
                <span className="text-neutral-600 dark:text-neutral-400">{h.email}</span>
              </span>
              <Button
                variant="ghost"
                busy={takeAway.isPending && takeAway.variables === h.id}
                onClick={() => takeAway.mutate(h.id)}
                aria-label={`Take ${role.name} away from ${h.name}`}
              >
                Take away
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">Nobody yet.</p>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (person) give.mutate();
        }}
      >
        <div className="min-w-48 flex-1">
          <Field label={`Give ${role.name} to`}>
            <Select value={person} onChange={(e) => setPerson(e.target.value)}>
              <option value="">Choose a member of staff</option>
              {candidates.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.email})
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button type="submit" variant="secondary" busy={give.isPending} disabled={!person}>
          Give role
        </Button>
      </form>
      <ErrorText error={give.error ?? takeAway.error} />
    </Card>
  );
}

function RoleForm({
  role,
  catalogue,
  onDone,
}: {
  role: CustomRole | null;
  catalogue: Catalogue;
  onDone: () => void;
}) {
  const client = useQueryClient();
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const done = () => {
    void client.invalidateQueries({ queryKey: KEY });
    onDone();
  };
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      role ? api.patch(`/api/v1/school/roles/${role.id}`, body) : api.post("/api/v1/school/roles", body),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/school/roles/${role?.id}`),
    onSuccess: done,
  });
  const groups = [...new Set(catalogue.map((c) => c.group))];
  const toggle = (code: string) =>
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({ name: f.name, description: f.description, permissions: [...chosen] });
  };
  const fieldError = save.error instanceof ApiError ? save.error : null;

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Name" hint='For example "Exams officer" or "Head of year".'>
        <Input name="name" required maxLength={60} defaultValue={role?.name} />
      </Field>
      <Field label="What it's for (optional)">
        <Input name="description" maxLength={200} defaultValue={role?.description} />
      </Field>
      {groups.map((group) => (
        <fieldset
          key={group}
          className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
        >
          <legend className="px-1 text-sm font-medium">{group}</legend>
          <div className="flex flex-col gap-1.5">
            {catalogue
              .filter((c) => c.group === group)
              .map((c) => (
                <label key={c.code} className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4 accent-brand"
                    checked={chosen.has(c.code)}
                    onChange={() => toggle(c.code)}
                  />
                  {c.label}
                </label>
              ))}
          </div>
        </fieldset>
      ))}
      <ErrorText error={fieldError ?? save.error ?? remove.error} />
      <div className="flex justify-between gap-2">
        {role ? (
          confirmDelete ? (
            <Button type="button" variant="danger" busy={remove.isPending} onClick={() => remove.mutate()}>
              Delete for {role.holders.length === 1 ? "1 person" : `${role.holders.length} people`}
            </Button>
          ) : (
            <Button type="button" variant="secondary" onClick={() => setConfirmDelete(true)}>
              Delete role
            </Button>
          )
        ) : (
          <span />
        )}
        <Button type="submit" busy={save.isPending} disabled={chosen.size === 0}>
          Save role
        </Button>
      </div>
    </form>
  );
}
