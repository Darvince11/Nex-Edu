"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";
import { ApiError, apiFetch, type Registration } from "@/lib/api";
import { SCHOOL_DOMAIN } from "@/lib/auth";
import { REGIONS, SCHOOL_TYPES, suggestSlug } from "@/lib/registration";
import { AuthField, AuthHeading, CheckCircleIcon, FormAlert, SubmitButton, TextInput } from "./auth";

type Availability = { slug: string; available: boolean; reason: string } | null;

export function RegisterSchoolForm({ onSubmitted }: { onSubmitted: (registration: Registration) => void }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [availability, setAvailability] = useState<Availability>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const effectiveSlug = slugEdited ? slug : suggestSlug(name);

  useEffect(() => {
    if (effectiveSlug.length < 3) {
      setAvailability(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const result = await apiFetch<{ available: boolean; reason: string }>(
          `/api/v1/registrations/slug-check?slug=${encodeURIComponent(effectiveSlug)}`,
          { school: false },
        );
        setAvailability({ slug: effectiveSlug, ...result });
      } catch {
        setAvailability(null); // the server checks again on submit
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [effectiveSlug]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setErrors({});
    setFormError(undefined);
    setBusy(true);
    try {
      const registration = await apiFetch<Registration>("/api/v1/registrations", {
        method: "POST",
        school: false,
        body: {
          school_name: name.trim(),
          slug: effectiveSlug,
          school_type: form.get("school_type"),
          region: form.get("region"),
          town: String(form.get("town")).trim(),
          phone: String(form.get("phone")).trim(),
          expected_pupils: Number(form.get("expected_pupils")),
        },
      });
      onSubmitted(registration);
    } catch (error) {
      if (error instanceof ApiError && error.body && typeof error.body === "object") {
        const body = error.body as Record<string, unknown>;
        const fields: Record<string, string> = {};
        for (const [key, value] of Object.entries(body)) {
          if (key === "code") continue;
          const text = Array.isArray(value) ? value.join(" ") : String(value);
          if (key === "detail" || key === "non_field_errors") setFormError(text);
          else fields[key] = text;
        }
        setErrors(fields);
        if (error.status === 429) setFormError("Too many attempts. Wait a while, then try again.");
      } else {
        setFormError("We couldn't send your registration. Check your connection and try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  const slugState = availability?.slug === effectiveSlug ? availability : null;

  return (
    <>
      <AuthHeading title="Tell us about your school">
        Nex Edu staff review every school before it goes live. This usually takes up to two working days.
      </AuthHeading>
      <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
        {formError && <FormAlert>{formError}</FormAlert>}
        <AuthField label="School name" error={errors.school_name}>
          {({ id, describedBy }) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              invalid={Boolean(errors.school_name)}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="organization"
              maxLength={200}
              required
            />
          )}
        </AuthField>
        <AuthField
          label="Web address"
          error={errors.slug ?? (slugState && !slugState.available ? slugState.reason : undefined)}
          hint={
            <>
              Your school's site:{" "}
              <span className="font-mono">
                {effectiveSlug || "yourschool"}.{SCHOOL_DOMAIN}
              </span>
              {slugState?.available && (
                <span className="ml-2 font-medium text-emerald-700 dark:text-emerald-400">Available</span>
              )}
            </>
          }
        >
          {({ id, describedBy }) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              invalid={Boolean(errors.slug) || slugState?.available === false}
              value={effectiveSlug}
              onChange={(e) => {
                setSlugEdited(true);
                setSlug(
                  e.target.value
                    .toLowerCase()
                    .replace(/[^a-z0-9-]/g, "")
                    .slice(0, 40),
                );
              }}
              autoCapitalize="none"
              spellCheck={false}
              required
              className="font-mono"
            />
          )}
        </AuthField>
        <div className="grid gap-5 sm:grid-cols-2">
          <AuthField label="Classes you run" error={errors.school_type}>
            {({ id, describedBy }) => (
              <select
                id={id}
                name="school_type"
                aria-describedby={describedBy}
                className="input h-11"
                defaultValue="basic"
              >
                {SCHOOL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            )}
          </AuthField>
          <AuthField label="Pupils (about)" error={errors.expected_pupils}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                name="expected_pupils"
                aria-describedby={describedBy}
                invalid={Boolean(errors.expected_pupils)}
                type="number"
                inputMode="numeric"
                min={1}
                max={10000}
                required
              />
            )}
          </AuthField>
          <AuthField label="Region" error={errors.region}>
            {({ id, describedBy }) => (
              <select
                id={id}
                name="region"
                aria-describedby={describedBy}
                className="input h-11"
                required
                defaultValue=""
              >
                <option value="" disabled>
                  Choose a region
                </option>
                {REGIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            )}
          </AuthField>
          <AuthField label="Town or city" error={errors.town}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                name="town"
                aria-describedby={describedBy}
                invalid={Boolean(errors.town)}
                autoComplete="address-level2"
                maxLength={100}
                required
              />
            )}
          </AuthField>
        </div>
        <AuthField
          label="School phone"
          error={errors.phone}
          hint="A Ghanaian number we can call to confirm your school, e.g. 024 412 3456."
        >
          {({ id, describedBy }) => (
            <TextInput
              id={id}
              name="phone"
              aria-describedby={describedBy}
              invalid={Boolean(errors.phone)}
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              required
            />
          )}
        </AuthField>
        <SubmitButton busy={busy}>Send for review</SubmitButton>
      </form>
    </>
  );
}

export function RegistrationStatus({ registration }: { registration: Registration }) {
  if (registration.status === "approved") {
    return (
      <>
        <AuthHeading title={`${registration.school_name} is ready`}>
          You're the owner. Before you see any school records, you'll set up a passkey or authenticator app.
        </AuthHeading>
        <Link href="/schools" className="btn h-11 w-full">
          Open my school
        </Link>
      </>
    );
  }
  if (registration.status === "rejected" || registration.status === "failed") {
    return (
      <>
        <AuthHeading
          title={
            registration.status === "rejected" ? "We couldn't approve this school" : "Setup didn't finish"
          }
        >
          {registration.school_name}
        </AuthHeading>
        <FormAlert tone="info">
          {registration.decision_note ||
            "Our team has been alerted and will contact you. You don't need to register again."}
        </FormAlert>
        {registration.status === "rejected" && (
          <p className="mt-6 text-sm text-neutral-500">
            You can send a new registration with corrected details. Questions? Email{" "}
            <a href="mailto:support@nexedu.com.gh" className="font-medium text-brand">
              support@nexedu.com.gh
            </a>
            .
          </p>
        )}
      </>
    );
  }
  return (
    <>
      <div className="mb-6 grid size-12 place-items-center rounded-full bg-brand/10 text-brand">
        <CheckCircleIcon className="size-7" />
      </div>
      <AuthHeading title="Thanks, we're reviewing your school">
        {registration.school_name} · {registration.slug}.{SCHOOL_DOMAIN}
      </AuthHeading>
      <ol className="flex flex-col gap-4 text-sm">
        {[
          ["We check your details", "Usually within two working days. We may call the school phone number."],
          ["You get an email", "We'll tell you as soon as your school is approved."],
          [
            "Sign in and secure your account",
            "Set up a passkey or authenticator app, then invite your staff.",
          ],
        ].map(([title, text], i) => (
          <li key={title} className="flex gap-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-neutral-100 text-xs font-semibold text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200">
              {i + 1}
            </span>
            <span>
              <span className="block font-medium">{title}</span>
              <span className="block text-neutral-500">{text}</span>
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}
