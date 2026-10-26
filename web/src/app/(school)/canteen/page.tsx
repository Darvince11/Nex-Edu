"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  Alert,
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
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { cedis, formatDate, toPesewas } from "@/lib/format";
import { useArms, useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type MenuItem = {
  id: number;
  name: string;
  kind: string;
  kind_label: string;
  price_pesewas: number;
  is_available: boolean;
};
type TillPupil = {
  student: string;
  name: string;
  class: string;
  balance_pesewas: number;
  daily_limit_pesewas: number | null;
  spent_today_pesewas: number;
  on_plan: boolean;
  served_today: boolean;
};
type Entry = {
  id: string;
  kind: string;
  kind_label: string;
  amount_pesewas: number;
  balance_after_pesewas: number;
  items: { name: string; qty: number; price_pesewas: number }[];
  reference: string;
  created_at: string;
};
type FamilyWallet = TillPupil & { low_balance_pesewas: number; entries: Entry[] };
type Summary = {
  sales_pesewas: number;
  purchases: number;
  top_ups_pesewas: number;
  plan_meals: number;
  held_pesewas: number;
  low_wallets: number;
};
type Plan = { student: string; name: string; class: string; note: string };

/** The canteen: the till for the canteen manager and bursar; wallets for parents. */
export default function CanteenPage() {
  const { can } = useSchool();
  if (can(PERM.CANTEEN_SELL, PERM.CANTEEN_MANAGE)) return <Staff />;
  return <Family />;
}

function Family() {
  const wallets = useQuery({
    queryKey: ["canteen-mine"],
    queryFn: () => api.get<FamilyWallet[]>("/api/v1/canteen/mine"),
  });
  return (
    <>
      <PageHeader
        title="Canteen"
        description="Your children's canteen money, what they bought, and daily limits."
      />
      <ErrorText error={wallets.error} />
      {wallets.isPending ? (
        <Loading />
      ) : wallets.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {wallets.data.map((w) => (
            <FamilyCard key={w.student} wallet={w} />
          ))}
        </div>
      ) : (
        <Empty>No canteen wallets.</Empty>
      )}
    </>
  );
}

function FamilyCard({ wallet }: { wallet: FamilyWallet }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.patch(`/api/v1/canteen/wallets/${wallet.student}`, body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["canteen-mine"] }),
  });
  return (
    <Card title={wallet.name}>
      <div className="mb-3 grid grid-cols-2 gap-3">
        <Stat label="In the wallet" value={cedis(wallet.balance_pesewas)} />
        <Stat label="Spent today" value={cedis(wallet.spent_today_pesewas)} />
      </div>
      {wallet.on_plan && (
        <p className="mb-3 text-sm">
          On this term's meal plan{wallet.served_today ? " · lunch served today" : ""}.
        </p>
      )}
      {wallet.balance_pesewas < wallet.low_balance_pesewas && (
        <div className="mb-3">
          <Alert tone="warning">Running low. Top up at the school office.</Alert>
        </div>
      )}
      <form
        className="mb-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
          save.mutate({
            daily_limit_pesewas: f.limit ? toPesewas(f.limit) : null,
            low_balance_pesewas: toPesewas(f.low || "0") ?? 0,
          });
        }}
      >
        <Field label="Most to spend a day (GH₵)" hint="Empty for no limit.">
          <Input
            name="limit"
            inputMode="decimal"
            defaultValue={
              wallet.daily_limit_pesewas !== null ? (wallet.daily_limit_pesewas / 100).toFixed(2) : ""
            }
          />
        </Field>
        <Field label="Tell me below (GH₵)">
          <Input
            name="low"
            inputMode="decimal"
            defaultValue={(wallet.low_balance_pesewas / 100).toFixed(2)}
          />
        </Field>
        <Button type="submit" variant="secondary" busy={save.isPending}>
          Save
        </Button>
      </form>
      <ErrorText error={save.error} />
      <h3 className="mb-1 text-sm font-medium">Recent</h3>
      {wallet.entries.length ? (
        <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
          {wallet.entries.map((e) => (
            <li key={e.id} className="flex justify-between gap-2 py-1.5">
              <span>
                {e.kind === "purchase" ? e.items.map((i) => `${i.qty} × ${i.name}`).join(", ") : e.kind_label}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {formatDate(e.created_at)}
                </span>
              </span>
              <span
                className={`tabular-nums ${e.amount_pesewas < 0 ? "" : "text-emerald-700 dark:text-emerald-400"}`}
              >
                {e.amount_pesewas < 0 ? "−" : "+"}
                {cedis(Math.abs(e.amount_pesewas))}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">Nothing yet.</p>
      )}
    </Card>
  );
}

function Staff() {
  const { can } = useSchool();
  const manage = can(PERM.CANTEEN_MANAGE);
  const [tab, setTab] = useState<"till" | "menu" | "plans">("till");
  const summary = useQuery({
    queryKey: ["canteen-summary"],
    queryFn: () => api.get<Summary>("/api/v1/canteen/summary"),
  });
  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Canteen"
        description="Sell at the till, take cash top-ups, and serve meal-plan pupils."
      />
      {s && (
        <div className="mb-5 grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="Sold today" value={cedis(s.sales_pesewas)} />
          <Stat label="Sales" value={s.purchases} />
          <Stat label="Topped up today" value={cedis(s.top_ups_pesewas)} />
          <Stat label="Plan meals today" value={s.plan_meals} />
          <Stat label="Held in wallets" value={cedis(s.held_pesewas)} />
        </div>
      )}
      {manage && (
        <div
          role="tablist"
          aria-label="Canteen"
          className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
        >
          {(
            [
              ["till", "Till"],
              ["menu", "Menu"],
              ["plans", "Meal plans"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === key ? "border-brand font-medium" : "border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <div role={manage ? "tabpanel" : undefined}>
        {tab === "till" && <Till manage={manage} />}
        {tab === "menu" && <MenuTab />}
        {tab === "plans" && <PlansTab />}
      </div>
    </>
  );
}

function Till({ manage }: { manage: boolean }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [pupil, setPupil] = useState<string | null>(null);
  const [basket, setBasket] = useState<Record<number, number>>({});
  const [refunding, setRefunding] = useState(false);
  const search = useQuery({
    queryKey: ["canteen-search", q],
    queryFn: () =>
      api.get<
        { student: string; name: string; class: string; admission_number: string; balance_pesewas: number }[]
      >(`/api/v1/canteen/pupils?q=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2 && !pupil,
  });
  const menu = useQuery({
    queryKey: ["canteen-menu"],
    queryFn: () => api.get<MenuItem[]>("/api/v1/canteen/menu"),
  });
  const current = useQuery({
    queryKey: ["canteen-till", pupil],
    queryFn: () => api.get<TillPupil>(`/api/v1/canteen/till/${pupil}`),
    enabled: Boolean(pupil),
  });
  const act = useMutation({
    mutationFn: ({ what, body }: { what: string; body?: Record<string, unknown> }) =>
      api.post<TillPupil>(`/api/v1/canteen/till/${pupil}/${what}`, body ?? {}),
    onSuccess: (data, vars) => {
      client.setQueryData(["canteen-till", pupil], data);
      void client.invalidateQueries({ queryKey: ["canteen-summary"] });
      if (vars.what === "sell") setBasket({});
      if (vars.what === "refund") setRefunding(false);
    },
  });
  const available = menu.data?.filter((m) => m.is_available) ?? [];
  const total = available.reduce((sum, m) => sum + (basket[m.id] ?? 0) * m.price_pesewas, 0);
  const p = current.data;

  return (
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      <Card title="Pupil">
        {pupil && p ? (
          <div className="flex flex-col gap-2 text-sm">
            <div className="font-medium">{p.name}</div>
            <div className="text-neutral-600 dark:text-neutral-300">{p.class}</div>
            <div className="text-2xl font-semibold tabular-nums">{cedis(p.balance_pesewas)}</div>
            <div className="text-neutral-600 dark:text-neutral-300">
              Spent today {cedis(p.spent_today_pesewas)}
              {p.daily_limit_pesewas !== null ? ` of ${cedis(p.daily_limit_pesewas)} a day` : ""}
            </div>
            {p.on_plan && (
              <div>
                {p.served_today ? (
                  <Badge tone="grey">Plan meal served today</Badge>
                ) : (
                  <Button
                    busy={act.isPending && act.variables?.what === "serve"}
                    onClick={() => act.mutate({ what: "serve" })}
                  >
                    Serve plan meal
                  </Button>
                )}
              </div>
            )}
            <form
              className="mt-2 flex flex-col gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
                act.mutate(
                  {
                    what: "top_up",
                    body: { amount_pesewas: toPesewas(f.amount ?? "") ?? 0, reference: f.reference },
                  },
                  { onSuccess: () => form.reset() },
                );
              }}
            >
              <Field label="Cash top-up (GH₵)">
                <Input name="amount" inputMode="decimal" required />
              </Field>
              <Field label="Receipt or note (optional)">
                <Input name="reference" maxLength={60} />
              </Field>
              <Button
                type="submit"
                variant="secondary"
                busy={act.isPending && act.variables?.what === "top_up"}
              >
                Add money
              </Button>
            </form>
            <div className="flex flex-wrap justify-between gap-2 pt-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setPupil(null);
                  setBasket({});
                  setQ("");
                }}
              >
                Next pupil
              </Button>
              {manage && (
                <Button variant="ghost" onClick={() => setRefunding(true)} disabled={p.balance_pesewas <= 0}>
                  Refund
                </Button>
              )}
            </div>
          </div>
        ) : (
          <>
            <Field label="Find the pupil" hint="Name or admission number.">
              <Input value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
            </Field>
            {search.data && search.data.length > 0 && (
              <ul
                aria-label="Matching pupils"
                className="mt-2 max-h-72 divide-y divide-neutral-100 overflow-y-auto text-sm dark:divide-neutral-800"
              >
                {search.data.map((r) => (
                  <li key={r.student}>
                    <button
                      type="button"
                      className="flex w-full justify-between gap-2 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800"
                      onClick={() => setPupil(r.student)}
                    >
                      <span>
                        <span className="font-medium">{r.name}</span>
                        <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                          {r.class} · {r.admission_number}
                        </span>
                      </span>
                      <span className="tabular-nums">{cedis(r.balance_pesewas)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <ErrorText error={act.error ?? current.error} />
      </Card>
      <Card title="Sell">
        {!pupil ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-300">Choose a pupil first.</p>
        ) : available.length ? (
          <>
            <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {available.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between gap-2 rounded-control border border-neutral-200 px-3 py-2 dark:border-neutral-800"
                >
                  <span className="text-sm">
                    <span className="font-medium">{m.name}</span>
                    <span className="block text-neutral-600 dark:text-neutral-300">
                      {cedis(m.price_pesewas)}
                    </span>
                  </span>
                  <span className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      onClick={() => setBasket((b) => ({ ...b, [m.id]: Math.max(0, (b[m.id] ?? 0) - 1) }))}
                      aria-label={`One less ${m.name}`}
                      disabled={!basket[m.id]}
                    >
                      −
                    </Button>
                    <span className="w-5 text-center tabular-nums">
                      <span className="sr-only">{m.name} in the basket: </span>
                      {basket[m.id] ?? 0}
                    </span>
                    <Button
                      variant="ghost"
                      onClick={() => setBasket((b) => ({ ...b, [m.id]: Math.min(20, (b[m.id] ?? 0) + 1) }))}
                      aria-label={`Add ${m.name}`}
                    >
                      +
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-lg font-semibold tabular-nums">Total {cedis(total)}</span>
              <Button
                busy={act.isPending && act.variables?.what === "sell"}
                disabled={total === 0}
                onClick={() =>
                  act.mutate({
                    what: "sell",
                    body: {
                      items: Object.entries(basket)
                        .filter(([, qty]) => qty > 0)
                        .map(([item, qty]) => ({ item: Number(item), qty })),
                    },
                  })
                }
              >
                Charge {cedis(total)}
              </Button>
            </div>
          </>
        ) : (
          <Empty>Nothing on the menu yet.</Empty>
        )}
      </Card>
      <Modal open={refunding} onClose={() => setRefunding(false)} title="Refund canteen money">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
            act.mutate({
              what: "refund",
              body: { amount_pesewas: toPesewas(f.amount ?? "") ?? 0, reason: f.reason },
            });
          }}
        >
          <Field label="Amount (GH₵)">
            <Input name="amount" inputMode="decimal" required />
          </Field>
          <Field label="Why">
            <Input name="reason" required maxLength={200} />
          </Field>
          <ErrorText error={act.error} />
          <div className="flex justify-end">
            <Button type="submit" variant="danger" busy={act.isPending}>
              Give money back
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function MenuTab() {
  const client = useQueryClient();
  const menu = useQuery({
    queryKey: ["canteen-menu"],
    queryFn: () => api.get<MenuItem[]>("/api/v1/canteen/menu"),
  });
  const [editing, setEditing] = useState<MenuItem | "new" | null>(null);
  const toggle = useMutation({
    mutationFn: (m: MenuItem) => api.patch(`/api/v1/canteen/menu/${m.id}`, { is_available: !m.is_available }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["canteen-menu"] }),
  });
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setEditing("new")}>Add to the menu</Button>
      </div>
      <ErrorText error={menu.error ?? toggle.error} />
      {menu.isPending ? (
        <Loading />
      ) : menu.data?.length ? (
        <Table head={["Item", "Kind", "Price", "On sale", ""]}>
          {menu.data.map((m) => (
            <tr key={m.id}>
              <Td className="font-medium">{m.name}</Td>
              <Td>{m.kind_label}</Td>
              <Td className="tabular-nums">{cedis(m.price_pesewas)}</Td>
              <Td>
                <Button
                  variant="ghost"
                  onClick={() => toggle.mutate(m)}
                  aria-label={`${m.is_available ? "Stop selling" : "Sell"} ${m.name}`}
                >
                  {m.is_available ? "Yes" : "No"}
                </Button>
              </Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setEditing(m)} aria-label={`Change ${m.name}`}>
                  Change
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>Nothing on the menu yet.</Empty>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add to the menu" : "Change item"}
      >
        {editing !== null && (
          <MenuForm item={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
    </>
  );
}

function MenuForm({ item, onDone }: { item: MenuItem | null; onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      item ? api.patch(`/api/v1/canteen/menu/${item.id}`, body) : api.post("/api/v1/canteen/menu", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["canteen-menu"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({ name: f.name, kind: f.kind, price_pesewas: toPesewas(f.price ?? "") });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Name">
        <Input name="name" required maxLength={80} defaultValue={item?.name} />
      </Field>
      <Field label="Kind">
        <Select name="kind" defaultValue={item?.kind ?? "meal"}>
          <option value="meal">Meal</option>
          <option value="snack">Snack</option>
          <option value="drink">Drink</option>
        </Select>
      </Field>
      <Field label="Price (GH₵)">
        <Input
          name="price"
          inputMode="decimal"
          required
          defaultValue={item ? (item.price_pesewas / 100).toFixed(2) : ""}
        />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function PlansTab() {
  const client = useQueryClient();
  const arms = useArms();
  const [arm, setArm] = useState("");
  const plans = useQuery({
    queryKey: ["canteen-plans"],
    queryFn: () => api.get<Plan[]>("/api/v1/canteen/plans"),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["canteen-plans"] });
  const add = useMutation({
    mutationFn: () => api.post<{ added: number }>("/api/v1/canteen/plans", { arm }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (student: string) => api.del(`/api/v1/canteen/plans?student=${student}`),
    onSuccess: refresh,
  });
  return (
    <>
      <p className="mb-3 max-w-prose text-sm text-neutral-600 dark:text-neutral-300">
        Pupils on a meal plan get one meal a day this term without paying at the till. Charge for it with a
        feeding fee in Fees and payments.
      </p>
      <form
        className="mb-4 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (arm) add.mutate();
        }}
      >
        <div className="w-48">
          <Field label="Add a whole class">
            <Select value={arm} onChange={(e) => setArm(e.target.value)}>
              <option value="">Choose a class</option>
              {arms.data?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Button type="submit" variant="secondary" busy={add.isPending} disabled={!arm}>
          Add class
        </Button>
        {add.data && <span className="text-sm">Added {add.data.added} pupil(s).</span>}
      </form>
      <ErrorText error={plans.error ?? add.error ?? remove.error} />
      {plans.isPending ? (
        <Loading />
      ) : plans.data?.length ? (
        <Table head={["Pupil", "Class", ""]}>
          {plans.data.map((p) => (
            <tr key={p.student}>
              <Td className="font-medium">{p.name}</Td>
              <Td>{p.class}</Td>
              <Td className="text-right">
                <Button
                  variant="ghost"
                  onClick={() => remove.mutate(p.student)}
                  aria-label={`Take ${p.name} off the meal plan`}
                >
                  Remove
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No pupils on a meal plan this term.</Empty>
      )}
    </>
  );
}
