import type { Metadata } from "next";
import Link from "next/link";
import { PageIntro, Section } from "@/components/marketing";

export const metadata: Metadata = {
  title: "Contact",
  description: "How to reach the Nex Edu team about your school, privacy or security.",
};

const CHANNELS = [
  {
    title: "Schools and support",
    text: "Questions about Nex Edu, prices, or help with your school's account.",
    email: "support@nexedu.com.gh",
  },
  {
    title: "Privacy and data requests",
    text: "Questions about personal data, or a request under Ghana's Data Protection Act.",
    email: "privacy@nexedu.com.gh",
  },
  {
    title: "Security",
    text: "Think you've found a security problem, or that someone used your account? Tell us straight away.",
    email: "security@nexedu.com.gh",
  },
];

export default function ContactPage() {
  return (
    <>
      <PageIntro eyebrow="Contact" title="Talk to the Nex Edu team">
        Write to the right address below and a person will reply. Never send passwords or codes by email;
        we'll never ask for them.
      </PageIntro>
      <Section>
        <div className="grid gap-4 md:grid-cols-3">
          {CHANNELS.map((c) => (
            <div
              key={c.email}
              className="rounded-card border border-neutral-200 p-5 shadow-card dark:border-neutral-800"
            >
              <h2 className="font-semibold">{c.title}</h2>
              <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">{c.text}</p>
              <a
                href={`mailto:${c.email}`}
                className="mt-4 inline-block font-medium text-link hover:text-link-hover"
              >
                {c.email}
              </a>
            </div>
          ))}
        </div>
        <p className="mt-8 text-sm text-neutral-500">
          Already use Nex Edu?{" "}
          <Link href="/login" className="font-medium text-link hover:text-link-hover">
            Sign in
          </Link>{" "}
          and contact your school first about pupils, fees or results; they manage those records.
        </p>
      </Section>
    </>
  );
}
