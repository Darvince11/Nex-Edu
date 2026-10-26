"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert, Button, Card, Empty, ErrorText, Loading, Modal, PageHeader, Select } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Plan = {
  session: string | null;
  already_run_at: string | null;
  classes: {
    arm: string;
    label: string;
    to: string | null;
    default: "promote" | "graduate";
    pupils: { id: string; name: string; admission_number: string }[];
  }[];
};
type Action = "promote" | "repeat" | "graduate" | "leave";
type Result = { summary: { promoted: number; repeated: number; graduated: number; left: number } };

/**
 * End of year: every class moves up a level (JHS 1 A → JHS 2 A) and the top class
 * graduates. Keep a pupil back or mark them as leaving before you apply.
 */
export default function PromotionPage() {
  const client = useQueryClient();
  const plan = useQuery({ queryKey: ["promotion"], queryFn: () => api.get<Plan>("/api/v1/promotion") });
  const [overrides, setOverrides] = useState<Record<string, Action>>({});
  const [confirming, setConfirming] = useState(false);
  const apply = useMutation({
    mutationFn: (confirm: boolean) => api.post<Result>("/api/v1/promotion", { overrides, confirm }),
    onSuccess: () => {
      setConfirming(false);
      setOverrides({});
      void client.invalidateQueries({ queryKey: ["promotion"] });
      void client.invalidateQueries({ queryKey: ["students"] });
    },
  });

  if (plan.isPending) return <Loading />;
  if (plan.error) return <ErrorText error={plan.error} />;
  const p = plan.data;
  const actionFor = (cls: Plan["classes"][number], id: string): Action => overrides[id] ?? cls.default;
  const totals = { promote: 0, repeat: 0, graduate: 0, leave: 0 };
  for (const cls of p.classes) for (const pupil of cls.pupils) totals[actionFor(cls, pupil.id)] += 1;
  const twice = apply.error instanceof ApiError && apply.error.status === 409;

  return (
    <>
      <PageHeader
        title="End of year"
        description="Move every class up a level and graduate the top class. Choose who repeats or leaves first."
        actions={
          p.classes.length > 0 && (
            <Button onClick={() => setConfirming(true)} disabled={apply.isPending}>
              Move pupils up
            </Button>
          )
        }
      />
      {p.already_run_at && (
        <div className="mb-4">
          <Alert tone="warning">
            Pupils were already moved up for {p.session} on {formatDate(p.already_run_at)}. Only do it again
            if that was a mistake you've undone.
          </Alert>
        </div>
      )}
      {apply.isSuccess && (
        <div className="mb-4">
          <Alert tone="success">
            Done: {apply.data.summary.promoted} moved up, {apply.data.summary.graduated} graduated,{" "}
            {apply.data.summary.repeated} repeating, {apply.data.summary.left} left.
          </Alert>
        </div>
      )}
      {!p.classes.length ? (
        <Empty>No pupils in any class.</Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {p.classes.map((cls) => (
            <Card key={cls.arm} title={`${cls.label} → ${cls.to ?? "Graduate"}`}>
              <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
                {cls.pupils.map((pupil) => (
                  <li key={pupil.id} className="flex items-center justify-between gap-2 py-1.5">
                    <span className="min-w-0 truncate">
                      {pupil.name}
                      <span className="ml-1 font-mono text-xs text-neutral-500">
                        {pupil.admission_number}
                      </span>
                    </span>
                    <Select
                      aria-label={`What happens to ${pupil.name}`}
                      className="w-36"
                      value={actionFor(cls, pupil.id)}
                      onChange={(e) => setOverrides((o) => ({ ...o, [pupil.id]: e.target.value as Action }))}
                    >
                      {cls.to && <option value="promote">Move up</option>}
                      <option value="repeat">Repeat</option>
                      {!cls.to && <option value="graduate">Graduate</option>}
                      <option value="leave">Leaves school</option>
                    </Select>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}

      <Modal open={confirming} onClose={() => setConfirming(false)} title="Move pupils up?">
        <div className="grid gap-3 text-sm">
          <p>
            {totals.promote} move up, {totals.graduate} graduate, {totals.repeat} repeat and {totals.leave}{" "}
            leave. Report cards and registers stay with the class they were in.
          </p>
          {twice && (
            <Alert tone="warning">
              {apply.error instanceof ApiError ? apply.error.message : ""} Press "Move them anyway" to go
              ahead.
            </Alert>
          )}
          {!twice && <ErrorText error={apply.error} />}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Not yet
            </Button>
            <Button busy={apply.isPending} onClick={() => apply.mutate(twice || Boolean(p.already_run_at))}>
              {twice ? "Move them anyway" : "Move pupils up"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
