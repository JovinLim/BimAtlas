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
    await expect(table.getByText(/IFC CLASS/i)).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /lock/i })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /name/i })).toBeVisible();
  });

  test("shows fixture entity rows with IfcClass and Global ID read-only", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await expect(table.locator("tbody .col-ifcClass input").first()).toHaveValue("IfcWall");
    await expect(table.locator("tbody .col-ifcClass input").nth(1)).toHaveValue("IfcSlab");
    await expect(table.locator("tbody .col-ifcClass input").nth(2)).toHaveValue("IfcColumn");
    await expect(table.locator("tbody .col-globalId input").first()).toHaveValue(
      "2O2Fr$t4X7Zf8NO2L3bQpE",
    );
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

  test("pressing Enter commits value and deselects active cell", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator("tbody .col-name input").first();
    await nameInput.click();
    await nameInput.fill("CommittedByEnter");
    await nameInput.press("Enter");

    await expect(nameInput).toHaveValue("CommittedByEnter");
    await expect(page.locator(".formula-cell-ref")).toHaveText("—");
    await expect(page.locator(".formula-input")).toBeDisabled();

    // Enter should escape editing; extra typing must not keep mutating the cell.
    await page.keyboard.type("abc");
    await expect(nameInput).toHaveValue("CommittedByEnter");
  });

  test("IfcClass column is protected (readonly)", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const ifcClassInput = table.locator("tbody .col-ifcClass input").first();
    await expect(ifcClassInput).toHaveValue("IfcWall");
    await expect(ifcClassInput).toHaveAttribute("readonly", "");
  });

  test("formula bar tracks selected cell and enforces protected cells", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const ifcClassInput = table.locator("tbody .col-ifcClass input").first();
    await ifcClassInput.click();

    await expect(page.locator(".formula-cell-ref")).toHaveText("C2");
    await expect(page.locator(".formula-input")).toHaveValue("IfcWall");
    await expect(page.locator(".formula-input")).toHaveAttribute("readonly", "");
  });

  test("formula bar can apply formula values to editable cells", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator("tbody .col-name input").first();
    await nameInput.click();

    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("=1+2");
    await formulaInput.press("Enter");
    await expect(nameInput).toHaveValue("=1+2");

    const nextNameInput = table.locator("tbody .col-name input").nth(1);
    await nextNameInput.click();
    await expect(nameInput).toHaveValue("3");
  });

  test("direct in-cell formula keeps raw input when reselected", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const firstNameInput = table.locator("tbody .col-name input").first();
    const secondNameInput = table.locator("tbody .col-name input").nth(1);

    await firstNameInput.click();
    await firstNameInput.fill("=1+2");
    await firstNameInput.press("Enter");

    // Unselected cell shows computed result.
    await expect(firstNameInput).toHaveValue("3");

    // When selected again, show raw formula input.
    await firstNameInput.click();
    await expect(firstNameInput).toHaveValue("=1+2");

    // Navigate away again to confirm computed rendering remains stable.
    await secondNameInput.click();
    await expect(firstNameInput).toHaveValue("3");
  });

  test("typing '=' then clicking another cell inserts reference", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const descriptionInput = table.locator("tbody .col-description input").first();
    const nameInput = table.locator("tbody .col-name input").first();

    await descriptionInput.click();
    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("=");
    await nameInput.click();

    await expect(page.locator(".formula-cell-ref")).toHaveText("E2");
    await expect(formulaInput).toHaveValue("=D2");
  });

  test("fill down copies active cell to next editable row", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const firstNameInput = table.locator("tbody .col-name input").first();
    await firstNameInput.click();

    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("11");
    await formulaInput.press("Enter");

    await firstNameInput.click();
    await page.keyboard.press("Control+d");
    const secondNameInput = table.locator("tbody .col-name input").nth(1);
    await expect(secondNameInput).toHaveValue("11");
  });

  test("dragging selects a multi-cell range", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const start = table.locator("[data-cell-ref='D2']");
    const end = table.locator("[data-cell-ref='E3']");

    const startBox = await start.boundingBox();
    const endBox = await end.boundingBox();
    if (!startBox || !endBox) throw new Error("Could not resolve drag boxes");

    await page.mouse.move(startBox.x + startBox.width / 2, startBox.y + startBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(endBox.x + endBox.width / 2, endBox.y + endBox.height / 2);
    await page.mouse.up();

    await expect(page.locator(".cell-input.selected-range")).toHaveCount(4);
  });

  test("undo and redo buttons revert committed edits", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator("tbody .col-name input").first();
    await nameInput.click();

    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("Renamed-By-Test");
    await formulaInput.press("Enter");
    await expect(nameInput).toHaveValue("Renamed-By-Test");

    await page.getByRole("button", { name: /^undo$/i }).click();
    await expect(nameInput).toHaveValue("Wall-001");

    await page.getByRole("button", { name: /^redo$/i }).click();
    await expect(nameInput).toHaveValue("Renamed-By-Test");
  });

  test("invalid formulas preserve user input instead of '#ERROR'", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator("tbody .col-name input").first();
    await nameInput.click();

    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("=1+");
    await formulaInput.press("Enter");

    await expect(nameInput).toHaveValue("=1+");
    await expect(formulaInput).toHaveValue("=1+");
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

  test("sheet column C remains editable for rows beyond IFC entities", async ({
    page,
  }) => {
    const addBtn = page.getByRole("button", { name: /add row/i });
    await addBtn.scrollIntoViewIfNeeded();
    let attempts = 0;
    while (attempts < 3) {
      await addBtn.click();
      const categoryProbe = page
        .getByRole("grid", { name: /sheet interactions/i })
        .locator("tbody .col-ifcClass input")
        .first();
      if (await categoryProbe.isVisible().catch(() => false)) break;
      attempts += 1;
      await page.waitForTimeout(200);
    }

    const sheetGrid = page.getByRole("grid", { name: /sheet interactions/i });
    const categoryCell = sheetGrid.locator("tbody .col-ifcClass input").first();
    await expect(categoryCell).not.toHaveAttribute("readonly", "");
    await categoryCell.fill("CustomCategory");
    await categoryCell.press("Enter");
    await expect(categoryCell).toHaveValue("CustomCategory");
  });
});
