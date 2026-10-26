"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import {
  api,
  type Contact,
  type Conversation,
  type ConversationMessage,
  type Paged,
  type Student,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Thread = Conversation & { messages: ConversationMessage[] };

/** Private messages between parents and the staff who teach their children. */
export default function MessagesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Messages />
    </Suspense>
  );
}

function Messages() {
  const { can, roles } = useSchool();
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("c"));
  const [everyone, setEveryone] = useState(false);
  const [writing, setWriting] = useState(false);
  const isParent = roles.includes("parent");
  const oversee = can(PERM.MESSAGES_OVERSEE);
  const canWrite = can(PERM.MESSAGES_USE);

  const list = useQuery({
    queryKey: ["conversations", everyone],
    queryFn: () => api.get<Conversation[]>(`/api/v1/communication/conversations${everyone ? "?all=1" : ""}`),
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="Messages"
        description={
          isParent
            ? "Write to your child's teachers, the head teacher or the bursar."
            : "Private messages with parents about their children."
        }
        actions={canWrite && <Button onClick={() => setWriting(true)}>New message</Button>}
      />
      {oversee && (
        <div className="mb-4 w-64">
          <Field label="Show">
            <Select value={everyone ? "all" : "mine"} onChange={(e) => setEveryone(e.target.value === "all")}>
              <option value="mine">My messages</option>
              <option value="all">Everyone's messages (read only)</option>
            </Select>
          </Field>
        </div>
      )}
      <ErrorText error={list.error} />
      {list.isPending ? (
        <Loading />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
          <nav aria-label="Conversations" className={selected ? "hidden lg:block" : ""}>
            {list.data?.length ? (
              <ul className="divide-y divide-neutral-100 overflow-hidden rounded-card border border-neutral-200 bg-white dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
                {list.data.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(c.id)}
                      aria-current={selected === c.id ? "true" : undefined}
                      className={`block w-full px-4 py-3 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800 ${selected === c.id ? "bg-brand/5 dark:bg-brand/15" : ""}`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className={`truncate ${c.unread ? "font-semibold" : "font-medium"}`}>
                          {c.subject}
                        </span>
                        <span className="shrink-0 text-xs text-neutral-600 dark:text-neutral-400">
                          {timeAgo(c.last_message_at)}
                        </span>
                      </span>
                      <span className="block truncate text-sm text-neutral-600 dark:text-neutral-300">
                        {otherSide(c, isParent, everyone)}
                      </span>
                      <span className="flex items-center justify-between gap-2 text-xs text-neutral-600 dark:text-neutral-400">
                        <span className="truncate">
                          About {c.student_name}
                          {c.student_class ? ` · ${c.student_class}` : ""}
                        </span>
                        {c.unread && (
                          <span className="inline-flex items-center gap-1 font-medium text-brand-strong dark:text-brand-sky">
                            <span aria-hidden className="size-2 rounded-full bg-brand" />
                            New
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>{everyone ? "Nobody has written yet." : "No messages yet."}</Empty>
            )}
          </nav>
          <div className={selected ? "" : "hidden lg:block"}>
            {selected ? (
              <ThreadView id={selected} onBack={() => setSelected(null)} />
            ) : (
              <p className="rounded-card border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500 dark:border-neutral-700">
                Choose a conversation to read it.
              </p>
            )}
          </div>
        </div>
      )}
      <Modal open={writing} onClose={() => setWriting(false)} title="New message">
        {writing && (
          <NewMessage
            isParent={isParent}
            onSent={(id) => {
              setWriting(false);
              setEveryone(false);
              setSelected(id);
            }}
          />
        )}
      </Modal>
    </>
  );
}

function otherSide(c: Conversation, isParent: boolean, everyone: boolean): string {
  if (everyone && !c.mine) return `${c.staff.name} and ${c.parent.name}`;
  return isParent ? c.staff.name : c.parent.name;
}

function ThreadView({ id, onBack }: { id: string; onBack: () => void }) {
  const client = useQueryClient();
  const thread = useQuery({
    queryKey: ["conversation", id],
    queryFn: async () => {
      const t = await api.get<Thread>(`/api/v1/communication/conversations/${id}`);
      // Opening a thread marks it read: refresh the list and the menu badge.
      void client.invalidateQueries({ queryKey: ["messages-unread"] });
      void client.invalidateQueries({ queryKey: ["conversations"] });
      return t;
    },
    refetchInterval: 15_000,
  });
  const [body, setBody] = useState("");
  const reply = useMutation({
    mutationFn: () => api.post(`/api/v1/communication/conversations/${id}/reply`, { body }),
    onSuccess: () => {
      setBody("");
      void client.invalidateQueries({ queryKey: ["conversation", id] });
      void client.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (body.trim()) reply.mutate();
  };

  if (thread.isPending) return <Loading />;
  if (thread.error) return <ErrorText error={thread.error} />;
  const t = thread.data;

  return (
    <section
      aria-labelledby="thread-title"
      className="flex flex-col rounded-card border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900"
    >
      <header className="border-b border-neutral-200 p-4 dark:border-neutral-800">
        <button
          type="button"
          onClick={onBack}
          className="mb-2 text-sm text-brand-strong hover:underline lg:hidden dark:text-brand-sky"
        >
          ← All messages
        </button>
        <h2 id="thread-title" className="font-medium">
          {t.subject}
        </h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          About {t.student_name}
          {t.student_class ? ` (${t.student_class})` : ""} · between {t.staff.name} and {t.parent.name}
        </p>
      </header>
      <ol className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto p-4">
        {t.messages.map((m) => (
          <li key={m.id} className={`flex flex-col ${m.mine ? "items-end" : "items-start"}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-card px-3 py-2 text-sm ${m.mine ? "bg-brand text-white" : "bg-neutral-100 dark:bg-neutral-800"}`}
            >
              {m.body}
            </div>
            <span className="mt-1 text-xs text-neutral-500">
              {m.mine ? "You" : m.sender_name} · {timeAgo(m.created_at)}
            </span>
          </li>
        ))}
      </ol>
      <div className="border-t border-neutral-200 p-4 dark:border-neutral-800">
        {t.mine ? (
          <form onSubmit={submit} className="flex flex-col gap-2">
            <Field label="Reply">
              <Textarea
                rows={3}
                value={body}
                maxLength={2000}
                onChange={(e) => setBody(e.target.value)}
                required
              />
            </Field>
            <ErrorText error={reply.error} />
            <div className="flex justify-end">
              <Button type="submit" busy={reply.isPending} disabled={!body.trim()}>
                Send
              </Button>
            </div>
          </form>
        ) : (
          <Alert>
            You can read this because you lead the school. Only {t.staff.name} and {t.parent.name} can write
            in it.
          </Alert>
        )}
      </div>
    </section>
  );
}

function NewMessage({ isParent, onSent }: { isParent: boolean; onSent: (id: string) => void }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [student, setStudent] = useState("");
  const search = isParent || q.trim().length >= 2;
  const pupils = useQuery({
    queryKey: ["students", "message-search", isParent ? "" : q],
    queryFn: () =>
      api.get<Paged<Student>>(
        `/api/v1/students?page_size=50${isParent ? "" : `&q=${encodeURIComponent(q.trim())}`}`,
      ),
    enabled: search,
  });
  const contacts = useQuery({
    queryKey: ["message-contacts", student],
    queryFn: () => api.get<Contact[]>(`/api/v1/communication/conversations/contacts?student=${student}`),
    enabled: Boolean(student),
  });
  const send = useMutation({
    mutationFn: (body: Record<string, string>) =>
      api.post<Conversation>("/api/v1/communication/conversations", body),
    onSuccess: (c) => {
      void client.invalidateQueries({ queryKey: ["conversations"] });
      onSent(c.id);
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    send.mutate({ student, to: f.to ?? "", subject: f.subject ?? "", body: f.body ?? "" });
  };
  const children = pupils.data?.results ?? [];

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {!isParent && (
        <Field label="Find the pupil" hint="Type at least two letters of their name or admission number.">
          <Input value={q} onChange={(e) => setQ(e.target.value)} />
        </Field>
      )}
      <Field label={isParent ? "Which child is it about?" : "Pupil"}>
        <Select value={student} onChange={(e) => setStudent(e.target.value)} required>
          <option value="" disabled>
            {search ? "Choose" : "Search above first"}
          </option>
          {children.map((p) => (
            <option key={p.id} value={p.id}>
              {p.first_name} {p.last_name}
              {p.arm_name ? ` (${p.arm_name})` : ""}
            </option>
          ))}
        </Select>
      </Field>
      {student &&
        (contacts.isPending ? (
          <Loading />
        ) : contacts.data?.length ? (
          <Field label="To">
            <Select name="to" required defaultValue="">
              <option value="" disabled>
                Choose who to write to
              </option>
              {contacts.data.map((c) => (
                <option key={c.user} value={c.user}>
                  {c.name} — {c.role}
                </option>
              ))}
            </Select>
          </Field>
        ) : (
          <Alert tone="warning">
            {isParent
              ? "Nobody is set up to receive messages about this child yet. Please contact the school office."
              : "None of this pupil's guardians has a login yet. Invite them from the Guardians page, or send an SMS announcement."}
          </Alert>
        ))}
      <Field label="Subject">
        <Input name="subject" required maxLength={140} />
      </Field>
      <Field label="Message">
        <Textarea name="body" required maxLength={2000} rows={5} />
      </Field>
      <p className="text-xs text-neutral-500">
        The proprietor and head teacher can read school messages to keep pupils safe.
      </p>
      <ErrorText error={send.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={send.isPending} disabled={!contacts.data?.length}>
          Send
        </Button>
      </div>
    </form>
  );
}
