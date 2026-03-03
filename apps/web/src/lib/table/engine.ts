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
    // @ts-expect-error - @univerjs/core is not in package.json
    await import(/* webpackIgnore: true */ "@univerjs/core");
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
