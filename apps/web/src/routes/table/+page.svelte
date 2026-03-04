<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import { page } from "$app/stores";
  import {
    TABLE_CHANNEL,
    TABLE_PROTOCOL_VERSION,
    ENABLE_TABLE_VIEWER_SELECTION_SYNC,
    type TableMessage,
  } from "$lib/table/protocol";
  import type { ProductMeta } from "$lib/search/protocol";
  import { TABLE_FIXTURE_PRODUCTS } from "$lib/table/fixtures";
  import { loadSettings } from "$lib/state/persistence";
  import { client, PROJECTS_QUERY } from "$lib/api/client";
  import EntityGrid from "$lib/table/EntityGrid.svelte";
  import BottomSheet from "$lib/table/BottomSheet.svelte";
  import type { SheetEntry } from "$lib/table/types";
  import {
    parseCellRef,
    type SpreadsheetCellState,
    type SpreadsheetSnapshot,
  } from "$lib/table/engine";
  import { evaluateFormula, getFormulaSuggestions, FORMULA_SUGGESTIONS } from "$lib/table/formulas";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);
  /** Products from main window context, or fixture when ?fixture=1 */
  let products = $state<ProductMeta[]>([]);
  let useFixture = $state(false);
  /** Row lock state: locked rows are read-only for editable cells. */
  let lockedIds = $state<Set<string>>(new Set());
  /** Bottom-sheet row lock state by entry id. */
  let sheetLockedIds = $state<Set<string>>(new Set());
  /** Bottom sheet entries (notes / quantity surveying). Session-only for v1. */
  let sheetEntries = $state<SheetEntry[]>([]);
  let topEdits = $state<Record<string, string>>({});
  let topFormulas = $state<Record<string, string>>({});
  let sheetFormulas = $state<Record<string, string>>({});
  let draftValues = $state<Record<string, string>>({});
  let activeCell = $state<SpreadsheetCellState | null>(null);
  let formulaInput = $state("");
  let formulaComposeSourceRef = $state<string | null>(null);
  let formulaSuggestionIndex = $state(0);
  let showFormulaGuideOverlay = $state(false);

  $effect(() => {
    if (!showFormulaGuideOverlay) return;
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") showFormulaGuideOverlay = false;
    };
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  });

  $effect(() => {
    const id = findHighlightGlobalId;
    if (!id || !segmentTopRef) return;
    tick().then(() => {
      const row = segmentTopRef?.querySelector(
        `tr.entity-row[data-global-id="${id}"]`,
      );
      row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  });

  const formulaPrefix = $derived.by(() => {
    const t = formulaInput.trim();
    if (!t.startsWith("=")) return "";
    const body = t.slice(1);
    const match = body.match(/^[A-Za-z]*/);
    return match ? match[0] : "";
  });
  const formulaSuggestionsList = $derived(getFormulaSuggestions(formulaPrefix));
  const showFormulaDropdown = $derived(
    formulaInput.trim().startsWith("=") &&
      /^[A-Za-z]*$/.test(formulaInput.trim().slice(1)) &&
      formulaSuggestionsList.length > 0 &&
      activeCell != null &&
      activeCell.editable,
  );
  /** GlobalId of the row to show as selected (from table focus or, when sync enabled, from viewer). */
  const selectedRowGlobalId = $derived.by(() => {
    if (activeCell && activeCell.surface === "entity") {
      const product = getTopProductByRow(activeCell.row);
      return product?.globalId ?? null;
    }
    if (ENABLE_TABLE_VIEWER_SELECTION_SYNC) return viewerSelectedGlobalId;
    return null;
  });
  let selectionRange = $state<{ startRef: string; endRef: string } | null>(null);
  let isDraggingSelection = $state(false);
  let undoStack = $state<SpreadsheetSnapshot[]>([]);
  let redoStack = $state<SpreadsheetSnapshot[]>([]);

  let channel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let hasChannelContext = $state(false);
  const NAV_COLS = ["A", "B", "C", "D", "E", "F"] as const;

  function colIndex(col: string): number {
    return NAV_COLS.indexOf(col as (typeof NAV_COLS)[number]);
  }

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    const fixtureParam = url.searchParams.get("fixture");
    if (b != null && b !== "") branchId = b;
    if (p != null && p !== "") projectId = p;
    if (r != null && r !== "") {
      const parsed = Number(r);
      revision = Number.isNaN(parsed) ? null : parsed;
    }
    useFixture = fixtureParam === "1" || fixtureParam === "true";
    if (useFixture) {
      products = [...TABLE_FIXTURE_PRODUCTS];
      lockedIds = new Set(products.map((p) => p.globalId));
    }
  }

  function applyContextFallbackFromSettings() {
    if (useFixture) return;
    const settings = loadSettings();
    if (!settings) return;
    if (branchId == null && settings.activeBranchId != null) {
      branchId = settings.activeBranchId;
    }
    if (projectId == null && settings.activeProjectId != null) {
      projectId = settings.activeProjectId;
    }
    if (revision == null && settings.activeRevision != null) {
      revision = settings.activeRevision;
    }
  }

  /** When the main viewer selects an entity, we highlight that row (only when sync enabled). */
  let viewerSelectedGlobalId = $state<string | null>(null);
  /** Pending "Find selected element" request: after next context we'll highlight/scroll or toast. */
  let findPending = $state(false);
  /** Row to highlight in orange and scroll into view (from "Find selected element"). */
  let findHighlightGlobalId = $state<string | null>(null);
  let toastMessage = $state<string | null>(null);
  let toastTimeoutId = $state<ReturnType<typeof setTimeout> | null>(null);
  let segmentTopRef = $state<HTMLElement | null>(null);

  function showToast(message: string) {
    if (toastTimeoutId != null) clearTimeout(toastTimeoutId);
    toastMessage = message;
    toastTimeoutId = setTimeout(() => {
      toastMessage = null;
      toastTimeoutId = null;
    }, 3000);
  }

  function handleIncomingMessage(e: MessageEvent<TableMessage>) {
    const msg = e.data;
    if (msg.type === "context" && msg.version === TABLE_PROTOCOL_VERSION) {
      if (useFixture) return;
      const wasFindPending = findPending;
      findPending = false;
      hasChannelContext = true;
      branchId = msg.branchId;
      projectId = msg.projectId;
      branchName = msg.branchName ?? null;
      projectName = msg.projectName ?? null;
      revision = msg.revision;
      products = msg.products ?? [];
      lockedIds = new Set(products.map((p) => p.globalId));

      const params = new URLSearchParams($page.url.searchParams);
      if (branchId != null) params.set("branchId", String(branchId));
      else params.delete("branchId");
      if (projectId != null) params.set("projectId", String(projectId));
      else params.delete("projectId");
      if (revision != null) params.set("revision", String(revision));
      else params.delete("revision");
      window.history.replaceState(
        null,
        "",
        `${$page.url.pathname}?${params.toString()}`,
      );

      if (contextRetryInterval != null) {
        clearInterval(contextRetryInterval);
        contextRetryInterval = null;
      }

      if (wasFindPending) {
        const globalId = msg.activeGlobalId ?? null;
        if (globalId == null || globalId === "") {
          showToast("No element selected in viewer");
          findHighlightGlobalId = null;
        } else {
          findHighlightGlobalId = globalId;
        }
      }
    } else if (
      ENABLE_TABLE_VIEWER_SELECTION_SYNC &&
      msg.type === "selection-sync"
    ) {
      viewerSelectedGlobalId = msg.globalId;
    }
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies TableMessage);
  }

  function findSelectedElement() {
    findPending = true;
    requestContext();
  }

  async function resolveNamesFromProjects() {
    if (!projectId || !branchId) return;
    if (projectName && branchName) return;
    try {
      const result = await client.query(PROJECTS_QUERY, {}).toPromise();
      const project = result.data?.projects?.find(
        (p: { id: string; name: string; branches: { id: string; name: string }[] }) =>
          p.id === projectId,
      );
      if (project) {
        projectName = project.name ?? projectName;
        const branch = project.branches?.find(
          (b: { id: string; name: string }) => b.id === branchId,
        );
        if (branch) branchName = branch.name ?? branchName;
      }
    } catch {
      // Non-blocking fallback; keep IDs if name lookup fails.
    }
  }

  function toggleLock(globalId: string) {
    pushHistory();
    const next = new Set(lockedIds);
    if (next.has(globalId)) {
      next.delete(globalId);
    } else {
      next.add(globalId);
    }
    lockedIds = next;
  }

  const allEntitiesLocked = $derived(
    products.length > 0 &&
      products.every((p) => lockedIds.has(p.globalId)) &&
      sheetEntries.every((entry) => sheetLockedIds.has(entry.id)),
  );

  function toggleLockAll() {
    if (products.length === 0 && sheetEntries.length === 0) return;
    pushHistory();
    if (allEntitiesLocked) {
      lockedIds = new Set();
      sheetLockedIds = new Set();
    } else {
      lockedIds = new Set(products.map((p) => p.globalId));
      sheetLockedIds = new Set(sheetEntries.map((entry) => entry.id));
    }
  }

  function toggleSheetEntryLock(entryId: string) {
    pushHistory();
    const next = new Set(sheetLockedIds);
    if (next.has(entryId)) {
      next.delete(entryId);
    } else {
      next.add(entryId);
    }
    sheetLockedIds = next;
  }

  function snapshot(): SpreadsheetSnapshot {
    return {
      topEdits: { ...topEdits },
      topFormulas: { ...topFormulas },
      sheetEntries: sheetEntries.map((entry) => ({ ...entry })),
      sheetFormulas: { ...sheetFormulas },
      lockedIds: Array.from(lockedIds),
      sheetLockedIds: Array.from(sheetLockedIds),
    };
  }

  function applySnapshot(value: SpreadsheetSnapshot) {
    topEdits = { ...value.topEdits };
    topFormulas = { ...value.topFormulas };
    sheetEntries = value.sheetEntries.map((entry) => ({ ...entry }));
    sheetFormulas = { ...value.sheetFormulas };
    lockedIds = new Set(value.lockedIds);
    sheetLockedIds = new Set(value.sheetLockedIds ?? []);
    draftValues = {};
    if (activeCell != null) {
      const ref = activeCell.ref;
      formulaInput = getFormulaForRef(ref) ?? getCommittedValue(ref);
    }
  }

  function pushHistory() {
    undoStack = [...undoStack, snapshot()].slice(-100);
    redoStack = [];
  }

  function undo() {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    undoStack = undoStack.slice(0, -1);
    redoStack = [...redoStack, snapshot()];
    applySnapshot(prev);
  }

  function redo() {
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    redoStack = redoStack.slice(0, -1);
    undoStack = [...undoStack, snapshot()];
    applySnapshot(next);
  }

  function sheetRowStart(): number {
    return products.length + 2;
  }

  function getTopProductByRow(row: number): ProductMeta | null {
    const index = row - 2;
    if (index < 0 || index >= products.length) return null;
    return products[index] ?? null;
  }

  function getSheetEntryByRow(row: number): SheetEntry | null {
    const index = row - sheetRowStart();
    if (index < 0 || index >= sheetEntries.length) return null;
    return sheetEntries[index] ?? null;
  }

  function isSheetRowLocked(row: number): boolean {
    const entry = getSheetEntryByRow(row);
    if (!entry) return false;
    return sheetLockedIds.has(entry.id);
  }

  function resolveCellByRef(ref: string): SpreadsheetCellState | null {
    const parsed = parseCellRef(ref);
    if (!parsed) return null;
    if (!NAV_COLS.includes(parsed.col as (typeof NAV_COLS)[number])) return null;

    const topProduct = getTopProductByRow(parsed.row);
    if (topProduct) {
      const editable =
        !lockedIds.has(topProduct.globalId) &&
        (parsed.col === "C" ||
          parsed.col === "D" ||
          parsed.col === "E" ||
          parsed.col === "F");
      const isProtected = parsed.col === "A" || parsed.col === "B";
      return {
        surface: "entity",
        row: parsed.row,
        col: parsed.col,
        ref,
        editable,
        protected: isProtected,
      };
    }

    const sheetEntry = getSheetEntryByRow(parsed.row);
    if (sheetEntry) {
      const isProtected = false;
      return {
        surface: "sheet",
        row: parsed.row,
        col: parsed.col,
        ref,
        editable: !isProtected && !isSheetRowLocked(parsed.row),
        protected: isProtected,
      };
    }
    return null;
  }

  function getTopFallback(ref: string, product: ProductMeta): string {
    const parsed = parseCellRef(ref);
    if (!parsed) return "";
    if (parsed.col === "A") return product.globalId ?? "";
    if (parsed.col === "B") return product.ifcClass ?? "";
    if (parsed.col === "C") return product.name ?? "";
    if (parsed.col === "D") return product.description ?? "";
    if (parsed.col === "E") return product.objectType ?? "";
    if (parsed.col === "F") return product.tag ?? "";
    return "";
  }

  function getSheetField(col: string): keyof Omit<SheetEntry, "id"> | null {
    if (col === "A") return "entityGlobalId";
    if (col === "B") return "category";
    if (col === "C") return "label";
    if (col === "D") return "value";
    if (col === "E") return "notes";
    if (col === "F") return "tag";
    return null;
  }

  function getCommittedValue(ref: string): string {
    const cell = resolveCellByRef(ref);
    if (!cell) return "";
    if (cell.surface === "entity") {
      if (topEdits[ref] !== undefined) return topEdits[ref] ?? "";
      const product = getTopProductByRow(cell.row);
      if (!product) return "";
      return getTopFallback(ref, product);
    }

    const entry = getSheetEntryByRow(cell.row);
    if (!entry) return "";
    const field = getSheetField(cell.col);
    if (!field) return "";
    const value = entry[field];
    return value == null ? "" : String(value);
  }

  function getFormulaForRef(ref: string): string | null {
    return topFormulas[ref] ?? sheetFormulas[ref] ?? null;
  }

  function getCellDisplayValue(ref: string, fallback: string): string {
    if (draftValues[ref] !== undefined) return draftValues[ref] ?? "";
    if (activeCell?.ref === ref) {
      const rawFormula = getFormulaForRef(ref);
      if (rawFormula != null) return rawFormula;
    }
    if (topEdits[ref] !== undefined) return topEdits[ref] ?? "";
    const parsed = parseCellRef(ref);
    if (!parsed) return fallback;
    if (parsed.row >= sheetRowStart() && sheetFormulas[ref] !== undefined) {
      return getCommittedValue(ref);
    }
    return fallback;
  }

  function updateTopFormula(ref: string, raw: string | null) {
    if (raw == null) {
      if (topFormulas[ref] === undefined) return;
      const next = { ...topFormulas };
      delete next[ref];
      topFormulas = next;
      return;
    }
    topFormulas = { ...topFormulas, [ref]: raw };
  }

  function updateSheetFormula(ref: string, raw: string | null) {
    if (raw == null) {
      if (sheetFormulas[ref] === undefined) return;
      const next = { ...sheetFormulas };
      delete next[ref];
      sheetFormulas = next;
      return;
    }
    sheetFormulas = { ...sheetFormulas, [ref]: raw };
  }

  function setCommittedCellValue(cell: SpreadsheetCellState, value: string, rawFormula: string | null) {
    if (cell.surface === "entity") {
      topEdits = { ...topEdits, [cell.ref]: value };
      updateTopFormula(cell.ref, rawFormula);
      return;
    }
    const field = getSheetField(cell.col);
    if (!field) return;
    const index = cell.row - sheetRowStart();
    if (index < 0 || index >= sheetEntries.length) return;
    sheetEntries = sheetEntries.map((entry, idx) => {
      if (idx !== index) return entry;
      return {
        ...entry,
        [field]: field === "entityGlobalId" && value.trim() === "" ? null : value,
      };
    });
    updateSheetFormula(cell.ref, rawFormula);
  }

  function syncSelectionToViewer(globalId: string | null) {
    if (!ENABLE_TABLE_VIEWER_SELECTION_SYNC) return;
    channel?.postMessage({ type: "selection-changed", globalId } satisfies TableMessage);
  }

  function selectCell(cell: SpreadsheetCellState) {
    activeCell = cell;
    formulaInput = getFormulaForRef(cell.ref) ?? getCommittedValue(cell.ref);
    if (formulaComposeSourceRef !== cell.ref) {
      formulaComposeSourceRef = null;
    }
    if (cell.surface === "entity") {
      const product = getTopProductByRow(cell.row);
      syncSelectionToViewer(product?.globalId ?? null);
    } else {
      syncSelectionToViewer(null);
    }
  }

  function onCellFocus(cell: SpreadsheetCellState) {
    selectCell(cell);
  }

  function onCellInput(cell: SpreadsheetCellState, value: string) {
    draftValues = { ...draftValues, [cell.ref]: value };
    if (activeCell?.ref === cell.ref) {
      formulaInput = value;
      formulaComposeSourceRef = value.trim().startsWith("=") ? cell.ref : null;
    }
  }

  function clearDraft(ref: string) {
    if (draftValues[ref] === undefined) return;
    const next = { ...draftValues };
    delete next[ref];
    draftValues = next;
  }

  function resolveValueForFormula(ref: string): string | null {
    const cell = resolveCellByRef(ref);
    if (!cell) return null;
    return getCommittedValue(ref);
  }

  function commitCell(cell: SpreadsheetCellState, rawInput: string) {
    if (!cell.editable) {
      clearDraft(cell.ref);
      formulaInput = getFormulaForRef(cell.ref) ?? getCommittedValue(cell.ref);
      return;
    }

    const input = rawInput;
    const previousValue = getCommittedValue(cell.ref);
    const previousFormula = getFormulaForRef(cell.ref);
    // Guard against stale blur commits after keyboard navigation (Enter/Tab).
    // In that sequence, a formula cell may already be committed, then re-rendered
    // to its computed value, and blur fires with that computed text. We should not
    // treat that blur as a real user edit that clears the formula.
    if (
      activeCell?.ref !== cell.ref &&
      previousFormula != null &&
      input === previousValue
    ) {
      clearDraft(cell.ref);
      return;
    }
    let nextValue = input;
    let nextFormula: string | null = null;

    if (input.trim().startsWith("=")) {
      const result = evaluateFormula(input, resolveValueForFormula);
      nextValue = result.ok ? result.value : input;
      nextFormula = input;
    }

    if (previousValue === nextValue && previousFormula === nextFormula) {
      clearDraft(cell.ref);
      if (activeCell?.ref === cell.ref) {
        formulaInput = nextFormula ?? nextValue;
      }
      return;
    }

    pushHistory();
    setCommittedCellValue(cell, nextValue, nextFormula);
    clearDraft(cell.ref);
    if (activeCell?.ref === cell.ref) {
      formulaInput = nextFormula ?? nextValue;
      formulaComposeSourceRef = null;
    }
  }

  function onCellCommit(cell: SpreadsheetCellState, value: string) {
    commitCell(cell, value);
  }

  function onCellCancel(cell: SpreadsheetCellState) {
    clearDraft(cell.ref);
    formulaComposeSourceRef = null;
    if (activeCell?.ref === cell.ref) {
      formulaInput = getFormulaForRef(cell.ref) ?? getCommittedValue(cell.ref);
    }
  }

  function focusCell(ref: string) {
    const el = document.querySelector<HTMLInputElement>(`[data-cell-ref="${ref}"]`);
    if (!el) return;
    el.focus();
    el.select();
  }

  function isCellInSelection(ref: string): boolean {
    if (!selectionRange) return false;
    const start = parseCellRef(selectionRange.startRef);
    const end = parseCellRef(selectionRange.endRef);
    const target = parseCellRef(ref);
    if (!start || !end || !target) return false;
    const minRow = Math.min(start.row, end.row);
    const maxRow = Math.max(start.row, end.row);
    const minCol = Math.min(colIndex(start.col), colIndex(end.col));
    const maxCol = Math.max(colIndex(start.col), colIndex(end.col));
    const targetCol = colIndex(target.col);
    if (targetCol < 0 || minCol < 0 || maxCol < 0) return false;
    return target.row >= minRow && target.row <= maxRow && targetCol >= minCol && targetCol <= maxCol;
  }

  function startSelection(ref: string) {
    selectionRange = { startRef: ref, endRef: ref };
    isDraggingSelection = true;
  }

  function updateSelectionEnd(ref: string) {
    if (!selectionRange) return;
    selectionRange = { ...selectionRange, endRef: ref };
  }

  function appendReferenceToFormula(targetRef: string): boolean {
    if (!formulaComposeSourceRef) return false;
    const sourceCell = resolveCellByRef(formulaComposeSourceRef);
    if (!sourceCell || !sourceCell.editable) return false;
    if (targetRef === formulaComposeSourceRef) return false;

    const sourceValue =
      draftValues[formulaComposeSourceRef] ??
      (activeCell?.ref === formulaComposeSourceRef
        ? formulaInput
        : (getFormulaForRef(formulaComposeSourceRef) ?? getCommittedValue(formulaComposeSourceRef)));
    if (!sourceValue.trim().startsWith("=")) return false;

    const sourceRef = formulaComposeSourceRef;
    const insertion =
      sourceValue.trim() === "=" ? `=${targetRef}` : `${sourceValue}${targetRef}`;
    draftValues = { ...draftValues, [sourceRef]: insertion };
    formulaInput = insertion;
    activeCell = sourceCell;
    setTimeout(() => {
      focusCell(sourceRef);
      const formulaField = document.querySelector<HTMLInputElement>(".formula-input");
      formulaField?.focus();
      formulaField?.setSelectionRange(insertion.length, insertion.length);
    }, 0);
    return true;
  }

  function onCellPointerDown(cell: SpreadsheetCellState, event: MouseEvent): boolean {
    if (event.button !== 0) return false;
    if (appendReferenceToFormula(cell.ref)) {
      event.preventDefault();
      return true;
    }
    startSelection(cell.ref);
    selectCell(cell);
    return false;
  }

  function onCellPointerEnter(cell: SpreadsheetCellState, event: MouseEvent) {
    if (!isDraggingSelection) return;
    if ((event.buttons & 1) !== 1) return;
    updateSelectionEnd(cell.ref);
  }

  function onCellPointerUp(cell: SpreadsheetCellState, _event: MouseEvent) {
    if (!isDraggingSelection) return;
    updateSelectionEnd(cell.ref);
    isDraggingSelection = false;
  }

  function onCellNavigate(
    cell: SpreadsheetCellState,
    direction: "up" | "down" | "left" | "right" | "enter" | "tab",
    shift: boolean,
  ) {
    if (direction === "enter") {
      // Keep Enter behavior deterministic: commit via key handler, then clear selection.
      // This avoids occasional stale focus/blur races and matches requested UX.
      activeCell = null;
      selectionRange = null;
      formulaComposeSourceRef = null;
      formulaInput = "";
      isDraggingSelection = false;
      if (ENABLE_TABLE_VIEWER_SELECTION_SYNC) syncSelectionToViewer(null);
      return;
    }

    let deltaRow = 0;
    let deltaCol = 0;
    if (direction === "up") deltaRow = -1;
    if (direction === "down") deltaRow = 1;
    if (direction === "left") deltaCol = -1;
    if (direction === "right") deltaCol = 1;
    if (direction === "tab") deltaCol = shift ? -1 : 1;

    const colIndex = NAV_COLS.indexOf(cell.col as (typeof NAV_COLS)[number]);
    const targetColIndex = Math.max(0, Math.min(NAV_COLS.length - 1, colIndex + deltaCol));
    const minRow = 2;
    const maxRow = Math.max(sheetRowStart() + sheetEntries.length - 1, products.length + 1);
    const targetRow = Math.max(minRow, Math.min(maxRow, cell.row + deltaRow));
    const nextRef = `${NAV_COLS[targetColIndex]}${targetRow}`;
    const nextCell = resolveCellByRef(nextRef);
    if (!nextCell) return;
    selectionRange = { startRef: nextRef, endRef: nextRef };
    isDraggingSelection = false;
    selectCell(nextCell);
    setTimeout(() => focusCell(nextRef), 0);
  }

  function applyFormulaSuggestion(suggestion: { template: string }) {
    const next = "=" + suggestion.template;
    formulaInput = next;
    if (activeCell != null) {
      draftValues = { ...draftValues, [activeCell.ref]: next };
      formulaComposeSourceRef = activeCell.ref;
    }
    const cursorPos = next.indexOf("(") + 1;
    requestAnimationFrame(() => {
      const el = document.querySelector<HTMLInputElement>(".formula-input");
      el?.focus();
      el?.setSelectionRange(cursorPos, cursorPos);
    });
  }

  function applyFormulaInput() {
    if (!activeCell) return;
    if (showFormulaDropdown && formulaSuggestionsList.length > 0) {
      const idx = Math.max(0, Math.min(formulaSuggestionIndex, formulaSuggestionsList.length - 1));
      applyFormulaSuggestion(formulaSuggestionsList[idx]);
      formulaSuggestionIndex = 0;
      return;
    }
    commitCell(activeCell, formulaInput);
  }

  function cancelFormulaInput() {
    if (!activeCell) return;
    const cell = activeCell;
    clearDraft(cell.ref);
    formulaInput = getFormulaForRef(cell.ref) ?? getCommittedValue(cell.ref);
    setTimeout(() => focusCell(cell.ref), 0);
  }

  function fillDownFromActive() {
    if (!activeCell || !activeCell.editable) return;
    const nextRef = `${activeCell.col}${activeCell.row + 1}`;
    const nextCell = resolveCellByRef(nextRef);
    if (!nextCell || !nextCell.editable) return;
    const seed = getFormulaForRef(activeCell.ref) ?? getCommittedValue(activeCell.ref);
    pushHistory();
    const result = seed.trim().startsWith("=")
      ? evaluateFormula(seed, resolveValueForFormula)
      : { ok: true, value: seed };
    const nextValue = result.ok ? result.value : seed;
    setCommittedCellValue(nextCell, nextValue, seed.trim().startsWith("=") ? seed : null);
    selectCell(nextCell);
    formulaInput = getFormulaForRef(nextCell.ref) ?? getCommittedValue(nextCell.ref);
    setTimeout(() => focusCell(nextCell.ref), 0);
  }

  function onFillDownRequest(_cell: SpreadsheetCellState) {
    fillDownFromActive();
  }

  function onSheetEntriesChange(nextEntries: SheetEntry[]) {
    if (nextEntries.length !== sheetEntries.length) {
      pushHistory();
    }
    const nextIds = new Set(nextEntries.map((entry) => entry.id));
    sheetLockedIds = new Set(
      Array.from(sheetLockedIds).filter((id) => nextIds.has(id)),
    );
    sheetEntries = nextEntries;
  }

  function handleGlobalKeydown(e: KeyboardEvent) {
    const lowered = e.key.toLowerCase();
    if ((e.metaKey || e.ctrlKey) && lowered === "z" && !e.shiftKey) {
      e.preventDefault();
      undo();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && (lowered === "y" || (lowered === "z" && e.shiftKey))) {
      e.preventDefault();
      redo();
      return;
    }
    if (e.key === "F2" && activeCell != null) {
      e.preventDefault();
      const cell = activeCell;
      setTimeout(() => focusCell(cell.ref), 0);
    }
  }

  function handleGlobalPointerUp() {
    isDraggingSelection = false;
  }

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();
    void resolveNamesFromProjects();

    channel = new BroadcastChannel(TABLE_CHANNEL);
    channel.onmessage = handleIncomingMessage;

    if (!useFixture) {
      requestContext();
      contextRetryTimeout = setTimeout(() => {
        if (!hasChannelContext && !useFixture) {
          requestContext();
        }
        contextRetryTimeout = null;
      }, 1500);

      if (!hasChannelContext && !useFixture) {
        let attempts = 0;
        contextRetryInterval = setInterval(() => {
          if (
            hasChannelContext ||
            useFixture ||
            attempts >= 8
          ) {
            if (contextRetryInterval != null) {
              clearInterval(contextRetryInterval);
              contextRetryInterval = null;
            }
            return;
          }
          requestContext();
          attempts += 1;
        }, 1000);
      }
    }
    if (typeof window !== "undefined") {
      window.addEventListener("keydown", handleGlobalKeydown);
      window.addEventListener("mouseup", handleGlobalPointerUp);
    }
  });

  onDestroy(() => {
    channel?.close();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
    if (toastTimeoutId != null) clearTimeout(toastTimeoutId);
    if (typeof window !== "undefined") {
      window.removeEventListener("keydown", handleGlobalKeydown);
      window.removeEventListener("mouseup", handleGlobalPointerUp);
    }
  });
</script>

<div class="table-page">
  <header class="table-header">
    <h2>Table</h2>
    {#if useFixture}
      <span class="context-pill fixture">Fixture data</span>
    {:else if branchName || projectName || branchId || projectId}
      <span class="context-pill mono">
        {projectName ?? projectId ?? "—"} / {branchName ?? branchId ?? "—"}
        {#if revision != null}(rev {revision}){/if}
      </span>
    {:else}
      <span class="context-pill empty">Waiting for context…</span>
    {/if}
  </header>

  <div class="formula-bar" aria-label="Formula bar">
    <span class="formula-cell-ref mono">{activeCell?.ref ?? "—"}</span>
    <div class="formula-input-wrap">
      <input
        type="text"
        class="formula-input"
        value={formulaInput}
        placeholder="Enter value or formula (e.g. =D2+E2, =SUM(D2:D4))"
        disabled={activeCell == null}
        readonly={activeCell != null && !activeCell.editable}
        autocomplete="off"
        oninput={(e) => {
          formulaInput = e.currentTarget.value;
          formulaSuggestionIndex = 0;
          if (activeCell != null) {
            draftValues = { ...draftValues, [activeCell.ref]: formulaInput };
            formulaComposeSourceRef = formulaInput.trim().startsWith("=")
              ? activeCell.ref
              : null;
          }
        }}
        onkeydown={(e) => {
          if (showFormulaDropdown && formulaSuggestionsList.length > 0) {
            const len = formulaSuggestionsList.length;
            const idx = Math.max(0, Math.min(formulaSuggestionIndex, len - 1));
            if (e.key === "ArrowDown") {
              e.preventDefault();
              formulaSuggestionIndex = (idx + 1) % len;
              return;
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              formulaSuggestionIndex = (idx - 1 + len) % len;
              return;
            }
            if (e.key === "Enter" || e.key === "Tab") {
              e.preventDefault();
              applyFormulaSuggestion(formulaSuggestionsList[idx]);
              formulaSuggestionIndex = 0;
              return;
            }
          }
          if (e.key === "Enter") {
            e.preventDefault();
            applyFormulaInput();
          } else if (e.key === "Escape") {
            e.preventDefault();
            if (showFormulaDropdown) {
              formulaSuggestionIndex = 0;
            } else {
              cancelFormulaInput();
            }
          }
        }}
      />
      {#if showFormulaDropdown}
        <ul
          id="formula-suggestions-list"
          class="formula-suggestions"
          role="listbox"
          aria-label="Formula options"
        >
          {#each formulaSuggestionsList as suggestion, i}
            <li
              id="formula-suggestion-{i}"
              role="option"
              aria-selected={i === Math.max(0, Math.min(formulaSuggestionIndex, formulaSuggestionsList.length - 1))}
              class="formula-suggestion-item"
              class:selected={i === Math.max(0, Math.min(formulaSuggestionIndex, formulaSuggestionsList.length - 1))}
              onmousedown={(e) => {
                e.preventDefault();
                applyFormulaSuggestion(suggestion);
                formulaSuggestionIndex = 0;
              }}
            >
              <span class="formula-suggestion-sig mono">{suggestion.signature}</span>
              <span class="formula-suggestion-desc">{suggestion.description}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
    <button
      type="button"
      class="formula-btn"
      onclick={applyFormulaInput}
      disabled={activeCell == null || !activeCell.editable}
    >
      Apply
    </button>
    <button
      type="button"
      class="formula-btn"
      onclick={cancelFormulaInput}
      disabled={activeCell == null}
    >
      Cancel
    </button>
    <button
      type="button"
      class="formula-btn"
      onclick={fillDownFromActive}
      disabled={activeCell == null || !activeCell.editable}
      aria-label="Fill down from active cell"
    >
      Fill Down
    </button>
    <button
      type="button"
      class="formula-btn"
      onclick={undo}
      disabled={undoStack.length === 0}
      aria-label="Undo"
    >
      Undo
    </button>
    <button
      type="button"
      class="formula-btn"
      onclick={redo}
      disabled={redoStack.length === 0}
      aria-label="Redo"
    >
      Redo
    </button>
  </div>

  <div class="table-split">
    <section
      class="table-segment table-segment-top"
      aria-label="IFC entities"
      bind:this={segmentTopRef}
    >
      <div class="segment-toolbar">
        <p class="segment-label">Total entities: {products.length}</p>
        <button
          type="button"
          class="formula-guide-btn"
          onclick={findSelectedElement}
          disabled={!hasChannelContext}
          aria-label="Find selected element in viewer"
        >
          Find selected element
        </button>
        <button
          type="button"
          class="formula-guide-btn"
          onclick={toggleLockAll}
          disabled={products.length === 0 && sheetEntries.length === 0}
          aria-label={allEntitiesLocked ? "Unlock all rows" : "Lock all rows"}
        >
          {allEntitiesLocked ? "Unlock all" : "Lock all"}
        </button>
        <button
          type="button"
          class="formula-guide-btn"
          onclick={() => (showFormulaGuideOverlay = true)}
          aria-label="Open formula guide"
        >
          Formula guide
        </button>
      </div>
      <EntityGrid
        products={products}
        lockedIds={lockedIds}
        onToggleLock={toggleLock}
        activeCellRef={activeCell?.ref ?? null}
        selectedRowGlobalId={selectedRowGlobalId}
        findHighlightGlobalId={findHighlightGlobalId}
        getCellDisplayValue={getCellDisplayValue}
        onCellFocus={onCellFocus}
        onCellInput={onCellInput}
        onCellCommit={onCellCommit}
        onCellCancel={onCellCancel}
        onCellNavigate={onCellNavigate}
        onFillDown={onFillDownRequest}
      isCellInSelection={isCellInSelection}
      onCellPointerDown={onCellPointerDown}
      onCellPointerEnter={onCellPointerEnter}
      onCellPointerUp={onCellPointerUp}
      />
    </section>
    <section class="table-segment table-segment-bottom" aria-label="Sheet interactions">
      <BottomSheet
        bind:entries={sheetEntries}
        rowStart={products.length + 2}
        onEntriesChange={onSheetEntriesChange}
        lockedEntryIds={sheetLockedIds}
        onToggleEntryLock={toggleSheetEntryLock}
        activeCellRef={activeCell?.ref ?? null}
        getCellDisplayValue={getCellDisplayValue}
        onCellFocus={onCellFocus}
        onCellInput={onCellInput}
        onCellCommit={onCellCommit}
        onCellCancel={onCellCancel}
        onCellNavigate={onCellNavigate}
        onFillDown={onFillDownRequest}
        isCellInSelection={isCellInSelection}
        onCellPointerDown={onCellPointerDown}
        onCellPointerEnter={onCellPointerEnter}
        onCellPointerUp={onCellPointerUp}
      />
    </section>
  </div>

  {#if showFormulaGuideOverlay}
    <div
      class="formula-guide-backdrop"
      role="presentation"
      onclick={() => (showFormulaGuideOverlay = false)}
      onkeydown={(e) => e.key === "Escape" && (showFormulaGuideOverlay = false)}
    >
      <div
        class="formula-guide-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="formula-guide-title"
        tabindex="-1"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.key === "Escape" && (showFormulaGuideOverlay = false)}
      >
        <div class="formula-guide-header">
          <h2 id="formula-guide-title">Formula guide</h2>
          <button
            type="button"
            class="formula-guide-close"
            onclick={() => (showFormulaGuideOverlay = false)}
            aria-label="Close formula guide"
          >
            ×
          </button>
        </div>
        <div class="formula-guide-body">
          {#each FORMULA_SUGGESTIONS as formula}
            <section class="formula-guide-section" aria-labelledby="formula-guide-{formula.name}">
              <h3 id="formula-guide-{formula.name}" class="formula-guide-name mono">{formula.name}</h3>
              <p class="formula-guide-usage mono">{formula.signature}</p>
              <p class="formula-guide-desc">{formula.description}</p>
            </section>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  {#if toastMessage}
    <div class="table-toast" role="status" aria-live="polite">
      {toastMessage}
    </div>
  {/if}
</div>

<style>
  .table-page {
    --table-grid-border-width: 1px;
    --table-grid-border-color: rgba(255, 255, 255, 0.06);
    --table-header-height: 28px;
    --table-subheader-height: 34px;
    --table-row-height: 34px;
    --lock-rail-width: 3rem;

    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: system-ui, -apple-system, sans-serif;
    overflow: hidden;
  }

  .table-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .table-header h2 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #ff8866;
  }

  .context-pill {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #ccc;
    max-width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .context-pill.empty {
    opacity: 0.7;
    font-style: italic;
  }

  .context-pill.fixture {
    color: #8f8;
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
  }

  .table-split {
    flex: 1 1 0;
    min-height: 0;
    display: grid;
    grid-template-rows: minmax(0, 1fr) minmax(190px, 38%);
  }

  .formula-bar {
    flex-shrink: 0;
    display: grid;
    grid-template-columns: auto minmax(280px, 1fr) repeat(5, auto);
    gap: 0.4rem;
    align-items: center;
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.02);
  }

  .formula-cell-ref {
    min-width: 2.8rem;
    text-align: center;
    padding: 0.35rem 0.5rem;
    border-radius: 0.25rem;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.04);
    font-size: 0.78rem;
    color: #e7e7f3;
  }

  .formula-input-wrap {
    position: relative;
    min-width: 0;
  }

  .formula-suggestions {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin: 0.15rem 0 0;
    padding: 0.25rem 0;
    list-style: none;
    border-radius: 0.35rem;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: #252538;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    max-height: 12rem;
    overflow-y: auto;
    z-index: 100;
  }

  .formula-suggestion-item {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    padding: 0.4rem 0.6rem;
    cursor: pointer;
    font-size: 0.8rem;
  }

  .formula-suggestion-item:hover,
  .formula-suggestion-item.selected {
    background: rgba(255, 136, 102, 0.15);
    color: #ffd8cf;
  }

  .formula-suggestion-sig {
    color: #e7e7f3;
    font-weight: 500;
  }

  .formula-suggestion-desc {
    font-size: 0.72rem;
    color: #a0a0b0;
  }

  .formula-suggestion-item:hover .formula-suggestion-desc,
  .formula-suggestion-item.selected .formula-suggestion-desc {
    color: #c8c8d8;
  }

  .formula-input {
    height: 2rem;
    border-radius: 0.35rem;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.03);
    color: #e0e0e0;
    padding: 0 0.6rem;
    font-size: 0.82rem;
  }

  .formula-input:focus {
    outline: none;
    border-color: rgba(255, 136, 102, 0.55);
    box-shadow: 0 0 0 2px rgba(255, 136, 102, 0.2);
  }

  .formula-input[readonly] {
    opacity: 0.8;
    color: #bbbbc8;
  }

  .formula-btn {
    height: 2rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0.35rem;
    background: rgba(255, 255, 255, 0.05);
    color: #e0e0e0;
    font-size: 0.75rem;
    padding: 0 0.6rem;
    cursor: pointer;
  }

  .formula-btn:hover:enabled {
    background: rgba(255, 136, 102, 0.18);
    border-color: rgba(255, 136, 102, 0.45);
    color: #ffd8cf;
  }

  .formula-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .table-segment {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  .segment-toolbar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(255, 255, 255, 0.02);
  }

  .segment-label {
    margin: 0;
    font-size: 0.8rem;
    color: #a0a0b0;
  }

  .formula-guide-btn {
    margin-left: auto;
    padding: 0.3rem 0.6rem;
    font-size: 0.75rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0.35rem;
    background: rgba(255, 255, 255, 0.05);
    color: #e0e0e0;
    cursor: pointer;
  }

  .formula-guide-btn:hover {
    background: rgba(255, 136, 102, 0.18);
    border-color: rgba(255, 136, 102, 0.45);
    color: #ffd8cf;
  }

  .formula-guide-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
  }

  .formula-guide-overlay {
    width: 75%;
    height: 75%;
    min-width: 18rem;
    min-height: 12rem;
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: #252538;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    overflow: hidden;
  }

  .formula-guide-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .formula-guide-header h2 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #ff8866;
  }

  .formula-guide-close {
    width: 2rem;
    height: 2rem;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    line-height: 1;
    border: none;
    border-radius: 0.35rem;
    background: transparent;
    color: #a0a0b0;
    cursor: pointer;
  }

  .formula-guide-close:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #e0e0e0;
  }

  .formula-guide-body {
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem;
  }

  .formula-guide-section {
    margin-bottom: 1.25rem;
  }

  .formula-guide-section:last-child {
    margin-bottom: 0;
  }

  .formula-guide-name {
    margin: 0 0 0.35rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: #e7e7f3;
  }

  .formula-guide-usage {
    margin: 0 0 0.35rem;
    font-size: 0.82rem;
    color: #ff8866;
  }

  .formula-guide-desc {
    margin: 0;
    font-size: 0.8rem;
    color: #a0a0b0;
    line-height: 1.4;
  }

  .table-segment-top {
    min-height: 0;
    overflow: auto;
  }

  .table-segment-bottom {
    min-height: 0;
    overflow: auto;
  }

  .table-toast {
    position: fixed;
    bottom: 1.5rem;
    left: 50%;
    transform: translateX(-50%);
    padding: 0.6rem 1rem;
    border-radius: 0.35rem;
    background: #2d2d3d;
    color: #e0e0e0;
    font-size: 0.875rem;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    z-index: 100;
  }
</style>
