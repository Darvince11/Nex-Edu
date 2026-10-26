"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  PageHeader,
  Table,
  Td,
} from "@/components/ui";
import { api, type StaffRegisterRow } from "@/lib/api";
import { todayInAccra } from "@/lib/format";

type Status = NonNullable<StaffRegisterRow["status"]>;
const STATUSES: [Status, string][] = [
  ["present", "Present"],
  ["late", "Late"],
  ["absent", "Absent"],
  ["on_leave", "On leave"],
  ["excused", "Excused"],
];
type Mark = { status: Status | null; time_in: string; note: string };
type Summary = {
  start: string;
  end: string;
  rows: {
    staff: string;
    name: string;
    present: number;
    late: number;
    absent: number;
    on_leave: number;
    excused: number;
  }[];
};

/** The daily staff register, taken by the head teacher or administrator. */
export default function StaffAttendancePage() {
  const client = useQueryClient();
  const [date, setDate] = useState(todayInAccra());
  const [marks, setMarks] = useState<Record<string, Mark>>({});
  const register = useQuery({
    queryKey: ["staff-register", date],
    queryFn: () => api.get<{ rows: StaffRegisterRow[] }>(`/api/v1/staff-register?date=${date}`),
  });
  const summary = useQuery({
    queryKey: ["staff-register-summary"],
    queryFn: () => api.get<Summary>("/api/v1/staff-register/summary"),
  });

  useEffect(() => {
    if (register.data) {
      setMarks(
        Object.fromEntries(
          register.data.rows.map((r) => [r.staff, { status: r.status, time_in: r.time_in, note: r.note }]),
        ),
      );
    }
  }, [register.data]);

  const save = useMutation({
    mutationFn: () =>
      api.post("/api/v1/staff-register", {
        date,
        entries: Object.entries(marks)
          .filter(([, m]) => m.status)
          .map(([staff, m]) => ({ staff, status: m.status, time_in: m.time_in || null, note: m.note })),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["staff-register"] });
      void client.invalidateQueries({ queryKey: ["staff-register-summary"] });
    },
  });
  const set = (staff: string, patch: Partial<Mark>) => {
    save.reset();
    setMarks((m) => ({
      ...m,
      [staff]: { ...(m[staff] ?? { status: null, time_in: "", note: "" }), ...patch },
    }));
  };
  const markAllPresent = () =>
    setMarks((m) =>
      Object.fromEntries(
        Object.entries(m).map(([k, v]) => [k, v.status ? v : { ...v, status: "present" as Status }]),
      ),
    );
  const unmarked = Object.values(marks).filter((m) => !m.status).length;

  return (
    <>
      <PageHeader
        title="Staff attendance"
        description="Who came to work today. Approved leave is filled in for you."
        actions={
          <div className="w-44">
            <Field label="Day">
              <Input
                type="date"
                value={date}
                max={todayInAccra()}
                onChange={(e) => setDate(e.target.value)}
              />
            </Field>
          </div>
        }
      />
      {register.isPending ? (
        <Loading />
      ) : register.error ? (
        <ErrorText error={register.error} />
      ) : !register.data.rows.length ? (
        <Empty>No staff yet. Add staff on the Staff page.</Empty>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-neutral-600 dark:text-neutral-300">
              {unmarked ? `${unmarked} not marked yet.` : "Everyone is marked."}
            </p>
            {unmarked > 0 && (
              <Button variant="secondary" onClick={markAllPresent}>
                Mark the rest present
              </Button>
            )}
          </div>
          <Table head={["Name", "Status", "Arrived", "Note"]}>
            {register.data.rows.map((r) => {
              const m = marks[r.staff] ?? { status: null, time_in: "", note: "" };
              return (
                <tr key={r.staff}>
                  <Td>
                    <span className="font-medium">{r.name}</span>
                    <span className="block text-xs text-neutral-500">
                      {[r.job_title, r.department].filter(Boolean).join(" · ") || r.staff_number}
                    </span>
                  </Td>
                  <Td>
                    <fieldset className="flex flex-wrap gap-1">
                      <legend className="sr-only">Status for {r.name}</legend>
                      {STATUSES.map(([value, label]) => (
                        <label
                          key={value}
                          className={`cursor-pointer rounded-control border px-2 py-1 text-xs has-focus-visible:outline-2 has-focus-visible:outline-brand ${
                            m.status === value
                              ? "border-brand bg-brand text-white"
                              : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                          }`}
                        >
                          <input
                            type="radio"
                            name={`status-${r.staff}`}
                            value={value}
                            checked={m.status === value}
                            onChange={() => set(r.staff, { status: value })}
                            className="sr-only"
                          />
                          {label}
                        </label>
                      ))}
                    </fieldset>
                  </Td>
                  <Td>
                    <Input
                      type="time"
                      aria-label={`Time ${r.name} arrived`}
                      value={m.time_in}
                      onChange={(e) => set(r.staff, { time_in: e.target.value })}
                      className="w-28"
                    />
                  </Td>
                  <Td>
                    <Input
                      aria-label={`Note for ${r.name}`}
                      value={m.note}
                      onChange={(e) => set(r.staff, { note: e.target.value })}
                      maxLength={200}
                    />
                  </Td>
                </tr>
              );
            })}
          </Table>
          <div className="mt-3 flex flex-wrap items-center justify-end gap-3">
            {save.isSuccess && (
              <span role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
                Register saved
              </span>
            )}
            <ErrorText error={save.error} />
            <Button busy={save.isPending} onClick={() => save.mutate()}>
              Save register
            </Button>
          </div>
        </>
      )}

      <div className="mt-6">
        <Card title="This month">
          {summary.data?.rows.length ? (
            <Table head={["Name", "Present", "Late", "Absent", "On leave", "Excused"]}>
              {summary.data.rows.map((r) => (
                <tr key={r.staff}>
                  <Td>{r.name}</Td>
                  <Td className="tabular-nums">{r.present}</Td>
                  <Td className="tabular-nums">{r.late}</Td>
                  <Td
                    className={`tabular-nums ${r.absent ? "font-medium text-red-700 dark:text-red-400" : ""}`}
                  >
                    {r.absent}
                  </Td>
                  <Td className="tabular-nums">{r.on_leave}</Td>
                  <Td className="tabular-nums">{r.excused}</Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Alert tone="info">No staff registers taken this month yet.</Alert>
          )}
        </Card>
      </div>
    </>
  );
}
