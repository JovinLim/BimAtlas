import { parseCellRef } from "$lib/table/engine";

type CellResolver = (ref: string) => string | null;

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
