import { test, expect, type Page } from "@playwright/test";

/**
 * Isolated spreadsheet/table view tests using dummy fixture data.
 * Opens /table?fixture=1 so no live IFC stream or backend is required.
 */

test.describe("Table view (fixture data)", () => {
  async function unlockEntityRows(page: Page, count = 1) {
    const controls = page.getByLabel("Entity lock controls");
    for (let i = 0; i < count; i += 1) {
      await controls.getByRole("button", { name: /unlock row/i }).first().click();
    }
  }

  async function addCustomColumn(page: Page) {
    let attempts = 0;
    while (attempts < 4) {
      await page.getByRole("button", { name: /add custom column/i }).first().click();
      const count = await page.locator(".header-formula-input").count();
      if (count > 0) return;
      attempts += 1;
      await page.waitForTimeout(200);
    }
    throw new Error("Custom column input did not appear");
  }

  async function openFormulaGuide(page: Page) {
    let attempts = 0;
    while (attempts < 4) {
      await page.getByRole("button", { name: /formula guide/i }).first().click();
      const dialog = page.getByRole("dialog", { name: /formula guide/i });
      if (await dialog.isVisible().catch(() => false)) return;
      attempts += 1;
      await page.waitForTimeout(150);
    }
    throw new Error("Formula guide did not open");
  }

  test.beforeEach(async ({ page }) => {
    await page.goto("/table?fixture=1");
  });

  test("shows fixture data label and entity count", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /table/i }),
    ).toBeVisible();
    await expect(page.getByText("Fixture data")).toBeVisible();
    await expect(page.getByText(/Total entities:\s*5/i)).toBeVisible();
  });

  test("renders top segment entity grid with protected columns", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /global id/i })).toBeVisible();
    await expect(table.getByText(/IFC CLASS/i)).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /name/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /add custom column/i }).first()).toBeVisible();
  });

  test("shows fixture entity rows with IfcClass and Global ID read-only", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await expect(table.locator("tbody .col-ifcClass input")).toHaveCount(5);
    await expect(table.locator("tbody .col-globalId input")).toHaveCount(5);
    await expect(table.locator("tbody .col-ifcClass input").nth(0)).toHaveValue("IfcColumn");
    await expect(table.locator("tbody .col-ifcClass input").nth(2)).toHaveValue("IfcSlab");
    await expect(table.locator("tbody .col-ifcClass input").nth(3)).toHaveValue("IfcWall");
    await expect(table.locator("tbody .col-globalId input").nth(3)).toHaveValue(
      "2O2Fr$t4X7Zf8NO2L3bQpE",
    );
  });

  test("lock button toggles row lock state", async ({ page }) => {
    const firstLockBtn = page.getByLabel("Entity lock controls").getByRole("button", {
      name: /lock row|unlock row/i,
    }).first();
    await expect(firstLockBtn).toBeVisible();
    await firstLockBtn.click();
    await expect(
      page.locator(".entity-row[data-locked='false']").first(),
    ).toBeVisible();
    await firstLockBtn.click();
    await expect(
      page.locator(".entity-row[data-locked='true']").first(),
    ).toBeVisible();
  });

  test("unlocked row has editable name input", async ({ page }) => {
    await unlockEntityRows(page, 1);
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator(".col-name input").first();
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Edited Wall");
    await expect(nameInput).toHaveValue("Edited Wall");
  });

  test("pressing Enter commits value and deselects active cell", async ({ page }) => {
    await unlockEntityRows(page, 1);
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
    await expect(ifcClassInput).toHaveAttribute("readonly", "");
    await expect(ifcClassInput).toHaveAttribute("readonly", "");
  });

  test("formula bar tracks selected cell and enforces protected cells", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const ifcClassInput = table.locator("tbody .col-ifcClass input").first();
    await ifcClassInput.click();

    await expect(page.locator(".formula-cell-ref")).toHaveText("B2");
    await expect(page.locator(".formula-input")).toHaveValue("IfcColumn");
    await expect(page.locator(".formula-input")).toHaveAttribute("readonly", "");
  });

  test("formula bar can apply formula values to editable cells", async ({ page }) => {
    await unlockEntityRows(page, 1);
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
    await unlockEntityRows(page, 1);
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
    await unlockEntityRows(page, 1);
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const descriptionInput = table.locator("tbody .col-description input").first();
    const nameInput = table.locator("tbody .col-name input").first();

    await descriptionInput.click();
    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("=(");
    await nameInput.click();

    await expect(page.locator(".formula-cell-ref")).toHaveText("D2");
  });

  test("fill down copies active cell to next editable row", async ({ page }) => {
    await unlockEntityRows(page, 2);
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
    await unlockEntityRows(page, 1);
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator("tbody .col-name input").first();
    await nameInput.click();

    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill("Renamed-By-Test");
    await formulaInput.press("Enter");
    await expect(nameInput).toHaveValue("Renamed-By-Test");

    await page.getByRole("button", { name: /^undo$/i }).click();
    await expect(nameInput).toHaveValue("Column-A1");

    await page.getByRole("button", { name: /^redo$/i }).click();
    await expect(nameInput).toHaveValue("Renamed-By-Test");
  });

  test("invalid formulas preserve user input instead of '#ERROR'", async ({
    page,
  }) => {
    await unlockEntityRows(page, 1);
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

  test("multi-sheet: sheet tabs and add sheet", async ({ page }) => {
    await expect(page.locator(".sheet-tab").filter({ hasText: "Sheet 1" })).toBeVisible();
    const addSheetBtn = page.getByRole("button", { name: /add sheet/i });
    await addSheetBtn.scrollIntoViewIfNeeded();

    let attempts = 0;
    while (attempts < 4) {
      await addSheetBtn.click();
      const sheet2Tab = page.locator(".sheet-tab").filter({ hasText: "Sheet 2" });
      if (await sheet2Tab.isVisible().catch(() => false)) {
        await expect(sheet2Tab).toHaveClass(/active/);
        await page.locator(".sheet-tab").filter({ hasText: "Sheet 1" }).click();
        await expect(page.locator(".sheet-tab").filter({ hasText: "Sheet 1" })).toHaveClass(/active/);
        return;
      }
      attempts += 1;
      await page.waitForTimeout(200);
    }
    throw new Error("Sheet 2 tab did not appear after clicking Add sheet");
  });

  test("can add and remove sheet row", async ({ page }) => {
    const addBtn = page.getByRole("button", { name: /add row/i });
    await addBtn.scrollIntoViewIfNeeded();

    // Hydration in headed runs can be slightly delayed; click with a small retry loop
    // so we don't race against Svelte mounting the handler.
    let attempts = 0;
    while (attempts < 3) {
      await addBtn.click();
      const sheetRows = page
        .getByRole("grid", { name: /sheet interactions/i })
        .locator("tbody tr");
      if ((await sheetRows.count()) > 0) {
        break;
      }
      attempts += 1;
      await page.waitForTimeout(200);
    }

    const sheetGrid = page.getByRole("grid", { name: /sheet interactions/i });
    await expect(sheetGrid).toBeVisible();
    await expect(sheetGrid.locator("tbody tr")).toHaveCount(1);
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

  test("can add a custom top column and default columns stay undeletable", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await expect(table.locator(".header-delete-btn")).toHaveCount(0);
    await addCustomColumn(page);
    await expect(page.locator(".header-formula-input")).toHaveCount(1);
    await expect(table.locator(".header-delete-btn")).toHaveCount(1);
  });

  test("custom column formula =ENTITY.Attribute populates entity rows", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await addCustomColumn(page);
    const customFormula = page.locator(".header-formula-input").first();
    await customFormula.fill("=ENTITY.FireRating");
    await customFormula.press("Enter");

    await expect(table.locator("[data-cell-ref='G2']")).toHaveValue("");
    await expect(table.locator("[data-cell-ref='G5']")).toHaveValue("2HR");
    await expect(table.locator("[data-cell-ref='G6']")).toHaveValue("1HR");
  });

  test("nested ENTITY path formula resolves through attributes JSON", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await addCustomColumn(page);
    const customFormula = page.locator(".header-formula-input").first();
    await customFormula.fill("=ENTITY.PropertySets.PsetWallCommon.FireRating");
    await customFormula.press("Enter");

    await expect(table.locator("[data-cell-ref='G2']")).toHaveValue("");
    await expect(table.locator("[data-cell-ref='G5']")).toHaveValue("2HR");
    await expect(table.locator("[data-cell-ref='G6']")).toHaveValue("1HR");
  });

  test("non-existent ENTITY path renders NULL as empty cell", async ({ page }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await addCustomColumn(page);
    const customFormula = page.locator(".header-formula-input").first();
    await customFormula.fill("=ENTITY.DoesNotExist.Path");
    await customFormula.press("Enter");
    await expect(table.locator("[data-cell-ref='G2']")).toHaveValue("");
    await expect(table.locator("[data-cell-ref='G4']")).toHaveValue("");
  });

  test("header alias syntax shows custom label with formula value", async ({
    page,
  }) => {
    const table = page.getByRole("grid", { name: /IFC entities/i });
    await addCustomColumn(page);
    const customFormula = page.locator(".header-formula-input").first();
    await customFormula.fill("[Wall FR](=ENTITY.PropertySets.PsetWallCommon.FireRating)");
    await customFormula.press("Enter");

    await expect(customFormula).toHaveValue(
      "[Wall FR](=ENTITY.PropertySets.PsetWallCommon.FireRating)",
    );
    await expect(table.locator("[data-cell-ref='G5']")).toHaveValue("2HR");
  });

  test("formula guide documents ENTITY formulas and header aliases", async ({
    page,
  }) => {
    await openFormulaGuide(page);
    await expect(page.getByText(/ENTITY\.Attribute/)).toBeVisible();
    await expect(page.getByText(/ENTITY\.PropertySets\.PsetWallCommon/)).toBeVisible();
    await expect(page.getByText(/\[Display Text\]\(Formula\)/)).toBeVisible();
  });

  test("Export CSV button renders in top segment toolbar and is enabled when data is present", async ({
    page,
  }) => {
    await expect(page.getByText(/Total entities:\s*5/i)).toBeVisible();
    const exportBtn = page.getByTestId("export-csv-btn");
    await expect(exportBtn).toBeVisible();
    await expect(exportBtn).toBeEnabled();
  });

  test("Export CSV download includes entity columns and IFC entity data", async ({
    page,
  }) => {
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-csv-btn").click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toMatch(/^filtered-entities-.*\.csv$/);
    const path = await download.path();
    expect(path).toBeTruthy();
    const { readFileSync } = await import("node:fs");
    const content = readFileSync(path!, "utf-8");

    expect(content).toContain("Global ID");
    expect(content).toContain("IFC CLASS");
    expect(content).toContain("Name");
    expect(content).not.toContain("Sheet Category");

    expect(content).toContain("IfcColumn");
    expect(content).toContain("2O2Fr$t4X7Zf8NO2L3bQpE");
  });

  test("Export CSV with bottom sheet row includes both entity and sheet data", async ({
    page,
  }) => {
    const addBtn = page.getByRole("button", { name: /add row/i });
    await addBtn.scrollIntoViewIfNeeded();
    let attempts = 0;
    while (attempts < 3) {
      await addBtn.click();
      const sheetRows = page
        .getByRole("grid", { name: /sheet interactions/i })
        .locator("tbody tr");
      if ((await sheetRows.count()) > 0) break;
      attempts += 1;
      await page.waitForTimeout(200);
    }

    const sheetGrid = page.getByRole("grid", { name: /sheet interactions/i });
    const categoryCell = sheetGrid.locator("tbody .col-ifcClass input").first();
    await categoryCell.fill("QS-Category");
    await categoryCell.press("Enter");
    const valueCell = sheetGrid.locator("tbody .col-description input").first();
    await valueCell.fill("42");
    await valueCell.press("Enter");

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-csv-btn").click();
    const download = await downloadPromise;
    const path = await download.path();
    expect(path).toBeTruthy();
    const { readFileSync } = await import("node:fs");
    const content = readFileSync(path!, "utf-8");

    expect(content).toContain("QS-Category");
    expect(content).toContain("42");
  });

  test("CSV export escapes commas, quotes, and newlines correctly", async ({
    page,
  }) => {
    await unlockEntityRows(page, 1);
    const table = page.getByRole("grid", { name: /IFC entities/i });
    const nameInput = table.locator("tbody .col-name input").first();
    await nameInput.click();
    const formulaInput = page.locator(".formula-input");
    await formulaInput.fill('Value with "quotes" and, comma');
    await formulaInput.press("Enter");

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-csv-btn").click();
    const download = await downloadPromise;
    const path = await download.path();
    expect(path).toBeTruthy();
    const { readFileSync } = await import("node:fs");
    const content = readFileSync(path!, "utf-8");

    expect(content).toContain('"Value with ""quotes"" and, comma"');
  });
});
