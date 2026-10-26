"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  Textarea,
} from "@/components/ui";
import { api, type LeaveRequest } from "@/lib/api";
import { formatDate, todayInAccra } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

const KINDS: [string, string][] = [
  ["annual", "Annual leave"],
  ["sick", "Sick leave"],
  ["maternity", "Maternity leave"],
  ["paternity", "Paternity leave"],
  ["study", "Study leave"],
  ["compassionate", "Compassionate leave"],
  ["other", "Other"],
];
const TONE: Record<LeaveRequest["status"], "amber" | "green" | "red" | "grey"> = {
  pending: "amber",
  approved: "green",
  rejected: "red",
  cancelled: "grey",
};
const PATH = "/api/v1/staff/leave";

/** Staff ask for leave here; the head teacher, administrator or proprietor decides. */
export default function LeavePage() {
  const { can } = useSchool();
  const approver = can(PERM.STAFF_MANAGE);
  const [asking, setAsking] = useState(false);
  const mine = useQuery({
    queryKey: ["leave", "mine"],
    queryFn: () => api.get<LeaveRequest[]>(`${PATH}?mine=1`),
  });

  return (
    <>
      <PageHeader
        title="Leave"
        description={
          approver
            ? "Ask for leave, and approve or reject requests from staff."
            : "Ask for leave and follow your requests."
        }
        actions={<Button onClick={() => setAsking(true)}>Ask for leave</Button>}
      />
      {approver && <Approvals />}
      <Card title="My requests">
        {mine.isPending ? (
          <Loading />
        ) : mine.error ? (
          <ErrorText error={mine.error} />
        ) : mine.data.length ? (
          <LeaveTable rows={mine.data} />
        ) : (
          <Empty>You haven't asked for leave.</Empty>
        )}
      </Card>
      <Modal open={asking} onClose={() => setAsking(false)} title="Ask for leave">
        <AskForLeave onDone={() => setAsking(false)} />
      </Modal>
    </>
  );
}

function LeaveTable({ rows, decide }: { rows: LeaveRequest[]; decide?: (r: LeaveRequest) => void }) {
  const client = useQueryClient();
  const cancel = useMutation({
    mutationFn: (id: string) => api.post(`${PATH}/${id}/cancel`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["leave"] }),
  });
  const today = todayInAccra();
  return (
    <>
      <ErrorText error={cancel.error} />
      <Table head={[...(decide ? ["Staff"] : []), "Kind", "From", "To", "Days", "Status", ""]}>
        {rows.map((r) => (
          <tr key={r.id}>
            {decide && <Td className="font-medium">{r.staff_name}</Td>}
            <Td>
              {r.kind_label}
              {r.reason && <span className="block text-xs text-neutral-500">{r.reason}</span>}
            </Td>
            <Td className="whitespace-nowrap">{formatDate(r.start)}</Td>
            <Td className="whitespace-nowrap">{formatDate(r.end)}</Td>
            <Td className="tabular-nums">{r.days}</Td>
            <Td>
              <Badge tone={TONE[r.status]}>{r.status_label}</Badge>
              {r.decision_note && <span className="block text-xs text-neutral-500">{r.decision_note}</span>}
            </Td>
            <Td className="whitespace-nowrap">
              {decide && r.status === "pending" && !r.mine && (
                <Button variant="secondary" onClick={() => decide(r)}>
                  Decide
                </Button>
              )}
              {r.mine && (r.status === "pending" || (r.status === "approved" && r.start > today)) && (
                <Button variant="ghost" busy={cancel.isPending} onClick={() => cancel.mutate(r.id)}>
                  Cancel
                </Button>
              )}
            </Td>
          </tr>
        ))}
      </Table>
    </>
  );
}

function Approvals() {
  const [deciding, setDeciding] = useState<LeaveRequest | null>(null);
  const waiting = useQuery({
    queryKey: ["leave", "pending"],
    queryFn: () => api.get<LeaveRequest[]>(`${PATH}?status=pending`),
  });
  const others = (waiting.data ?? []).filter((r) => !r.mine);
  return (
    <div className="mb-6">
      <Card title={`Waiting for approval${others.length ? ` (${others.length})` : ""}`}>
        {waiting.isPending ? (
          <Loading />
        ) : others.length ? (
          <LeaveTable rows={others} decide={setDeciding} />
        ) : (
          <Empty>No requests are waiting.</Empty>
        )}
      </Card>
      <Modal
        open={Boolean(deciding)}
        onClose={() => setDeciding(null)}
        title={`Leave for ${deciding?.staff_name ?? ""}`}
      >
        {deciding && <Decide request={deciding} onDone={() => setDeciding(null)} />}
      </Modal>
    </div>
  );
}

function Decide({ request, onDone }: { request: LeaveRequest; onDone: () => void }) {
  const client = useQueryClient();
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: (approve: boolean) => api.post(`${PATH}/${request.id}/decide`, { approve, note }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["leave"] });
      onDone();
    },
  });
  return (
    <div className="grid gap-3 text-sm">
      <p>
        {request.kind_label}, {request.days} working day{request.days === 1 ? "" : "s"}:{" "}
        {formatDate(request.start)} to {formatDate(request.end)}.
      </p>
      {request.reason && <p className="text-neutral-600 dark:text-neutral-300">“{request.reason}”</p>}
      <Field label="Note to the staff member" hint="Required when you reject.">
        <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
      </Field>
      <ErrorText error={decide.error} />
      <div className="flex justify-end gap-2">
        <Button
          variant="secondary"
          busy={decide.isPending && decide.variables === false}
          onClick={() => decide.mutate(false)}
        >
          Reject
        </Button>
        <Button busy={decide.isPending && decide.variables === true} onClick={() => decide.mutate(true)}>
          Approve
        </Button>
      </div>
    </div>
  );
}

function AskForLeave({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const ask = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post(PATH, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["leave"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    ask.mutate(Object.fromEntries(new FormData(e.currentTarget)));
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field label="Kind of leave">
          <Select name="kind" defaultValue="annual">
            {KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="First day">
        <Input name="start" type="date" required min={todayInAccra()} />
      </Field>
      <Field label="Last day">
        <Input name="end" type="date" required min={todayInAccra()} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Reason (optional)">
          <Textarea name="reason" rows={3} maxLength={500} />
        </Field>
      </div>
      <p className="text-xs text-neutral-500 sm:col-span-2">
        Only working days (Monday to Friday) are counted. The head teacher is told straight away.
      </p>
      <div className="sm:col-span-2">
        <ErrorText error={ask.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={ask.isPending}>
          Send request
        </Button>
      </div>
    </form>
  );
}
