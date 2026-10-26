"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, todayInAccra } from "@/lib/format";
import { useSchool } from "@/lib/hooks";

type Settings = {
  published: boolean;
  tagline: string;
  about: string;
  address: string;
  phone: string;
  email: string;
  office_hours: string;
  show_events: boolean;
  show_admissions: boolean;
  updated_at: string;
};
type WebPage = { id: string; slug: string; title: string; body: string; order: number; published: boolean };
type News = { id: string; title: string; body: string; date: string; published: boolean };
type Tab = "front" | "pages" | "news";

const slugify = (title: string) =>
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);

/** The school's public website: front page, extra pages and news. Plain text only. */
export default function WebsitePage() {
  const { slug } = useSchool();
  const [tab, setTab] = useState<Tab>("front");
  return (
    <>
      <PageHeader
        title="School website"
        description="What the public sees about your school. Nothing about pupils or staff appears on it."
        actions={
          slug && (
            <a
              href={`/site?school=${encodeURIComponent(slug)}`}
              target="_blank"
              rel="noopener"
              className="text-sm font-medium text-link hover:underline"
            >
              View the site
            </a>
          )
        }
      />
      <div
        role="tablist"
        aria-label="School website"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["front", "Front page"],
            ["pages", "Pages"],
            ["news", "News"],
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
        {tab === "front" && <Front />}
        {tab === "pages" && <Pages />}
        {tab === "news" && <NewsTab />}
      </div>
    </>
  );
}

function Front() {
  const client = useQueryClient();
  const { hasModule } = useSchool();
  const settings = useQuery({
    queryKey: ["website-settings"],
    queryFn: () => api.get<Settings>("/api/v1/website/settings"),
  });
  const save = useMutation({
    mutationFn: (body: Partial<Settings>) => api.patch<Settings>("/api/v1/website/settings", body),
    onSuccess: (data) => client.setQueryData(["website-settings"], data),
  });
  if (!settings.data) return settings.error ? <ErrorText error={settings.error} /> : <Loading />;
  const s = settings.data;
  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3 rounded-card border border-neutral-200 p-4 dark:border-neutral-800">
        <div>
          <p className="font-medium">
            {s.published ? "The website is published" : "The website isn't published"}
          </p>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            {s.published ? "Anyone with the link can see it." : "Only you can see these pages for now."}
          </p>
        </div>
        <div className="ml-auto">
          <Button
            variant={s.published ? "secondary" : "primary"}
            busy={save.isPending && save.variables?.published !== undefined}
            onClick={() => save.mutate({ published: !s.published })}
          >
            {s.published ? "Take the site down" : "Publish the site"}
          </Button>
        </div>
      </div>
      <form
        key={s.updated_at}
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
          save.mutate({
            tagline: f.tagline,
            about: f.about,
            address: f.address,
            phone: f.phone,
            email: f.email,
            office_hours: f.office_hours,
            show_events: f.show_events === "on",
            show_admissions: f.show_admissions === "on",
          });
        }}
      >
        <Field label="Tagline or motto">
          <Input name="tagline" maxLength={200} defaultValue={s.tagline} />
        </Field>
        <Field label="About the school" hint="Plain text. Leave a blank line between paragraphs.">
          <Textarea name="about" rows={6} maxLength={4000} defaultValue={s.about} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Address">
            <Input name="address" maxLength={300} defaultValue={s.address} />
          </Field>
          <Field label="Phone">
            <Input name="phone" type="tel" maxLength={20} defaultValue={s.phone} />
          </Field>
          <Field label="Email">
            <Input name="email" type="email" defaultValue={s.email} />
          </Field>
          <Field label="Office hours">
            <Input
              name="office_hours"
              maxLength={120}
              defaultValue={s.office_hours}
              placeholder="Mon–Fri, 7:30–4:00"
            />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="show_events"
            defaultChecked={s.show_events}
            className="size-4 accent-brand"
          />
          Show upcoming events that are for everyone on the calendar
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="show_admissions"
            defaultChecked={s.show_admissions}
            className="size-4 accent-brand"
          />
          Show an "Apply for admission" button
          {!hasModule("admissions") && " (needs Admissions switched on)"}
        </label>
        <ErrorText error={save.error} />
        {save.isSuccess && save.variables?.published === undefined && <Alert tone="success">Saved.</Alert>}
        <div className="flex justify-end">
          <Button type="submit" busy={save.isPending && save.variables?.published === undefined}>
            Save front page
          </Button>
        </div>
      </form>
    </div>
  );
}

function Pages() {
  const [open, setOpen] = useState<WebPage | "new" | null>(null);
  const pages = useQuery({
    queryKey: ["website-pages"],
    queryFn: () => api.get<WebPage[]>("/api/v1/website/pages"),
  });
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setOpen("new")}>New page</Button>
      </div>
      <ErrorText error={pages.error} />
      {pages.isPending ? (
        <Loading />
      ) : pages.data?.length ? (
        <Table head={["Title", "Address", "Shown", ""]}>
          {pages.data.map((p) => (
            <tr key={p.id}>
              <Td className="font-medium">{p.title}</Td>
              <Td>#{p.slug}</Td>
              <Td>{p.published ? <Badge tone="green">Shown</Badge> : <Badge tone="grey">Hidden</Badge>}</Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(p)} aria-label={`Edit page ${p.title}`}>
                  Edit
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No pages yet. Add one for your history, fees policy or uniform, say.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "New page" : "Edit page"}
      >
        {open !== null && <PageForm page={open === "new" ? null : open} onDone={() => setOpen(null)} />}
      </Modal>
    </>
  );
}

function PageForm({ page, onDone }: { page: WebPage | null; onDone: () => void }) {
  const client = useQueryClient();
  const [title, setTitle] = useState(page?.title ?? "");
  const done = () => {
    void client.invalidateQueries({ queryKey: ["website-pages"] });
    onDone();
  };
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      page ? api.patch(`/api/v1/website/pages/${page.id}`, body) : api.post("/api/v1/website/pages", body),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/website/pages/${page?.id}`),
    onSuccess: done,
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          title,
          slug: page?.slug ?? slugify(title),
          body: f.body,
          order: Number(f.order || 0),
          published: f.published === "on",
        });
      }}
    >
      <Field label="Title">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={80} />
      </Field>
      <Field label="Text" hint="Plain text. Leave a blank line between paragraphs.">
        <Textarea name="body" required rows={10} maxLength={20000} defaultValue={page?.body} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Order on the menu">
          <Input name="order" type="number" min={0} max={99} defaultValue={page?.order ?? 0} />
        </Field>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            name="published"
            defaultChecked={page?.published ?? true}
            className="size-4 accent-brand"
          />
          Show on the website
        </label>
      </div>
      <ErrorText error={save.error ?? remove.error} />
      <div className="flex justify-between gap-2">
        {page ? (
          <Button type="button" variant="ghost" busy={remove.isPending} onClick={() => remove.mutate()}>
            Delete page
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" busy={save.isPending}>
          Save page
        </Button>
      </div>
    </form>
  );
}

function NewsTab() {
  const [open, setOpen] = useState<News | "new" | null>(null);
  const news = useQuery({
    queryKey: ["website-news"],
    queryFn: () => api.get<News[]>("/api/v1/website/news"),
  });
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setOpen("new")}>Add news</Button>
      </div>
      <ErrorText error={news.error} />
      {news.isPending ? (
        <Loading />
      ) : news.data?.length ? (
        <Table head={["Date", "Headline", "Shown", ""]}>
          {news.data.map((n) => (
            <tr key={n.id}>
              <Td>{formatDate(n.date)}</Td>
              <Td className="font-medium">{n.title}</Td>
              <Td>{n.published ? <Badge tone="green">Shown</Badge> : <Badge tone="grey">Hidden</Badge>}</Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(n)} aria-label={`Edit news ${n.title}`}>
                  Edit
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No news yet.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "Add news" : "Edit news"}
      >
        {open !== null && <NewsForm post={open === "new" ? null : open} onDone={() => setOpen(null)} />}
      </Modal>
    </>
  );
}

function NewsForm({ post, onDone }: { post: News | null; onDone: () => void }) {
  const client = useQueryClient();
  const done = () => {
    void client.invalidateQueries({ queryKey: ["website-news"] });
    onDone();
  };
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      post ? api.patch(`/api/v1/website/news/${post.id}`, body) : api.post("/api/v1/website/news", body),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/website/news/${post?.id}`),
    onSuccess: done,
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({ title: f.title, body: f.body, date: f.date, published: f.published === "on" });
      }}
    >
      <Field label="Headline">
        <Input name="title" required maxLength={120} defaultValue={post?.title} />
      </Field>
      <Field label="Story">
        <Textarea name="body" required rows={6} maxLength={8000} defaultValue={post?.body} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Date" hint="A future date waits until then">
          <Input name="date" type="date" required defaultValue={post?.date ?? todayInAccra()} />
        </Field>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            name="published"
            defaultChecked={post?.published ?? true}
            className="size-4 accent-brand"
          />
          Show on the website
        </label>
      </div>
      <ErrorText error={save.error ?? remove.error} />
      <div className="flex justify-between gap-2">
        {post ? (
          <Button type="button" variant="ghost" busy={remove.isPending} onClick={() => remove.mutate()}>
            Delete
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" busy={save.isPending}>
          Save news
        </Button>
      </div>
    </form>
  );
}
