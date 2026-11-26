import {expect, test} from "@playwright/test";

test("switches direction and searches the live catalog", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name:"Available services"})).toBeVisible();
  await page.getByLabel("Keywords").fill("absent-marketplace-fixture");
  await page.getByRole("button", {name:"Search services"}).click();
  await expect(page.getByText("No matching services.")).toBeVisible();
  await page.getByRole("button", {name:"עברית"}).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", {name:"שירותים זמינים"})).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "he");
});

test("connect page provides the built skill and OpenAPI schema", async ({page}) => {
  await page.goto("/");
  await page.getByRole("link", {name:"Connect Your Agent"}).click();
  await expect(page.getByRole("heading", {name:"Connect Your Agent"})).toBeVisible();
  const archive = await page.request.get("/downloads/agentrelai-skill.zip");
  expect(archive.ok()).toBeTruthy();
  expect((await archive.body()).subarray(0, 2).toString()).toBe("PK");
  const schema = await page.request.get("/api/openapi.json");
  expect((await schema.json()).paths["/api/v1/services"]).toBeDefined();
});
