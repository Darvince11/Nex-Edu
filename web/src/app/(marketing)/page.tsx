import type { Metadata } from "next";
import Link from "next/link";
import { CallToAction, FeatureCard, Section } from "@/components/marketing";

export const metadata: Metadata = {
  title: { absolute: "Nex Edu · School management for Ghanaian basic schools" },
  description:
    "Pupils, attendance, results, fees and parent messages for KG, primary and JHS schools in Ghana, in one secure place.",
};

const FEATURES = [
  {
    title: "Pupils and admissions",
    text: "One record per pupil with guardians and class history. Take applications on your own online form, then offer and enrol in a few clicks. Import existing records from Excel.",
  },
  {
    title: "Attendance that works offline",
    text: "Class teachers take the register on a phone or laptop, even when the network drops. It syncs when you're back online, and parents can get an SMS when a child is absent.",
  },
  {
    title: "Scores and report cards",
    text: "Teachers enter scores for their own subjects. Nex Edu works out totals, grades, positions and BECE-style aggregates, then produces report cards you publish when ready.",
  },
  {
    title: "Fees and mobile money",
    text: "Set fees by class and term, issue invoices, and record payments. Parents can pay by MTN MoMo, Telecel Cash, AirtelTigo Money or card, and receipts are numbered automatically.",
  },
  {
    title: "Parents kept informed",
    text: "Announcements reach parents in their Nex Edu inbox, and by SMS for those without smartphones. Parents see their own children's attendance, results and fees, and nothing else.",
  },
  {
    title: "Staff and access",
    text: "Invite staff and give each person a role. Teachers see only their own classes, the bursar sees finance, and you decide who can do what.",
  },
];

const PROTECTIONS = [
  [
    "A database for every school",
    "Your records live apart from every other school's, with their own encryption key.",
  ],
  [
    "Two-step sign-in for staff",
    "Everyone who can see children's records enters a code from an authenticator app.",
  ],
  [
    "A record of every change",
    "Score changes, payments and staff access are logged in an audit trail that can't be edited quietly.",
  ],
  [
    "Built around Act 843",
    "We collect what schools need and nothing more, following Ghana's Data Protection Act.",
  ],
];

export default function HomePage() {
  return (
    <>
      <section className="border-b border-neutral-200 bg-brand-50 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 sm:py-20 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="text-sm font-semibold tracking-wide text-link uppercase">For KG, primary and JHS</p>
            <h1 className="mt-3 text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">
              Run your school from one secure place.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-neutral-600 dark:text-neutral-300">
              Nex Edu brings pupils, attendance, results, fees and parent messages together for Ghanaian basic
              schools.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/signup" className="btn h-12 px-6 text-base">
                Register your school
              </Link>
              <Link href="/features" className="btn-secondary h-12 px-6 text-base">
                See what's included
              </Link>
            </div>
          </div>
          <ReportCardPreview />
        </div>
      </section>

      <Section
        title="Everything a basic school runs on"
        intro="Built around how Ghanaian schools work: three terms, GES subjects, BECE grading and mobile money."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <FeatureCard key={f.title} title={f.title}>
              {f.text}
            </FeatureCard>
          ))}
        </div>
      </Section>

      <section className="border-y border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
        <Section
          title="Built to protect children's data"
          intro="A school system holds information about children. We treat that as the first requirement, not an extra."
        >
          <dl className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {PROTECTIONS.map(([title, text]) => (
              <div key={title}>
                <dt className="font-semibold">{title}</dt>
                <dd className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">{text}</dd>
              </div>
            ))}
          </dl>
        </Section>
      </section>

      <Section title="Getting started">
        <ol className="grid gap-4 sm:grid-cols-3">
          {[
            ["Register", "Create your account and tell us about your school. It takes a few minutes."],
            [
              "We confirm your school",
              "A member of our team checks your details, usually within two working days.",
            ],
            ["Set up and invite", "Add your classes and fees, then invite your staff and parents."],
          ].map(([title, text], i) => (
            <li key={title} className="rounded-card border border-neutral-200 p-5 dark:border-neutral-800">
              <span className="grid size-8 place-items-center rounded-full bg-brand text-sm font-semibold text-white">
                {i + 1}
              </span>
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">{text}</p>
            </li>
          ))}
        </ol>
      </Section>

      <CallToAction />
    </>
  );
}

/** A small, clearly labelled example of a report card: shows the product without inventing claims. */
function ReportCardPreview() {
  const rows = [
    ["English Language", "78", "1"],
    ["Mathematics", "84", "1"],
    ["Integrated Science", "71", "2"],
    ["Social Studies", "66", "2"],
  ];
  return (
    <figure className="rounded-card border border-neutral-200 bg-white p-5 shadow-card dark:border-neutral-800 dark:bg-neutral-950">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-neutral-500">Terminal report · Term 1</p>
          <p className="font-semibold">JHS 2 A</p>
        </div>
        <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand-strong dark:text-brand-bright">
          Example
        </span>
      </div>
      <table className="mt-4 w-full text-left text-sm">
        <thead className="text-xs text-neutral-500">
          <tr>
            <th className="py-1 font-medium">Subject</th>
            <th className="py-1 text-right font-medium">Score</th>
            <th className="py-1 text-right font-medium">Grade</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
          {rows.map(([subject, score, grade]) => (
            <tr key={subject}>
              <td className="py-2">{subject}</td>
              <td className="py-2 text-right tabular-nums">{score}</td>
              <td className="py-2 text-right tabular-nums">{grade}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <figcaption className="mt-4 text-xs text-neutral-500">
        Example data. Report cards show each subject's score, grade and position, with the BECE-style
        aggregate.
      </figcaption>
    </figure>
  );
}
