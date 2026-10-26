import { expect, test } from "@playwright/test";
import { expectAccessible } from "./a11y";
import { signInToSchool } from "./session";

const PROPRIETOR = { email: "director@greenfield.test" };

test("the school website is written, published and seen by the public", async ({ page, browser }) => {
  test.slow(); // a visitor opens the site too
  const motto = `Knowledge is light ${Date.now().toString(36)}`;
  await signInToSchool(page, PROPRIETOR);
  const nav = page.getByRole("navigation", { name: "School" }).first();
  await nav.getByRole("link", { name: "Modules" }).click();
  const website = page.getByRole("switch", { name: "School website" });
  await website.click({ force: true });
  await expect(website).toBeChecked();

  await nav.getByRole("link", { name: "School website" }).click();
  await page.getByRole("textbox", { name: "Tagline or motto" }).fill(motto);
  await page.getByRole("textbox", { name: /^About the school/ }).fill("A friendly basic school in Accra.");
  await page.getByRole("button", { name: "Save front page" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.getByRole("tab", { name: "Pages" }).click();
  await page.getByRole("button", { name: "New page" }).click();
  const form = page.getByRole("dialog");
  await form.getByRole("textbox", { name: "Title" }).fill("Our history");
  await form.getByRole("textbox", { name: /^Text/ }).fill("<b>Founded</b> in 1998 by the community.");
  await expectAccessible(page, "website page form");
  await form.getByRole("button", { name: "Save page" }).click();
  await expect(page.getByRole("row", { name: /Our history/ })).toBeVisible();

  await page.getByRole("tab", { name: "Front page" }).click();
  await page.getByRole("button", { name: "Publish the site" }).click();
  await expect(page.getByText("The website is published")).toBeVisible();
  await expectAccessible(page, "website editor");

  const visitorContext = await browser.newContext();
  const visitor = await visitorContext.newPage();
  await visitor.goto("/site?school=greenfield");
  await expect(visitor.getByText(motto)).toBeVisible();
  await expect(visitor.getByRole("heading", { name: "Our history" })).toBeVisible();
  await expect(visitor.getByText("Founded in 1998 by the community.")).toBeVisible(); // tags stripped
  await expect(visitor.getByRole("link", { name: "Apply for admission" })).toBeVisible();
  await expectAccessible(visitor, "public website");

  // Leave the demo school as it was.
  await page.getByRole("button", { name: "Take the site down" }).click();
  await expect(page.getByText("The website isn't published")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByText("This school's website isn't available.")).toBeVisible();
  await visitorContext.close();
  await page.getByRole("tab", { name: "Pages" }).click();
  await page.getByRole("button", { name: "Edit page Our history" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete page" }).click();
  await expect(page.getByText(/^No pages yet/)).toBeVisible();
  await nav.getByRole("link", { name: "Modules" }).click();
  await page.getByRole("switch", { name: "School website" }).click({ force: true });
  await expect(page.getByRole("switch", { name: "School website" })).not.toBeChecked();
});
