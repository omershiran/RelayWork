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
  await page.getByRole("main").getByRole("link", {name:"Connect Your Agent"}).click();
  await expect(page.getByRole("heading", {name:"Connect Your Agent"})).toBeVisible();
  const archive = await page.request.get("/downloads/agentrelai-skill.zip");
  expect(archive.ok()).toBeTruthy();
  expect((await archive.body()).subarray(0, 2).toString()).toBe("PK");
  const schema = await page.request.get("/api/openapi.json");
  expect((await schema.json()).paths["/api/v1/services"]).toBeDefined();
});

test("presents the two agent roles and simulates a labelled checkout", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name:"Customer agent"})).toBeVisible();
  await expect(page.getByRole("heading", {name:"Business agent", exact:true})).toBeVisible();
  await expect(page.getByRole("link", {name:"Browse as a person"})).toBeVisible();
  await page.goto("/checkout-preview");
  await page.getByRole("button", {name:"Simulate payment"}).click();
  await expect(page.getByRole("status")).toHaveText("Sandbox payment confirmed.");
  await expect(page.getByText("No money is charged. This preview does not update any order.")).toBeVisible();
});

test("offers the internal customer agent separately from external connections", async ({page}) => {
  await page.goto("/");
  const main = page.getByRole("main");
  await expect(main.getByRole("link", {name:"Connect Your Agent"})).toBeVisible();
  await main.getByRole("link", {name:"Open my customer agent"}).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", {name:"Sign in"})).toBeVisible();
});

test("opens a real private buyer chat in one click and restores its history", async ({page, baseURL}) => {
  const spool = process.env.AGENTRELAI_DEV_MAIL_DIR;
  test.skip(!spool, "Requires the development-only mail spool");
  const {readdir, readFile} = await import("node:fs/promises");
  const {randomUUID} = await import("node:crypto");
  const {join} = await import("node:path");
  const email = "buyer-e2e-" + randomUUID() + "@example.com";
  const password = "Fixture " + randomUUID();
  const headers = {Origin:baseURL};
  const account = {email,password};
  expect((await page.request.post("/api/v1/auth/register", {headers,data:account})).status()).toBe(202);
  let token;
  for (const file of await readdir(spool)) {
    const content = await readFile(join(spool, file), "utf8");
    if (content.startsWith("To: " + email + "\n")) {
      token = content.trim().split("#verify:")[1];
      break;
    }
  }
  expect(Boolean(token)).toBe(true);
  expect((await page.request.post("/api/v1/auth/verify", {headers,data:{token,password}})).status()).toBe(200);
  expect((await page.request.post("/api/v1/auth/login", {headers,data:account})).status()).toBe(200);
  await page.goto("/account");
  await page.getByRole("button", {name:"Open my customer agent"}).click();
  await expect(page).toHaveURL(/\/buyer\/[0-9a-f-]+$/);
  await page.getByLabel("Your message").fill("Calculate 8 × 7");
  await page.getByRole("button", {name:"Send", exact:true}).click();
  await expect(page.getByText("56", {exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByText("56", {exact:true})).toBeVisible();
});
