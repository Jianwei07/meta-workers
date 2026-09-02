import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "../src/App";

vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
  const url = String(input);
  const body = url.endsWith("/api/users")
    ? [{ id: "user_alice", name: "Alice" }]
    : url.endsWith("/artifacts") || url.endsWith("/memories") || url.endsWith("/routines")
      ? []
    : url.endsWith("/agents")
      ? [{ id: "agent_alice_kyc", user_id: "user_alice", name: "KYC Research Agent", instructions: "Research public companies.", model: "grok-4.3", permission_mode: "ask", kind: "kyc" }]
      : { thread_id: "thread_alice_kyc", messages: [], active_run: null, pending_approval: null, cursor: 0 };
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}));

test("shows the trusted POC boundary and seeded agent", async () => {
  render(<App />);
  expect(screen.getByText(/no authentication/i)).toBeInTheDocument();
  expect((await screen.findAllByText("KYC Research Agent")).length).toBeGreaterThan(0);
});
