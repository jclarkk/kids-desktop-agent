import { test, expect } from "@playwright/test";

test.describe("Kids Desktop Agent UI", () => {
  test.beforeEach(async ({ page }) => {
    // Stub speech APIs so TTS/STT never block headless Chrome
    await page.addInitScript(() => {
      // @ts-expect-error test stub
      window.speechSynthesis = {
        speaking: false,
        pending: false,
        paused: false,
        onvoiceschanged: null,
        getVoices: () => [],
        speak: (u: { onend?: () => void }) => {
          // Finish "speech" instantly so subtitle flow advances
          setTimeout(() => u.onend?.(), 10);
        },
        cancel: () => undefined,
        pause: () => undefined,
        resume: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      };
    });
    await page.goto("/");
  });

  test("connects to backend (status dot) and shows kid home controls", async ({ page }) => {
    await expect(page.locator(".conn-dot.ok")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".ptt-btn")).toBeVisible();
    await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
    // Home is avatar-only: no settings chips or transcript log
    await expect(page.locator(".ptt-hint")).toContainText(/hold/i);
  });

  test("keyboard drawer sends text and reply appears as subtitle", async ({ page }) => {
    await expect(page.locator(".conn-dot.ok")).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Toggle keyboard" }).click();
    const input = page.getByPlaceholder(/Type here/i);
    await input.fill("Hello from playwright");
    await page.getByRole("button", { name: "Send" }).click();
    // Kid's words show immediately, stub reply follows as avatar subtitle
    await expect(page.locator(".subtitle")).toContainText(/Hello from playwright|stub/i, {
      timeout: 15_000,
    });
    await expect(page.locator(".subtitle")).toContainText(/stub/i, { timeout: 15_000 });
  });

  test("kid menu shows friend picker, games, and grown-ups entry", async ({ page }) => {
    await expect(page.locator(".conn-dot.ok")).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(page.getByText("My friend")).toBeVisible();
    await expect(page.getByText("Games")).toBeVisible();
    await expect(page.getByText(/Grown-ups/)).toBeVisible();
    await page.getByRole("button", { name: "Close menu" }).click();
    await expect(page.getByText("My friend")).not.toBeVisible();
  });

  test("parent settings open from menu, reject wrong PIN, unlock with 1234", async ({ page }) => {
    await expect(page.locator(".conn-dot.ok")).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByText(/Grown-ups/).click();

    await page.locator('input[name="pin"]').fill("0000");
    await page.getByRole("button", { name: "Unlock" }).click();
    await expect(page.getByText(/Incorrect PIN/i)).toBeVisible({ timeout: 10_000 });

    await page.locator('input[name="pin"]').fill("1234");
    await page.getByRole("button", { name: "Unlock" }).click();
    // Unlocked panel shows tabbed sections
    await expect(page.getByRole("tab", { name: "AI" })).toBeVisible({ timeout: 10_000 });
    await page.getByRole("tab", { name: "Safety & PIN" }).click();
    await expect(page.getByText(/Parent PIN/)).toBeVisible();
  });
});
