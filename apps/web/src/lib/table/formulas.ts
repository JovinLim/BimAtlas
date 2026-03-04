import { parseCellRef } from "$lib/table/engine";

type CellResolver = (ref: string) => string | null;

/** Formula functions supported by the spreadsheet (for autocomplete dropdown). */
export interface FormulaSuggestion {
  name: string;
  /** Inserted after "=", e.g. "SUM()" — cursor is placed inside the parens. */
  template: string;
  /** Display signature, e.g. "SUM(start:end)". */
  signature: string;
  description: string;
}

export const FORMULA_SUGGESTIONS: FormulaSuggestion[] = [
  {
    name: "SUM",
    template: "SUM()",
    signature: "SUM(start:end)",
    description: "Sum a range of cells (e.g. =SUM(D2:D4))",
  },
  {
    name: "AVERAGE",
    template: "AVERAGE()",
    signature: "AVERAGE(start:end)",
    description: "Average of numeric cells in a range; skips empty/non-numeric (e.g. =AVERAGE(D2:D4))",
  },
];

export function getFormulaSuggestions(prefix: string): FormulaSuggestion[] {
  const lower = prefix.trim().toLowerCase();
  if (lower === "") return [...FORMULA_SUGGESTIONS];
  return FORMULA_SUGGESTIONS.filter((s) =>
    s.name.toLowerCase().startsWith(lower),
  );
}

export interface FormulaResult {
  ok: boolean;
  value: string;
}

function toNumber(value: string | null): number | null {
  if (value == null || value.trim() === "") return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function colToIndex(col: string): number {
  let result = 0;
  const normalized = col.toUpperCase();
  for (let i = 0; i < normalized.length; i += 1) {
    result = result * 26 + (normalized.charCodeAt(i) - 64);
  }
  return result - 1;
}

function indexToCol(index: number): string {
  let n = index + 1;
  let out = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

function eachRefInRange(startRef: string, endRef: string): string[] {
  const start = parseCellRef(startRef);
  const end = parseCellRef(endRef);
  if (!start || !end) return [];
  const colStart = Math.min(colToIndex(start.col), colToIndex(end.col));
  const colEnd = Math.max(colToIndex(start.col), colToIndex(end.col));
  const rowStart = Math.min(start.row, end.row);
  const rowEnd = Math.max(start.row, end.row);
  const refs: string[] = [];
  for (let row = rowStart; row <= rowEnd; row += 1) {
    for (let col = colStart; col <= colEnd; col += 1) {
      refs.push(`${indexToCol(col)}${row}`);
    }
  }
  return refs;
}

export function evaluateFormula(input: string, resolver: CellResolver): FormulaResult {
  const trimmed = input.trim();
  if (!trimmed.startsWith("=")) {
    return { ok: true, value: input };
  }
  const body = trimmed.slice(1).trim();
  if (body === "") {
    return { ok: false, value: "#ERROR" };
  }

  const singleRef = /^([A-Za-z]+\d+)$/.exec(body);
  if (singleRef) {
    const resolved = resolver(singleRef[1].toUpperCase());
    if (resolved == null) return { ok: false, value: "#REF" };
    return { ok: true, value: resolved };
  }

  const sumRange = /^SUM\(([A-Za-z]+\d+):([A-Za-z]+\d+)\)$/i.exec(body);
  if (sumRange) {
    const refs = eachRefInRange(sumRange[1], sumRange[2]);
    if (refs.length === 0) return { ok: false, value: "#REF" };
    let total = 0;
    for (const ref of refs) {
      const resolved = resolver(ref);
      const numeric = toNumber(resolved);
      if (numeric == null) return { ok: false, value: "#ERROR" };
      total += numeric;
    }
    return { ok: true, value: String(total) };
  }

  const averageRange = /^AVERAGE\(([A-Za-z]+\d+):([A-Za-z]+\d+)\)$/i.exec(body);
  if (averageRange) {
    const refs = eachRefInRange(averageRange[1], averageRange[2]);
    if (refs.length === 0) return { ok: false, value: "#REF" };
    const numbers: number[] = [];
    for (const ref of refs) {
      try {
        const resolved = resolver(ref);
        if (resolved == null || String(resolved).trim() === "") continue;
        const numeric = toNumber(resolved);
        if (numeric !== null) numbers.push(numeric);
      } catch {
        // Skip cells that fail to resolve (e.g. circular ref); don't fail the whole formula
        continue;
      }
    }
    if (numbers.length === 0) return { ok: false, value: "#DIV/0!" };
    const sum = numbers.reduce((a, b) => a + b, 0);
    const avg = sum / numbers.length;
    if (!Number.isFinite(avg)) return { ok: false, value: "#ERROR" };
    return { ok: true, value: String(avg) };
  }

  const refs = Array.from(body.matchAll(/[A-Za-z]+\d+/g)).map((m) =>
    m[0].toUpperCase(),
  );
  let expression = body;
  for (const ref of refs) {
    const resolved = resolver(ref);
    if (resolved == null) return { ok: false, value: "#REF" };
    const numeric = toNumber(resolved);
    if (numeric == null) return { ok: false, value: "#ERROR" };
    expression = expression.replaceAll(ref, String(numeric));
  }
  if (!/^[\d+\-*/().\s]+$/.test(expression)) {
    return { ok: false, value: "#ERROR" };
  }

  try {
    const result = Function(`"use strict"; return (${expression});`)();
    if (!Number.isFinite(result)) {
      return { ok: false, value: "#ERROR" };
    }
    return { ok: true, value: String(result) };
  } catch {
    return { ok: false, value: "#ERROR" };
  }
}
