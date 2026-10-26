import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "./brand";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/features", label: "Features" },
  { href: "/pricing", label: "Pricing" },
  { href: "/faq", label: "FAQ" },
  { href: "/contact", label: "Contact" },
];

/** Header and footer for the public site. Server-rendered; the phone menu needs no JavaScript. */
export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-white dark:bg-neutral-950">
      <header className="sticky top-0 z-30 border-b border-neutral-200 bg-white/95 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/95">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <Link href="/" aria-label="Nex Edu home">
            <Logo className="h-10" />
          </Link>
          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="hidden items-center gap-2 md:flex">
            <ThemeToggle />
            <Link href="/login" className="btn-secondary h-10">
              Sign in
            </Link>
            <Link href="/signup" className="btn h-10">
              Register your school
            </Link>
          </div>
          <div className="flex items-center gap-1 md:hidden">
            <ThemeToggle />
            <details className="relative">
              <summary className="cursor-pointer list-none rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700">
                Menu
              </summary>
              <div className="absolute right-0 z-40 mt-2 flex w-60 flex-col gap-1 rounded-lg border border-neutral-200 bg-white p-2 shadow-lg dark:border-neutral-800 dark:bg-neutral-900">
                {NAV.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="rounded-md px-3 py-2 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
                  >
                    {item.label}
                  </Link>
                ))}
                <Link href="/login" className="btn-secondary mt-1 h-10">
                  Sign in
                </Link>
                <Link href="/signup" className="btn h-10">
                  Register your school
                </Link>
              </div>
            </details>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:grid-cols-[2fr_1fr_1fr]">
          <div>
            <Logo className="h-9" />
            <p className="mt-3 max-w-sm text-sm text-neutral-500">
              School management for Ghanaian basic schools: KG, primary and JHS.
            </p>
          </div>
          <FooterLinks
            title="Product"
            links={[
              ["/features", "Features"],
              ["/pricing", "Pricing"],
              ["/faq", "FAQ"],
              ["/signup", "Register your school"],
            ]}
          />
          <FooterLinks
            title="Company"
            links={[
              ["/contact", "Contact"],
              ["/legal/privacy", "Privacy notice"],
              ["/legal/terms", "Terms of service"],
            ]}
          />
        </div>
        <p className="border-t border-neutral-200 py-4 text-center text-xs text-neutral-500 dark:border-neutral-800">
          © {new Date().getFullYear()} Nex Edu
        </p>
      </footer>
    </div>
  );
}

function FooterLinks({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <h2 className="text-sm font-semibold">{title}</h2>
      <ul className="mt-3 flex flex-col gap-2 text-sm">
        {links.map(([href, label]) => (
          <li key={href}>
            <Link href={href} className="text-neutral-600 hover:text-link dark:text-neutral-300">
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PageIntro({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <section className="border-b border-neutral-200 bg-brand-50 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="mx-auto max-w-6xl px-4 py-14 sm:py-16">
        {eyebrow && <p className="text-sm font-semibold tracking-wide text-link uppercase">{eyebrow}</p>}
        <h1 className="mt-2 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        {children && (
          <div className="mt-4 max-w-2xl text-lg text-neutral-600 dark:text-neutral-300">{children}</div>
        )}
      </div>
    </section>
  );
}

export function Section({
  title,
  intro,
  children,
}: {
  title?: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:py-16">
      {title && <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>}
      {intro && <p className="mt-3 max-w-2xl text-neutral-600 dark:text-neutral-300">{intro}</p>}
      <div className={title || intro ? "mt-8" : ""}>{children}</div>
    </section>
  );
}

export function FeatureCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-card border border-neutral-200 bg-white p-5 shadow-card dark:border-neutral-800 dark:bg-neutral-900">
      <h3 className="font-semibold">{title}</h3>
      <div className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">{children}</div>
    </div>
  );
}

/** Closing band: one clear next step. Navy, like the sign-in panel; no gradients. */
export function CallToAction() {
  return (
    <section className="bg-brand-navy text-white">
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-4 py-12 sm:flex-row sm:items-center">
        <div className="flex items-center gap-4">
          <Image
            src="/brand/nex-edu-mark-dark.png"
            alt=""
            width={349}
            height={365}
            className="hidden h-12 w-auto sm:block"
          />
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Bring your school onto Nex Edu</h2>
            <p className="mt-1 text-white/70">
              Register in a few minutes. We confirm every school before it goes live.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="inline-flex h-11 items-center rounded-control bg-white px-4 font-medium text-brand-navy hover:bg-white/90"
          >
            Register your school
          </Link>
          <Link
            href="/contact"
            className="inline-flex h-11 items-center rounded-control border border-white/40 px-4 font-medium hover:bg-white/10"
          >
            Talk to us
          </Link>
        </div>
      </div>
    </section>
  );
}
