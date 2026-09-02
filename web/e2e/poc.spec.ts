import { expect, test } from "@playwright/test";

test("opens the seeded coworker shell and navigates its POC surfaces", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path === "/api/users"
      ? [{ id: "user_alice", name: "Alice" }, { id: "user_bob", name: "Bob" }]
      : path.endsWith("/agents")
        ? [{ id: "agent_alice_kyc", user_id: "user_alice", name: "KYC Research Agent", instructions: "Research public companies.", model: "grok-4.3", permission_mode: "ask", kind: "kyc" }]
        : path.endsWith("/thread")
          ? { thread_id: "thread_alice_kyc", messages: [], active_run: null, pending_approval: null, cursor: 0 }
          : [];
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await expect(page.getByText("Trusted POC · no authentication")).toBeVisible();
  await expect(page.getByRole("heading", { name: "KYC Research Agent", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Activity" }).click();
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("navigation", { name: "Agent list" })).toBeVisible();
});
