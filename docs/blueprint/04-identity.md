# 04 · Identity, sign-up and school onboarding

**Decision (23 Oct 2026): Nex Edu runs its own identity system on django-allauth (headless), not Auth0.**
The owner reversed the earlier Auth0 choice. Reasons that support it: no per-user licence cost at 30k–60k
monthly users, no extra processor holding parents' and staff identity data outside our own hosting, and the
stack was already built and tested. All Auth0 code was removed.

## 1. Flows

| Who | How they get in |
|---|---|
| **School owner** | `/signup`: name, email, password, consent → 8-letter email code → school details → **Nex Edu staff approve** (`manage.py review_registration`) → school created → owner membership → MFA set-up on first visit |
| **Staff, parents, students** | Invited by their school: the email links to `/account/password/reset/<key>` to set a password (proves inbox control) |
| **Platform staff** | `manage.py add_platform_staff`, then "Forgot password" to set a password, then MFA |
| **Everyone** | `/login`: email + password, or a passkey; staff then pass MFA (TOTP or recovery code) |
| **Forgotten password** | `/forgot-password` → one-time link valid 3 days |

Creating an account opens nothing. School access comes only from a membership, which only a school invitation
or an approved registration creates (`test_a_new_account_opens_no_school`).

## 2. Security controls

| Control | How | Test |
|---|---|---|
| Password storage | Argon2id | settings |
| Password rules | ≥12 characters, not all digits, not similar to name/email, not a common password, not in a breach (HIBP k-anonymity, fails open if HIBP is down) | `test_invalid_signups_create_nothing`, `test_breached_passwords_are_refused` |
| Email ownership | Mandatory verification by an 8-letter code (20-letter alphabet, ~2.6×10¹⁰ codes), 15-minute expiry, 3 attempts, then a fresh sign-in is needed | `test_signup_records_consent_and_waits_for_the_email_code`, `test_three_wrong_codes_end_the_verification` |
| No account discovery | Sign-up, sign-in and reset answer the same whether or not the email exists; a duplicate sign-up emails the real owner instead | `test_signing_up_with_a_taken_email_reveals_nothing`, `test_wrong_passwords_get_the_same_answer_for_known_and_unknown_emails` |
| Bots | Hidden honeypot field (our own; allauth's only covers its HTML forms) → refused, nothing created, **no email sent**, so it can't be used to spam a third party | `test_bots_filling_the_honeypot_create_nothing_and_send_nothing` |
| Rate limits | Sign-up 5/hour/IP; sign-in 20/min/IP; failed sign-in 5 per 5 min per account; one new code per minute; registrations 10/hour/user | `test_signups_are_rate_limited_per_ip`, `test_submissions_are_rate_limited` |
| Spam via names | Names with links, `<`, `>` or `@` are refused (names appear in our emails) | `test_invalid_signups_create_nothing` |
| Second factor | Passkeys (WebAuthn) and TOTP with recovery codes; mandatory for every staff role and platform staff, enforced on every API call | `test_staff_without_mfa_are_blocked`, `test_platform_staff_need_mfa` |
| Sessions | Server-side sessions, `HttpOnly`, `SameSite=Lax`, `Secure` in production, rotated with the CSRF token at sign-in, 8-hour lifetime | settings |
| CSRF and origin | CSRF token on every write; Django refuses untrusted `Origin` | `test_browser_sign_in_passes_csrf_origin_check`, `test_untrusted_origin_is_rejected` |
| Page security | Nonce-based CSP, no third-party scripts, fonts or CAPTCHAs (nothing tracks people on the sign-in pages), HSTS, frame-ancestors none | `test_security_headers`; proxy.ts |
| Redirects | `next`/return paths must be same-site relative paths | `web/src/lib/auth.test.ts` |
| Audit | Sign-up, sign-in, failed sign-in (email only), sign-out, email verified, password reset/change, MFA added/removed, registrations: hash-chained, append-only platform log with IP and request ID; never passwords or codes | `test_security_events_are_audited_without_secrets` |
| Owner access | Membership created only after the school database exists, in the same transaction that approves the request; failure or rejection leaves no access | `test_approval_creates_the_school_and_then_the_owner`, `test_failed_setup_leaves_no_owner_access` |
| Reviewer identity | Only active platform staff can be named as reviewer | `test_only_platform_staff_can_be_named_as_reviewer` |

## 3. Data protection (Act 843)

- **Minimum data at sign-up:** name, email, password. School details only after the email is verified.
- **Consent recorded:** `User.terms_accepted_at` and `User.terms_version` (`settings.TERMS_VERSION`); bump the
  version when the terms or privacy notice change and ask people to accept again.
- **Notices:** `/legal/privacy` and `/legal/terms` describe current behaviour. **Drafts**: they need review by
  Ghanaian counsel before launch, and say so on the page.
- **Duplicates handled privately:** a registration whose name matches an existing school is flagged for reviewers
  only; the applicant learns nothing about other schools.
- **No third parties** on sign-in pages: no analytics, CAPTCHA or web fonts.

## 4. Still open

| Item | Phase |
|---|---|
| Super Admin screen for the registration queue (today: `manage.py review_registration`) | 7 |
| Provisioning in a background job with orphan clean-up (today: runs inside the approve command) | 3 |
| New-device / new-location sign-in alerts | 8 |
| Idle timeout of 30 minutes for staff sessions | 5 |
| Re-consent prompt when `TERMS_VERSION` changes | 5 |
| Pupil username logins (no email) | 5 |
| Playwright end-to-end tests of the screens | 2 |
| Legal review of the privacy notice and terms | before launch |
