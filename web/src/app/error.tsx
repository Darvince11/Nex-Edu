"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Logo } from "@/components/brand";
import { reportError } from "@/lib/error-reporting";

/** Shown when a page crashes. The error goes to Nex Edu's Problems list automatically. */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => reportError(error, "page"), [error]);
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-4 px-4">
      <Logo className="h-11" />
      <h1 className="text-2xl font-semibold">Something went wrong on this page</h1>
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        We've been told about it automatically. Try again, and if it keeps happening, let your school office
        know.
      </p>
      <div className="flex gap-2">
        <button type="button" onClick={reset} className="btn h-11">
          Try again
        </button>
        <Link href="/" className="btn-secondary h-11">
          Go home
        </Link>
      </div>
    </main>
  );
}
