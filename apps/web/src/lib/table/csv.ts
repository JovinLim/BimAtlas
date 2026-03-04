/**
 * CSV export for the merged table (entity grid + bottom sheet).
 * Produces UTF-8 CSV with proper escaping for commas, quotes, and newlines.
 */

/** Escape a cell value for CSV: wrap in quotes if needed, double internal quotes. */
export function escapeCsvCell(value: string): string {
  const str = value == null ? "" : String(value);
  const needsQuotes =
    str.includes(",") || str.includes('"') || str.includes("\n") || str.includes("\r");
  if (needsQuotes) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export interface CsvExportParams {
  /** Column labels in display order (matches frontend UI). */
  headers: string[];
  /** Entity row values: array of rows, each row is array of cell values. */
  entityRows: string[][];
  /** Sheet row values: each row maps to same columns (entityGlobalId, category, label, value, notes, tag for A–F). */
  sheetRows: Array<{
    entityGlobalId: string | null;
    category: string;
    label: string;
    value: string;
    notes: string;
    tag: string;
  }>;
}

/**
 * Build CSV text for the full merged table.
 * Headers: only the columns shown in the frontend (no extra "Sheet" columns).
 * Rows: entity rows first, then sheet rows. Both use the same column set.
 */
export function buildMergedCsv(params: CsvExportParams): string {
  const { headers, entityRows, sheetRows } = params;

  const lines: string[] = [];
  lines.push(headers.map(escapeCsvCell).join(","));

  for (const row of entityRows) {
    lines.push(row.map(escapeCsvCell).join(","));
  }

  const sheetColCount = 6;
  for (const entry of sheetRows) {
    const sheetCells = [
      entry.entityGlobalId ?? "",
      entry.category ?? "",
      entry.label ?? "",
      entry.value ?? "",
      entry.notes ?? "",
      entry.tag ?? "",
    ];
    const padded = headers.map((_, i) =>
      i < sheetColCount ? sheetCells[i] ?? "" : "",
    );
    lines.push(padded.map(escapeCsvCell).join(","));
  }

  return lines.join("\n");
}

/** Generate filename: filtered-entities-<revisionId>-<yyyyMMdd-HHmm>.csv */
export function csvFilename(revisionId: string | number | null): string {
  const rev = revisionId != null ? String(revisionId) : "unknown";
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const h = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  return `filtered-entities-${rev}-${y}${m}${d}-${h}${min}.csv`;
}

/** Trigger browser download of CSV with UTF-8 BOM for Excel compatibility. */
export function downloadCsv(csvText: string, filename: string): void {
  const bom = "\uFEFF";
  const blob = new Blob([bom + csvText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
