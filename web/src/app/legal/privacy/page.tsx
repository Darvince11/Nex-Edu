import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal";

export const metadata: Metadata = { title: "Privacy notice" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy notice" updated="23 October 2026">
      <LegalSection title="Who we are">
        <p>
          Nex Edu provides school management software to basic schools in Ghana. Each school decides what
          information it keeps about its pupils, parents and staff, so under Ghana's Data Protection Act, 2012
          (Act 843) <strong>the school is the data controller</strong> and Nex Edu processes that data on the
          school's behalf, under a data processing agreement with each school.
        </p>
        <p>
          For your own Nex Edu account (your name, email address and sign-in details) Nex Edu is responsible
          directly.
        </p>
      </LegalSection>

      <LegalSection title="What we collect when you create an account">
        <ul className="list-disc pl-5">
          <li>Your first and last name, and your email address.</li>
          <li>Your password, stored only as a one-way Argon2 hash; we can't read it.</li>
          <li>
            If you set one up: your authenticator app's secret key and recovery codes, stored encrypted; never
            your phone itself.
          </li>
          <li>When and which version of these terms you accepted.</li>
          <li>
            Security records: sign-ins, failed sign-ins, password and two-step changes, with time and IP
            address.
          </li>
        </ul>
        <p>
          If you register a school we also collect the school's name, location, phone number and approximate
          number of pupils, so that our staff can confirm the school is genuine.
        </p>
      </LegalSection>

      <LegalSection title="Why we use it">
        <ul className="list-disc pl-5">
          <li>To create and secure your account, and to let only you sign in.</li>
          <li>To review school registrations before any school workspace is created.</li>
          <li>To detect and investigate misuse, such as attempts to break into accounts.</li>
          <li>To send messages about your account. We don't send marketing or sell your data.</li>
        </ul>
      </LegalSection>

      <LegalSection title="How we protect it">
        <ul className="list-disc pl-5">
          <li>Every school has its own separate database and its own encryption key.</li>
          <li>Sensitive records, such as health notes and ID numbers, are encrypted again field by field.</li>
          <li>Staff accounts must use a code from an authenticator app in addition to a password.</li>
          <li>
            Connections are encrypted (HTTPS), and the security records above can't be edited without
            detection.
          </li>
          <li>Nex Edu staff accounts have no access to schools' records in the app.</li>
        </ul>
      </LegalSection>

      <LegalSection title="Where it is stored">
        <p>
          Data is hosted with Amazon Web Services in its Cape Town (South Africa) region, with backups in the
          European Union. This is processing outside Ghana; schools are told about it in their data processing
          agreement, together with the safeguards that apply.
        </p>
      </LegalSection>

      <LegalSection title="How long we keep it">
        <p>
          Your account stays until you or your school close it. Security records are kept for at least 12
          months. A school's records are kept for as long as the school uses Nex Edu, then exported to the
          school and deleted according to the school's agreement and any legal duty to keep them.
        </p>
      </LegalSection>

      <LegalSection title="Your rights">
        <p>
          Under Act 843 you can ask to see the personal data held about you, have it corrected, or object to
          its use, and you can complain to the Data Protection Commission. For records a school keeps about
          you or your child, contact the school first; we help schools answer these requests.
        </p>
        <p>
          Contact:{" "}
          <a href="mailto:privacy@nexedu.com.gh" className="font-medium text-link">
            privacy@nexedu.com.gh
          </a>
        </p>
      </LegalSection>
    </LegalPage>
  );
}
