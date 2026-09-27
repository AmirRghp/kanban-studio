import { expect, test, type Page } from "@playwright/test";

import { measureForDrag, signIn, waitForBoard } from "./helpers";

// Every test in this file stubs POST /api/chat in the browser, so the suite makes no
// OpenRouter calls at all. That keeps it fast, deterministic, and free of rate limits.
// The real model is exercised by the backend's own `live` tests, which only run when
// RUN_LIVE=1 is set.
const stubChat = async (
  page: Page,
  turn: { reply: string; board?: unknown; warnings?: string[] }
) => {
  let board = turn.board;
  await page.route("**/api/chat", async (route) => {
    const request = route.request();
    const sent = JSON.parse(request.postData() ?? "{}");
    board =
      board ??
      {
        columns: [
          { id: "col-backlog", title: "Backlog", cardIds: ["card-1", "card-new"] },
          { id: "col-done", title: "Done", cardIds: [] },
        ],
        cards: {
          "card-1": { id: "card-1", title: "Existing", details: "d" },
          "card-new": {
            id: "card-new",
            title: `Card for ${sent.message}`,
            details: "added by the stub",
          },
        },
      };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        reply: turn.reply,
        board,
        warnings: turn.warnings ?? [],
      }),
    });
  });
};

test.beforeEach(async ({ page }) => {
  // LOAD-BEARING, shared-board invariant: this suite runs against ONE seeded board that
  // every spec in the e2e run shares. A chat test that let its stubbed board reach the
  // server would leave every later spec asserting against two columns instead of five.
  // Any new spec that stubs /api/board must absorb PUTs exactly like this, or give its
  // own board via DATABASE_PATH on a dedicated service. Reads and sign-in stay real.
  await page.route("**/api/board", async (route) => {
    if (route.request().method() !== "PUT") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: route.request().postData() ?? "{}",
    });
  });

  await signIn(page);
  await waitForBoard(page);
});

test("shows the assistant sidebar next to the board", async ({ page }) => {
  await expect(page.getByTestId("chat-sidebar")).toBeVisible();
  await expect(page.getByText("No conversation yet")).toBeVisible();
  // The board keeps all five columns with the sidebar present.
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("sending a message shows the reply without a reload", async ({ page }) => {
  await stubChat(page, { reply: "All done, added the card." });

  await page.getByLabel("Message").fill("Add a card called Anything");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("All done, added the card.")).toBeVisible();
  // Scoped to the transcript: the stub names the new card after the message, so an
  // unscoped query would match the card title as well.
  await expect(
    page.getByTestId("chat-messages").getByText("Add a card called Anything")
  ).toBeVisible();
});

test("a chat reply updates the board with no reload", async ({ page }) => {
  await stubChat(page, { reply: "Added it." });

  await page.getByLabel("Message").fill("Add a card called From The Assistant");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(
    page.getByText("Card for Add a card called From The Assistant")
  ).toBeVisible();
  // A reload would lose the stub, so this proves the update was client state.
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(2);
});

test("warnings from skipped operations are shown", async ({ page }) => {
  await stubChat(page, {
    reply: "I could not do that one.",
    warnings: ["skipped: no card with id 'card-99'"],
  });

  await page.getByLabel("Message").fill("move a missing card");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByTestId("chat-warnings")).toContainText("card-99");
});

test("New chat clears the conversation but keeps the board", async ({ page }) => {
  await stubChat(page, { reply: "Added a card for you." });

  await page.getByLabel("Message").fill("add something");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Added a card for you.")).toBeVisible();

  await page.getByRole("button", { name: "New chat" }).click();

  await expect(page.getByText("No conversation yet")).toBeVisible();
  await expect(page.getByText("Added a card for you.")).toHaveCount(0);
  // The board the assistant changed is still there.
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(2);
});

test("the input is disabled while a reply is in flight", async ({ page }) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/chat", async (route) => {
    await held;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        reply: "Finished.",
        board: {
          columns: [{ id: "c", title: "C", cardIds: [] }],
          cards: {},
        },
        warnings: [],
      }),
    });
  });

  await page.getByLabel("Message").fill("slow one");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByTestId("chat-pending")).toBeVisible();
  await expect(page.getByLabel("Message")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();

  release();
  await expect(page.getByText("Finished.")).toBeVisible();
  await expect(page.getByLabel("Message")).toBeEnabled();
});

test("the board still drags after the chat has been used", async ({ page }) => {
  await stubChat(page, { reply: "Noted." });

  await page.getByLabel("Message").fill("hello");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Noted.")).toBeVisible();

  const source = page.locator('[data-testid^="column-"]').first();
  const target = page.locator('[data-testid^="column-"]').last();
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

  await page.mouse.move(cardBox.x + cardBox.width / 2, cardBox.y + cardBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    targetBox.x + targetBox.width / 2,
    targetBox.y + 120,
    { steps: 12 }
  );
  await page.mouse.up();

  await expect(target.getByTestId(testId)).toBeVisible();
});
