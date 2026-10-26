"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { LogoMark } from "@/components/brand";
import { Alert, Loading } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PUBLIC_SCHOOL_LOGO, useSchoolLogo } from "@/lib/hooks";

type Site = {
  school: string;
  tagline: string;
  about: string;
  contact: { address: string; phone: string; email: string; office_hours: string };
  admissions_open: boolean;
  pages: { slug: string; title: string; body: string }[];
  news: { title: string; body: string; date: string }[];
  events: { title: string; kind: string; starts_on: string; ends_on: string }[];
};

export default function SitePage() {
  return (
    <Suspense fallback={<Loading />}>
      <PublicSite />
    </Suspense>
  );
}

/**
 * The school's public website. In production the school comes from the
 * subdomain (greenfield.nexedu.com.gh/site); locally use /site?school=greenfield.
 * Everything here is plain text the school wrote; React escapes it.
 */
function PublicSite() {
  const params = useSearchParams();
  const school = params.get("school") ?? undefined;
  const logo = useSchoolLogo(PUBLIC_SCHOOL_LOGO, school, true);
  const site = useQuery({
    queryKey: ["public-site", school],
    queryFn: () => apiFetch<Site>("/api/v1/public/site", { school }),
    retry: false,
  });
  const apply = school ? `/apply?school=${encodeURIComponent(school)}` : "/apply";

  if (site.isPending) return <Loading />;
  if (!site.data)
    return (
      <main className="mx-auto max-w-2xl px-4 py-16">
        <Alert tone="error">This school's website isn't available. Check the link and try again.</Alert>
      </main>
    );
  const s = site.data;
  const contact = [s.contact.address, s.contact.phone, s.contact.email, s.contact.office_hours].some(Boolean);
  return (
    <div className="min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-4 px-4 py-5">
          {logo && (
            // biome-ignore lint/performance/noImgElement: a local blob URL; next/image can't optimise it.
            <img src={logo} alt={`${s.school} logo`} className="h-14 w-auto" />
          )}
          <div>
            <h1 className="text-2xl font-semibold">{s.school}</h1>
            {s.tagline && <p className="text-sm text-neutral-600 dark:text-neutral-300">{s.tagline}</p>}
          </div>
          {s.admissions_open && (
            <a
              href={apply}
              className="ml-auto rounded-control bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong"
            >
              Apply for admission
            </a>
          )}
        </div>
        {s.pages.length > 0 && (
          <nav aria-label="Pages" className="mx-auto max-w-4xl px-4 pb-3">
            <ul className="flex flex-wrap gap-4 text-sm">
              {s.pages.map((p) => (
                <li key={p.slug}>
                  <a href={`#${p.slug}`} className="text-link hover:underline">
                    {p.title}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </header>
      <main className="mx-auto flex max-w-4xl flex-col gap-10 px-4 py-8">
        {s.about && (
          <section aria-labelledby="about">
            <h2 id="about" className="mb-2 text-xl font-semibold">
              About us
            </h2>
            <p className="whitespace-pre-wrap leading-relaxed">{s.about}</p>
          </section>
        )}
        {s.pages.map((p) => (
          <section key={p.slug} aria-labelledby={p.slug}>
            <h2 id={p.slug} className="mb-2 text-xl font-semibold">
              {p.title}
            </h2>
            <p className="whitespace-pre-wrap leading-relaxed">{p.body}</p>
          </section>
        ))}
        {s.news.length > 0 && (
          <section aria-labelledby="news">
            <h2 id="news" className="mb-3 text-xl font-semibold">
              News
            </h2>
            <ul className="flex flex-col gap-5">
              {s.news.map((n) => (
                <li key={`${n.date}-${n.title}`}>
                  <article>
                    <h3 className="font-medium">{n.title}</h3>
                    <p className="text-xs text-neutral-600 dark:text-neutral-400">{formatDate(n.date)}</p>
                    <p className="mt-1 whitespace-pre-wrap">{n.body}</p>
                  </article>
                </li>
              ))}
            </ul>
          </section>
        )}
        {s.events.length > 0 && (
          <section aria-labelledby="events">
            <h2 id="events" className="mb-3 text-xl font-semibold">
              Coming up
            </h2>
            <ul className="flex flex-col gap-2">
              {s.events.map((e) => (
                <li key={`${e.starts_on}-${e.title}`} className="text-sm">
                  <span className="font-medium">{e.title}</span>{" "}
                  <span className="text-neutral-600 dark:text-neutral-400">
                    {formatDate(e.starts_on)}
                    {e.ends_on !== e.starts_on && ` to ${formatDate(e.ends_on)}`}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {contact && (
          <section aria-labelledby="contact">
            <h2 id="contact" className="mb-2 text-xl font-semibold">
              Contact us
            </h2>
            <address className="flex flex-col gap-1 not-italic">
              {s.contact.address && <span className="whitespace-pre-wrap">{s.contact.address}</span>}
              {s.contact.phone && (
                <a href={`tel:${s.contact.phone.replace(/\s/g, "")}`} className="text-link hover:underline">
                  {s.contact.phone}
                </a>
              )}
              {s.contact.email && (
                <a href={`mailto:${s.contact.email}`} className="text-link hover:underline">
                  {s.contact.email}
                </a>
              )}
              {s.contact.office_hours && <span>Office hours: {s.contact.office_hours}</span>}
            </address>
          </section>
        )}
      </main>
      <footer className="flex items-center justify-center gap-2 py-8 text-xs text-neutral-600 dark:text-neutral-400">
        <LogoMark className="h-6" alt="" />
        Powered by Nex Edu
      </footer>
    </div>
  );
}
