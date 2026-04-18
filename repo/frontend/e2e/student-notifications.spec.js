/**
 * Real fullstack E2E: student login and notifications drawer journey.
 *
 * No API mocking.  The test provisions a fresh student account against the
 * live backend (Docker), drives the browser through the Vite dev-server (which
 * proxies /api/* to http://localhost:8000), and cleans up after itself.
 *
 * Prerequisites:
 *   docker compose up   (db + api services must be healthy)
 *   vite dev server is started automatically by playwright.config.js
 */
import { expect, test } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const BOOTSTRAP_TOKEN =
  process.env.BOOTSTRAP_ADMIN_TOKEN ?? "integration-test-bootstrap-2026";

/** The integration-test bootstrap admin created by backend/integration/conftest.py */
const ADMIN_USER = "ext_integration_admin";
const ADMIN_PASS = "ExtInt3gration@2026!";

test.describe("Student notifications E2E", () => {
  let adminToken = null;
  let studentId = null;
  const uid = Math.random().toString(16).slice(2, 10);
  const STUDENT_USER = `e2e_stu_${uid}`;
  const STUDENT_PASS = "E2eTestPass@2026!";

  test.beforeAll(async ({ request }) => {
    // Ensure the bootstrap admin exists.  409 means it already exists – fine.
    await request.post(`${BACKEND}/api/v1/auth/bootstrap-admin`, {
      headers: { "X-Bootstrap-Token": BOOTSTRAP_TOKEN },
      data: { username: ADMIN_USER, password: ADMIN_PASS }
    });

    // Log in as admin to obtain a token for provisioning test data.
    const login = await request.post(`${BACKEND}/api/v1/auth/login`, {
      data: { username: ADMIN_USER, password: ADMIN_PASS }
    });
    expect(login.ok()).toBeTruthy();
    adminToken = (await login.json()).token;

    // Create a fresh student user for this test run.
    const stu = await request.post(`${BACKEND}/api/v1/admin/users`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        username: STUDENT_USER,
        password: STUDENT_PASS,
        role: "STUDENT",
        is_active: true
      }
    });
    expect(stu.ok()).toBeTruthy();
    studentId = (await stu.json()).id;
  });

  test.afterAll(async ({ request }) => {
    if (studentId && adminToken) {
      await request.delete(`${BACKEND}/api/v1/admin/users/${studentId}`, {
        headers: { Authorization: `Bearer ${adminToken}` }
      });
    }
  });

  test("student login and notification drawer journey", async ({ page }) => {
    // --- Login flow ---
    await page.goto("/login");
    await page.getByLabel("Username").fill(STUDENT_USER);
    await page.getByLabel("Password").fill(STUDENT_PASS);
    await page.getByRole("button", { name: "Sign In" }).click();

    // Authenticated landing page
    await expect(page).toHaveURL(/\/app$/);
    await expect(page.getByText("Student Workspace")).toBeVisible();

    // --- Notifications drawer ---
    await page.getByRole("button", { name: "open notifications" }).click();

    // Drawer heading must be visible
    await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible();

    // Body shows either the empty-state placeholder or real notification items.
    // Both are valid: a fresh student has no notifications.
    const noNotifText = page.getByText("No notifications yet");
    const firstListItem = page.getByRole("listitem").first();
    await expect(noNotifText.or(firstListItem)).toBeVisible({ timeout: 5000 });
  });
});
