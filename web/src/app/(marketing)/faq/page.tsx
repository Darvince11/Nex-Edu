import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { CallToAction, PageIntro, Section } from "@/components/marketing";

export const metadata: Metadata = {
  title: "Questions and answers",
  description: "Answers about Nex Edu for school owners, head teachers and parents.",
};

const QUESTIONS: [string, ReactNode][] = [
  [
    "Which schools is Nex Edu for?",
    "Basic schools in Ghana: kindergarten, primary (Basic 1 to 6) and junior high (JHS 1 to 3). Senior high schools aren't supported yet.",
  ],
  [
    "How do we get started?",
    <>
      The owner or head of the school <Link href="/signup">registers</Link> with their email and the school's
      details. A member of our team confirms the school, usually within two working days, and you can then set
      up classes and fees and invite staff.
    </>,
  ],
  [
    "Can we bring in our existing pupil records?",
    "Yes. Upload pupils and their guardians from a CSV or Excel file. Every row is checked first, and nothing is saved if a row has a problem, so you never end up with half an import.",
  ],
  [
    "Do parents need a smartphone?",
    "No. Parents with a smartphone or computer get their own inbox and can see their children's attendance, results and fees. Important messages, such as absence alerts and results, can also go by SMS.",
  ],
  [
    "Can parents pay school fees with mobile money?",
    "Yes, once the school switches on online payments: MTN MoMo, Telecel Cash, AirtelTigo Money or a card, through Paystack or Flutterwave. Payments go to the school's own account and receipts are issued automatically.",
  ],
  [
    "Does attendance work when the internet is poor?",
    "Yes. Teachers can take the register without a connection; it's saved on the device and sent when the connection returns, without creating duplicates.",
  ],
  [
    "Who can see our school's data?",
    "Only people your school invites, and each sees only what their role allows: teachers their own classes, parents their own children. Each school has its own database and encryption key, and Nex Edu staff accounts can't see school records.",
  ],
  [
    "Where is the data stored?",
    <>
      With Amazon Web Services in Cape Town, South Africa, with backups in the European Union. Your school
      stays in control of its data under Ghana's Data Protection Act; see the{" "}
      <Link href="/legal/privacy">privacy notice</Link>.
    </>,
  ],
  [
    "How do staff sign in safely?",
    "With their email, a password of at least 12 characters, and a code from an authenticator app such as Google or Microsoft Authenticator. Recovery codes let them in if they lose their phone.",
  ],
  [
    "What does it cost?",
    <>
      We're agreeing prices with our first schools. See <Link href="/pricing">pricing</Link> or{" "}
      <Link href="/contact">contact us</Link> for a quote.
    </>,
  ],
];

export default function FaqPage() {
  return (
    <>
      <PageIntro eyebrow="FAQ" title="Questions and answers" />
      <Section>
        <div className="mx-auto max-w-3xl divide-y divide-neutral-200 rounded-card border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
          {QUESTIONS.map(([question, answer]) => (
            <details
              key={question}
              className="group p-5 [&_a]:font-medium [&_a]:text-link [&_a:hover]:text-link-hover"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">
                {question}
                <span
                  aria-hidden="true"
                  className="text-xl text-neutral-400 transition-transform group-open:rotate-45"
                >
                  +
                </span>
              </summary>
              <div className="mt-3 text-neutral-600 dark:text-neutral-300">{answer}</div>
            </details>
          ))}
        </div>
      </Section>
      <CallToAction />
    </>
  );
}
