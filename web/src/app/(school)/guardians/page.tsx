"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Empty,
  ErrorText,
  Input,
  Loading,
  PageHeader,
  Select,
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useArms, useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Guardian = {
  key: string;
  name: string;
  phone: string;
  email: string;
  has_login: boolean;
  receives_sms: boolean;
  children: { id: string; name: string; class: string; relationship: string }[];
};

/**
 * Every parent and guardian, listed once with all their children. Teachers see
 * the families of their own classes.
 */
export default function GuardiansPage() {
  const client = useQueryClient();
  const { can } = useSchool();
  const canInvite = can(PERM.MEMBERS_MANAGE, PERM.STUDENTS_MANAGE, PERM.ADMISSIONS_MANAGE);
  const wholeSchool = can(PERM.STUDENTS_MANAGE);
  const arms = useArms(!wholeSchool);
  const [q, setQ] = useState("");
  const [arm, setArm] = useState("");
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (arm) params.set("arm", arm);
  const guardians = useQuery({
    queryKey: ["guardians", q.trim(), arm],
    queryFn: () => api.get<Guardian[]>(`/api/v1/guardians?${params}`),
    placeholderData: keepPreviousData,
  });
  const invite = useMutation({
    mutationFn: (key: string) => api.post<{ linked_children: number }>("/api/v1/guardians", { key }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["guardians"] }),
  });

  return (
    <>
      <PageHeader
        title="Guardians"
        description="Parents and guardians, each listed once with all their children."
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_14rem]">
        <Input
          type="search"
          placeholder="Search by guardian, phone, email or pupil…"
          aria-label="Search guardians"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select value={arm} onChange={(e) => setArm(e.target.value)} aria-label="Class">
          <option value="">All classes</option>
          {arms.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </Select>
      </div>
      {invite.isSuccess && (
        <div className="mb-3">
          <Alert tone="success">
            Invitation sent. They'll see {invite.data.linked_children} child
            {invite.data.linked_children === 1 ? "" : "ren"} when they sign in.
          </Alert>
        </div>
      )}
      <ErrorText error={invite.error} />
      {guardians.isPending ? (
        <Loading />
      ) : guardians.error ? (
        <ErrorText error={guardians.error} />
      ) : !guardians.data.length ? (
        <Empty>No guardians found. Add them on a pupil's page.</Empty>
      ) : (
        <Table head={["Guardian", "Contact", "Children", "Nex Edu", ""]}>
          {guardians.data.map((g) => (
            <tr key={g.key}>
              <Td className="font-medium">{g.name || "No name given"}</Td>
              <Td className="text-xs">
                {g.phone || "—"}
                {g.email && <span className="block text-neutral-500">{g.email}</span>}
                {!g.receives_sms && <span className="block text-neutral-500">No SMS</span>}
              </Td>
              <Td>
                <ul className="grid gap-0.5 text-sm">
                  {g.children.map((c) => (
                    <li key={c.id}>
                      <Link href={`/students/${c.id}`} className="hover:underline">
                        {c.name}
                      </Link>
                      <span className="text-xs text-neutral-500">
                        {" "}
                        · {c.class || "no class"} · {c.relationship}
                      </span>
                    </li>
                  ))}
                </ul>
              </Td>
              <Td>
                {g.has_login ? <Badge tone="green">Has a login</Badge> : <Badge tone="grey">No login</Badge>}
              </Td>
              <Td>
                {canInvite && !g.has_login && g.email && (
                  <Button
                    variant="secondary"
                    busy={invite.isPending && invite.variables === g.key}
                    onClick={() => invite.mutate(g.key)}
                    aria-label={`Invite ${g.name || g.email} to Nex Edu`}
                  >
                    Invite to Nex Edu
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
