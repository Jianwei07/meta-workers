import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

export default defineConfig({
  testDir: "e2e",
  webServer: { command: "pnpm dev --host 127.0.0.1 --port 4173", url: "http://127.0.0.1:4173", reuseExistingServer: true },
  use: { baseURL: "http://127.0.0.1:4173", launchOptions: existsSync(macChrome) ? { executablePath: macChrome } : {} },
});
