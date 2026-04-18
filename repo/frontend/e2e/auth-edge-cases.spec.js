/**
 * Auth failure and edge-case E2E tests.
 *
 * Covers:
 *  - Invalid credentials → "Invalid credentials." error shown in the login UI
 *  - Front-end form validation (empty fields, short password)
 *  - Unauthenticated navigation to /app → redirect to /login
 *  - Stale/invalid token in localStorage → bootstrap clears it, redirects to /login
 *
 * Prerequisites:
 *   docker compose up   (db + api services must be healthy)
 *   vite dev server is started automatically by playwright.config.js
 */
import { expect, test } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const BOOTSTRAP_TOKEN =
  process.env.BOOTSTRAP_ADMIN_TOKEN ?? "integration-test-bootstrap-2026";

const ADMIN_USER = "ext_integration_admin";
const ADMIN_PASS = "ExtInt3gration@2026!";

test.describe("Auth failure cases", () => {
  test("shows 'Invalid credentials.' when the password is wrong", async ({ page, request }) => {
    // Ensure the bootstrap admin exists
    await request.post(`${BACKEND}/api/v1/auth/bootstrap-admin`, {
      headers: { "X-Bootstrap-Token": BOOTSTRAP_TOKEN },
      data: { username: ADMIN_USER, password: ADMIN_PASS },
    });

    await page.goto("/login");
    await page.getByLabel("Username").fill(ADMIN_USER);
    await page.getByLabel("Password").fill("WrongPassword999!");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page.getByRole("alert")).toContainText("Invalid credentials.");
    // Must remain on the login page
    await expect(page).toHaveURL(/\/login/);
  });

  test("shows field validation errors when the form is submitted empty", async ({ page }) => {
    await page.goto("/login");
    // Fill password only with a short value to trigger both errors
    await page.getByLabel("Password").fill("short");
    await page.getByRole("button", { name: "Sign In" }).click();

    // Username required error
    await expect(page.getByText("Username is required.")).toBeVisible();
    // Short password error
    await expect(page.getByText("Password must be at least 12 characters.")).toBeVisible();
    // No API call should have been made; we remain on login
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("Auth routing guards", () => {
  test("navigating to /app without auth redirects to /login", async ({ page }) => {
    // Navigate directly without any auth token
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
  });

  test("stale localStorage token is cleared and user is redirected to /login", async ({ page }) => {
    // Plant an invalid token before the page boots so the bootstrap effect picks it up
    await page.addInitScript(() => {
      localStorage.setItem("cems_token", "totally-invalid-token-xyz");
    });

    await page.goto("/app");

    // The bootstrap effect calls /auth/me with the bad token → 401 → token removed → redirect
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });

    // Confirm the token was cleared from localStorage
    const stored = await page.evaluate(() => localStorage.getItem("cems_token"));
    expect(stored).toBeNull();
  });
});
