export interface SheetEntry {
  id: string;
  entityGlobalId: string | null;
  category: string;
  label: string;
  value: string;
  notes: string;
  tag: string;
}

/** State for a single bottom sheet (multi-sheet support). */
export interface SheetState {
  id: string;
  name: string;
  entries: SheetEntry[];
  formulas: Record<string, string>;
  lockedIds: Set<string>;
  /** Template id in DB when saved; null when unsaved. */
  templateId?: string | null;
}
