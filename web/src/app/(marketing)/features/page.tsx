import type { Metadata } from "next";
import { CallToAction, PageIntro, Section } from "@/components/marketing";

export const metadata: Metadata = {
  title: "Features",
  description: "What Nex Edu does today for Ghanaian KG, primary and JHS schools, and what's planned next.",
};

const AREAS: { title: string; items: string[] }[] = [
  {
    title: "Pupils and admissions",
    items: [
      "Pupil records with guardians, contact details and class",
      "Health notes and ID numbers stored encrypted, visible only to staff who need them",
      "Import pupils and guardians from CSV or Excel, checked before anything is saved",
      "Your own online admission form, with applications to review, offer and enrol",
    ],
  },
  {
    title: "Academics",
    items: [
      "Academic years and three terms, with the current term set once for everyone",
      "KG 1 to JHS 3 classes and streams, and GES subjects ready to use",
      "Timetable that warns about clashes for a class or a teacher",
      "Teachers assigned to their own classes and subjects",
    ],
  },
  {
    title: "Attendance",
    items: [
      "Daily registers for each class, taken by the class teacher",
      "Works offline and syncs later, without double entries",
      "Optional SMS to parents when a child is absent",
    ],
  },
  {
    title: "Assessment and report cards",
    items: [
      "Assessment components (class work, exams) that add up to 100",
      "Score entry limited to each teacher's own subjects",
      "Totals, grades, class positions and BECE-style aggregates worked out for you",
      "Report cards published when you're ready; scores locked after, with recorded amendments",
    ],
  },
  {
    title: "Fees and payments",
    items: [
      "Fee items and amounts by class and term, and invoices for every pupil",
      "Part payments, discounts and voided invoices handled properly",
      "Online payment by MTN MoMo, Telecel Cash, AirtelTigo Money or card",
      "Numbered receipts, and a term summary of what's been billed and collected",
    ],
  },
  {
    title: "Communication",
    items: [
      "Announcements to the whole school, a class level or a single class",
      "A private inbox for every parent and member of staff",
      "SMS through a Ghanaian gateway, with a monthly limit you set",
    ],
  },
];

const SCHOOL_TYPES = [
  ["KG only", "Kindergarten 1 and 2"],
  ["KG and primary", "KG 1 to Basic 6"],
  ["KG, primary and JHS", "KG 1 to JHS 3"],
  ["JHS only", "JHS 1 to 3"],
];

const PLANNED = [
  "Library",
  "Transport",
  "Hostel and boarding",
  "Canteen",
  "Clinic",
  "Payroll (PAYE and SSNIT)",
  "Accounting",
  "Homework and e-learning",
  "Parent–teacher messages",
  "School calendar",
];

export default function FeaturesPage() {
  return (
    <>
      <PageIntro eyebrow="Features" title="What Nex Edu does for your school">
        Everything below works today. Planned modules are listed separately at the end of the page.
      </PageIntro>

      <Section>
        <div className="grid gap-x-10 gap-y-10 md:grid-cols-2">
          {AREAS.map((area) => (
            <div key={area.title}>
              <h2 className="text-xl font-semibold">{area.title}</h2>
              <ul className="mt-3 flex flex-col gap-2 text-neutral-600 dark:text-neutral-300">
                {area.items.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <section className="border-y border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
        <Section
          title="Schools we support"
          intro="Nex Edu is built for basic schools. Choose the classes you run when you register."
        >
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {SCHOOL_TYPES.map(([name, range]) => (
              <li
                key={name}
                className="rounded-card border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950"
              >
                <p className="font-semibold">{name}</p>
                <p className="mt-1 text-sm text-neutral-500">{range}</p>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-sm text-neutral-500">Senior high schools aren't supported yet.</p>
        </Section>
      </section>

      <Section
        title="Planned"
        intro="These modules aren't available yet. Schools will be able to switch on the ones they need."
      >
        <ul className="flex flex-wrap gap-2">
          {PLANNED.map((name) => (
            <li
              key={name}
              className="rounded-full border border-neutral-300 px-3 py-1 text-sm text-neutral-600 dark:border-neutral-700 dark:text-neutral-300"
            >
              {name} <span className="text-neutral-500">· planned</span>
            </li>
          ))}
        </ul>
      </Section>

      <CallToAction />
    </>
  );
}
