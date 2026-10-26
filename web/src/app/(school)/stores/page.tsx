"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { cedis, formatDate, toPesewas } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Item = {
  id: number;
  name: string;
  category: string;
  category_label: string;
  unit: string;
  reorder_level: number;
  in_stock: number;
  low: boolean;
  location: string;
  is_active: boolean;
};
type StoresRequest = {
  id: string;
  item: number;
  item_name: string;
  unit: string;
  quantity: number;
  reason: string;
  requested_by_name: string;
  status: "pending" | "issued" | "declined";
  status_label: string;
  decision_note: string;
  created_at: string;
};
type Movement = {
  id: string;
  kind: string;
  kind_label: string;
  quantity: number;
  stock_after: number;
  date: string;
  supplier_name: string;
  unit_cost_pesewas: number | null;
  issued_to: string;
  note: string;
};
type Supplier = { id: number; name: string; phone: string; email: string; notes: string };
type Asset = {
  id: string;
  tag: string;
  name: string;
  category: string;
  location: string;
  assigned_to: string;
  condition: string;
  condition_label: string;
  purchased_on: string | null;
  cost_pesewas: number | null;
};
type Summary = { items: number; low_count: number; waiting: number; assets: Record<string, number> };
type Tab = "stock" | "requests" | "assets" | "suppliers";

const CATEGORIES: [string, string][] = [
  ["stationery", "Stationery"],
  ["cleaning", "Cleaning"],
  ["books", "Exercise books and textbooks"],
  ["uniform", "Uniforms"],
  ["sports", "Sports"],
  ["kitchen", "Kitchen"],
  ["science", "Science and ICT"],
  ["other", "Other"],
];
const STATUS_TONE = { pending: "amber", issued: "green", declined: "grey" } as const;

/** The stores: stock, requests from staff, the equipment register and suppliers. */
export default function StoresPage() {
  const { can } = useSchool();
  return can(PERM.INVENTORY_MANAGE) ? <Keeper /> : <AskTheStores />;
}

function AskTheStores() {
  const client = useQueryClient();
  const items = useQuery({
    queryKey: ["stock-items"],
    queryFn: () => api.get<Item[]>("/api/v1/inventory/items"),
  });
  const mine = useQuery({
    queryKey: ["stores-requests"],
    queryFn: () => api.get<StoresRequest[]>("/api/v1/inventory/requests"),
  });
  const ask = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/inventory/requests", body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["stores-requests"] }),
  });
  return (
    <>
      <PageHeader title="Stores" description="Ask the stores for chalk, exercise books and other supplies." />
      <form
        className="mb-6 grid max-w-2xl gap-3 sm:grid-cols-[1fr_7rem]"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
          ask.mutate(
            { item: Number(f.item), quantity: Number(f.quantity), reason: f.reason },
            { onSuccess: () => form.reset() },
          );
        }}
      >
        <Field label="What do you need?">
          <Select name="item" required defaultValue="">
            <option value="" disabled>
              Choose
            </option>
            {items.data?.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} ({i.unit})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="How many">
          <Input name="quantity" type="number" min={1} max={10000} required defaultValue={1} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="What it's for (optional)">
            <Input name="reason" maxLength={200} />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <ErrorText error={ask.error} />
          {ask.isSuccess && <Alert tone="success">Sent. You'll get a message when it's ready.</Alert>}
        </div>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" busy={ask.isPending}>
            Ask the stores
          </Button>
        </div>
      </form>
      <h2 className="mb-2 font-medium">Your requests</h2>
      {mine.data?.length ? <RequestTable rows={mine.data} /> : <Empty>No requests yet.</Empty>}
    </>
  );
}

function RequestTable({
  rows,
  onDecide,
}: {
  rows: StoresRequest[];
  onDecide?: (r: StoresRequest, approve: boolean) => void;
}) {
  return (
    <Table head={["When", "Item", "How many", onDecide ? "Who" : "Reason", "Status", ""]}>
      {rows.map((r) => (
        <tr key={r.id}>
          <Td className="whitespace-nowrap">{formatDate(r.created_at)}</Td>
          <Td className="font-medium">{r.item_name}</Td>
          <Td className="tabular-nums">
            {r.quantity} {r.unit}
          </Td>
          <Td>
            {onDecide ? r.requested_by_name : r.reason || "—"}
            {onDecide && r.reason && (
              <span className="block text-xs text-neutral-600 dark:text-neutral-400">{r.reason}</span>
            )}
          </Td>
          <Td>
            <Badge tone={STATUS_TONE[r.status]}>{r.status_label}</Badge>
            {r.decision_note && (
              <span className="block text-xs text-neutral-600 dark:text-neutral-400">{r.decision_note}</span>
            )}
          </Td>
          <Td className="whitespace-nowrap text-right">
            {onDecide && r.status === "pending" && (
              <>
                <Button
                  variant="secondary"
                  onClick={() => onDecide(r, true)}
                  aria-label={`Issue ${r.item_name} to ${r.requested_by_name}`}
                >
                  Issue
                </Button>{" "}
                <Button
                  variant="ghost"
                  onClick={() => onDecide(r, false)}
                  aria-label={`Decline ${r.item_name} for ${r.requested_by_name}`}
                >
                  Decline
                </Button>
              </>
            )}
          </Td>
        </tr>
      ))}
    </Table>
  );
}

function Keeper() {
  const [tab, setTab] = useState<Tab>("stock");
  const summary = useQuery({
    queryKey: ["stores-summary"],
    queryFn: () => api.get<Summary>("/api/v1/inventory/summary"),
  });
  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Stores"
        description="Stock in and out, requests from staff, equipment and suppliers."
      />
      {s && (
        <div className="mb-5 grid gap-4 sm:grid-cols-4">
          <Stat label="Items kept" value={s.items} />
          <Stat label="Running low" value={s.low_count} />
          <Stat label="Requests waiting" value={s.waiting} />
          <Stat label="Equipment needing repair" value={s.assets.poor ?? 0} />
        </div>
      )}
      <div
        role="tablist"
        aria-label="Stores"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["stock", "Stock"],
            ["requests", "Requests"],
            ["assets", "Equipment"],
            ["suppliers", "Suppliers"],
          ] as [Tab, string][]
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
      <div role="tabpanel">
        {tab === "stock" && <StockTab />}
        {tab === "requests" && <RequestsTab />}
        {tab === "assets" && <AssetsTab />}
        {tab === "suppliers" && <SuppliersTab />}
      </div>
    </>
  );
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    for (const key of [
      "stock-items",
      "stores-summary",
      "stores-requests",
      "stock-movements",
      "assets",
      "suppliers",
    ])
      void client.invalidateQueries({ queryKey: [key] });
  };
}

function StockTab() {
  const [q, setQ] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [open, setOpen] = useState<Item | "new" | null>(null);
  const [moving, setMoving] = useState<{ item: Item; kind: "receive" | "issue" | "count" } | null>(null);
  const items = useQuery({
    queryKey: ["stock-items", q, lowOnly],
    queryFn: () =>
      api.get<Item[]>(`/api/v1/inventory/items?q=${encodeURIComponent(q.trim())}${lowOnly ? "&low=1" : ""}`),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-60">
          <Field label="Search">
            <Input value={q} onChange={(e) => setQ(e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-brand"
            checked={lowOnly}
            onChange={(e) => setLowOnly(e.target.checked)}
          />
          Running low only
        </label>
        <div className="ml-auto">
          <Button onClick={() => setOpen("new")}>Add an item</Button>
        </div>
      </div>
      <ErrorText error={items.error} />
      {items.isPending ? (
        <Loading />
      ) : items.data?.length ? (
        <Table head={["Item", "In stock", "Where", ""]}>
          {items.data.map((i) => (
            <tr key={i.id} className={i.is_active ? "" : "opacity-60"}>
              <Td>
                <button
                  type="button"
                  className="text-left font-medium text-brand-strong hover:underline dark:text-brand-sky"
                  onClick={() => setOpen(i)}
                >
                  {i.name}
                </button>
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {i.category_label}
                </span>
              </Td>
              <Td className="whitespace-nowrap tabular-nums">
                {i.in_stock} {i.unit} {i.low && i.reorder_level > 0 && <Badge tone="amber">Low</Badge>}
              </Td>
              <Td>{i.location || "—"}</Td>
              <Td className="whitespace-nowrap text-right">
                <Button
                  variant="ghost"
                  onClick={() => setMoving({ item: i, kind: "receive" })}
                  aria-label={`Receive ${i.name}`}
                >
                  In
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setMoving({ item: i, kind: "issue" })}
                  aria-label={`Issue ${i.name}`}
                >
                  Out
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setMoving({ item: i, kind: "count" })}
                  aria-label={`Count ${i.name}`}
                >
                  Count
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No items.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "Add an item" : "Item"}
      >
        {open !== null && <ItemForm item={open === "new" ? null : open} onDone={() => setOpen(null)} />}
      </Modal>
      <Modal
        open={moving !== null}
        onClose={() => setMoving(null)}
        title={
          moving
            ? `${{ receive: "Receive", issue: "Issue", count: "Count" }[moving.kind]}: ${moving.item.name}`
            : ""
        }
      >
        {moving && <MoveForm item={moving.item} kind={moving.kind} onDone={() => setMoving(null)} />}
      </Modal>
    </>
  );
}

function ItemForm({ item, onDone }: { item: Item | null; onDone: () => void }) {
  const refresh = useRefresh();
  const history = useQuery({
    queryKey: ["stock-movements", item?.id],
    queryFn: () => api.get<Movement[]>(`/api/v1/inventory/items/${item?.id}/movements`),
    enabled: Boolean(item),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      item
        ? api.patch(`/api/v1/inventory/items/${item.id}`, body)
        : api.post("/api/v1/inventory/items", body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      name: f.name,
      category: f.category,
      unit: f.unit,
      reorder_level: Number(f.reorder_level || 0),
      location: f.location,
      ...(item ? { is_active: f.is_active === "on" } : {}),
    });
  };
  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Name">
            <Input name="name" required maxLength={120} defaultValue={item?.name} />
          </Field>
        </div>
        <Field label="Kind">
          <Select name="category" defaultValue={item?.category ?? "stationery"}>
            {CATEGORIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Counted in" hint='e.g. "boxes", "reams"'>
          <Input name="unit" required maxLength={20} defaultValue={item?.unit ?? "pieces"} />
        </Field>
        <Field label="Warn when down to">
          <Input name="reorder_level" type="number" min={0} defaultValue={item?.reorder_level ?? 0} />
        </Field>
        <Field label="Where it's kept (optional)">
          <Input name="location" maxLength={60} defaultValue={item?.location} />
        </Field>
        {item && (
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              name="is_active"
              defaultChecked={item.is_active}
              className="size-4 accent-brand"
            />{" "}
            Still kept
          </label>
        )}
        <div className="sm:col-span-2">
          <ErrorText error={save.error} />
        </div>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" busy={save.isPending}>
            {item ? "Save changes" : "Add item"}
          </Button>
        </div>
      </form>
      {item && (
        <section aria-labelledby="history-title">
          <h3 id="history-title" className="mb-1 font-medium">
            History
          </h3>
          {history.data?.length ? (
            <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
              {history.data.map((m) => (
                <li key={m.id} className="flex justify-between gap-2 py-1.5">
                  <span>
                    {m.kind_label}
                    {m.issued_to ? ` to ${m.issued_to}` : ""}
                    {m.supplier_name ? ` from ${m.supplier_name}` : ""}
                    <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                      {formatDate(m.date)}
                      {m.unit_cost_pesewas ? ` · ${cedis(m.unit_cost_pesewas)} each` : ""}
                      {m.note ? ` · ${m.note}` : ""}
                    </span>
                  </span>
                  <span className="tabular-nums">
                    {m.quantity > 0 ? "+" : ""}
                    {m.quantity} → {m.stock_after}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600 dark:text-neutral-300">Nothing yet.</p>
          )}
        </section>
      )}
    </div>
  );
}

function MoveForm({
  item,
  kind,
  onDone,
}: {
  item: Item;
  kind: "receive" | "issue" | "count";
  onDone: () => void;
}) {
  const refresh = useRefresh();
  const suppliers = useQuery({
    queryKey: ["suppliers"],
    queryFn: () => api.get<Supplier[]>("/api/v1/inventory/suppliers"),
    enabled: kind === "receive",
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/inventory/items/${item.id}/${kind}`, body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    if (kind === "count") save.mutate({ counted: Number(f.counted), note: f.note });
    else if (kind === "issue")
      save.mutate({ quantity: Number(f.quantity), issued_to: f.issued_to, note: f.note });
    else
      save.mutate({
        quantity: Number(f.quantity),
        supplier: f.supplier ? Number(f.supplier) : null,
        unit_cost_pesewas: f.cost ? toPesewas(f.cost) : null,
        note: f.note,
      });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <p className="text-sm">
        In stock now: {item.in_stock} {item.unit}
      </p>
      {kind === "count" ? (
        <Field label={`Counted on the shelf (${item.unit})`}>
          <Input name="counted" type="number" min={0} required />
        </Field>
      ) : (
        <Field label={`How many (${item.unit})`}>
          <Input name="quantity" type="number" min={1} required />
        </Field>
      )}
      {kind === "issue" && (
        <Field label="Given to" hint="A person, class or department.">
          <Input name="issued_to" required maxLength={120} />
        </Field>
      )}
      {kind === "receive" && (
        <>
          <Field label="From (optional)">
            <Select name="supplier" defaultValue="">
              <option value="">Not recorded</option>
              {suppliers.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Cost of each (GH₵, optional)">
            <Input name="cost" inputMode="decimal" />
          </Field>
        </>
      )}
      <Field label="Note (optional)">
        <Input name="note" maxLength={200} />
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

function RequestsTab() {
  const refresh = useRefresh();
  const [status, setStatus] = useState("pending");
  const rows = useQuery({
    queryKey: ["stores-requests", status],
    queryFn: () => api.get<StoresRequest[]>(`/api/v1/inventory/requests${status ? `?status=${status}` : ""}`),
  });
  const decide = useMutation({
    mutationFn: ({ r, approve }: { r: StoresRequest; approve: boolean }) =>
      api.post(`/api/v1/inventory/requests/${r.id}/${approve ? "approve" : "decline"}`, {}),
    onSuccess: refresh,
  });
  return (
    <>
      <div className="mb-4 w-44">
        <Field label="Show">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">Waiting</option>
            <option value="issued">Issued</option>
            <option value="declined">Declined</option>
            <option value="">All</option>
          </Select>
        </Field>
      </div>
      <ErrorText error={rows.error ?? decide.error} />
      {rows.isPending ? (
        <Loading />
      ) : rows.data?.length ? (
        <RequestTable rows={rows.data} onDecide={(r, approve) => decide.mutate({ r, approve })} />
      ) : (
        <Empty>No requests.</Empty>
      )}
    </>
  );
}

function AssetsTab() {
  const refresh = useRefresh();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Asset | "new" | null>(null);
  const assets = useQuery({
    queryKey: ["assets", q],
    queryFn: () => api.get<Asset[]>(`/api/v1/inventory/assets?q=${encodeURIComponent(q.trim())}`),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: ({ asset, body }: { asset: Asset | null; body: Record<string, unknown> }) =>
      asset
        ? api.patch(`/api/v1/inventory/assets/${asset.id}`, body)
        : api.post("/api/v1/inventory/assets", body),
    onSuccess: () => {
      refresh();
      setOpen(null);
    },
  });
  const editing = open === "new" ? null : open;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-60">
          <Field label="Search">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tag, name or place" />
          </Field>
        </div>
        <div className="ml-auto">
          <Button onClick={() => setOpen("new")}>Add equipment</Button>
        </div>
      </div>
      <ErrorText error={assets.error} />
      {assets.isPending ? (
        <Loading />
      ) : assets.data?.length ? (
        <Table head={["Tag", "Equipment", "Where", "With", "Condition", ""]}>
          {assets.data.map((a) => (
            <tr key={a.id}>
              <Td className="font-mono text-xs">{a.tag}</Td>
              <Td className="font-medium">{a.name}</Td>
              <Td>{a.location || "—"}</Td>
              <Td>{a.assigned_to || "—"}</Td>
              <Td>
                <Badge tone={a.condition === "good" ? "green" : a.condition === "retired" ? "grey" : "amber"}>
                  {a.condition_label}
                </Badge>
              </Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(a)} aria-label={`Change ${a.tag}`}>
                  Change
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No equipment recorded.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={editing ? `Change ${editing.tag}` : "Add equipment"}
      >
        {open !== null && (
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
              save.mutate({
                asset: editing,
                body: {
                  tag: f.tag,
                  name: f.name,
                  category: f.category,
                  location: f.location,
                  assigned_to: f.assigned_to,
                  condition: f.condition,
                  purchased_on: f.purchased_on || null,
                  cost_pesewas: f.cost ? toPesewas(f.cost) : null,
                },
              });
            }}
          >
            <Field label="Tag number">
              <Input name="tag" required maxLength={30} defaultValue={editing?.tag} />
            </Field>
            <Field label="What it is">
              <Input name="name" required maxLength={120} defaultValue={editing?.name} />
            </Field>
            <Field label="Kind (optional)">
              <Input
                name="category"
                maxLength={60}
                defaultValue={editing?.category}
                placeholder="Furniture, ICT…"
              />
            </Field>
            <Field label="Where (optional)">
              <Input name="location" maxLength={80} defaultValue={editing?.location} />
            </Field>
            <Field label="Given to (optional)">
              <Input name="assigned_to" maxLength={120} defaultValue={editing?.assigned_to} />
            </Field>
            <Field label="Condition">
              <Select name="condition" defaultValue={editing?.condition ?? "good"}>
                <option value="good">Good</option>
                <option value="fair">Fair</option>
                <option value="poor">Needs repair</option>
                <option value="retired">Written off</option>
              </Select>
            </Field>
            <Field label="Bought on (optional)">
              <Input name="purchased_on" type="date" defaultValue={editing?.purchased_on ?? ""} />
            </Field>
            <Field label="Cost (GH₵, optional)">
              <Input
                name="cost"
                inputMode="decimal"
                defaultValue={editing?.cost_pesewas ? (editing.cost_pesewas / 100).toFixed(2) : ""}
              />
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
        )}
      </Modal>
    </>
  );
}

function SuppliersTab() {
  const refresh = useRefresh();
  const suppliers = useQuery({
    queryKey: ["suppliers"],
    queryFn: () => api.get<Supplier[]>("/api/v1/inventory/suppliers"),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/inventory/suppliers", body),
    onSuccess: refresh,
  });
  return (
    <>
      <form
        className="mb-4 grid max-w-3xl gap-2 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
          add.mutate({ name: f.name, phone: f.phone }, { onSuccess: () => form.reset() });
        }}
      >
        <Field label="Supplier">
          <Input name="name" required maxLength={120} />
        </Field>
        <Field label="Phone (optional)">
          <Input name="phone" maxLength={20} />
        </Field>
        <Button type="submit" variant="secondary" busy={add.isPending}>
          Add supplier
        </Button>
      </form>
      <ErrorText error={suppliers.error ?? add.error} />
      {suppliers.data?.length ? (
        <Table head={["Supplier", "Phone"]}>
          {suppliers.data.map((s) => (
            <tr key={s.id}>
              <Td className="font-medium">{s.name}</Td>
              <Td>{s.phone || "—"}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No suppliers yet.</Empty>
      )}
    </>
  );
}
