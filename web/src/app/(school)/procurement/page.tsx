"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { cedis, formatDate, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Line = { description: string; item: number | null; quantity: number; unit_cost_pesewas: number };
type Requisition = {
  id: string;
  number: string;
  purpose: string;
  lines: Line[];
  total_pesewas: number;
  needed_by: string | null;
  status: string;
  status_label: string;
  requested_by_name: string;
  decision_note: string;
  order_number: string;
  created_at: string;
};
type Order = {
  id: string;
  number: string;
  requisition_number: string;
  purpose: string;
  supplier_name: string;
  account_name: string;
  total_pesewas: number;
  status: string;
  status_label: string;
  received_on: string | null;
  paid_on: string | null;
};
type Tab = "requests" | "orders" | "limit";

const TONE: Record<string, "amber" | "blue" | "green" | "grey" | "red"> = {
  submitted: "amber",
  head_approved: "amber",
  approved: "green",
  rejected: "red",
  ordered: "blue",
  cancelled: "grey",
  issued: "blue",
  received: "amber",
  paid: "green",
};

/** Buying for the school: ask, approve, order, receive, pay. */
export default function ProcurementPage() {
  const { can } = useSchool();
  const manage = can(PERM.PROCUREMENT_MANAGE);
  const [tab, setTab] = useState<Tab>("requests");
  const tabs: [Tab, string][] = [
    ["requests", "Purchase requests"],
    ...(manage ? ([["orders", "Orders"]] as [Tab, string][]) : []),
    ...(can(PERM.PROCUREMENT_FINAL) ? ([["limit", "Approval limit"]] as [Tab, string][]) : []),
  ];
  return (
    <>
      <PageHeader
        title="Procurement"
        description="Ask to buy something, approve requests, and follow orders to the supplier."
      />
      <div
        role="tablist"
        aria-label="Procurement"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {tabs.map(([key, label]) => (
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
      <div role="tabpanel">
        {tab === "requests" && <Requests />}
        {tab === "orders" && manage && <Orders />}
        {tab === "limit" && <Limit />}
      </div>
    </>
  );
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    for (const key of ["requisitions", "purchase-orders"]) void client.invalidateQueries({ queryKey: [key] });
  };
}

function Requests() {
  const { can } = useSchool();
  const refresh = useRefresh();
  const [asking, setAsking] = useState(false);
  const [ordering, setOrdering] = useState<Requisition | null>(null);
  const [deciding, setDeciding] = useState<{ req: Requisition; approve: boolean } | null>(null);
  const rows = useQuery({
    queryKey: ["requisitions"],
    queryFn: () => api.get<Requisition[]>("/api/v1/procurement/requests"),
  });
  const decide = useMutation({
    mutationFn: ({ id, approve, note }: { id: string; approve: boolean; note: string }) =>
      api.post(`/api/v1/procurement/requests/${id}/decide`, { approve, note }),
    onSuccess: () => {
      refresh();
      setDeciding(null);
    },
  });
  const mayDecide = (r: Requisition) =>
    (r.status === "submitted" && can(PERM.PROCUREMENT_APPROVE, PERM.PROCUREMENT_FINAL)) ||
    (r.status === "head_approved" && can(PERM.PROCUREMENT_FINAL));
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setAsking(true)}>Ask to buy something</Button>
      </div>
      <ErrorText error={rows.error ?? decide.error} />
      {rows.isPending ? (
        <Loading />
      ) : rows.data?.length ? (
        <Table head={["Request", "For", "Asked by", "Total", "Status", ""]}>
          {rows.data.map((r) => (
            <tr key={r.id}>
              <Td className="whitespace-nowrap">
                <span className="font-mono text-xs">{r.number}</span>
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {formatDate(r.created_at)}
                </span>
              </Td>
              <Td>
                {r.purpose}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {r.lines.map((l) => `${l.quantity} × ${l.description}`).join(", ")}
                </span>
              </Td>
              <Td>{r.requested_by_name}</Td>
              <Td className="tabular-nums">{cedis(r.total_pesewas)}</Td>
              <Td>
                <Badge tone={TONE[r.status] ?? "grey"}>{r.status_label}</Badge>
                {r.order_number && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {r.order_number}
                  </span>
                )}
                {r.decision_note && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {r.decision_note}
                  </span>
                )}
              </Td>
              <Td className="whitespace-nowrap text-right">
                {mayDecide(r) && (
                  <>
                    <Button
                      variant="secondary"
                      onClick={() => setDeciding({ req: r, approve: true })}
                      aria-label={`Approve ${r.number}`}
                    >
                      Approve
                    </Button>{" "}
                    <Button
                      variant="ghost"
                      onClick={() => setDeciding({ req: r, approve: false })}
                      aria-label={`Turn down ${r.number}`}
                    >
                      Turn down
                    </Button>
                  </>
                )}
                {r.status === "approved" && can(PERM.PROCUREMENT_MANAGE) && (
                  <Button variant="secondary" onClick={() => setOrdering(r)} aria-label={`Order ${r.number}`}>
                    Order
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No purchase requests.</Empty>
      )}
      <Modal open={asking} onClose={() => setAsking(false)} title="Ask to buy something">
        {asking && (
          <AskForm
            onDone={() => {
              refresh();
              setAsking(false);
            }}
          />
        )}
      </Modal>
      <Modal
        open={ordering !== null}
        onClose={() => setOrdering(null)}
        title={`Order ${ordering?.number ?? ""}`}
      >
        {ordering && (
          <OrderForm
            req={ordering}
            onDone={() => {
              refresh();
              setOrdering(null);
            }}
          />
        )}
      </Modal>
      <Modal
        open={deciding !== null}
        onClose={() => setDeciding(null)}
        title={deciding?.approve ? "Approve this request?" : "Turn down this request?"}
      >
        {deciding && (
          <form
            className="flex flex-col gap-3 text-sm"
            onSubmit={(e) => {
              e.preventDefault();
              decide.mutate({
                id: deciding.req.id,
                approve: deciding.approve,
                note: String(new FormData(e.currentTarget).get("note") ?? ""),
              });
            }}
          >
            <p>
              {deciding.req.purpose}: {cedis(deciding.req.total_pesewas)}
            </p>
            <Field label="Note (optional)">
              <Input name="note" maxLength={200} />
            </Field>
            <div className="flex justify-end">
              <Button type="submit" busy={decide.isPending} variant={deciding.approve ? "primary" : "danger"}>
                {deciding.approve ? "Approve" : "Turn down"}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}

function AskForm({ onDone }: { onDone: () => void }) {
  const [lines, setLines] = useState<{ description: string; quantity: string; cost: string }[]>([
    { description: "", quantity: "1", cost: "" },
  ]);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/procurement/requests", body),
    onSuccess: onDone,
  });
  const total = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (toPesewas(l.cost) ?? 0), 0);
  const set = (i: number, patch: Partial<(typeof lines)[number]>) =>
    setLines((all) => all.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          purpose: f.purpose,
          needed_by: f.needed_by || null,
          lines: lines
            .filter((l) => l.description.trim())
            .map((l) => ({
              description: l.description,
              item: null,
              quantity: Number(l.quantity),
              unit_cost_pesewas: toPesewas(l.cost) ?? 0,
            })),
        });
      }}
    >
      <Field label="What it's for">
        <Input name="purpose" required maxLength={200} />
      </Field>
      <fieldset className="flex flex-col gap-2 rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
        <legend className="px-1 text-sm font-medium">Things to buy</legend>
        {lines.map((l, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: rows are edited in place; order is the identity.
          <div key={i} className="grid grid-cols-[1fr_5rem_7rem_auto] items-end gap-2">
            <Field label="Item">
              <Input
                value={l.description}
                onChange={(e) => set(i, { description: e.target.value })}
                maxLength={120}
              />
            </Field>
            <Field label="How many">
              <Input
                value={l.quantity}
                onChange={(e) => set(i, { quantity: e.target.value })}
                inputMode="numeric"
              />
            </Field>
            <Field label="Price each (GH₵)">
              <Input value={l.cost} onChange={(e) => set(i, { cost: e.target.value })} inputMode="decimal" />
            </Field>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setLines((all) => all.filter((_, j) => j !== i))}
              aria-label={`Remove line ${i + 1}`}
            >
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setLines((all) => [...all, { description: "", quantity: "1", cost: "" }])}
          >
            Add a line
          </Button>
        </div>
      </fieldset>
      <Field label="Needed by (optional)">
        <Input name="needed_by" type="date" />
      </Field>
      <p className="text-sm font-medium">Total: {cedis(total)}</p>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Send for approval
        </Button>
      </div>
    </form>
  );
}

function OrderForm({ req, onDone }: { req: Requisition; onDone: () => void }) {
  const suppliers = useQuery({
    queryKey: ["suppliers"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/api/v1/inventory/suppliers"),
  });
  const accounts = useQuery({
    queryKey: ["ledger-accounts", "expense"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/api/v1/accounting/accounts?type=expense"),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/procurement/requests/${req.id}/order`, body),
    onSuccess: onDone,
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({ supplier: Number(f.supplier), account: Number(f.account) });
      }}
    >
      <p className="text-sm">
        {req.purpose}: {cedis(req.total_pesewas)}
      </p>
      <Field label="Supplier" hint="Add suppliers under Stores.">
        <Select name="supplier" required defaultValue="">
          <option value="" disabled>
            Choose
          </option>
          {suppliers.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Spent on">
        <Select name="account" required defaultValue="">
          <option value="" disabled>
            Choose
          </option>
          {accounts.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
      </Field>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Send order
        </Button>
      </div>
    </form>
  );
}

function Orders() {
  const refresh = useRefresh();
  const orders = useQuery({
    queryKey: ["purchase-orders"],
    queryFn: () => api.get<Order[]>("/api/v1/procurement/orders"),
  });
  const act = useMutation({
    mutationFn: ({ id, what }: { id: string; what: "receive" | "pay" }) =>
      api.post(`/api/v1/procurement/orders/${id}/${what}`, {}),
    onSuccess: refresh,
  });
  return (
    <>
      <ErrorText error={orders.error ?? act.error} />
      {orders.data?.length ? (
        <Table head={["Order", "Supplier", "For", "Total", "Status", ""]}>
          {orders.data.map((o) => (
            <tr key={o.id}>
              <Td className="font-mono text-xs">{o.number}</Td>
              <Td>{o.supplier_name}</Td>
              <Td>
                {o.purpose}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">{o.account_name}</span>
              </Td>
              <Td className="tabular-nums">{cedis(o.total_pesewas)}</Td>
              <Td>
                <Badge tone={TONE[o.status] ?? "grey"}>{o.status_label}</Badge>
              </Td>
              <Td className="text-right">
                {o.status === "issued" && (
                  <Button
                    variant="secondary"
                    onClick={() => act.mutate({ id: o.id, what: "receive" })}
                    aria-label={`Goods in for ${o.number}`}
                  >
                    Goods in
                  </Button>
                )}
                {o.status === "received" && (
                  <Button
                    variant="secondary"
                    onClick={() => act.mutate({ id: o.id, what: "pay" })}
                    aria-label={`Pay ${o.supplier_name} for ${o.number}`}
                  >
                    Paid supplier
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No orders yet.</Empty>
      )}
    </>
  );
}

function Limit() {
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: ["procurement-settings"],
    queryFn: () => api.get<{ proprietor_above_pesewas: number }>("/api/v1/procurement/settings"),
  });
  const save = useMutation({
    mutationFn: (amount: number) =>
      api.patch("/api/v1/procurement/settings", { proprietor_above_pesewas: amount }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["procurement-settings"] }),
  });
  if (!settings.data) return <Loading />;
  return (
    <Card title="When you approve too">
      <form
        className="flex max-w-md flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(toPesewas(String(new FormData(e.currentTarget).get("amount") ?? "")) ?? 0);
        }}
      >
        <Field label="Requests above (GH₵)">
          <Input
            name="amount"
            inputMode="decimal"
            defaultValue={(settings.data.proprietor_above_pesewas / 100).toFixed(2)}
          />
        </Field>
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </form>
      {save.isSuccess && <Alert tone="success">Saved.</Alert>}
      <ErrorText error={save.error} />
    </Card>
  );
}
