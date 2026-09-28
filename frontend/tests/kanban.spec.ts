import { expect, test } from "@playwright/test";

import {
  createBoard,
  measureForDrag,
  registerAndSignIn,
  waitForBoard,
  waitForSaved,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await registerAndSignIn(page, "kb");
});

test("loads the starter board with five empty columns", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
  await expect(page.locator('[data-testid^="card-"]')).toHaveCount(0);
});

test("adds a card to a column", async ({ page }) => {
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Playwright card");
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText("Playwright card")).toBeVisible();
});

test("a new card survives a reload", async ({ page }) => {
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Survives a reload");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText("Survives a reload")).toBeVisible();
  await waitForSaved(page);

  await page.reload();
  await waitForBoard(page);

  await expect(
    page.locator('[data-testid^="column-"]').first().getByText("Survives a reload")
  ).toBeVisible();
});

test("a card's due date and labels survive a reload", async ({ page }) => {
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Planned work");
  await firstColumn.getByRole("button", { name: /add card/i }).click();

  const card = firstColumn.locator('[data-testid^="card-"]').first();
  await card.getByRole("button", { name: /edit planned work/i }).click();
  await card.getByLabel("Due date").fill("2030-01-15");
  await card.getByLabel("Labels").fill("design, urgent");
  await card.getByRole("button", { name: "Save" }).click();

  await expect(card.getByText("2030-01-15")).toBeVisible();
  await expect(card.getByText("design")).toBeVisible();
  await expect(card.getByText("urgent")).toBeVisible();
  await waitForSaved(page);

  await page.reload();
  await waitForBoard(page);

  const reloaded = page
    .locator('[data-testid^="column-"]')
    .first()
    .locator('[data-testid^="card-"]')
    .first();
  await expect(reloaded.getByText("2030-01-15")).toBeVisible();
  await expect(reloaded.getByText("design")).toBeVisible();
  await expect(reloaded.getByText("urgent")).toBeVisible();
});

test("a renamed column keeps its name after a reload", async ({ page }) => {
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  const title = firstColumn.getByLabel("Column title");
  await title.fill("Renamed by e2e");
  await waitForSaved(page);

  await page.reload();
  await waitForBoard(page);

  await expect(
    page.locator('[data-testid^="column-"]').first().getByLabel("Column title")
  ).toHaveValue("Renamed by e2e");
});

test("a moved card stays in its new column after a reload", async ({ page }) => {
  // Data independent: pick the first card of the first column and the last column by
  // position, rather than hardcoding seeded ids.
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Drag me around");
  await firstColumn.getByRole("button", { name: /add card/i }).click();

  const columns = page.locator('[data-testid^="column-"]');
  const source = columns.first();
  const target = columns.last();
  const card = source.locator('[data-testid^="card-"]').first();
  const testId = await card.getAttribute("data-testid");
  if (!testId) throw new Error("Card has no data-testid.");

  await measureForDrag(page);
  const cardBox = await card.boundingBox();
  const targetBox = await target.boundingBox();
  if (!cardBox || !targetBox || cardBox.y < 0 || targetBox.y < 0) {
    throw new Error(
      `Card or target is outside the viewport: card y=${cardBox?.y}, target y=${targetBox?.y}.`
    );
  }

  await page.mouse.move(
    cardBox.x + cardBox.width / 2,
    cardBox.y + cardBox.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    targetBox.x + targetBox.width / 2,
    targetBox.y + 120,
    { steps: 12 }
  );
  await page.mouse.up();

  await expect(target.getByTestId(testId)).toBeVisible();
  await waitForSaved(page);

  await page.reload();
  await waitForBoard(page);

  await expect(
    page.locator('[data-testid^="column-"]').last().getByTestId(testId)
  ).toBeVisible();
});

test("creates a second board and switches between them", async ({ page }) => {
  await createBoard(page, "Side project");
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
  await expect(page.locator('[data-testid^="card-"]')).toHaveCount(0);

  // The first board is still there and still holds its cards.
  await page.getByTestId("board-switcher").click();
  await page.getByRole("option", { name: /First board/ }).click();
  await waitForBoard(page);
  await createBoard(page, "Throwaway");
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Board-specific card");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await waitForSaved(page);

  await switchToBoardViaSwitcher(page, "First board");
  await expect(page.getByText("Board-specific card")).toHaveCount(0);

  await switchToBoardViaSwitcher(page, "Throwaway");
  await expect(page.getByText("Board-specific card")).toBeVisible();
});

async function switchToBoardViaSwitcher(page: import("@playwright/test").Page, name: string) {
  await page.getByTestId("board-switcher").click();
  await page.getByRole("option", { name: new RegExp(name) }).first().click();
  await waitForBoard(page);
}

test("renames a board from the switcher", async ({ page }) => {
  await createBoard(page, "Boring name");

  await page.getByTestId("board-switcher").click();
  await page.getByRole("button", { name: "Rename Boring name" }).click();
  await page.getByLabel("Board name").fill("Exciting name");
  await page.getByRole("button", { name: "Save", exact: true }).click();

  // The switcher button shows the active board's name; the rename is visible in the
  // menu. After a reload the app lands on the user's first board, so verify through
  // the menu rather than the button.
  await expect(
    page.getByRole("option", { name: /Exciting name/ })
    ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await waitForBoard(page);
  await page.getByTestId("board-switcher").click();
  await expect(
    page.getByRole("option", { name: /Exciting name/ })
  ).toBeVisible();
});

test("deletes a board and falls back to another", async ({ page }) => {
  await createBoard(page, "Doomed board");

  await page.getByTestId("board-switcher").click();
  await page.getByRole("button", { name: "Delete Doomed board" }).click();
  await page.getByTestId(/confirm-delete-/).click();

  await expect(page.getByRole("option", { name: /Doomed board/ })).toHaveCount(0);
});
