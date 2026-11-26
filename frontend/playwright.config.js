import {defineConfig} from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {baseURL: process.env.AGENTRELAI_BROWSER_URL || "http://127.0.0.1:8090"},
});
