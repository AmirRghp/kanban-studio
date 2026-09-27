import { expect, type Page } from "@playwright/test";

export const signIn = async (page: Page) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await waitForBoard(page);
};

export const waitForBoard = async (page: Page) => {
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]').first()).toBeVisible();
};

// Persistence is debounced, so a reload can race the in-flight PUT. Waiting for the
// indicator makes these tests deterministic instead of timing-dependent.
export const waitForSaved = async (page: Page) => {
  await expect(page.getByTestId("save-status")).toHaveText("All changes saved");
};

// Coordinate-based drags need both the card and the target inside the viewport.
// Typing into the chat textarea scrolls it into view, which can push the board above
// the fold and leave boundingBox() returning negative y, so the drag silently does
// nothing. Scroll back to the top and re-measure before dragging.
export const measureForDrag = async (page: import("@playwright/test").Page) => {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
};
