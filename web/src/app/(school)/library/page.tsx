"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Book = {
  id: string;
  title: string;
  author: string;
  isbn: string;
  publisher: string;
  category: string;
  category_label: string;
  level: number | null;
  level_name: string;
  shelf: string;
  copies_total: number;
  copies_available: number;
};
type Copy = { id: string; accession_number: string; status: string; status_label: string; condition: string };
type Loan = {
  id: string;
  accession_number: string;
  title: string;
  student: string | null;
  borrower: string;
  borrower_class: string;
  borrowed_on: string;
  due_on: string;
  returned_on: string | null;
  outcome: "open" | "returned" | "lost";
  renewals: number;
  overdue_days: number;
  reminded_on: string | null;
};
type Rules = {
  pupil_loan_days: number;
  staff_loan_days: number;
  pupil_limit: number;
  staff_limit: number;
  max_renewals: number;
};
type Overview = {
  settings: Rules;
  titles?: number;
  copies?: number;
  on_shelf?: number;
  on_loan?: number;
  lost?: number;
  overdue?: number;
  popular?: { book: string; title: string; loans: number }[];
};
type Borrower = { id: string; name: string; holding: number; class?: string; admission_number?: string };
type Tab = "desk" | "loans" | "catalogue" | "rules";

const CATEGORIES: [string, string][] = [
  ["reader", "Reader / storybook"],
  ["textbook", "Textbook"],
  ["reference", "Reference"],
  ["fiction", "Fiction"],
  ["non_fiction", "Non-fiction"],
  ["other", "Other"],
];

/** The school library: the desk for lending and returns, loans, the catalogue and the rules. */
export default function LibraryPage() {
  const { can } = useSchool();
  if (!can(PERM.LIBRARY_MANAGE)) return <Borrowing />;
  return <Desk />;
}

function useOverview() {
  return useQuery({ queryKey: ["library"], queryFn: () => api.get<Overview>("/api/v1/library") });
}

function Desk() {
  const [tab, setTab] = useState<Tab>("desk");
  const overview = useOverview();
  const o = overview.data;
  return (
    <>
      <PageHeader
        title="Library"
        description="Lend and take back books, see who has what, and keep the catalogue."
      />
      {o?.titles !== undefined && (
        <div className="mb-5 grid gap-4 sm:grid-cols-4">
          <Stat label="Titles" value={o.titles} />
          <Stat label="Copies on the shelf" value={`${o.on_shelf} of ${o.copies}`} />
          <Stat label="On loan" value={o.on_loan ?? 0} />
          <Stat label="Overdue" value={o.overdue ?? 0} />
        </div>
      )}
      <div
        role="tablist"
        aria-label="Library"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["desk", "Desk"],
            ["loans", "On loan"],
            ["catalogue", "Catalogue"],
            ["rules", "Lending rules"],
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
        {tab === "desk" && <DeskTab popular={o?.popular ?? []} />}
        {tab === "loans" && <LoansTab />}
        {tab === "catalogue" && <CatalogueTab manage />}
        {tab === "rules" && o && <RulesTab rules={o.settings} />}
      </div>
    </>
  );
}

function useRefreshLibrary() {
  const client = useQueryClient();
  return () => {
    for (const key of ["library", "library-loans", "library-books"])
      void client.invalidateQueries({ queryKey: [key] });
  };
}

function DeskTab({ popular }: { popular: { book: string; title: string; loans: number }[] }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <LendCard />
      <ReturnCard />
      {popular.length > 0 && (
        <Card title="Borrowed most (last 90 days)">
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {popular.map((p) => (
              <li key={p.book}>
                {p.title} <span className="text-neutral-600 dark:text-neutral-400">· {p.loans} loans</span>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

function LendCard() {
  const refresh = useRefreshLibrary();
  const [q, setQ] = useState("");
  const [borrower, setBorrower] = useState<{ kind: "student" | "staff_user"; who: Borrower } | null>(null);
  const [accession, setAccession] = useState("");
  const [done, setDone] = useState<Loan | null>(null);
  const search = useQuery({
    queryKey: ["library-borrowers", q],
    queryFn: () =>
      api.get<{ pupils: Borrower[]; staff: Borrower[] }>(
        `/api/v1/library/borrowers?q=${encodeURIComponent(q.trim())}`,
      ),
    enabled: q.trim().length >= 2 && !borrower,
  });
  const lend = useMutation({
    mutationFn: () =>
      api.post<Loan>("/api/v1/library/loans/issue", {
        accession_number: accession,
        ...(borrower ? { [borrower.kind]: borrower.who.id } : {}),
      }),
    onSuccess: (loan) => {
      setDone(loan);
      setAccession("");
      setBorrower(null);
      setQ("");
      refresh();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (borrower && accession.trim()) lend.mutate();
  };
  const results = search.data
    ? [
        ...search.data.pupils.map((p) => ({ kind: "student" as const, who: p })),
        ...search.data.staff.map((s) => ({ kind: "staff_user" as const, who: s })),
      ]
    : [];

  return (
    <Card title="Lend a book">
      <form onSubmit={submit} className="flex flex-col gap-3">
        {borrower ? (
          <div className="flex items-center justify-between gap-2 rounded-control bg-neutral-50 px-3 py-2 text-sm dark:bg-neutral-800">
            <span>
              <span className="font-medium">{borrower.who.name}</span>{" "}
              <span className="text-neutral-600 dark:text-neutral-300">
                {borrower.kind === "staff_user" ? "Staff" : borrower.who.class} · {borrower.who.holding}{" "}
                book(s) out
              </span>
            </span>
            <Button type="button" variant="ghost" onClick={() => setBorrower(null)}>
              Change
            </Button>
          </div>
        ) : (
          <>
            <Field label="Borrower" hint="Type a pupil's or staff member's name, or an admission number.">
              <Input value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
            </Field>
            {results.length > 0 && (
              <ul
                aria-label="Matching borrowers"
                className="max-h-56 divide-y divide-neutral-100 overflow-y-auto rounded-control border border-neutral-200 text-sm dark:divide-neutral-800 dark:border-neutral-800"
              >
                {results.map((r) => (
                  <li key={`${r.kind}-${r.who.id}`}>
                    <button
                      type="button"
                      className="flex w-full justify-between gap-2 px-3 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800"
                      onClick={() => setBorrower(r)}
                    >
                      <span className="font-medium">{r.who.name}</span>
                      <span className="text-neutral-600 dark:text-neutral-300">
                        {r.kind === "staff_user" ? "Staff" : `${r.who.class} · ${r.who.admission_number}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {q.trim().length >= 2 && search.data && results.length === 0 && (
              <p className="text-sm text-neutral-600 dark:text-neutral-300">Nobody matches.</p>
            )}
          </>
        )}
        <Field label="Book number" hint="The accession number on the book, for example LIB-00012.">
          <Input
            value={accession}
            onChange={(e) => setAccession(e.target.value)}
            autoComplete="off"
            required
          />
        </Field>
        <ErrorText error={lend.error} />
        {done && !lend.error && (
          <Alert tone="success">
            Lent “{done.title}” to {done.borrower}. Due back {formatDate(done.due_on)}.
          </Alert>
        )}
        <div className="flex justify-end">
          <Button type="submit" busy={lend.isPending} disabled={!borrower || !accession.trim()}>
            Lend
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ReturnCard() {
  const refresh = useRefreshLibrary();
  const [accession, setAccession] = useState("");
  const [condition, setCondition] = useState("");
  const [done, setDone] = useState<Loan | null>(null);
  const giveBack = useMutation({
    mutationFn: () =>
      api.post<Loan>("/api/v1/library/loans/return", { accession_number: accession, condition }),
    onSuccess: (loan) => {
      setDone(loan);
      setAccession("");
      setCondition("");
      refresh();
    },
  });
  return (
    <Card title="Take a book back">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (accession.trim()) giveBack.mutate();
        }}
        className="flex flex-col gap-3"
      >
        <Field label="Book number">
          <Input
            value={accession}
            onChange={(e) => setAccession(e.target.value)}
            autoComplete="off"
            required
          />
        </Field>
        <Field label="Condition now (optional)">
          <Select value={condition} onChange={(e) => setCondition(e.target.value)}>
            <option value="">No change</option>
            <option value="good">Good</option>
            <option value="fair">Fair</option>
            <option value="poor">Poor</option>
          </Select>
        </Field>
        <ErrorText error={giveBack.error} />
        {done && !giveBack.error && (
          <Alert tone="success">
            “{done.title}” is back from {done.borrower}
            {done.overdue_days > 0 ? `, ${done.overdue_days} day(s) late` : ""}.
          </Alert>
        )}
        <div className="flex justify-end">
          <Button type="submit" busy={giveBack.isPending} disabled={!accession.trim()}>
            Take back
          </Button>
        </div>
      </form>
    </Card>
  );
}

function LoansTab() {
  const { hasModule } = useSchool();
  const refresh = useRefreshLibrary();
  const [state, setState] = useState("open");
  const [q, setQ] = useState("");
  const [sms, setSms] = useState(false);
  const [losing, setLosing] = useState<Loan | null>(null);
  const loans = useQuery({
    queryKey: ["library-loans", state, q],
    queryFn: () => api.get<Loan[]>(`/api/v1/library/loans?state=${state}&q=${encodeURIComponent(q.trim())}`),
    placeholderData: keepPreviousData,
  });
  const renew = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/library/loans/${id}/renew`),
    onSuccess: refresh,
  });
  const lost = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/library/loans/${id}/lost`),
    onSuccess: () => {
      setLosing(null);
      refresh();
    },
  });
  const remind = useMutation({
    mutationFn: () => api.post<{ pupils: number }>("/api/v1/library/loans/remind", { sms }),
    onSuccess: refresh,
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Field label="Show">
            <Select value={state} onChange={(e) => setState(e.target.value)}>
              <option value="open">On loan</option>
              <option value="overdue">Overdue</option>
              <option value="closed">Returned or lost</option>
            </Select>
          </Field>
        </div>
        <div className="w-56">
          <Field label="Search">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Title, book number or pupil"
            />
          </Field>
        </div>
        {state === "overdue" && (
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {hasModule("sms") && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-brand"
                  checked={sms}
                  onChange={(e) => setSms(e.target.checked)}
                />
                Also by SMS
              </label>
            )}
            <Button
              variant="secondary"
              busy={remind.isPending}
              onClick={() => remind.mutate()}
              disabled={!loans.data?.length}
            >
              Remind parents
            </Button>
          </div>
        )}
      </div>
      <ErrorText error={loans.error ?? renew.error ?? remind.error} />
      {remind.data && (
        <div className="mb-3">
          <Alert tone="success">
            {remind.data.pupils
              ? `Reminded the parents of ${remind.data.pupils} pupil(s).`
              : "Everyone with an overdue book has already been reminded today."}
          </Alert>
        </div>
      )}
      {loans.isPending ? (
        <Loading />
      ) : loans.data?.length ? (
        <Table head={["Book", "Borrower", "Borrowed", "Due", ""]}>
          {loans.data.map((l) => (
            <tr key={l.id}>
              <Td>
                <span className="font-medium">{l.title}</span>
                <span className="block font-mono text-xs text-neutral-600 dark:text-neutral-400">
                  {l.accession_number}
                </span>
              </Td>
              <Td>
                {l.borrower}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {l.borrower_class}
                </span>
              </Td>
              <Td className="whitespace-nowrap">{formatDate(l.borrowed_on)}</Td>
              <Td className="whitespace-nowrap">
                {l.outcome === "open" ? (
                  <>
                    {formatDate(l.due_on)}
                    {l.overdue_days > 0 && (
                      <span className="ml-2">
                        <Badge tone="red">{`${l.overdue_days} day${l.overdue_days === 1 ? "" : "s"} late`}</Badge>
                      </span>
                    )}
                  </>
                ) : l.outcome === "lost" ? (
                  <Badge tone="red">Lost</Badge>
                ) : (
                  `Back ${formatDate(l.returned_on)}`
                )}
              </Td>
              <Td className="whitespace-nowrap text-right">
                {l.outcome === "open" && (
                  <>
                    {l.overdue_days === 0 && (
                      <Button
                        variant="ghost"
                        busy={renew.isPending && renew.variables === l.id}
                        onClick={() => renew.mutate(l.id)}
                      >
                        Renew
                      </Button>
                    )}
                    <Button variant="ghost" onClick={() => setLosing(l)}>
                      Lost
                    </Button>
                  </>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>{state === "overdue" ? "No overdue books." : "Nothing to show."}</Empty>
      )}
      <Modal open={losing !== null} onClose={() => setLosing(null)} title="Mark this book as lost?">
        {losing && (
          <div className="flex flex-col gap-3 text-sm">
            <p>
              “{losing.title}” ({losing.accession_number}) borrowed by {losing.borrower} will be taken off the
              shelf list. This is recorded in the audit log.
            </p>
            <ErrorText error={lost.error} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setLosing(null)}>
                Cancel
              </Button>
              <Button variant="danger" busy={lost.isPending} onClick={() => lost.mutate(losing.id)}>
                Mark lost
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

function CatalogueTab({ manage }: { manage: boolean }) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [open, setOpen] = useState<Book | "new" | "import" | null>(null);
  const books = useQuery({
    queryKey: ["library-books", q, category],
    queryFn: () =>
      api.get<Book[]>(
        `/api/v1/library/books?q=${encodeURIComponent(q.trim())}${category ? `&category=${category}` : ""}`,
      ),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Field label="Search the catalogue">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Title, author, ISBN or book number"
            />
          </Field>
        </div>
        <div className="w-48">
          <Field label="Kind">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All kinds</option>
              {CATEGORIES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {manage && (
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" onClick={() => setOpen("import")}>
              Import from spreadsheet
            </Button>
            <Button onClick={() => setOpen("new")}>Add a book</Button>
          </div>
        )}
      </div>
      <ErrorText error={books.error} />
      {books.isPending ? (
        <Loading />
      ) : books.data?.length ? (
        <Table head={["Title", "Kind", "Shelf", "On the shelf"]}>
          {books.data.map((b) => (
            <tr key={b.id}>
              <Td>
                {manage ? (
                  <button
                    type="button"
                    className="text-left font-medium text-brand-strong hover:underline dark:text-brand-sky"
                    onClick={() => setOpen(b)}
                  >
                    {b.title}
                  </button>
                ) : (
                  <span className="font-medium">{b.title}</span>
                )}
                {b.author && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">{b.author}</span>
                )}
              </Td>
              <Td>
                {b.category_label}
                {b.level_name ? ` · ${b.level_name}` : ""}
              </Td>
              <Td>{b.shelf || "—"}</Td>
              <Td className="tabular-nums">
                {b.copies_available} of {b.copies_total}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>{q || category ? "No books match." : "No books yet."}</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "Add a book" : open === "import" ? "Import books" : "Book"}
      >
        {open === "import" && <ImportForm onDone={() => setOpen(null)} />}
        {open !== null && open !== "import" && (
          <BookForm book={open === "new" ? null : open} onDone={() => setOpen(null)} />
        )}
      </Modal>
    </>
  );
}

function BookForm({ book, onDone }: { book: Book | null; onDone: () => void }) {
  const refresh = useRefreshLibrary();
  const client = useQueryClient();
  const levels = useQuery({
    queryKey: ["levels"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/api/v1/academics/levels"),
  });
  const detail = useQuery({
    queryKey: ["library-book", book?.id],
    queryFn: () => api.get<Book & { copy_list: Copy[] }>(`/api/v1/library/books/${book?.id}`),
    enabled: Boolean(book),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      book ? api.patch(`/api/v1/library/books/${book.id}`, body) : api.post("/api/v1/library/books", body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  const more = useMutation({
    mutationFn: (copies: number) => api.post(`/api/v1/library/books/${book?.id}/add_copies`, { copies }),
    onSuccess: () => {
      refresh();
      void client.invalidateQueries({ queryKey: ["library-book", book?.id] });
    },
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch(`/api/v1/library/copies/${id}`, { status }),
    onSuccess: () => {
      refresh();
      void client.invalidateQueries({ queryKey: ["library-book", book?.id] });
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      title: f.title,
      author: f.author,
      isbn: f.isbn,
      publisher: f.publisher,
      category: f.category,
      level: f.level || null,
      shelf: f.shelf,
      ...(book ? {} : { copies: Number(f.copies || 1) }),
    });
  };
  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Title">
            <Input name="title" required maxLength={200} defaultValue={book?.title} />
          </Field>
        </div>
        <Field label="Author (optional)">
          <Input name="author" maxLength={160} defaultValue={book?.author} />
        </Field>
        <Field label="ISBN (optional)">
          <Input name="isbn" maxLength={20} defaultValue={book?.isbn} />
        </Field>
        <Field label="Publisher (optional)">
          <Input name="publisher" maxLength={120} defaultValue={book?.publisher} />
        </Field>
        <Field label="Kind">
          <Select name="category" defaultValue={book?.category ?? "reader"}>
            {CATEGORIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Suits class (optional)">
          <Select name="level" defaultValue={book?.level ?? ""}>
            <option value="">Any class</option>
            {levels.data?.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Shelf (optional)">
          <Input name="shelf" maxLength={40} defaultValue={book?.shelf} />
        </Field>
        {!book && (
          <Field label="Number of copies" hint="Each copy gets its own book number.">
            <Input name="copies" type="number" min={1} max={200} defaultValue={1} required />
          </Field>
        )}
        <div className="sm:col-span-2">
          <ErrorText error={save.error} />
        </div>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" busy={save.isPending}>
            {book ? "Save changes" : "Add book"}
          </Button>
        </div>
      </form>
      {book && (
        <section aria-labelledby="copies-title">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 id="copies-title" className="font-medium">
              Copies
            </h3>
            <Button variant="secondary" busy={more.isPending} onClick={() => more.mutate(1)}>
              Add a copy
            </Button>
          </div>
          <ErrorText error={more.error ?? setStatus.error} />
          {detail.data?.copy_list.length ? (
            <ul className="divide-y divide-neutral-100 rounded-control border border-neutral-200 text-sm dark:divide-neutral-800 dark:border-neutral-800">
              {detail.data.copy_list.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <span>
                    <span className="font-mono">{c.accession_number}</span>{" "}
                    <span className="text-neutral-600 dark:text-neutral-400">
                      {c.status_label} · {c.condition}
                    </span>
                  </span>
                  {c.status === "available" && (
                    <Button
                      variant="ghost"
                      onClick={() => setStatus.mutate({ id: c.id, status: "withdrawn" })}
                    >
                      Withdraw
                    </Button>
                  )}
                  {(c.status === "withdrawn" || c.status === "lost") && (
                    <Button
                      variant="ghost"
                      onClick={() => setStatus.mutate({ id: c.id, status: "available" })}
                    >
                      Back on the shelf
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Loading />
          )}
        </section>
      )}
    </div>
  );
}

function ImportForm({ onDone }: { onDone: () => void }) {
  const refresh = useRefreshLibrary();
  const upload = useMutation({
    mutationFn: (form: FormData) =>
      api.post<{ titles: number; copies: number }>("/api/v1/library/import", form),
    onSuccess: refresh,
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        upload.mutate(new FormData(e.currentTarget));
      }}
      className="flex flex-col gap-3 text-sm"
    >
      <p>
        Save your book list as a CSV file with these columns: <strong>Title</strong> (needed), Author, ISBN,
        Publisher, Category, Shelf, Copies (1 if empty). Every row is checked first; nothing is added if a row
        is wrong.
      </p>
      <Field label="CSV file">
        <Input type="file" name="file" accept=".csv,text/csv" required />
      </Field>
      <ErrorText error={upload.error} />
      {upload.data && (
        <Alert tone="success">
          Added {upload.data.titles} titles and {upload.data.copies} copies.
        </Alert>
      )}
      <div className="flex justify-end gap-2">
        {upload.data ? (
          <Button type="button" onClick={onDone}>
            Done
          </Button>
        ) : (
          <Button type="submit" busy={upload.isPending}>
            Import
          </Button>
        )}
      </div>
    </form>
  );
}

function RulesTab({ rules }: { rules: Rules }) {
  const refresh = useRefreshLibrary();
  const save = useMutation({
    mutationFn: (body: Rules) => api.patch<Rules>("/api/v1/library", body),
    onSuccess: refresh,
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      pupil_loan_days: Number(f.pupil_loan_days),
      staff_loan_days: Number(f.staff_loan_days),
      pupil_limit: Number(f.pupil_limit),
      staff_limit: Number(f.staff_limit),
      max_renewals: Number(f.max_renewals),
    });
  };
  const number = (name: keyof Rules, label: string, max: number, min = 1) => (
    <Field label={label}>
      <Input name={name} type="number" min={min} max={max} defaultValue={rules[name]} required />
    </Field>
  );
  return (
    <Card title="Lending rules">
      <form onSubmit={submit} className="grid max-w-xl gap-3 sm:grid-cols-2">
        {number("pupil_loan_days", "Pupils keep a book for (days)", 120)}
        {number("staff_loan_days", "Staff keep a book for (days)", 365)}
        {number("pupil_limit", "Books a pupil may have out", 20)}
        {number("staff_limit", "Books a staff member may have out", 50)}
        {number("max_renewals", "Times a loan can be renewed", 10, 0)}
        <div className="sm:col-span-2">
          <ErrorText error={save.error} />
          {save.isSuccess && <Alert tone="success">Saved. New loans follow these rules.</Alert>}
        </div>
        <div className="flex justify-end sm:col-span-2">
          <Button type="submit" busy={save.isPending}>
            Save rules
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Parents, pupils and teachers: books borrowed (own, children's or pupils'), and the catalogue. */
function Borrowing() {
  const { roles } = useSchool();
  const overview = useOverview();
  const loans = useQuery({
    queryKey: ["library-loans", "all-mine"],
    queryFn: () => api.get<Loan[]>("/api/v1/library/loans?state=all"),
  });
  const out = loans.data?.filter((l) => l.outcome === "open") ?? [];
  const past = loans.data?.filter((l) => l.outcome !== "open").slice(0, 20) ?? [];
  const parent = roles.includes("parent");
  return (
    <>
      <PageHeader
        title="Library"
        description={
          parent
            ? "Books your children have borrowed, and the school's catalogue."
            : "Books borrowed, and the school's catalogue."
        }
      />
      <section aria-labelledby="out-title" className="mb-6">
        <h2 id="out-title" className="mb-2 font-medium">
          Borrowed now
        </h2>
        <ErrorText error={loans.error} />
        {loans.isPending ? (
          <Loading />
        ) : out.length ? (
          <Table head={["Book", "Borrower", "Due back"]}>
            {out.map((l) => (
              <tr key={l.id}>
                <Td className="font-medium">{l.title}</Td>
                <Td>{l.borrower}</Td>
                <Td className="whitespace-nowrap">
                  {formatDate(l.due_on)}
                  {l.overdue_days > 0 && (
                    <span className="ml-2">
                      <Badge tone="red">Overdue</Badge>
                    </span>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No books out.</Empty>
        )}
        {overview.data && (
          <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
            Pupils may borrow {overview.data.settings.pupil_limit} book(s) at a time, for{" "}
            {overview.data.settings.pupil_loan_days} days.
          </p>
        )}
      </section>
      {past.length > 0 && (
        <section aria-labelledby="past-title" className="mb-6">
          <h2 id="past-title" className="mb-2 font-medium">
            Returned
          </h2>
          <ul className="text-sm">
            {past.map((l) => (
              <li key={l.id}>
                {l.title} · {l.borrower} ·{" "}
                {l.outcome === "lost" ? "lost" : `back ${formatDate(l.returned_on)}`}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="catalogue-title">
        <h2 id="catalogue-title" className="mb-2 font-medium">
          Catalogue
        </h2>
        <CatalogueTab manage={false} />
      </section>
    </>
  );
}
