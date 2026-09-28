import { expect, type Page } from "@playwright/test";

// Each spec registers its own user, so it owns its own boards and cannot be corrupted
// by another spec. That replaces the old shared-seeded-board invariant that required
// workers:1 and PUT absorption: with per-spec users the suites are independent.
let userCounter = 0;

export const registerAndSignIn = async (page: Page, label = "") => {
  userCounter += 1;
  const username = `e2e-${label || "u"}-${Date.now()}-${userCounter}`.slice(0, 30);
  await page.goto("/");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("e2e-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await waitForBoard(page);
  return username;
};

// The legacy demo account: still valid, and owns the seeded demo board.
export const signIn = async (page: Page) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await waitForBoard(page);
};

export const waitForBoard = async (page: Page) => {
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.getByTestId("board-grid")).toBeVisible();
};

// Persistence is debounced, so a reload can race the in-flight PUT. Waiting for the
// indicator makes these tests deterministic instead of timing-dependent.
export const waitForSaved = async (page: Page) => {
  await expect(page.getByTestId("save-status")).toHaveText("All changes saved");
};

export const createBoard = async (page: Page, name: string) => {
  await page.getByTestId("board-switcher").click();
  await page.getByRole("button", { name: "+ New board" }).click();
  await page.getByLabel("New board name").fill(name);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByTestId("board-switcher")).toContainText(name);
};

export const switchToBoard = async (page: Page, name: string) => {
  await page.getByTestId("board-switcher").click();
  await page.getByRole("option", { name: new RegExp(`^${escapeRegExp(name)}`) }).click();
  await waitForBoard(page);
};

const escapeRegExp = (value: string) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Coordinate-based drags need both the card and the target inside the viewport.
// Typing into the chat textarea scrolls it into view, which can push the board above
// the fold and leave boundingBox() returning negative y, so the drag silently does
// nothing. Scroll back to the top and re-measure before dragging.
export const measureForDrag = async (page: Page) => {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
};
