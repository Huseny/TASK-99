/**
 * Cross-role multi-step E2E workflow.
 *
 * Scenario: An admin provisions an instructor and a student.  Each role logs
 * into the app and lands on their own workspace.  The student then attempts to
 * call an admin-only API endpoint directly and receives a 403.
 *
 * This test verifies:
 *  - Admin can create users of different roles
 *  - Each role sees their own portal after login
 *  - Role-based API authorization is enforced (student cannot call admin endpoints)
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

test.describe("Cross-role provisioning and login workflow", () => {
  let adminToken = null;
  let instructorId = null;
  let studentId = null;

  const uid = Math.random().toString(16).slice(2, 10);
  const INSTRUCTOR_USER = `e2e_ins_${uid}`;
  const INSTRUCTOR_PASS = "InstructorPass@2026!";
  const STUDENT_USER = `e2e_stu2_${uid}`;
  const STUDENT_PASS = "StudentPass@2026!!";

  test.beforeAll(async ({ request }) => {
    // Ensure the bootstrap admin exists
    await request.post(`${BACKEND}/api/v1/auth/bootstrap-admin`, {
      headers: { "X-Bootstrap-Token": BOOTSTRAP_TOKEN },
      data: { username: ADMIN_USER, password: ADMIN_PASS },
    });

    // Log in as admin
    const loginResp = await request.post(`${BACKEND}/api/v1/auth/login`, {
      data: { username: ADMIN_USER, password: ADMIN_PASS },
    });
    expect(loginResp.ok()).toBeTruthy();
    adminToken = (await loginResp.json()).token;

    // Create instructor
    const insResp = await request.post(`${BACKEND}/api/v1/admin/users`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        username: INSTRUCTOR_USER,
        password: INSTRUCTOR_PASS,
        role: "INSTRUCTOR",
        is_active: true,
      },
    });
    expect(insResp.ok()).toBeTruthy();
    instructorId = (await insResp.json()).id;

    // Create student
    const stuResp = await request.post(`${BACKEND}/api/v1/admin/users`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        username: STUDENT_USER,
        password: STUDENT_PASS,
        role: "STUDENT",
        is_active: true,
      },
    });
    expect(stuResp.ok()).toBeTruthy();
    studentId = (await stuResp.json()).id;
  });

  test.afterAll(async ({ request }) => {
    const headers = { Authorization: `Bearer ${adminToken}` };
    if (instructorId) {
      await request.delete(`${BACKEND}/api/v1/admin/users/${instructorId}`, { headers });
    }
    if (studentId) {
      await request.delete(`${BACKEND}/api/v1/admin/users/${studentId}`, { headers });
    }
  });

  test("instructor can log in and land on the app portal", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill(INSTRUCTOR_USER);
    await page.getByLabel("Password").fill(INSTRUCTOR_PASS);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).toHaveURL(/\/app$/, { timeout: 10000 });
    // The portal should load (not stuck on spinner or login)
    await expect(page.getByRole("button", { name: "open notifications" })).toBeVisible({
      timeout: 10000,
    });
  });

  test("student can log in and see the Student Workspace", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill(STUDENT_USER);
    await page.getByLabel("Password").fill(STUDENT_PASS);
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).toHaveURL(/\/app$/, { timeout: 10000 });
    await expect(page.getByText("Student Workspace")).toBeVisible({ timeout: 10000 });
  });

  test("student token is rejected by admin-only endpoints (403)", async ({ request }) => {
    // Log in as the student to obtain a token
    const loginResp = await request.post(`${BACKEND}/api/v1/auth/login`, {
      data: { username: STUDENT_USER, password: STUDENT_PASS },
    });
    expect(loginResp.ok()).toBeTruthy();
    const studentToken = (await loginResp.json()).token;

    // Attempt to call an admin-only endpoint
    const resp = await request.get(`${BACKEND}/api/v1/admin/organizations`, {
      headers: { Authorization: `Bearer ${studentToken}` },
    });
    expect(resp.status()).toBe(403);
  });
});
