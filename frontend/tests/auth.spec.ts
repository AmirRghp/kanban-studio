import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

test("signed out visitors see the login form, not the board", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("login-form")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toHaveCount(0);
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(0);
});

test("signs in with the valid credentials", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
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
