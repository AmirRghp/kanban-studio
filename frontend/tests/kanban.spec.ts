import { expect, test } from "@playwright/test";

import { measureForDrag, signIn, waitForBoard, waitForSaved } from "./helpers";

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("loads the kanban board", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
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
