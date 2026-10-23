import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage, LegalSection } from "@/components/legal";

export const metadata: Metadata = { title: "Terms of service" };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of service" updated="23 October 2026">
      <LegalSection title="Using Nex Edu">
        <p>
          These terms apply to everyone with a Nex Edu account. Schools that subscribe also sign a separate
          agreement, including a data processing agreement, which takes priority over these terms where the
          two differ.
        </p>
      </LegalSection>

      <LegalSection title="Your account">
        <ul className="list-disc pl-5">
          <li>Give accurate details and keep your email address up to date.</li>
          <li>Keep your password, passkeys and codes to yourself. Nex Edu staff will never ask for them.</li>
          <li>
            Tell us straight away at security@nexedu.com.gh if you think someone else has used your account.
          </li>
          <li>
            Creating an account doesn't give access to any school. A school invites you, or approves your
            role.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="Registering a school">
        <p>
          Only someone authorised to act for a school may register it. We review every registration and may
          ask for proof, decline a registration, or close a workspace that was registered falsely.
        </p>
      </LegalSection>

      <LegalSection title="Acceptable use">
        <ul className="list-disc pl-5">
          <li>
            Use pupils', parents' and staff members' information only for the school's legitimate purposes.
          </li>
          <li>
            Don't try to reach data you haven't been given access to, or to test our security without
            permission.
          </li>
          <li>Don't send messages through Nex Edu that are unlawful, abusive or unrelated to the school.</li>
        </ul>
      </LegalSection>

      <LegalSection title="Personal data">
        <p>
          How we handle personal data is described in the{" "}
          <Link href="/legal/privacy" className="font-medium text-brand">
            privacy notice
          </Link>
          .
        </p>
      </LegalSection>

      <LegalSection title="Changes and contact">
        <p>
          If we change these terms we'll tell you, and you'll be asked to accept the new version. Questions:{" "}
          <a href="mailto:support@nexedu.com.gh" className="font-medium text-brand">
            support@nexedu.com.gh
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
