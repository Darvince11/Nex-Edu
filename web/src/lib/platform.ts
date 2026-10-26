import type { PlatformTenant } from "./api";

/** How a school's lifecycle status reads in the Super Admin console. */
export const TENANT_STATUS: Record<
  PlatformTenant["status"],
  { label: string; tone: "green" | "amber" | "red" | "grey" }
> = {
  active: { label: "Active", tone: "green" },
  provisioning: { label: "Setting up", tone: "amber" },
  suspended: { label: "Suspended", tone: "amber" },
  failed: { label: "Setup failed", tone: "red" },
  offboarded: { label: "Closed", tone: "grey" },
};

/** Platform audit actions in plain words; unknown ones fall back to the code. */
export const PLATFORM_ACTIONS: Record<string, string> = {
  "registration.submitted": "Registration submitted",
  "registration.approval_started": "Approved; set-up started",
  "registration.approved": "School set up and live",
  "registration.failed": "School set-up failed",
  "registration.rejected": "Registration rejected",
  "tenant.usage_refreshed": "Figures refreshed",
  "tenant.suspended": "School suspended",
  "tenant.reactivated": "School reactivated",
  "tenant.offboarded": "School closed (data kept 90 days)",
  "tenant.purged": "School data destroyed",
  "tenant.export_downloaded": "Proprietor downloaded the export",
  "billing.invoice_issued": "Invoice issued",
  "billing.invoice_paid": "Invoice paid",
  "billing.invoice_voided": "Invoice cancelled",
  "billing.checkout_started": "Proprietor started a payment",
  "billing.sms_bought": "SMS bundle bought",
  "billing.sms_added": "SMS added by Nex Edu",
  "billing.charge_mismatch": "Payment amount didn't match",
  "support.access_granted": "Proprietor gave support access",
  "support.access_revoked": "Proprietor ended support access",
  "support.configuration_viewed": "Support looked at the set-up",
  "platform_staff.granted": "Platform role granted",
  "platform_staff.revoked": "Platform role removed",
};

type PlatformRoleName = "super_admin" | "support" | "billing";
const SUPPORT: PlatformRoleName[] = ["super_admin", "support"];
const MONEY: PlatformRoleName[] = ["super_admin", "billing"];
const EVERYONE: PlatformRoleName[] = ["super_admin", "support", "billing"];

export type PlatformNavItem = {
  href: string;
  label: string;
  roles: PlatformRoleName[];
  exact?: boolean;
  badge?: "registrations" | "problems";
};

/** The console menu. The API checks every request itself; this only decides what's listed. */
export const PLATFORM_NAV: { label: string; items: PlatformNavItem[] }[] = [
  { label: "Overview", items: [{ href: "/platform", label: "Dashboard", roles: EVERYONE, exact: true }] },
  {
    label: "Schools",
    items: [
      { href: "/platform/registrations", label: "Registrations", roles: SUPPORT, badge: "registrations" },
      { href: "/platform/schools", label: "Schools", roles: SUPPORT },
    ],
  },
  {
    label: "Money",
    items: [
      { href: "/platform/billing", label: "Pricing and billing", roles: MONEY, exact: true },
      { href: "/platform/billing/invoices", label: "Invoices", roles: MONEY },
      { href: "/platform/billing/history", label: "Billing history", roles: MONEY },
    ],
  },
  {
    label: "Records",
    items: [
      { href: "/platform/audit", label: "General audit log", roles: SUPPORT, exact: true },
      { href: "/platform/audit/mine", label: "My audit log", roles: EVERYONE },
    ],
  },
  {
    label: "Communication",
    items: [{ href: "/platform/announcements", label: "Announcements", roles: SUPPORT }],
  },
  {
    label: "System",
    items: [
      { href: "/platform/system", label: "System settings", roles: SUPPORT, badge: "problems", exact: true },
      { href: "/platform/system/operations", label: "Jobs and databases", roles: SUPPORT },
    ],
  },
];

export function platformNavFor(roles: string[]) {
  return PLATFORM_NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.roles.some((r) => roles.includes(r))),
  })).filter((group) => group.items.length > 0);
}

/** Plain-words labels for platform audit actions; unknown ones fall back to the code. */
export const AUDIT_ACTIONS: Record<string, string> = {
  ...PLATFORM_ACTIONS,
  "auth.signed_in": "Signed in",
  "auth.signed_out": "Signed out",
  "auth.signed_up": "Created an account",
  "auth.sign_in_failed": "Failed sign-in",
  "auth.email_verified": "Verified email",
  "auth.password_reset_requested": "Asked to reset password",
  "auth.password_reset": "Reset password",
  "auth.password_changed": "Changed password",
  "auth.password_set": "Set password",
  "auth.mfa_added": "Added authenticator app",
  "auth.mfa_removed": "Removed authenticator app",
  "auth.mfa_reset": "Reset authenticator",
  "account.profile_updated": "Updated profile",
  "billing.price_changed": "Changed a price",
  "billing.period_changed": "Changed billing period",
  "billing.payment_recorded": "Recorded a payment",
  "billing.invoices_run": "Made the month's invoices",
  "billing.rules_changed": "Changed billing rules",
  "billing.sms_bundle_added": "Added an SMS bundle",
  "billing.sms_bundle_changed": "Changed an SMS bundle",
  "announcement.drafted": "Drafted announcement",
  "announcement.published": "Sent announcement",
  "problem.status_changed": "Updated a problem",
  "system.vulnerability_scan_started": "Started vulnerability scan",
  "members.invited": "Invited someone",
  "members.activated": "Restored access",
};
