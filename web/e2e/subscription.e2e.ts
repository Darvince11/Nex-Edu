import { expect, type Page, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signIn } from "./session";
import { OPS } from "./totp";

const PROPRIETOR = { email: "director@greenfield.test" };

async function signInAsOps(page: Page) {
  await signIn(page, OPS);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test("invoices, suspension, the proprietor's billing page and support access", async ({ browser }) => {
  test.setTimeout(240_000); // two people, several screens
  const opsContext = await browser.newContext();
  const ops = await opsContext.newPage();
  await signInAsOps(ops);
  const menu = ops.getByRole("navigation", { name: "Platform" });

  // An SMS bundle for schools to buy, and this month's invoices.
  await menu.getByRole("link", { name: "Pricing and billing" }).click();
  await ops.getByRole("button", { name: "Add a bundle" }).click();
  const bundle = ops.getByRole("dialog");
  await bundle.getByRole("spinbutton", { name: "Number of SMS" }).fill("1000");
  await bundle.getByRole("textbox", { name: "Price (GH₵)" }).fill("30");
  await bundle.getByRole("button", { name: "Save bundle" }).click();
  await expect(ops.getByRole("cell", { name: "1,000 SMS", exact: true })).toBeVisible();
  await expectAccessible(ops, "platform: pricing and billing");

  await menu.getByRole("link", { name: "Invoices" }).click();
  await ops.getByRole("button", { name: "Make this month's invoices" }).click();
  await expect(ops.getByRole("row", { name: /Greenfield/ }).first()).toBeVisible();
  await expectAccessible(ops, "platform: invoices");

  // Suspend the demo school.
  await ops.goto("/platform/schools/greenfield");
  await ops.getByRole("button", { name: "Suspend" }).click();
  const suspend = ops.getByRole("dialog");
  await suspend.getByRole("textbox", { name: /^Reason/ }).fill("Checking the account");
  await suspend.getByRole("button", { name: "Suspend" }).click();
  await expect(ops.getByText(/Suspended .*Checking the account/)).toBeVisible();
  await expectAccessible(ops, "platform: suspended school");

  // The proprietor is told and can still reach billing.
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await signIn(owner, PROPRIETOR);
  await expect(owner.getByText(/Greenfield.* is suspended/)).toBeVisible({ timeout: 45_000 });
  await owner.getByRole("link", { name: "Billing and your data" }).click();
  await expect(owner.getByRole("heading", { name: /Nex Edu billing/ })).toBeVisible();
  await expect(owner.getByText("Nex Edu has suspended the school.")).toBeVisible();
  await expect(owner.getByRole("button", { name: /^Pay / })).toBeVisible();
  await expectAccessible(owner, "proprietor: billing while suspended");

  // Back on; the proprietor buys nothing here (no Paystack in tests) but opens support access.
  await ops.getByRole("button", { name: "Reactivate" }).click();
  await ops.getByRole("dialog").getByRole("button", { name: "Reactivate" }).click();
  await expect(ops.getByText("Active. Everyone at the school can sign in.")).toBeVisible();

  await owner.reload();
  await expect(owner.getByRole("button", { name: "Buy 1,000 SMS for GH₵30.00" })).toBeVisible();
  await owner.getByRole("textbox", { name: "What should they look at?" }).fill("Timetable won't save");
  await owner.getByRole("button", { name: "Allow access" }).click();
  await expect(owner.getByText(/Support can look until/)).toBeVisible();

  await ops.reload();
  await ops.getByRole("button", { name: "Look at the set-up" }).click();
  await expect(ops.getByText(/Asked for: .Timetable won't save/)).toBeVisible();
  await expect(ops.getByRole("region", { name: "Classes" })).toContainText("JHS 1");
  await expectAccessible(ops, "platform: support look");

  // Everyone running the school sees that support can look.
  await owner.goto("/dashboard");
  await expect(owner.getByText(/Nex Edu support can see how this school is set up/)).toBeVisible();
  await owner.goto("/account/billing?school=greenfield");
  await expect(owner.getByRole("heading", { name: "When support looked" })).toBeVisible();
  await owner.getByRole("button", { name: "End access now" }).click();
  await expect(owner.getByRole("button", { name: "Allow access" })).toBeVisible();
  await expectAccessible(owner, "proprietor: billing");

  // Leave the demo data as it was: cancel the invoice made here.
  await ops.goto("/platform/billing/invoices?school=greenfield&status=open");
  const cancel = ops.getByRole("button", { name: /^Cancel NXI-/ }).first();
  if (await cancel.isVisible()) {
    await cancel.click();
    await ops
      .getByRole("dialog")
      .getByRole("textbox", { name: /^Reason/ })
      .fill("Test invoice");
    await ops.getByRole("dialog").getByRole("button", { name: "Cancel invoice" }).click();
  }
  await menu.getByRole("link", { name: "Jobs and databases" }).click();
  await expect(ops.getByRole("heading", { name: "Jobs and databases" })).toBeVisible();
  await expect(ops.getByText("subscription-billing")).toBeVisible();
  await expectAccessible(ops, "platform: jobs and databases");
  await ownerContext.close();
  await opsContext.close();
});
