"use client";

import Link from "next/link";
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useEffect,
  useRef,
} from "react";
import { ApiError } from "@/lib/api";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-neutral-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  children,
  actions,
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-card border border-neutral-200 bg-white p-4 shadow-card dark:border-neutral-800 dark:bg-neutral-900">
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="font-medium">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-card border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="text-sm text-neutral-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-neutral-500">{hint}</div>}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
};

export function Button({
  variant = "primary",
  busy,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-strong",
    secondary:
      "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800",
    danger: "bg-red-700 text-white hover:bg-red-800",
    ghost: "hover:bg-neutral-100 dark:hover:bg-neutral-800",
  }[variant];
  return (
    <button
      type="button"
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-control px-3 py-2 text-sm font-medium disabled:opacity-60 ${styles} ${className}`}
      {...rest}
    >
      {busy && (
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: the control is passed in as children.
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-neutral-500">{hint}</span>}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${props.className ?? ""}`} />;
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={`input ${props.className ?? ""}`}>
      {children}
    </select>
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={4} {...props} className={`input ${props.className ?? ""}`} />;
}

const BADGE_TONES: Record<string, string> = {
  green: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  amber: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  red: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  blue: "bg-brand/10 text-brand-strong dark:bg-brand/25 dark:text-brand-sky",
  grey: "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
};

const STATUS_TONES: Record<string, keyof typeof BADGE_TONES> = {
  paid: "green",
  success: "green",
  published: "green",
  enrolled: "green",
  active: "green",
  present: "green",
  sent: "green",
  part_paid: "amber",
  pending: "amber",
  late: "amber",
  offered: "blue",
  under_review: "blue",
  submitted: "blue",
  draft: "grey",
  issued: "grey",
  excused: "grey",
  absent: "red",
  failed: "red",
  rejected: "red",
  void: "red",
  skipped: "grey",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: keyof typeof BADGE_TONES }) {
  const key = tone ?? (typeof children === "string" ? STATUS_TONES[children] : undefined) ?? "grey";
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${BADGE_TONES[key]}`}
    >
      {typeof children === "string" ? children.replace(/_/g, " ") : children}
    </span>
  );
}

export function Alert({
  tone = "info",
  children,
}: {
  tone?: "info" | "error" | "success" | "warning";
  children: ReactNode;
}) {
  const styles = {
    info: "bg-brand/5 text-brand-navy dark:bg-brand/20 dark:text-neutral-100",
    error: "bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100",
    success: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
    warning: "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-control p-3 text-sm ${styles}`}>
      {children}
    </div>
  );
}

/** Shown when the API says this person's role doesn't allow what the page needs. */
export function Forbidden({ children, title }: { children?: ReactNode; title?: string }) {
  return (
    <div
      role="status"
      className="flex flex-col items-center gap-2 rounded-card border border-neutral-200 p-8 text-center dark:border-neutral-800"
    >
      <svg
        viewBox="0 0 24 24"
        className="size-8 text-neutral-400"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
        <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
      </svg>
      <p className="font-medium">{title ?? "You don't have access to this"}</p>
      <p className="max-w-sm text-sm text-neutral-500">
        {children ??
          "Your role at this school doesn't include it. Ask your head teacher or administrator if you need it."}
      </p>
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  if (error instanceof ApiError && error.status === 403) {
    if (error.code === "module_disabled") {
      return (
        <Forbidden title="This feature is switched off">
          Your school has switched this feature off. The proprietor can switch it on under Settings, Modules.
        </Forbidden>
      );
    }
    if (error.code === "mfa_enrollment_required") {
      return (
        <Alert tone="warning">
          Set up an authenticator app to see school records.{" "}
          <Link href="/security" className="font-medium underline">
            Set one up
          </Link>
        </Alert>
      );
    }
    return <Forbidden />;
  }
  return <Alert tone="error">{error instanceof Error ? error.message : "Something went wrong."}</Alert>;
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500 dark:border-neutral-700">
      {children}
    </div>
  );
}

export function Loading() {
  return <p className="py-6 text-sm text-neutral-500">Loading…</p>;
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    // Focusable so keyboard users can scroll a wide table sideways (WCAG 2.1.1).
    <div
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be reachable by keyboard.
      tabIndex={0}
      className="overflow-x-auto rounded-card border border-neutral-200 focus-visible:outline-2 focus-visible:outline-brand dark:border-neutral-800"
    >
      <table className="w-full text-left text-sm">
        <thead className="bg-neutral-50 text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400">
          <tr>
            {head.map((h, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static header cells.
              <th key={i} className="px-3 py-2 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-3 py-2 align-top ${className}`}>{children}</td>;
}

/** Native <dialog>: focus trapping and Escape handling come from the browser. */
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className="m-auto w-full max-w-lg rounded-card bg-white p-0 text-neutral-900 shadow-xl backdrop:bg-black/40 dark:bg-neutral-900 dark:text-neutral-100"
    >
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
        <h2 className="font-medium">{title}</h2>
        <Button variant="ghost" onClick={onClose} aria-label="Close">
          ✕
        </Button>
      </div>
      <div className="p-4">{open && children}</div>
    </dialog>
  );
}
