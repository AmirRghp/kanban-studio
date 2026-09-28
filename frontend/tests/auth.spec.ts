import { expect, test } from "@playwright/test";

import { registerAndSignIn, signIn } from "./helpers";

test("signed out visitors see the login form, not the board", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("login-form")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toHaveCount(0);
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(0);
});

test("signs in with the demo credentials", async ({ page }) => {
  await signIn(page);

  await expect(page.getByTestId("login-form")).toHaveCount(0);
});

test("rejects invalid credentials and stays signed out", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByTestId("login-error")).toHaveText(
    "Invalid username or password"
  );
  await expect(page.getByTestId("login-form")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toHaveCount(0);
});

test("a visitor can register a real account and lands on a clean board", async ({
  page,
}) => {
  await registerAndSignIn(page, "auth");

  await expect(page.getByTestId("login-form")).toHaveCount(0);
  // The starter board: the standard five columns, no cards.
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
  await expect(page.locator('[data-testid^="card-"]')).toHaveCount(0);
});

test("registration validates its input", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Username").fill("ab");
  await page.getByLabel("Password").fill("long-enough-1");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByTestId("login-error")).toBeVisible();
  await expect(page.getByTestId("login-form")).toBeVisible();
});

test("a duplicate username is refused with a clear message", async ({ page }) => {
  const username = await registerAndSignIn(page, "dup");
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page.getByTestId("login-form")).toBeVisible();

  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("another-password-1");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByTestId("login-error")).toHaveText(
    "That username is already taken."
  );
});

test("a registered user can sign back in", async ({ page }) => {
  const username = await registerAndSignIn(page, "again");
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page.getByTestId("login-form")).toBeVisible();

  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("e2e-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
});

test("the session survives a reload", async ({ page }) => {
  await signIn(page);

  await page.reload();

  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.getByTestId("login-form")).toHaveCount(0);
});

test("signs out and locks the board away again", async ({ page }) => {
  await signIn(page);

  await page.getByRole("button", { name: /sign out/i }).click();

  await expect(page.getByTestId("login-form")).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("login-form")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toHaveCount(0);
});
