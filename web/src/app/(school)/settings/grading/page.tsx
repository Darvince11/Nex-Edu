"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Component = {
  id: number;
  name: string;
  code: string;
  max_score: string;
  order: number;
  is_active: boolean;
};
type Band = {
  id: number;
  section: string;
  grade: string;
  min_score: string;
  max_score: string;
  remark: string;
  points: string;
};

const KEYS: [string, string][] = [
  ["", "Default key (KG and primary)"],
  ["kg", "Kindergarten"],
  ["lower_primary", "Lower primary"],
  ["upper_primary", "Upper primary"],
  ["jhs", "JHS (BECE grades)"],
];

/**
 * How scores are made up and graded. The head teacher, administrator and
 * proprietor change it; others can look. Report cards use it next time
 * results are computed.
 */
export default function GradingPage() {
  const { can } = useSchool();
  const edit = can(PERM.ASSESSMENTS_CONFIGURE);
  return (
    <>
      <PageHeader
        title="Grading"
        description="The parts of each subject's score and the grading keys used on report cards. Changes apply the next time results are computed."
      />
      {!edit && (
        <div className="mb-4">
          <Alert tone="info">You can look; the head teacher or administrator changes grading.</Alert>
        </div>
      )}
      <Components edit={edit} />
      <div className="mt-6">
        <Bands edit={edit} />
      </div>
    </>
  );
}

function Components({ edit }: { edit: boolean }) {
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["grading-components"],
    queryFn: () => api.get<Component[]>("/api/v1/assessments/components"),
  });
  const [editing, setEditing] = useState<Component | "new" | null>(null);
  const toggle = useMutation({
    mutationFn: (c: Component) =>
      api.patch(`/api/v1/assessments/components/${c.id}`, { is_active: !c.is_active }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["grading-components"] }),
  });
  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  const total = list.data.filter((c) => c.is_active).reduce((sum, c) => sum + Number(c.max_score), 0);
  return (
    <Card
      title="Parts of the score"
      actions={
        edit && (
          <Button variant="secondary" onClick={() => setEditing("new")}>
            Add a part
          </Button>
        )
      }
    >
      <Table head={["Part", "Code", "Out of", "In use", ""]}>
        {list.data.map((c) => (
          <tr key={c.id} className={c.is_active ? "" : "opacity-60"}>
            <Td className="font-medium">{c.name}</Td>
            <Td className="font-mono text-xs">{c.code}</Td>
            <Td className="tabular-nums">{Number(c.max_score)}</Td>
            <Td>{c.is_active ? "Yes" : "No"}</Td>
            <Td className="whitespace-nowrap">
              {edit && (
                <>
                  <Button variant="ghost" onClick={() => setEditing(c)} aria-label={`Edit ${c.name}`}>
                    Edit
                  </Button>
                  <Button variant="ghost" onClick={() => toggle.mutate(c)}>
                    {c.is_active ? "Stop using" : "Use"}
                  </Button>
                </>
              )}
            </Td>
          </tr>
        ))}
      </Table>
      <p
        className={`mt-3 text-sm ${total === 100 ? "text-neutral-600 dark:text-neutral-300" : "font-medium text-red-700 dark:text-red-400"}`}
      >
        Parts in use add up to {total}.{" "}
        {total === 100 ? "That's right." : "They must add up to 100 before results can be computed."}
      </p>
      <ErrorText error={toggle.error} />
      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add a part" : "Edit part"}
      >
        {editing && (
          <ComponentForm component={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
    </Card>
  );
}

function ComponentForm({ component, onDone }: { component: Component | null; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      component
        ? api.patch(`/api/v1/assessments/components/${component.id}`, body)
        : api.post("/api/v1/assessments/components", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["grading-components"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({ ...f, order: Number(f.order || 0) });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="Name">
        <Input
          name="name"
          required
          maxLength={40}
          defaultValue={component?.name}
          placeholder="e.g. Class score"
        />
      </Field>
      <Field label="Short code" hint="Shown on report cards, e.g. CS">
        <Input name="code" required maxLength={10} defaultValue={component?.code} />
      </Field>
      <Field label="Out of">
        <Input
          name="max_score"
          type="number"
          min={1}
          max={100}
          step="0.5"
          required
          defaultValue={component?.max_score}
        />
      </Field>
      <Field label="Order on report cards">
        <Input name="order" type="number" min={0} defaultValue={component?.order ?? 0} />
      </Field>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function Bands({ edit }: { edit: boolean }) {
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["grading-bands"],
    queryFn: () => api.get<Band[]>("/api/v1/assessments/grade-bands"),
  });
  const [editing, setEditing] = useState<Band | { section: string } | null>(null);
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/assessments/grade-bands/${id}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["grading-bands"] }),
  });
  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  const keys = KEYS.filter(([section]) => section === "" || list.data.some((b) => b.section === section));
  return (
    <div className="grid gap-4">
      <ErrorText error={remove.error} />
      {keys.map(([section, label]) => {
        const bands = list.data
          .filter((b) => b.section === section)
          .sort((a, b) => Number(b.min_score) - Number(a.min_score));
        return (
          <Card
            key={section || "default"}
            title={label}
            actions={
              edit && (
                <Button variant="secondary" onClick={() => setEditing({ section })}>
                  Add a grade
                </Button>
              )
            }
          >
            <Table head={["Grade", "From", "To", "Remark", "Points", ""]}>
              {bands.map((b) => (
                <tr key={b.id}>
                  <Td className="font-medium">{b.grade}</Td>
                  <Td className="tabular-nums">{Number(b.min_score)}</Td>
                  <Td className="tabular-nums">{Number(b.max_score)}</Td>
                  <Td>{b.remark}</Td>
                  <Td className="tabular-nums">{Number(b.points)}</Td>
                  <Td className="whitespace-nowrap">
                    {edit && (
                      <>
                        <Button
                          variant="ghost"
                          onClick={() => setEditing(b)}
                          aria-label={`Edit grade ${b.grade}`}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => remove.mutate(b.id)}
                          aria-label={`Delete grade ${b.grade}`}
                        >
                          Delete
                        </Button>
                      </>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          </Card>
        );
      })}
      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing && "id" in editing ? "Edit grade" : "Add a grade"}
      >
        {editing && <BandForm band={editing} onDone={() => setEditing(null)} />}
      </Modal>
    </div>
  );
}

function BandForm({ band, onDone }: { band: Band | { section: string }; onDone: () => void }) {
  const client = useQueryClient();
  const existing = "id" in band ? band : null;
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      existing
        ? api.patch(`/api/v1/assessments/grade-bands/${existing.id}`, body)
        : api.post("/api/v1/assessments/grade-bands", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["grading-bands"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    save.mutate({ ...Object.fromEntries(new FormData(e.currentTarget)), section: band.section });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="Grade">
        <Input name="grade" required maxLength={4} defaultValue={existing?.grade} />
      </Field>
      <Field label="Remark">
        <Input
          name="remark"
          required
          maxLength={40}
          defaultValue={existing?.remark}
          placeholder="e.g. Highest"
        />
      </Field>
      <Field label="From score">
        <Input
          name="min_score"
          type="number"
          min={0}
          max={100}
          step="0.01"
          required
          defaultValue={existing?.min_score}
        />
      </Field>
      <Field label="To score">
        <Input
          name="max_score"
          type="number"
          min={0}
          max={100}
          step="0.01"
          required
          defaultValue={existing?.max_score}
        />
      </Field>
      <Field label="Points" hint="For BECE aggregates (1 is best)">
        <Input name="points" type="number" min={0} step="0.5" defaultValue={existing?.points ?? "0"} />
      </Field>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}
