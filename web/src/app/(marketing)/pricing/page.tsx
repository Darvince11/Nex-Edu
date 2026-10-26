import type { Metadata } from "next";
import Link from "next/link";
import { CallToAction, PageIntro, Section } from "@/components/marketing";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Nex Edu prices for Ghanaian basic schools. Ask us for a quote for your school.",
};

const INCLUDED = [
  "Pupil records, admissions and online application form",
  "Attendance, including offline registers",
  "Score entry, report cards and BECE-style aggregates",
  "Fees, invoices, receipts and mobile money payments",
  "Announcements, inbox and SMS to parents",
  "Staff roles, two-step sign-in and an audit trail",
];

export default function PricingPage() {
  return (
    <>
      <PageIntro eyebrow="Pricing" title="Pricing for your school">
        We're agreeing prices with our first schools. Tell us about your school and we'll send you a quote in
        cedis.
      </PageIntro>

      <Section>
        <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
          <div className="rounded-card border border-neutral-200 p-6 shadow-card dark:border-neutral-800">
            <h2 className="text-xl font-semibold">Every school gets</h2>
            <ul className="mt-4 flex flex-col gap-2 text-neutral-600 dark:text-neutral-300">
              {INCLUDED.map((item) => (
                <li key={item} className="flex gap-2">
                  <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" />
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-5 text-sm text-neutral-500">
              SMS messages and online payment fees from mobile money providers may be charged separately.
            </p>
          </div>
          <div className="flex flex-col justify-center gap-4">
            <h2 className="text-xl font-semibold">Get a quote</h2>
            <p className="text-neutral-600 dark:text-neutral-300">
              Register your school and we'll talk about price when we confirm your details, or write to us
              first if you'd like to talk it through. No card details are needed to register.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/signup" className="btn h-11">
                Register your school
              </Link>
              <Link href="/contact" className="btn-secondary h-11">
                Contact us
              </Link>
            </div>
          </div>
        </div>
      </Section>

      <CallToAction />
    </>
  );
}
