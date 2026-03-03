import { test, expect } from "@playwright/test";

/**
 * Isolated spreadsheet/table view tests using dummy fixture data.
 * Opens /table?fixture=1 so no live IFC stream or backend is required.
 */

test.describe("Table view (fixture data)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/table?fixture=1");
  });

  test("shows fixture data label and entity count", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /table/i }),
    ).toBeVisible();
    await expect(page.getByText("Fixture data")).toBeVisible();
    await expect(page.getByText(/Entities \(5\)/)).toBeVisible();
  });

  test("renders top segment entity grid with protected columns", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /global id/i })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /ifcclass/i })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /lock/i })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /name/i })).toBeVisible();
  });

  test("shows fixture entity rows with IfcClass and Global ID read-only", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await expect(table.getByText("IfcWall").first()).toBeVisible();
    await expect(table.getByText("IfcSlab")).toBeVisible();
    await expect(table.getByText("IfcColumn")).toBeVisible();
    await expect(table.getByText("2O2Fr$t4X7Zf8NO2L3bQpE")).toBeVisible();
  });

  test("lock button toggles row lock state", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const firstLockBtn = table.getByRole("button", {
      name: /lock row|unlock row/i,
    }).first();
    await expect(firstLockBtn).toBeVisible();
    await firstLockBtn.click();
    await expect(
      page.locator(".entity-row[data-locked='true']").first(),
    ).toBeVisible();
    await firstLockBtn.click();
    await expect(
      page.locator(".entity-row[data-locked='false']").first(),
    ).toBeVisible();
  });

  test("unlocked row has editable name input", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator(".col-name input").first();
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Edited Wall");
    await expect(nameInput).toHaveValue("Edited Wall");
  });

  test("IfcClass column is protected (readonly)", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const ifcClassInput = table.locator("tbody .col-ifcClass input").first();
    await expect(ifcClassInput).toHaveValue("IfcWall");
    await expect(ifcClassInput).toHaveAttribute("readonly", "");
  });

  test("bottom segment shows add row", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /add row/i }),
    ).toBeVisible();
  });

  test("can add and remove sheet row", async ({ page }) => {
    const addBtn = page.getByRole("button", { name: /add row/i });
    await addBtn.scrollIntoViewIfNeeded();

    // Hydration in headed runs can be slightly delayed; click with a small retry loop
    // so we don't race against Svelte mounting the handler.
    let attempts = 0;
    while (attempts < 3) {
      await addBtn.click();
      const removeBtn = page.getByRole("button", { name: /remove row/i }).first();
      if (await removeBtn.isVisible().catch(() => false)) {
        break;
      }
      attempts += 1;
      await page.waitForTimeout(200);
    }

    await expect(page.getByRole("button", { name: /remove row/i }).first()).toBeVisible();
    await page.getByRole("button", { name: /remove row/i }).first().click();
    const sheetGrid = page.getByRole("grid", { name: /sheet interactions/i });
    await expect(sheetGrid).toBeVisible();
  });
});
