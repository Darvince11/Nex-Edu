"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  Alert,
  Badge,
  Button,
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
import { api, type Member } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { ROLE_LABELS, type Role } from "@/lib/roles";

export default function PeoplePage() {
  const client = useQueryClient();
  const [role, setRole] = useState("");
  const [inviting, setInviting] = useState(false);
  const members = useQuery({
    queryKey: ["members", role],
    queryFn: () => api.get<Member[]>(`/api/v1/members${role ? `?role=${role}` : ""}`),
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      api.post(`/api/v1/members/${id}/${action}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["members"] }),
  });

  return (
    <>
      <PageHeader
        title="People"
        description="Staff, parents and students with a Nex Edu login at this school."
        actions={<Button onClick={() => setInviting(true)}>Invite someone</Button>}
      />
      <div className="mb-4 w-56">
        <Select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
          <option value="">Everyone</option>
          {Object.entries(ROLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <ErrorText error={members.error ?? act.error} />
      {act.isSuccess && act.variables.action === "resend_invite" && (
        <Alert tone="success">Invitation sent again.</Alert>
      )}
      {members.isPending ? (
        <Loading />
      ) : members.data?.length ? (
        <Table head={["Name", "Role", "Contact", "Security", "Last sign-in", ""]}>
          {members.data.map((m) => (
            <tr key={m.id} className={m.is_active ? "" : "opacity-50"}>
              <Td className="font-medium">{`${m.first_name} ${m.last_name}`.trim() || "—"}</Td>
              <Td>{m.role_label}</Td>
              <Td>
                {m.email}
                <div className="text-xs text-neutral-500">{m.phone}</div>
              </Td>
              <Td>
                {!m.has_password ? (
                  <Badge tone="amber">invited</Badge>
                ) : m.mfa_enrolled ? (
                  <Badge tone="green">MFA on</Badge>
                ) : (
                  <Badge tone="grey">password only</Badge>
                )}
              </Td>
              <Td>{formatDate(m.last_login)}</Td>
              <Td className="whitespace-nowrap">
                {!m.has_password && m.is_active && (
                  <Button variant="ghost" onClick={() => act.mutate({ id: m.id, action: "resend_invite" })}>
                    Resend invite
                  </Button>
                )}
                <Button
                  variant="ghost"
                  onClick={() => act.mutate({ id: m.id, action: m.is_active ? "deactivate" : "activate" })}
                >
                  {m.is_active ? "Remove access" : "Restore access"}
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Nobody yet.</Empty>
      )}
      <Modal open={inviting} onClose={() => setInviting(false)} title="Invite someone">
        <Invite onDone={() => setInviting(false)} />
      </Modal>
    </>
  );
}

function Invite({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const invite = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/members", body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["members"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    invite.mutate(Object.fromEntries(new FormData(e.currentTarget)));
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="First name">
        <Input name="first_name" />
      </Field>
      <Field label="Last name">
        <Input name="last_name" />
      </Field>
      <Field label="Email">
        <Input name="email" type="email" required />
      </Field>
      <Field label="Mobile (optional)">
        <Input name="phone" inputMode="tel" placeholder="024 412 3456" />
      </Field>
      <Field label="Role">
        <Select name="role" defaultValue="teacher">
          {(Object.entries(ROLE_LABELS) as [Role, string][]).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <p className="self-end text-xs text-neutral-500">
        They'll get an email to set a password. You can't give anyone more access than you have.
      </p>
      <div className="sm:col-span-2">
        <ErrorText error={invite.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={invite.isPending}>
          Send invitation
        </Button>
      </div>
    </form>
  );
}
