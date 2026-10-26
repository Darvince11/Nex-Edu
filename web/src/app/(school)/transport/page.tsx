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
} from "@/components/ui";
import { api, type Paged, type Student } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type StopRow = {
  id?: number;
  name: string;
  order?: number;
  pickup_at: string | null;
  drop_at: string | null;
  rider_count?: number;
};
type Route = {
  id: string;
  name: string;
  vehicle: string | null;
  vehicle_name: string;
  seats: number | null;
  is_active: boolean;
  rider_count: number;
  stops: StopRow[];
};
type Vehicle = {
  id: string;
  name: string;
  registration: string;
  seats: number;
  driver_user_id: string | null;
  driver_name: string;
  attendant: string;
  attendant_phone: string;
  is_active: boolean;
};
type Roll = {
  route: string;
  date: string;
  direction: "morning" | "afternoon";
  riders: {
    student: string;
    name: string;
    class: string;
    stop: string;
    time: string | null;
    status: string;
  }[];
};
type Rider = {
  student: string;
  name: string;
  class: string;
  route: string;
  route_name: string;
  stop: string;
  direction: string;
};
type Mine = {
  student: string;
  name: string;
  route: string;
  vehicle: string;
  registration: string;
  driver: string;
  attendant: string;
  attendant_phone: string;
  stop: string;
  pickup_at: string | null;
  drop_at: string | null;
  direction: string;
  today: { morning?: string; afternoon?: string };
};

const hhmm = (t: string | null | undefined) => (t ? t.slice(0, 5) : "—");
const STATUS_LABEL: Record<string, string> = {
  boarded: "Got on",
  dropped: "Dropped off",
  absent: "Not at the stop",
};

/** School transport: set-up for leaders, the pick-up list for drivers, each child's bus for parents. */
export default function TransportPage() {
  const { can } = useSchool();
  if (can(PERM.TRANSPORT_MANAGE)) return <Manage />;
  if (can(PERM.TRANSPORT_RECORD)) return <DriverView />;
  return <FamilyView />;
}

function FamilyView() {
  const mine = useQuery({
    queryKey: ["transport-mine"],
    queryFn: () => api.get<Mine[]>("/api/v1/transport/mine"),
  });
  return (
    <>
      <PageHeader title="School bus" description="Your child's route, stop and times, and today's trips." />
      <ErrorText error={mine.error} />
      {mine.isPending ? (
        <Loading />
      ) : mine.data?.length ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {mine.data.map((m) => (
            <Card key={m.student} title={m.name}>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-neutral-600 dark:text-neutral-300">Route</dt>
                <dd>{m.route}</dd>
                <dt className="text-neutral-600 dark:text-neutral-300">Bus</dt>
                <dd>
                  {m.vehicle}
                  {m.registration ? ` (${m.registration})` : ""}
                </dd>
                <dt className="text-neutral-600 dark:text-neutral-300">Stop</dt>
                <dd>{m.stop}</dd>
                <dt className="text-neutral-600 dark:text-neutral-300">Pick-up</dt>
                <dd>{hhmm(m.pickup_at)}</dd>
                <dt className="text-neutral-600 dark:text-neutral-300">Drop-off</dt>
                <dd>{hhmm(m.drop_at)}</dd>
                {m.driver && (
                  <>
                    <dt className="text-neutral-600 dark:text-neutral-300">Driver</dt>
                    <dd>{m.driver}</dd>
                  </>
                )}
                {m.attendant && (
                  <>
                    <dt className="text-neutral-600 dark:text-neutral-300">Attendant</dt>
                    <dd>
                      {m.attendant}
                      {m.attendant_phone ? ` · ${m.attendant_phone}` : ""}
                    </dd>
                  </>
                )}
              </dl>
              <p className="mt-3 text-sm">
                Today: morning {m.today.morning ?? "not yet"} · afternoon {m.today.afternoon ?? "not yet"}
              </p>
            </Card>
          ))}
        </div>
      ) : (
        <Empty>Your children don't ride the school bus.</Empty>
      )}
    </>
  );
}

function DriverView() {
  const routes = useQuery({
    queryKey: ["routes"],
    queryFn: () => api.get<Route[]>("/api/v1/transport/routes"),
  });
  const [route, setRoute] = useState("");
  const chosen = route || routes.data?.[0]?.id || "";
  return (
    <>
      <PageHeader
        title="Pick-up list"
        description="Mark each pupil as they get on and off the bus. Parents get a note."
      />
      <ErrorText error={routes.error} />
      {routes.isPending ? (
        <Loading />
      ) : routes.data?.length ? (
        <>
          {routes.data.length > 1 && (
            <div className="mb-4 w-64">
              <Field label="Route">
                <Select value={chosen} onChange={(e) => setRoute(e.target.value)}>
                  {routes.data.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          )}
          {chosen && <RollView route={chosen} />}
        </>
      ) : (
        <Empty>You don't have a route yet. Ask the school office to put you on a bus.</Empty>
      )}
    </>
  );
}

function RollView({ route }: { route: string }) {
  const client = useQueryClient();
  const [direction, setDirection] = useState<"morning" | "afternoon">(
    new Date().getHours() < 12 ? "morning" : "afternoon",
  );
  const roll = useQuery({
    queryKey: ["roll", route, direction],
    queryFn: () => api.get<Roll>(`/api/v1/transport/routes/${route}/roll?direction=${direction}`),
  });
  const mark = useMutation({
    mutationFn: (body: { student: string; status: string }) =>
      api.post(`/api/v1/transport/routes/${route}/mark`, { ...body, direction }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["roll", route, direction] }),
  });
  const options =
    direction === "morning"
      ? [
          ["boarded", "Got on"],
          ["absent", "Not at the stop"],
        ]
      : [
          ["boarded", "Got on"],
          ["dropped", "Dropped off"],
        ];
  return (
    <section aria-labelledby="roll-title">
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <h2 id="roll-title" className="font-medium">
          {roll.data ? `${roll.data.route}, ${formatDate(roll.data.date)}` : "Pick-up list"}
        </h2>
        <div className="w-40">
          <Field label="Trip">
            <Select
              value={direction}
              onChange={(e) => setDirection(e.target.value as "morning" | "afternoon")}
            >
              <option value="morning">Morning</option>
              <option value="afternoon">Afternoon</option>
            </Select>
          </Field>
        </div>
      </div>
      <ErrorText error={roll.error ?? mark.error} />
      {roll.isPending ? (
        <Loading />
      ) : roll.data?.riders.length ? (
        <ul className="divide-y divide-neutral-100 rounded-card border border-neutral-200 bg-white dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
          {roll.data.riders.map((r) => (
            <li key={r.student} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
              <span>
                <span className="font-medium">{r.name}</span>
                <span className="block text-sm text-neutral-600 dark:text-neutral-300">
                  {r.stop} · {hhmm(r.time)} · {r.class}
                </span>
              </span>
              <span className="flex flex-wrap items-center gap-2">
                {r.status && (
                  <Badge tone={r.status === "absent" ? "amber" : "green"}>
                    {STATUS_LABEL[r.status] ?? r.status}
                  </Badge>
                )}
                {options.map(([value, label]) => (
                  <Button
                    key={value}
                    variant={r.status === value ? "primary" : "secondary"}
                    busy={
                      mark.isPending &&
                      mark.variables?.student === r.student &&
                      mark.variables.status === value
                    }
                    onClick={() => mark.mutate({ student: r.student, status: value ?? "" })}
                    aria-label={`${label}: ${r.name}`}
                  >
                    {label}
                  </Button>
                ))}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Nobody rides this trip.</Empty>
      )}
    </section>
  );
}

function Manage() {
  const [tab, setTab] = useState<"routes" | "vehicles" | "riders">("routes");
  return (
    <>
      <PageHeader
        title="School transport"
        description="Buses, routes and stops, and which pupils ride them."
      />
      <div
        role="tablist"
        aria-label="Transport"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["routes", "Routes"],
            ["vehicles", "Buses"],
            ["riders", "Pupils on the buses"],
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
      <div role="tabpanel">
        {tab === "routes" && <RoutesTab />}
        {tab === "vehicles" && <VehiclesTab />}
        {tab === "riders" && <RidersTab />}
      </div>
    </>
  );
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    for (const key of ["routes", "vehicles", "riders"]) void client.invalidateQueries({ queryKey: [key] });
  };
}

function RoutesTab() {
  const routes = useQuery({
    queryKey: ["routes"],
    queryFn: () => api.get<Route[]>("/api/v1/transport/routes"),
  });
  const [editing, setEditing] = useState<Route | "new" | null>(null);
  const [adding, setAdding] = useState<Route | null>(null);
  const [roll, setRoll] = useState<Route | null>(null);
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setEditing("new")}>New route</Button>
      </div>
      <ErrorText error={routes.error} />
      {routes.isPending ? (
        <Loading />
      ) : routes.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {routes.data.map((r) => (
            <Card
              key={r.id}
              title={`${r.name} · ${r.rider_count}${r.seats ? ` of ${r.seats}` : ""} pupils`}
              actions={
                <Button variant="ghost" onClick={() => setEditing(r)} aria-label={`Change ${r.name}`}>
                  Change
                </Button>
              }
            >
              <p className="mb-2 text-sm text-neutral-600 dark:text-neutral-300">
                {r.vehicle_name || "No bus yet"}
              </p>
              <Table head={["Stop", "Pick-up", "Drop-off", "Pupils"]}>
                {r.stops.map((s) => (
                  <tr key={s.id}>
                    <Td>{s.name}</Td>
                    <Td className="tabular-nums">{hhmm(s.pickup_at)}</Td>
                    <Td className="tabular-nums">{hhmm(s.drop_at)}</Td>
                    <Td className="tabular-nums">{s.rider_count ?? 0}</Td>
                  </tr>
                ))}
              </Table>
              <div className="mt-3 flex flex-wrap justify-end gap-2">
                <Button variant="secondary" onClick={() => setRoll(r)}>
                  Pick-up list
                </Button>
                <Button variant="secondary" onClick={() => setAdding(r)} disabled={!r.stops.length}>
                  Add a pupil
                </Button>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Empty>No routes yet.</Empty>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New route" : "Change route"}
      >
        {editing !== null && (
          <RouteForm route={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
      <Modal
        open={adding !== null}
        onClose={() => setAdding(null)}
        title={`Add a pupil to ${adding?.name ?? ""}`}
      >
        {adding && <AddRider route={adding} onDone={() => setAdding(null)} />}
      </Modal>
      <Modal open={roll !== null} onClose={() => setRoll(null)} title="Pick-up list">
        {roll && <RollView route={roll.id} />}
      </Modal>
    </>
  );
}

function RouteForm({ route, onDone }: { route: Route | null; onDone: () => void }) {
  const refresh = useRefresh();
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/api/v1/transport/vehicles"),
  });
  const [name, setName] = useState(route?.name ?? "");
  const [vehicle, setVehicle] = useState(route?.vehicle ?? "");
  const [stops, setStops] = useState<StopRow[]>(
    route?.stops ?? [{ name: "", pickup_at: null, drop_at: null }],
  );
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      route
        ? api.patch(`/api/v1/transport/routes/${route.id}`, body)
        : api.post("/api/v1/transport/routes", body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  const set = (i: number, patch: Partial<StopRow>) =>
    setStops((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({
      name,
      vehicle: vehicle || null,
      stops: stops
        .filter((s) => s.name.trim())
        .map((s) => ({
          id: s.id,
          name: s.name.trim(),
          pickup_at: s.pickup_at || null,
          drop_at: s.drop_at || null,
        })),
    });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Route name">
        <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
      </Field>
      <Field label="Bus">
        <Select value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
          <option value="">No bus yet</option>
          {vehicles.data?.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.seats} seats)
            </option>
          ))}
        </Select>
      </Field>
      <fieldset className="flex flex-col gap-2 rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
        <legend className="px-1 text-sm font-medium">Stops, in order</legend>
        {stops.map((s, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: new stops have no id yet; order is the identity.
          <div key={i} className="grid grid-cols-[1fr_6.5rem_6.5rem_auto] items-end gap-2">
            <Field label={`Stop ${i + 1}`}>
              <Input value={s.name} onChange={(e) => set(i, { name: e.target.value })} maxLength={80} />
            </Field>
            <Field label="Pick-up">
              <Input
                type="time"
                value={s.pickup_at?.slice(0, 5) ?? ""}
                onChange={(e) => set(i, { pickup_at: e.target.value })}
              />
            </Field>
            <Field label="Drop-off">
              <Input
                type="time"
                value={s.drop_at?.slice(0, 5) ?? ""}
                onChange={(e) => set(i, { drop_at: e.target.value })}
              />
            </Field>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setStops((all) => all.filter((_, j) => j !== i))}
              aria-label={`Remove stop ${i + 1}`}
            >
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setStops((all) => [...all, { name: "", pickup_at: null, drop_at: null }])}
          >
            Add a stop
          </Button>
        </div>
      </fieldset>
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Save route
        </Button>
      </div>
    </form>
  );
}

function AddRider({ route, onDone }: { route: Route; onDone: () => void }) {
  const refresh = useRefresh();
  const [q, setQ] = useState("");
  const pupils = useQuery({
    queryKey: ["students", "bus-search", q],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?page_size=20&q=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2,
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/transport/routes/${route.id}/add_rider`, body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        add.mutate({ student: f.student, stop: Number(f.stop), direction: f.direction });
      }}
    >
      <Field label="Find the pupil">
        <Input value={q} onChange={(e) => setQ(e.target.value)} />
      </Field>
      <Field label="Pupil">
        <Select name="student" required defaultValue="">
          <option value="" disabled>
            {q.trim().length >= 2 ? "Choose" : "Search first"}
          </option>
          {pupils.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.first_name} {p.last_name} {p.arm_name ? `(${p.arm_name})` : ""}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Stop">
        <Select name="stop" required defaultValue={String(route.stops[0]?.id ?? "")}>
          {route.stops.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Rides">
        <Select name="direction" defaultValue="both">
          <option value="both">Both ways</option>
          <option value="morning">Mornings only</option>
          <option value="afternoon">Afternoons only</option>
        </Select>
      </Field>
      <p className="text-xs text-neutral-600 dark:text-neutral-400">
        A pupil on another route is moved to this one.
      </p>
      <ErrorText error={add.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={add.isPending}>
          Add pupil
        </Button>
      </div>
    </form>
  );
}

function VehiclesTab() {
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/api/v1/transport/vehicles"),
  });
  const [editing, setEditing] = useState<Vehicle | "new" | null>(null);
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setEditing("new")}>Add a bus</Button>
      </div>
      <ErrorText error={vehicles.error} />
      {vehicles.isPending ? (
        <Loading />
      ) : vehicles.data?.length ? (
        <Table head={["Bus", "Seats", "Driver", "Attendant", ""]}>
          {vehicles.data.map((v) => (
            <tr key={v.id}>
              <Td>
                <span className="font-medium">{v.name}</span>
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">{v.registration}</span>
              </Td>
              <Td className="tabular-nums">{v.seats}</Td>
              <Td>{v.driver_name || "—"}</Td>
              <Td>
                {v.attendant || "—"}
                {v.attendant_phone && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {v.attendant_phone}
                  </span>
                )}
              </Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setEditing(v)} aria-label={`Change ${v.name}`}>
                  Change
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No buses yet.</Empty>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add a bus" : "Change bus"}
      >
        {editing !== null && (
          <VehicleForm vehicle={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
    </>
  );
}

function VehicleForm({ vehicle, onDone }: { vehicle: Vehicle | null; onDone: () => void }) {
  const refresh = useRefresh();
  const drivers = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.get<{ id: string; name: string }[]>("/api/v1/transport/drivers"),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      vehicle
        ? api.patch(`/api/v1/transport/vehicles/${vehicle.id}`, body)
        : api.post("/api/v1/transport/vehicles", body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          name: f.name,
          registration: f.registration,
          seats: Number(f.seats),
          driver_user_id: f.driver_user_id || null,
          attendant: f.attendant,
          attendant_phone: f.attendant_phone,
        });
      }}
    >
      <Field label="Name">
        <Input name="name" required maxLength={60} defaultValue={vehicle?.name} placeholder="Bus 1" />
      </Field>
      <Field label="Registration (optional)">
        <Input
          name="registration"
          maxLength={20}
          defaultValue={vehicle?.registration}
          placeholder="GR 1234-23"
        />
      </Field>
      <Field label="Seats">
        <Input name="seats" type="number" min={1} max={120} required defaultValue={vehicle?.seats ?? 30} />
      </Field>
      <Field label="Driver" hint="People with the Driver role.">
        <Select name="driver_user_id" defaultValue={vehicle?.driver_user_id ?? ""}>
          <option value="">No driver yet</option>
          {drivers.data?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Attendant (optional)">
        <Input name="attendant" maxLength={80} defaultValue={vehicle?.attendant} />
      </Field>
      <Field label="Attendant's phone (optional)">
        <Input name="attendant_phone" maxLength={20} defaultValue={vehicle?.attendant_phone} />
      </Field>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Save bus
        </Button>
      </div>
    </form>
  );
}

function RidersTab() {
  const refresh = useRefresh();
  const riders = useQuery({
    queryKey: ["riders"],
    queryFn: () => api.get<Rider[]>("/api/v1/transport/riders"),
  });
  const remove = useMutation({
    mutationFn: (r: Rider) =>
      api.post(`/api/v1/transport/routes/${r.route}/remove_rider`, { student: r.student }),
    onSuccess: refresh,
  });
  return (
    <>
      <ErrorText error={riders.error ?? remove.error} />
      {riders.isPending ? (
        <Loading />
      ) : riders.data?.length ? (
        <Table head={["Pupil", "Route", "Stop", "Rides", ""]}>
          {riders.data.map((r) => (
            <tr key={r.student}>
              <Td>
                <span className="font-medium">{r.name}</span>
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">{r.class}</span>
              </Td>
              <Td>{r.route_name}</Td>
              <Td>{r.stop}</Td>
              <Td>{r.direction}</Td>
              <Td className="text-right">
                <Button
                  variant="ghost"
                  onClick={() => remove.mutate(r)}
                  aria-label={`Take ${r.name} off the bus`}
                >
                  Remove
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No pupils on the buses yet.</Empty>
      )}
    </>
  );
}
