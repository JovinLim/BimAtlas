/**
 * Table engine adapter boundary.
 * Default implementation is Svelte-native (EntityGrid + BottomSheet).
 * Optional Univer integration can be swapped in behind a feature flag or
 * dynamic import for phase-2 if spreadsheet requirements justify it.
 */

/** Capabilities the table UI expects from an engine (current or future Univer). */
export interface TableEngineCapabilities {
  /** Whether the engine supports lock/unlock per row. */
  rowLock: boolean;
  /** Whether the engine supports protected (read-only) columns. */
  protectedColumns: boolean;
  /** Whether the engine supports a separate sheet/notes area. */
  sheetArea: boolean;
}

/** Engine descriptor for feature detection and optional swap. */
export interface TableEngine {
  id: "svelte-native" | "univer";
  capabilities: TableEngineCapabilities;
}

export type SpreadsheetSurface = "entity" | "sheet";

export interface SpreadsheetCellRef {
  surface: SpreadsheetSurface;
  row: number;
  col: string;
}

export interface SpreadsheetCellState extends SpreadsheetCellRef {
  ref: string;
  editable: boolean;
  protected: boolean;
}

export interface SpreadsheetSnapshot {
  topEdits: Record<string, string>;
  topFormulas: Record<string, string>;
  sheetEntries: Array<{
    id: string;
    entityGlobalId: string | null;
    category: string;
    label: string;
    value: string;
    notes: string;
    tag: string;
  }>;
  sheetFormulas: Record<string, string>;
  lockedIds: string[];
  sheetLockedIds: string[];
}

const DEFAULT_ENGINE: TableEngine = {
  id: "svelte-native",
  capabilities: {
    rowLock: true,
    protectedColumns: true,
    sheetArea: true,
  },
};

let currentEngine: TableEngine = DEFAULT_ENGINE;

/**
 * Returns the active table engine. Use this to branch UI or behavior
 * when a Univer engine is enabled (e.g. via VITE_TABLE_ENGINE=univer).
 */
export function getTableEngine(): TableEngine {
  return currentEngine;
}

/**
 * Optional: load Univer-based engine dynamically (e.g. when feature flag is set).
 * Reserved for phase-2. Calling this without installing @univerjs/* will throw.
 */
export async function loadUniverEngine(): Promise<TableEngine> {
  const env = typeof import.meta !== "undefined" && import.meta.env
    ? (import.meta.env.VITE_TABLE_ENGINE as string | undefined)
    : undefined;
  if (env !== "univer") {
    return currentEngine;
  }
  try {
    // Optional dependency: not installed by default; reserved for phase-2.
    const univerPackage = "@univerjs/core";
    await import(/* @vite-ignore */ univerPackage);
    currentEngine = {
      id: "univer",
      capabilities: {
        rowLock: true,
        protectedColumns: true,
        sheetArea: true,
      },
    };
    return currentEngine;
  } catch {
    return currentEngine;
  }
}

export function toCellRef(col: string, row: number): string {
  return `${col.toUpperCase()}${row}`;
}

export function parseCellRef(value: string): { col: string; row: number } | null {
  const match = /^([A-Za-z]+)(\d+)$/.exec(value.trim());
  if (!match) return null;
  return {
    col: match[1].toUpperCase(),
    row: Number(match[2]),
  };
}
