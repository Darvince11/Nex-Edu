import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "./brand";
import { ThemeToggle } from "./theme-toggle";

/** Layout for legal pages. Every page says plainly that it's a draft until counsel signs it off. */
export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-white dark:bg-neutral-950">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <Link href="/login" aria-label="Nex Edu">
            <Logo className="h-9" />
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/legal/privacy" className="text-neutral-600 hover:text-link dark:text-neutral-300">
              Privacy
            </Link>
            <Link href="/legal/terms" className="text-neutral-600 hover:text-link dark:text-neutral-300">
              Terms
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          Draft for review by Ghanaian legal counsel. It describes how Nex Edu works today and may change
          before launch.
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-neutral-500">Last updated {updated}</p>
        <div className="mt-8 flex flex-col gap-8 text-[15px] leading-relaxed text-neutral-700 dark:text-neutral-300">
          {children}
        </div>
      </main>
    </div>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">{title}</h2>
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  );
}
