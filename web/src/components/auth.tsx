"use client";

import Image from "next/image";
import Link from "next/link";
import {
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { formatEmailCode, type PasswordRule } from "@/lib/auth";
import { Logo } from "./brand";

/* Icons: inline so no icon library ships to slow connections. */
type IconProps = { className?: string };
const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function ShieldIcon({ className = "size-5" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" {...stroke}>
      <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function LockIcon({ className = "size-5" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" {...stroke}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

export function KeyIcon({ className = "size-5" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" {...stroke}>
      <circle cx="8" cy="15" r="4" />
      <path d="m11 12 8.5-8.5M16 7l2.5 2.5M14 9l2 2" />
    </svg>
  );
}

export function SchoolIcon({ className = "size-5" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" {...stroke}>
      <path d="m3 9 9-5 9 5-9 5-9-5Z" />
      <path d="M7 11.5V16c0 1.4 2.2 3 5 3s5-1.6 5-3v-4.5M21 9v5" />
    </svg>
  );
}

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true" {...stroke}>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="m4 4 16 16" />}
    </svg>
  );
}

export function CheckCircleIcon({ className = "size-5" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" {...stroke}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </svg>
  );
}

/* Layout */

const TRUST = [
  {
    icon: KeyIcon,
    title: "Passkeys and two-step sign-in",
    text: "Staff accounts always need a second step.",
  },
  {
    icon: LockIcon,
    title: "Each school's data kept apart",
    text: "Its own database and its own encryption key.",
  },
  {
    icon: ShieldIcon,
    title: "Designed around Act 843",
    text: "Ghana's Data Protection Act guides what we collect and keep.",
  },
];

/**
 * Split-screen frame for sign-in, sign-up and password pages: brand panel on
 * large screens, the form alone on phones.
 */
export function AuthShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="grid min-h-dvh bg-white lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] dark:bg-neutral-950">
      <aside className="relative hidden overflow-hidden bg-brand-navy p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-14">
        {/* Outline rings for depth, not gradients (design system). */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-40 -bottom-40 size-136 rounded-full border border-white/10"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-20 -bottom-20 size-88 rounded-full border border-brand-bright/25"
        />
        <Link href="/login" className="relative w-fit" aria-label="Nex Edu">
          <Image
            src="/brand/nex-edu-logo-dark.png"
            alt="Nex Edu"
            width={772}
            height={365}
            className="h-12 w-auto"
          />
        </Link>
        <div className="relative max-w-md">
          <h2 className="text-3xl leading-tight font-semibold tracking-tight xl:text-4xl">
            Every pupil, every term, in one place.
          </h2>
          <p className="mt-3 text-base text-white/70">
            Records, results, fees and parent messages for Ghanaian basic schools.
          </p>
          <ul className="mt-10 flex flex-col gap-5">
            {TRUST.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/10 text-brand-sky">
                  <Icon />
                </span>
                <span>
                  <span className="block text-sm font-medium">{title}</span>
                  <span className="block text-sm text-white/60">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-white/50">© {new Date().getFullYear()} Nex Edu</p>
      </aside>

      <div className="flex min-w-0 flex-col">
        <main className="flex flex-1 items-center justify-center px-4 py-10 sm:px-8">
          <div className={`w-full ${wide ? "max-w-lg" : "max-w-sm"}`}>
            <Link href="/login" className="mb-8 block w-fit lg:hidden" aria-label="Nex Edu">
              <Logo className="h-11" />
            </Link>
            {children}
          </div>
        </main>
        <footer className="flex flex-wrap justify-center gap-x-5 gap-y-1 px-4 pb-6 text-xs text-neutral-500">
          <Link href="/legal/privacy" className="hover:text-brand">
            Privacy notice
          </Link>
          <Link href="/legal/terms" className="hover:text-brand">
            Terms of service
          </Link>
          <a href="mailto:support@nexedu.com.gh" className="hover:text-brand">
            Help
          </a>
        </footer>
      </div>
    </div>
  );
}

/** Page heading that takes focus on each step, so screen readers announce the change. */
export function AuthHeading({ title, children }: { title: string; children?: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: refocus whenever the step title changes.
  useEffect(() => {
    ref.current?.focus();
  }, [title]);
  return (
    <div className="mb-7">
      <h1 ref={ref} tabIndex={-1} className="text-2xl font-semibold tracking-tight outline-none sm:text-3xl">
        {title}
      </h1>
      {children && <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">{children}</p>}
    </div>
  );
}

export function Steps({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="mb-8 flex items-center gap-2" aria-label="Progress">
      {steps.map((label, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li
            key={label}
            className="flex flex-1 flex-col gap-1.5"
            aria-current={state === "current" ? "step" : undefined}
          >
            <span
              className={`h-1 rounded-full ${state === "todo" ? "bg-neutral-200 dark:bg-neutral-800" : "bg-brand"}`}
            />
            <span
              className={`text-xs ${state === "current" ? "font-medium text-brand-strong dark:text-brand-bright" : "text-neutral-500"}`}
            >
              <span className="sr-only">
                {state === "done" ? "Completed: " : state === "current" ? "Current: " : ""}
              </span>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* Form controls */

type FieldShellProps = {
  label: ReactNode;
  error?: string;
  hint?: ReactNode;
  aside?: ReactNode;
  children: (ids: { id: string; describedBy?: string }) => ReactNode;
};

/** Label, control, hint and error wired together with ids for assistive tech. */
export function AuthField({ label, error, hint, aside, children }: FieldShellProps) {
  const id = useId();
  const describedBy =
    [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        {aside}
      </div>
      {children({ id, describedBy })}
      {hint && (
        <div id={`${id}-hint`} className="text-xs text-neutral-500">
          {hint}
        </div>
      )}
      {error && (
        <p id={`${id}-error`} className="text-xs font-medium text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextInput({
  invalid,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      {...props}
      aria-invalid={invalid || undefined}
      className={`input h-11 ${invalid ? "border-red-600 focus:border-red-600 focus:ring-red-600/20" : ""} ${className}`}
    />
  );
}

export function PasswordInput(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const checkCaps = (e: KeyboardEvent<HTMLInputElement>) => setCapsLock(e.getModifierState("CapsLock"));
  return (
    <div>
      <div className="relative">
        <TextInput
          {...props}
          type={visible ? "text" : "password"}
          spellCheck={false}
          autoCapitalize="none"
          className="pr-12"
          onKeyUp={checkCaps}
          onKeyDown={checkCaps}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-md text-neutral-500 hover:text-brand focus-visible:text-brand focus-visible:outline-2 focus-visible:outline-brand"
        >
          <EyeIcon off={visible} />
        </button>
      </div>
      {capsLock && (
        <p className="mt-1.5 text-xs font-medium text-amber-700 dark:text-amber-400" role="status">
          Caps Lock is on
        </p>
      )}
    </div>
  );
}

export function PasswordChecklist({ rules }: { rules: PasswordRule[] }) {
  return (
    <ul className="mt-1 grid gap-1 text-xs" aria-live="polite">
      {rules.map((rule) => (
        <li
          key={rule.label}
          className={`flex items-center gap-1.5 ${rule.ok ? "text-emerald-700 dark:text-emerald-400" : "text-neutral-500"}`}
        >
          <span
            aria-hidden="true"
            className={`grid size-4 place-items-center rounded-full text-[10px] ${rule.ok ? "bg-emerald-600 text-white" : "border border-neutral-300 dark:border-neutral-700"}`}
          >
            {rule.ok ? "✓" : ""}
          </span>
          <span>
            <span className="sr-only">{rule.ok ? "Done: " : "Not yet: "}</span>
            {rule.label}
          </span>
        </li>
      ))}
      <li className="text-neutral-500">We also refuse common passwords and ones exposed in data breaches.</li>
    </ul>
  );
}

/** One field for the emailed "BCDF-GHJK" code: formats as you type and accepts paste. */
export function EmailCodeInput({
  value,
  onChange,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> & {
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
}) {
  return (
    <TextInput
      {...props}
      value={value}
      onChange={(e) => onChange(formatEmailCode(e.target.value))}
      inputMode="text"
      autoComplete="one-time-code"
      autoCapitalize="characters"
      spellCheck={false}
      maxLength={9}
      placeholder="XXXX-XXXX"
      className="h-14 text-center font-mono text-2xl tracking-[0.35em] uppercase placeholder:tracking-[0.35em] placeholder:text-neutral-300 dark:placeholder:text-neutral-700"
    />
  );
}

export function Divider({ children }: { children: ReactNode }) {
  return (
    <div className="my-6 flex items-center gap-3 text-xs text-neutral-500">
      <span className="h-px flex-1 bg-neutral-200 dark:bg-neutral-800" />
      {children}
      <span className="h-px flex-1 bg-neutral-200 dark:bg-neutral-800" />
    </div>
  );
}

export function FormAlert({
  tone = "error",
  children,
}: {
  tone?: "error" | "success" | "info";
  children: ReactNode;
}) {
  const styles = {
    error: "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-100",
    success:
      "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
    info: "border-brand/20 bg-brand/5 text-brand-navy dark:bg-brand/15 dark:text-neutral-100",
  }[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-lg border px-3.5 py-3 text-sm ${styles}`}
    >
      {children}
    </div>
  );
}

export function SubmitButton({
  busy,
  children,
  variant = "primary",
}: {
  busy?: boolean;
  children: ReactNode;
  variant?: "primary" | "secondary";
}) {
  return (
    <button
      type="submit"
      disabled={busy}
      className={`${variant === "primary" ? "btn" : "btn-secondary"} h-11 w-full gap-2`}
    >
      {busy && (
        <span
          className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden="true"
        />
      )}
      {children}
      {busy && <span className="sr-only">(working)</span>}
    </button>
  );
}
