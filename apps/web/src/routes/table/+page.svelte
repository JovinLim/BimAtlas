<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import { page } from "$app/stores";
  import {
    TABLE_CHANNEL,
    TABLE_PROTOCOL_VERSION,
    type TableMessage,
  } from "$lib/table/protocol";
  import type { ProductMeta } from "$lib/search/protocol";
  import { TABLE_FIXTURE_PRODUCTS } from "$lib/table/fixtures";
  import { loadSettings } from "$lib/state/persistence";
  import {
    client,
    PROJECTS_QUERY,
    OPENED_SHEET_TEMPLATES_QUERY,
    SEARCH_SHEET_TEMPLATES_QUERY,
    SHEET_TEMPLATES_QUERY,
    SHEET_TEMPLATE_QUERY,
    CREATE_SHEET_TEMPLATE_MUTATION,
    UPDATE_SHEET_TEMPLATE_MUTATION,
    DELETE_SHEET_TEMPLATE_MUTATION,
  } from "$lib/api/client";
  import EntityGridDynamic from "$lib/table/EntityGridDynamic.svelte";
  import BottomSheet from "$lib/table/BottomSheet.svelte";
  import type { SheetEntry, SheetState } from "$lib/table/types";
  import {
    colToIndex,
    indexToCol,
    parseCellRef,
    type DefaultTopColumnKey,
    type SpreadsheetCellState,
    type SheetSnapshot,
    type SpreadsheetSnapshot,
    type TopTableColumn,
  } from "$lib/table/engine";
  import {
    evaluateFormula,
    extractEntityPath,
    getFormulaSuggestions,
    FORMULA_SUGGESTIONS,
    parseHeaderAliasFormula,
    resolveEntityPath,
  } from "$lib/table/formulas";
  import {
    buildMergedCsv,
    csvFilename,
    downloadCsv,
  } from "$lib/table/csv";

  const API_BASE = import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);
  /** Products from main window context, or fixture when ?fixture=1 */
  let products = $state<ProductMeta[]>([]);
  let useFixture = $state(false);

  const DEFAULT_TOP_COLUMNS: TopTableColumn[] = [
    {
      id: "col-global-id",
      col: "A",
      label: "Global ID",
      headerFormula: "",
      isDefault: true,
      deletable: false,
      editableCells: false,
      protected: true,
      defaultKey: "globalId",
    },
    {
      id: "col-ifc-class",
      col: "B",
      label: "IFC CLASS",
      headerFormula: "",
      isDefault: true,
      deletable: false,
      editableCells: false,
      protected: true,
      defaultKey: "ifcClass",
    },
    {
      id: "col-name",
      col: "C",
      label: "Name",
      headerFormula: "",
      isDefault: true,
      deletable: false,
      editableCells: true,
      protected: false,
      defaultKey: "name",
    },
    {
      id: "col-description",
      col: "D",
      label: "Description",
      headerFormula: "",
      isDefault: true,
      deletable: false,
      editableCells: true,
      protected: false,
      defaultKey: "description",
    },
    {
      id: "col-object-type",
      col: "E",
      label: "Object Type",
      headerFormula: "",
      isDefault: true,
      deletable: false,
      editableCells: true,
      protected: false,
      defaultKey: "objectType",
    },
    {
      id: "col-tag",
      col: "F",
      label: "Tag",
      headerFormula: "",
      isDefault: true,
      deletable: false,
      editableCells: true,
      protected: false,
      defaultKey: "tag",
    },
  ];

  /** Minimum column width in px. Enforced for both top grid and bottom sheet. */
  const MIN_COLUMN_WIDTH_PX = 48;

  /** Default column widths in px (A–F). Used when no user resize has been stored. */
  const DEFAULT_COLUMN_WIDTHS_PX: Record<string, number> = {
    A: 256,  /* globalId, 16rem */
    B: 160,  /* ifcClass, 10rem */
    C: 160,  /* name, 10rem */
    D: 224,  /* description, 14rem */
    E: 160,  /* objectType, 10rem */
    F: 160,  /* tag, 10rem */
  };
  const DEFAULT_WIDTH_PX = 192; /* custom columns, 12rem */

  /**
   * Single mapping for column widths (px), keyed by column letter.
   * Only this mapping is used; top grid updates it via resize, bottom sheet only reads it.
   */
  let columnWidths = $state<Record<string, number>>({ ...DEFAULT_COLUMN_WIDTHS_PX });

  /** Read from the mapping (with fallback and min clamp). Both tables use this so they never differ. */
  function getColumnWidthPx(col: string): number {
    const w = columnWidths[col] ?? DEFAULT_COLUMN_WIDTHS_PX[col] ?? DEFAULT_WIDTH_PX;
    return Math.max(MIN_COLUMN_WIDTH_PX, w);
  }

  function setColumnWidth(col: string, widthPx: number) {
    const clamped = Math.max(MIN_COLUMN_WIDTH_PX, Math.round(widthPx));
    columnWidths = { ...columnWidths, [col]: clamped };
  }

  let topColumns = $state<TopTableColumn[]>([...DEFAULT_TOP_COLUMNS]);
  let headerDrafts = $state<Record<string, string>>({});
  type SortKey = DefaultTopColumnKey;
  /** Sort by column key; default ascending (A–Z). */
  let sortBy = $state<SortKey>("name");
  let sortDir = $state<"asc" | "desc">("asc");
  /** Row lock state: locked rows are read-only for editable cells. */
  let lockedIds = $state<Set<string>>(new Set());
  /** Multi-sheet: bottom sheet state per tab. */
  const _initialSheetId = crypto.randomUUID();
  let sheets = $state<SheetState[]>([
    {
      id: _initialSheetId,
      name: "Sheet 1",
      entries: [],
      formulas: {},
      lockedIds: new Set<string>(),
    },
  ]);
  let activeSheetId = $state<string>(_initialSheetId);
  const activeSheet = $derived(sheets.find((s) => s.id === activeSheetId) ?? sheets[0]!);

  function updateActiveSheet(updates: {
    entries?: SheetEntry[];
    formulas?: Record<string, string>;
    lockedIds?: Set<string>;
  }) {
    sheets = sheets.map((s) =>
      s.id === activeSheetId
        ? {
            ...s,
            ...(updates.entries !== undefined && { entries: updates.entries }),
            ...(updates.formulas !== undefined && { formulas: updates.formulas }),
            ...(updates.lockedIds !== undefined && { lockedIds: updates.lockedIds }),
          }
        : s,
    );
  }

  function addSheet() {
    pushHistory();
    const id = crypto.randomUUID();
    const nextIndex = sheets.length + 1;
    sheets = [
      ...sheets,
      {
        id,
        name: `Sheet ${nextIndex}`,
        entries: [],
        formulas: {},
        lockedIds: new Set<string>(),
      },
    ];
    activeSheetId = id;
  }

  function setActiveSheet(id: string) {
    if (sheets.some((s) => s.id === id)) activeSheetId = id;
  }

  let editingSheetId = $state<string | null>(null);
  let editingSheetName = $state("");
  let editingSheetInputRef = $state<HTMLInputElement | null>(null);
  let closeSheetConfirmDialog = $state<SheetState | null>(null);
  let sheetTabContextMenu = $state<{ x: number; y: number; sheet: SheetState } | null>(null);

  function requestCloseSheet(sheet: SheetState, e?: MouseEvent) {
    e?.stopPropagation();
    if (sheets.length <= 1) return;
    if (sheet.templateId) {
      performCloseSheet(sheet);
    } else {
      closeSheetConfirmDialog = sheet;
    }
  }

  async function performCloseSheet(sheet: SheetState) {
    if (sheet.templateId && projectId) {
      try {
        await client
          .mutation(UPDATE_SHEET_TEMPLATE_MUTATION, {
            id: sheet.templateId,
            open: false,
          })
          .toPromise();
      } catch (err) {
        console.error("Failed to update template open state:", err);
      }
    }
    const next = sheets.filter((s) => s.id !== sheet.id);
    const wasActive = activeSheetId === sheet.id;
    sheets = next;
    if (wasActive && next.length > 0) activeSheetId = next[0]!.id;
    pushHistory();
  }

  async function performDeleteSheet(sheet: SheetState) {
    if (sheet.templateId && projectId) {
      try {
        await client
          .mutation(DELETE_SHEET_TEMPLATE_MUTATION, { id: sheet.templateId })
          .toPromise();
      } catch (err) {
        console.error("Failed to delete sheet template:", err);
        showToast("Failed to delete sheet");
        return;
      }
    }
    const next = sheets.filter((s) => s.id !== sheet.id);
    const wasActive = activeSheetId === sheet.id;
    sheets = next;
    if (wasActive && next.length > 0) activeSheetId = next[0]!.id;
    pushHistory();
  }

  function handleCloseSheetCancel() {
    closeSheetConfirmDialog = null;
  }

  async function handleCloseSheetSaveAndClose() {
    const sheet = closeSheetConfirmDialog;
    if (!sheet || !projectId) {
      closeSheetConfirmDialog = null;
      return;
    }
    const name = prompt("Template name (required):", sheet.name);
    if (!name || !name.trim()) {
      showToast("Template name is required");
      return;
    }
    try {
      const result = await client
        .mutation(CREATE_SHEET_TEMPLATE_MUTATION, {
          projectId,
          name: name.trim(),
          sheet: serializeSheetForStorage(sheet, name.trim()),
        })
        .toPromise();
      if (result.data?.createSheetTemplate) {
        closeSheetConfirmDialog = null;
        await performCloseSheet(sheet);
      }
    } catch (err) {
      console.error("Failed to save template:", err);
      alert("Failed to save template. See console for details.");
    }
  }

  function startEditingSheet(sheet: SheetState) {
    pushHistory();
    editingSheetId = sheet.id;
    editingSheetName = sheet.name;
    tick().then(() => editingSheetInputRef?.focus());
  }

  function commitSheetRename() {
    if (editingSheetId == null) return;
    const name = editingSheetName.trim() || "Sheet";
    sheets = sheets.map((s) =>
      s.id === editingSheetId ? { ...s, name } : s,
    );
    editingSheetId = null;
    editingSheetName = "";
  }

  let topEdits = $state<Record<string, string>>({});
  let topFormulas = $state<Record<string, string>>({});
  let draftValues = $state<Record<string, string>>({});
  let activeCell = $state<SpreadsheetCellState | null>(null);
  let activeHeaderColumnId = $state<string | null>(null);
  let formulaInput = $state("");
  let formulaComposeSourceRef = $state<string | null>(null);
  let formulaSuggestionIndex = $state(0);
  let showFormulaGuideOverlay = $state(false);
  let showCellContentOverlay = $state(false);
  let templateSearchQuery = $state("");
  let templateResults = $state<{ id: string; name: string }[]>([]);
  let loadingTemplates = $state(false);
  let lastOpenedLoadProjectId = $state<string | null>(null);

  type StoredSheetCell = { value?: string; formula?: string };
  type StoredSheetV2 = {
    v: 2;
    sheet: {
      name?: string;
      cols?: string[];
      rowCount: number;
      cells: Record<string, StoredSheetCell>;
      lockedRows?: number[];
    };
    entity?: {
      topEdits?: Record<string, string>;
      topFormulas?: Record<string, string>;
      topColumns?: TopTableColumn[];
      lockedEntityIds?: string[];
    };
  };
  type LegacyStoredSheet = {
    entries?: SheetEntry[];
    formulas?: Record<string, string>;
    lockedIds?: string[];
  };

  type DeserializedStoredTemplate = {
    sheet: SheetState;
    entity?: {
      topEdits: Record<string, string>;
      topFormulas: Record<string, string>;
      topColumns: TopTableColumn[];
      lockedEntityIds: Set<string>;
    };
  };

  function createEmptySheetEntry(): SheetEntry {
    return {
      id: crypto.randomUUID(),
      entityGlobalId: null,
      category: "",
      label: "",
      value: "",
      notes: "",
      tag: "",
    };
  }

  function isStoredSheetV2(input: unknown): input is StoredSheetV2 {
    if (!input || typeof input !== "object") return false;
    const maybe = input as { v?: unknown; sheet?: { cells?: unknown } };
    return maybe.v === 2 && typeof maybe.sheet?.cells === "object" && maybe.sheet?.cells != null;
  }

  function mapSheetColToField(col: string): keyof Omit<SheetEntry, "id"> | null {
    if (col === "A") return "entityGlobalId";
    if (col === "B") return "category";
    if (col === "C") return "label";
    if (col === "D") return "value";
    if (col === "E") return "notes";
    if (col === "F") return "tag";
    return null;
  }

  function toStoredSheetRef(ref: string, rowCount: number): string | null {
    const parsed = parseCellRef(ref);
    if (!parsed) return null;
    const start = sheetRowStart();
    if (parsed.row >= start) return `${parsed.col}${parsed.row - start + 1}`;
    if (parsed.row >= 1 && parsed.row <= rowCount) return ref;
    return null;
  }

  function localSheetRefToAbsolute(localRef: string): string | null {
    const parsed = parseCellRef(localRef);
    if (!parsed) return null;
    const start = sheetRowStart();
    return `${parsed.col}${start + parsed.row - 1}`;
  }

  function serializeSheetForStorage(sheet: SheetState, name?: string): StoredSheetV2 {
    const cells: Record<string, StoredSheetCell> = {};
    const rowCount = sheet.entries.length;
    for (let idx = 0; idx < rowCount; idx += 1) {
      const row = idx + 1;
      const entry = sheet.entries[idx]!;
      for (const col of SHEET_COLUMNS) {
        const field = mapSheetColToField(col);
        if (!field) continue;
        const raw = entry[field];
        const value = raw == null ? "" : String(raw);
        if (value === "") continue;
        cells[`${col}${row}`] = { ...(cells[`${col}${row}`] ?? {}), value };
      }
    }
    for (const [ref, formula] of Object.entries(sheet.formulas)) {
      const storedRef = toStoredSheetRef(ref, rowCount);
      if (!storedRef || !formula) continue;
      cells[storedRef] = { ...(cells[storedRef] ?? {}), formula };
    }
    const lockedRows = sheet.entries
      .map((entry, idx) => (sheet.lockedIds.has(entry.id) ? idx + 1 : null))
      .filter((row): row is number => row != null);
    return {
      v: 2,
      sheet: {
        name: name ?? sheet.name,
        cols: [...SHEET_COLUMNS],
        rowCount,
        cells,
        lockedRows,
      },
      entity: {
        topEdits: { ...topEdits },
        topFormulas: { ...topFormulas },
        topColumns: topColumns.map((c) => ({ ...c })),
        lockedEntityIds: Array.from(lockedIds),
      },
    };
  }

  function deserializeStoredSheet(
    data: unknown,
    fallbackName: string,
    templateId: string | null = null,
  ): DeserializedStoredTemplate {
    if (isStoredSheetV2(data)) {
      const v2 = data;
      const v2Sheet = v2.sheet;
      const parsedRows = Object.keys(v2Sheet.cells)
        .map((ref) => parseCellRef(ref)?.row ?? 0)
        .filter((row) => row > 0);
      const maxCellRow = parsedRows.length > 0 ? Math.max(...parsedRows) : 0;
      const maxLockedRow = v2Sheet.lockedRows && v2Sheet.lockedRows.length > 0
        ? Math.max(...v2Sheet.lockedRows)
        : 0;
      const rowCount = Math.max(v2Sheet.rowCount ?? 0, maxCellRow, maxLockedRow);
      const entries = Array.from({ length: rowCount }, () => createEmptySheetEntry());
      const formulas: Record<string, string> = {};
      for (const [localRef, cell] of Object.entries(v2Sheet.cells)) {
        const parsed = parseCellRef(localRef);
        if (!parsed || parsed.row < 1 || parsed.row > entries.length) continue;
        const field = mapSheetColToField(parsed.col);
        if (!field) continue;
        const entry = entries[parsed.row - 1]!;
        if (cell.value !== undefined) {
          const nextValue = String(cell.value);
          if (field === "entityGlobalId") {
            entry.entityGlobalId = nextValue.trim() === "" ? null : nextValue;
          } else {
            entry[field] = nextValue;
          }
        }
        if (cell.formula) {
          const absoluteRef = localSheetRefToAbsolute(localRef);
          if (absoluteRef) formulas[absoluteRef] = cell.formula;
        }
      }
      const lockedIds = new Set<string>();
      for (const localRow of v2Sheet.lockedRows ?? []) {
        const entry = entries[localRow - 1];
        if (entry) lockedIds.add(entry.id);
      }
      return {
        sheet: {
          id: templateId ?? crypto.randomUUID(),
          name: v2Sheet.name ?? fallbackName,
          entries,
          formulas,
          lockedIds,
          templateId,
        },
        entity: v2.entity
          ? {
              topEdits: { ...(v2.entity.topEdits ?? {}) },
              topFormulas: { ...(v2.entity.topFormulas ?? {}) },
              topColumns:
                v2.entity.topColumns?.map((c: TopTableColumn) => ({ ...c })) ??
                [...DEFAULT_TOP_COLUMNS],
              lockedEntityIds: new Set(v2.entity.lockedEntityIds ?? []),
            }
          : undefined,
      };
    }

    const legacy = (data ?? {}) as LegacyStoredSheet;
    const entries = (legacy.entries ?? []).map((e) => ({
      ...e,
      id: e.id ?? crypto.randomUUID(),
    }));
    const formulas = legacy.formulas ?? {};
    const lockedIds = new Set<string>(legacy.lockedIds ?? []);
    return {
      sheet: {
        id: templateId ?? crypto.randomUUID(),
        name: fallbackName,
        entries,
        formulas,
        lockedIds,
        templateId,
      },
    };
  }

  const projectIdFromUrl = $derived($page.url.searchParams.get("projectId"));
  const mayNeedSheetLoad = $derived(
    (projectId != null || projectIdFromUrl != null) && !useFixture,
  );
  const sheetsReady = $derived(
    useFixture ||
      !mayNeedSheetLoad ||
      (projectId != null && lastOpenedLoadProjectId === projectId),
  );

  async function loadOpenedTemplates() {
    if (!projectId || useFixture || lastOpenedLoadProjectId === projectId) return;
    try {
      const openedResult = await client
        .query(OPENED_SHEET_TEMPLATES_QUERY, { projectId })
        .toPromise();
      const list = openedResult.data?.openedSheetTemplates ?? [];
      lastOpenedLoadProjectId = projectId;
      if (list.length === 0) {
        const allResult = await client
          .query(SHEET_TEMPLATES_QUERY, { projectId })
          .toPromise();
        const allTemplates = allResult.data?.sheetTemplates ?? [];
        if (allTemplates.length > 0) return;
        const defaultState: SheetState = {
          id: crypto.randomUUID(),
          name: "Sheet 1",
          entries: [],
          formulas: {},
          lockedIds: new Set<string>(),
          templateId: null,
        };
        const createResult = await client
          .mutation(CREATE_SHEET_TEMPLATE_MUTATION, {
            projectId,
            name: "Sheet 1",
            sheet: serializeSheetForStorage(defaultState, "Sheet 1"),
            open: true,
          })
          .toPromise();
        const created = createResult.data?.createSheetTemplate;
        if (created) {
          sheets = [
            {
              id: created.id,
              name: created.name,
              entries: [],
              formulas: {},
              lockedIds: new Set<string>(),
              templateId: created.id,
            },
          ];
          activeSheetId = created.id;
        }
        return;
      }
      const parsed: DeserializedStoredTemplate[] = list.map(
        (t: { id: string; name: string; sheet: unknown }) =>
          deserializeStoredSheet(t.sheet, t.name, t.id),
      );
      const newSheets: SheetState[] = parsed.map((p: DeserializedStoredTemplate) => p.sheet);
      sheets = newSheets;
      activeSheetId = newSheets[0]!.id;
      const firstEntity = parsed.find((p: DeserializedStoredTemplate) => p.entity)?.entity;
      if (firstEntity) {
        topEdits = firstEntity.topEdits;
        topFormulas = firstEntity.topFormulas;
        topColumns = firstEntity.topColumns;
        lockedIds = firstEntity.lockedEntityIds;
        fetchEntityAttributesIfNeeded(topColumns);
      }
    } catch (err) {
      console.error("Failed to load opened templates:", err);
    }
  }

  async function loadTemplateSearch() {
    if (!projectId) return;
    loadingTemplates = true;
    try {
      const query = templateSearchQuery.trim();
      const result = query
        ? await client
            .query(SEARCH_SHEET_TEMPLATES_QUERY, { query, projectId })
            .toPromise()
        : await client
            .query(SHEET_TEMPLATES_QUERY, { projectId })
            .toPromise();
      const list = query
        ? (result.data?.searchSheetTemplates ?? [])
        : (result.data?.sheetTemplates ?? []);
      templateResults = list.map((t: { id: string; name: string }) => ({ id: t.id, name: t.name }));
    } catch (err) {
      console.error("Failed to search templates:", err);
      templateResults = [];
    } finally {
      loadingTemplates = false;
    }
  }

  $effect(() => {
    const pid = projectId;
    if (!pid) return;
    void loadOpenedTemplates();
  });

  $effect(() => {
    const q = templateSearchQuery;
    const pid = projectId;
    if (!pid) return;
    const t = setTimeout(() => {
      void loadTemplateSearch();
    }, 200);
    return () => clearTimeout(t);
  });

  async function handleSaveTemplate() {
    if (!projectId) return;
    const payload = serializeSheetForStorage(activeSheet);
    try {
      if (activeSheet.templateId) {
        const result = await client
          .mutation(UPDATE_SHEET_TEMPLATE_MUTATION, {
            id: activeSheet.templateId,
            name: activeSheet.name,
            sheet: payload,
          })
          .toPromise();
        if (result.data?.updateSheetTemplate) {
          showToast("Template updated");
        }
      } else {
        const name = prompt("Template name (required):", activeSheet.name);
        if (!name || !name.trim()) {
          showToast("Template name is required");
          return;
        }
        const createPayload = serializeSheetForStorage(activeSheet, name.trim());
        const result = await client
          .mutation(CREATE_SHEET_TEMPLATE_MUTATION, {
            projectId,
            name: name.trim(),
            sheet: createPayload,
          })
          .toPromise();
        const created = result.data?.createSheetTemplate;
        if (created) {
          sheets = sheets.map((s) =>
            s.id === activeSheetId
              ? { ...s, id: created.id, name: created.name, templateId: created.id }
              : s,
          );
          activeSheetId = created.id;
          showToast("Template saved");
        }
      }
      templateSearchQuery = "";
      loadTemplateSearch();
    } catch (err) {
      console.error("Failed to save template:", err);
      alert("Failed to save template. See console for details.");
    }
  }

  async function handleLoadTemplate(template: { id: string; name: string }) {
    try {
      const result = await client
        .query(SHEET_TEMPLATE_QUERY, { id: template.id })
        .toPromise();
      const data = result.data?.sheetTemplate;
      if (!data?.sheet) return;
      const loaded = deserializeStoredSheet(data.sheet, template.name, template.id);
      pushHistory();
      updateActiveSheet({
        entries: loaded.sheet.entries,
        formulas: loaded.sheet.formulas,
        lockedIds: loaded.sheet.lockedIds,
      });
      if (loaded.entity) {
        topEdits = loaded.entity.topEdits;
        topFormulas = loaded.entity.topFormulas;
        topColumns = loaded.entity.topColumns;
        lockedIds = loaded.entity.lockedEntityIds;
        fetchEntityAttributesIfNeeded(topColumns);
      }
    } catch (err) {
      console.error("Failed to load template:", err);
      alert("Failed to load template. See console for details.");
    }
  }

  $effect(() => {
    const menu = sheetTabContextMenu;
    if (!menu) return;
    const el = document.querySelector("[data-sheet-tab-context-menu]");
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (el && !el.contains(target)) sheetTabContextMenu = null;
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") sheetTabContextMenu = null;
    };
    document.addEventListener("mousedown", onMouseDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("mousedown", onMouseDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  });

  $effect(() => {
    const visible = showCellContentOverlay || showFormulaGuideOverlay;
    if (!visible) return;
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        showCellContentOverlay = false;
        showFormulaGuideOverlay = false;
      }
    };
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  });

  const formulaPrefix = $derived.by(() => {
    const t = formulaInput.trim();
    if (!t.startsWith("=")) return "";
    const body = t.slice(1);
    const match = body.match(/^[A-Za-z]*/);
    return match ? match[0] : "";
  });
  const formulaSuggestionsList = $derived(
    getFormulaSuggestions(formulaPrefix, {
      allowEntityFormulas: activeCell?.surface !== "sheet" || activeHeaderColumnId != null,
    }),
  );
  const showFormulaDropdown = $derived(
    formulaInput.trim().startsWith("=") &&
      /^[A-Za-z]*$/.test(formulaInput.trim().slice(1)) &&
      formulaSuggestionsList.length > 0 &&
      ((activeCell != null && activeCell.editable) || activeHeaderColumnId != null),
  );
  /** When sync enabled: globalId from viewer selection (highlights row). */
  let viewerSelectedGlobalId = $state<string | null>(null);
  /** Toggle: sync table selection with 3D viewer (two-way). */
  let syncWithViewer = $state(false);
  /** GlobalId of the row to show as selected (from table focus or, when sync enabled, from viewer). */
  const selectedRowGlobalId = $derived.by(() => {
    if (activeCell && activeCell.surface === "entity") {
      const product = getTopProductByRow(activeCell.row);
      return product?.globalId ?? null;
    }
    if (syncWithViewer) return viewerSelectedGlobalId;
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
  let lastReceivedContextDataKey: string | null = null;
  let lastSentSelectionToViewer: string | null = null;
  let segmentTopRef = $state<HTMLElement | null>(null);
  function getNavCols(): string[] {
    return topColumns.map((column) => column.col);
  }

  /** Sheet area always uses columns A–F. */
  const SHEET_COLUMNS = ["A", "B", "C", "D", "E", "F"];

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

  let toastMessage = $state<string | null>(null);

  $effect(() => {
    if (!syncWithViewer) return;
    const id = viewerSelectedGlobalId;
    if (!id || !segmentTopRef) return;
    tick().then(() => {
      const row = segmentTopRef?.querySelector(
        `tr.entity-row[data-global-id="${id}"]`,
      );
      row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  });
  let toastTimeoutId = $state<ReturnType<typeof setTimeout> | null>(null);
  let tableSplitRef = $state<HTMLElement | null>(null);

  const TABLE_TOP_HEIGHT_KEY = "bimatlas-table-top-height";
  const MIN_TOP_PX = 120;
  const MIN_BOTTOM_PX = 190;

  /** Top segment height in px; null = use default grid. Persisted to localStorage. */
  let topSegmentHeightPx = $state<number | null>(null);
  let isResizingSplit = $state(false);

  function loadTopSegmentHeight(): number | null {
    if (typeof window === "undefined") return null;
    try {
      const v = localStorage.getItem(TABLE_TOP_HEIGHT_KEY);
      if (v == null) return null;
      const n = Number(v);
      return Number.isFinite(n) && n >= MIN_TOP_PX ? n : null;
    } catch {
      return null;
    }
  }

  function saveTopSegmentHeight(px: number) {
    if (typeof window === "undefined") return;
    try {
      localStorage.setItem(TABLE_TOP_HEIGHT_KEY, String(px));
    } catch {
      /* ignore */
    }
  }

  function startResizeSplit(e: MouseEvent) {
    e.preventDefault();
    if (topSegmentHeightPx == null && segmentTopRef) {
      topSegmentHeightPx = segmentTopRef.getBoundingClientRect().height;
    }
    isResizingSplit = true;
  }

  function onResizeSplitMove(e: MouseEvent) {
    if (!isResizingSplit || !tableSplitRef) return;
    const rect = tableSplitRef.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const maxTop = rect.height - MIN_BOTTOM_PX;
    const clamped = Math.max(MIN_TOP_PX, Math.min(maxTop, y));
    topSegmentHeightPx = clamped;
  }

  function endResizeSplit() {
    if (!isResizingSplit) return;
    if (topSegmentHeightPx != null) saveTopSegmentHeight(topSegmentHeightPx);
    isResizingSplit = false;
  }

  function showToast(message: string) {
    if (toastTimeoutId != null) clearTimeout(toastTimeoutId);
    toastMessage = message;
    toastTimeoutId = setTimeout(() => {
      toastMessage = null;
      toastTimeoutId = null;
    }, 3000);
  }

  function syncUrlWithContext() {
    const params = new URLSearchParams($page.url.searchParams);
    if (branchId != null) params.set("branchId", String(branchId));
    else params.delete("branchId");
    if (projectId != null) params.set("projectId", String(projectId));
    else params.delete("projectId");
    if (revision != null) params.set("revision", String(revision));
    else params.delete("revision");
    const nextQuery = params.toString();
    const currentQuery = $page.url.searchParams.toString();
    if (nextQuery === currentQuery) return;
    window.history.replaceState(null, "", `${$page.url.pathname}?${nextQuery}`);
  }

  function contextDataKey(
    msg: Extract<TableMessage, { type: "context" }>,
  ): string {
    return JSON.stringify({
      branchId: msg.branchId,
      projectId: msg.projectId,
      branchName: msg.branchName ?? null,
      projectName: msg.projectName ?? null,
      revision: msg.revision,
      version: msg.version,
      products: (msg.products ?? []).map((p) => p.globalId),
    });
  }

  function exportCsv() {
    const headers = topColumns.map((c) => c.label);
    const entityRows: string[][] = [];
    for (let i = 0; i < displayProducts.length; i += 1) {
      const product = displayProducts[i];
      const row = 2 + i;
      const rowValues: string[] = [];
      for (const col of topColumns) {
        const ref = `${col.col}${row}`;
        const v = getCommittedValue(ref);
        rowValues.push(
          v !== "" ? v : product ? getTopFallback(ref, product) : "",
        );
      }
      entityRows.push(rowValues);
    }
    const sheetRows = activeSheet.entries.map((e) => ({
      entityGlobalId: e.entityGlobalId,
      category: e.category ?? "",
      label: e.label ?? "",
      value: e.value ?? "",
      notes: e.notes ?? "",
      tag: e.tag ?? "",
    }));
    const csvText = buildMergedCsv({
      headers,
      entityRows,
      sheetRows,
    });
    const filename = csvFilename(revision);
    downloadCsv(csvText, filename);
    showToast("CSV exported");
  }

  function handleContextMessage(msg: Extract<TableMessage, { type: "context" }>) {
    if (msg.version !== TABLE_PROTOCOL_VERSION || useFixture) return;

    hasChannelContext = true;

    const nextContextDataKey = contextDataKey(msg);
    const contextChanged = nextContextDataKey !== lastReceivedContextDataKey;
    if (contextChanged) {
      branchId = msg.branchId;
      projectId = msg.projectId;
      branchName = msg.branchName ?? null;
      projectName = msg.projectName ?? null;
      revision = msg.revision;
      products = msg.products ?? [];
      lockedIds = new Set(products.map((p) => p.globalId));
      fetchEntityAttributesIfNeeded(topColumns);
      syncUrlWithContext();
      lastReceivedContextDataKey = nextContextDataKey;
    }

    if (contextRetryInterval != null) {
      clearInterval(contextRetryInterval);
      contextRetryInterval = null;
    }

  }

  type TableMessageHandlers = {
    [K in TableMessage["type"]]?: (message: Extract<TableMessage, { type: K }>) => void;
  };

  const tableMessageHandlers: TableMessageHandlers = {
    context: handleContextMessage,
    "selection-sync": (message) => {
      if (!syncWithViewer) return;
      viewerSelectedGlobalId = message.globalId;
      if (message.globalId == null) {
        activeCell = null;
        activeHeaderColumnId = null;
        selectionRange = null;
        formulaComposeSourceRef = null;
        formulaInput = "";
      }
    },
  };

  function handleIncomingMessage(e: MessageEvent<TableMessage>) {
    const msg = e.data;
    if (!msg || typeof msg.type !== "string") return;
    const handler = tableMessageHandlers[msg.type as TableMessage["type"]] as
      | ((message: TableMessage) => void)
      | undefined;
    handler?.(msg);
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies TableMessage);
  }

  function setSyncWithViewer(enabled: boolean) {
    syncWithViewer = enabled;
    if (!enabled) viewerSelectedGlobalId = null;
    channel?.postMessage({ type: "sync-mode", enabled } satisfies TableMessage);
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
      activeSheet.entries.every((entry) => activeSheet.lockedIds.has(entry.id)),
  );

  function toggleLockAll() {
    if (products.length === 0 && activeSheet.entries.length === 0) return;
    pushHistory();
    if (allEntitiesLocked) {
      lockedIds = new Set();
      updateActiveSheet({ lockedIds: new Set() });
    } else {
      lockedIds = new Set(products.map((p) => p.globalId));
      updateActiveSheet({
        lockedIds: new Set(activeSheet.entries.map((entry) => entry.id)),
      });
    }
  }

  function toggleSheetEntryLock(entryId: string) {
    pushHistory();
    const next = new Set(activeSheet.lockedIds);
    if (next.has(entryId)) {
      next.delete(entryId);
    } else {
      next.add(entryId);
    }
    updateActiveSheet({ lockedIds: next });
  }

  function snapshot(): SpreadsheetSnapshot {
    return {
      topEdits: { ...topEdits },
      topFormulas: { ...topFormulas },
      topColumns: topColumns.map((column) => ({ ...column })),
      sheets: sheets.map((s) => ({
        id: s.id,
        name: s.name,
        entries: s.entries.map((e) => ({ ...e })),
        formulas: { ...s.formulas },
        lockedIds: Array.from(s.lockedIds),
        templateId: s.templateId ?? undefined,
      })),
      activeSheetId,
      lockedIds: Array.from(lockedIds),
    };
  }

  function applySnapshot(value: SpreadsheetSnapshot) {
    topEdits = { ...value.topEdits };
    topFormulas = { ...value.topFormulas };
    topColumns = value.topColumns?.map((column) => ({ ...column })) ?? [...DEFAULT_TOP_COLUMNS];
    headerDrafts = {};
    const legacy = value as SpreadsheetSnapshot & {
      sheetEntries?: SheetEntry[];
      sheetFormulas?: Record<string, string>;
      sheetLockedIds?: string[];
    };
    if (legacy.sheetEntries != null && !value.sheets?.length) {
      const id = activeSheetId || crypto.randomUUID();
      sheets = [
        {
          id,
          name: "Sheet 1",
          entries: legacy.sheetEntries.map((e) => ({ ...e })),
          formulas: { ...(legacy.sheetFormulas ?? {}) },
          lockedIds: new Set(legacy.sheetLockedIds ?? []),
        },
      ];
      activeSheetId = id;
    } else if (value.sheets?.length) {
      sheets = value.sheets.map((s) => ({
        id: s.id,
        name: s.name,
        entries: s.entries.map((e) => ({ ...e })),
        formulas: { ...s.formulas },
        lockedIds: new Set(s.lockedIds ?? []),
        templateId: (s as { templateId?: string }).templateId ?? null,
      }));
      activeSheetId = value.activeSheetId ?? value.sheets[0]!.id;
    }
    lockedIds = new Set(value.lockedIds);
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

  const displayProducts = $derived.by(() => {
    const key = sortBy;
    const dir = sortDir;
    return [...products].sort((a, b) => {
      const va = (a[key] ?? "") as string;
      const vb = (b[key] ?? "") as string;
      const cmp = va.localeCompare(vb, undefined, { sensitivity: "base" });
      return dir === "asc" ? cmp : -cmp;
    });
  });

  function sheetRowStart(): number {
    return products.length + 2;
  }

  function getTopProductByRow(row: number): ProductMeta | null {
    const index = row - 2;
    if (index < 0 || index >= displayProducts.length) return null;
    return displayProducts[index] ?? null;
  }

  function getSheetEntryByRow(row: number): SheetEntry | null {
    const index = row - sheetRowStart();
    if (index < 0 || index >= activeSheet.entries.length) return null;
    return activeSheet.entries[index] ?? null;
  }

  function isSheetRowLocked(row: number): boolean {
    const entry = getSheetEntryByRow(row);
    if (!entry) return false;
    return activeSheet.lockedIds.has(entry.id);
  }

  function getTopColumnByCol(col: string): TopTableColumn | null {
    return topColumns.find((column) => column.col === col) ?? null;
  }

  function resolveCellByRef(ref: string): SpreadsheetCellState | null {
    const parsed = parseCellRef(ref);
    if (!parsed) return null;
    const navCols = getNavCols();
    if (!navCols.includes(parsed.col) && !SHEET_COLUMNS.includes(parsed.col)) {
      return null;
    }

    const topProduct = getTopProductByRow(parsed.row);
    if (topProduct) {
      const column = getTopColumnByCol(parsed.col);
      if (!column) return null;
      const editable = !lockedIds.has(topProduct.globalId) && column.editableCells;
      const isProtected = column.protected;
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
      const sheetField = getSheetField(parsed.col);
      if (!sheetField) return null;
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

  function toDisplayString(value: unknown): string {
    if (value == null) return "";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    return JSON.stringify(value);
  }

  function normalizeFormulaValue(formula: string): string {
    const trimmed = formula.trim();
    if (trimmed === "") return "";
    return trimmed.startsWith("=") ? trimmed : `=${trimmed}`;
  }

  function getTopDefaultValue(column: TopTableColumn, product: ProductMeta): string {
    if (column.defaultKey === "globalId") return product.globalId ?? "";
    if (column.defaultKey === "ifcClass") return product.ifcClass ?? "";
    if (column.defaultKey === "name") return product.name ?? "";
    if (column.defaultKey === "description") return product.description ?? "";
    if (column.defaultKey === "objectType") return product.objectType ?? "";
    if (column.defaultKey === "tag") return product.tag ?? "";
    return "";
  }

  function getTopFallback(ref: string, product: ProductMeta): string {
    const parsed = parseCellRef(ref);
    if (!parsed) return "";
    const column = getTopColumnByCol(parsed.col);
    if (!column) return "";
    if (column.defaultKey) return getTopDefaultValue(column, product);
    if (!column.headerFormula.trim()) return "";

    // ENTITY paths are resolved against product.attributes (the row's entity JSON from the API).
    // So =ENTITY.PropertySets means product.attributes.PropertySets; no need for ENTITY.attributes.X.
    const normalizedFormula = normalizeFormulaValue(column.headerFormula);
    const entityPath = extractEntityPath(normalizedFormula);
    if (entityPath) {
      const attrs = (product.attributes as Record<string, unknown> | null | undefined) ?? null;
      const resolved = resolveEntityPath(attrs, entityPath);
      if (attrs === null && resolved === null) return "—";
      return toDisplayString(resolved);
    }

    const result = evaluateFormula(normalizedFormula, resolveValueForFormula);
    return result.ok ? result.value : "";
  }

  function deriveLabelFromFormula(formula: string): string {
    const entityPath = extractEntityPath(normalizeFormulaValue(formula));
    if (entityPath) {
      const parts = entityPath.split(".").filter(Boolean);
      return parts[parts.length - 1] ?? "Custom";
    }
    const compact = formula.replace(/^=/, "").trim();
    if (compact.length === 0) return "Custom";
    return compact.length > 20 ? `${compact.slice(0, 20)}…` : compact;
  }

  function parseHeaderFormulaInput(input: string): {
    label: string;
    formula: string;
  } {
    const alias = parseHeaderAliasFormula(input);
    if (alias) {
      return {
        label: alias.displayText || "Custom",
        formula: normalizeFormulaValue(alias.formula),
      };
    }
    if (input.trim() === "") {
      return {
        label: "Custom",
        formula: "",
      };
    }
    if (!input.trim().startsWith("=")) {
      return {
        label: input.trim(),
        formula: "",
      };
    }
    const normalized = normalizeFormulaValue(input);
    if (normalized.trim() === "=") {
      return {
        label: "Custom",
        formula: "",
      };
    }
    return {
      label: deriveLabelFromFormula(normalized),
      formula: normalized,
    };
  }

  let headerFormulaFocusedColumnId = $state<string | null>(null);

  function getHeaderFormulaInput(columnId: string): string {
    const draft = headerDrafts[columnId];
    if (draft !== undefined) return draft;
    const column = topColumns.find((c) => c.id === columnId);
    if (!column) return "";
    if (column.headerFormula.trim() === "") return "";
    if (headerFormulaFocusedColumnId !== columnId) return column.label;
    return `[${column.label}](${column.headerFormula})`;
  }

  function onHeaderFormulaInput(columnId: string, value: string) {
    headerDrafts = { ...headerDrafts, [columnId]: value };
  }

  function onHeaderFormulaCancel(columnId: string) {
    if (headerDrafts[columnId] === undefined) return;
    const next = { ...headerDrafts };
    delete next[columnId];
    headerDrafts = next;
  }

  function clearColumnRefs(columnCol: string) {
    const nextTopEdits = { ...topEdits };
    const nextTopFormulas = { ...topFormulas };
    const nextDraftValues = { ...draftValues };
    for (const ref of Object.keys(nextTopEdits)) {
      if (parseCellRef(ref)?.col === columnCol) delete nextTopEdits[ref];
    }
    for (const ref of Object.keys(nextTopFormulas)) {
      if (parseCellRef(ref)?.col === columnCol) delete nextTopFormulas[ref];
    }
    for (const ref of Object.keys(nextDraftValues)) {
      if (parseCellRef(ref)?.col === columnCol) delete nextDraftValues[ref];
    }
    topEdits = nextTopEdits;
    topFormulas = nextTopFormulas;
    draftValues = nextDraftValues;
  }

  function resequenceColumns(columns: TopTableColumn[]): TopTableColumn[] {
    return columns.map((column, index) => ({ ...column, col: indexToCol(index) }));
  }

  function addCustomColumn() {
    const next: TopTableColumn = {
      id: `col-custom-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      col: indexToCol(topColumns.length),
      label: "Custom",
      headerFormula: "",
      isDefault: false,
      deletable: true,
      editableCells: false,
      protected: true,
    };
    topColumns = [...topColumns, next];
    headerDrafts = { ...headerDrafts, [next.id]: "" };
  }

  function deleteCustomColumn(columnId: string) {
    const target = topColumns.find((column) => column.id === columnId);
    if (!target || target.isDefault) return;
    clearColumnRefs(target.col);
    topColumns = resequenceColumns(topColumns.filter((column) => column.id !== columnId));
    const nextDrafts = { ...headerDrafts };
    delete nextDrafts[columnId];
    headerDrafts = nextDrafts;
    if (activeCell?.col === target.col) {
      activeCell = null;
      formulaInput = "";
      selectionRange = null;
    }
  }

  /** Top-level attribute keys required by ENTITY.* formulas in the given columns. */
  function getRequiredEntityPathKeys(columns: TopTableColumn[]): string[] {
    const keys = new Set<string>();
    for (const col of columns) {
      const path = extractEntityPath(normalizeFormulaValue(col.headerFormula));
      if (path) {
        const top = path.split(".").map((p) => p.trim()).filter(Boolean)[0];
        if (top) keys.add(top);
      }
    }
    return [...keys];
  }

  async function fetchEntityAttributesFromBackend(
    branchId: string,
    revision: number | null,
    globalIds: string[],
    paths: string[],
  ): Promise<Record<string, Record<string, unknown>>> {
    const res = await fetch(`${API_BASE}/table/entity-attributes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        branchId,
        revision,
        globalIds,
        paths,
      }),
    });
    if (!res.ok) throw new Error(`entity-attributes: ${res.status}`);
    const data = (await res.json()) as { attributesByGlobalId: Record<string, Record<string, unknown>> };
    return data.attributesByGlobalId ?? {};
  }

  function commitHeaderFormula(columnId: string, rawInput: string) {
    const column = topColumns.find((c) => c.id === columnId);
    if (!column || column.isDefault) return;
    const trimmed = rawInput.trim();
    const { label, formula } = parseHeaderFormulaInput(trimmed);
    const nextColumns = topColumns.map((c) =>
      c.id === columnId
        ? {
            ...c,
            label,
            headerFormula: formula,
          }
        : c,
    );
    topColumns = nextColumns;
    const nextDrafts = { ...headerDrafts };
    delete nextDrafts[columnId];
    headerDrafts = nextDrafts;
    clearColumnRefs(column.col);

    fetchEntityAttributesIfNeeded(nextColumns);
  }

  function fetchEntityAttributesIfNeeded(columns: TopTableColumn[]) {
    if (useFixture || !branchId || !revision || products.length === 0) return;
    const paths = getRequiredEntityPathKeys(columns);
    if (paths.length === 0) return;
    const globalIds = products.map((p) => p.globalId);
    fetchEntityAttributesFromBackend(branchId, revision, globalIds, paths)
      .then((attributesByGlobalId) => {
        products = products.map((p) => {
          const attrs = attributesByGlobalId[p.globalId];
          if (attrs == null) return p;
          const merged = { ...(p.attributes as Record<string, unknown> ?? {}), ...attrs };
          return { ...p, attributes: merged };
        });
      })
      .catch((err) => {
        console.warn("Failed to fetch entity attributes for table:", err);
      });
  }

  function getSheetField(col: string): keyof Omit<SheetEntry, "id"> | null {
    return mapSheetColToField(col);
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
    return topFormulas[ref] ?? activeSheet.formulas[ref] ?? null;
  }

  function getCellDisplayValue(ref: string, fallback: string): string {
    if (draftValues[ref] !== undefined) return draftValues[ref] ?? "";
    if (activeCell?.ref === ref) {
      const rawFormula = getFormulaForRef(ref);
      if (rawFormula != null) return rawFormula;
    }
    if (topEdits[ref] !== undefined) return topEdits[ref] ?? "";
    const resolved = resolveCellByRef(ref);
    if (resolved?.surface === "entity") {
      return getCommittedValue(ref);
    }
    const parsed = parseCellRef(ref);
    if (!parsed) return fallback;
    if (parsed.row >= sheetRowStart() && activeSheet.formulas[ref] !== undefined) {
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
      if (activeSheet.formulas[ref] === undefined) return;
      const next = { ...activeSheet.formulas };
      delete next[ref];
      updateActiveSheet({ formulas: next });
      return;
    }
    updateActiveSheet({ formulas: { ...activeSheet.formulas, [ref]: raw } });
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
    if (index < 0 || index >= activeSheet.entries.length) return;
    const nextEntries = activeSheet.entries.map((entry, idx) => {
      if (idx !== index) return entry;
      return {
        ...entry,
        [field]: field === "entityGlobalId" && value.trim() === "" ? null : value,
      };
    });
    updateActiveSheet({ entries: nextEntries });
    updateSheetFormula(cell.ref, rawFormula);
  }

  function syncSelectionToViewer(globalId: string | null) {
    if (!syncWithViewer) return;
    if (lastSentSelectionToViewer === globalId) return;
    lastSentSelectionToViewer = globalId;
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
    activeHeaderColumnId = null;
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
    const minCol = Math.min(colToIndex(start.col), colToIndex(end.col));
    const maxCol = Math.max(colToIndex(start.col), colToIndex(end.col));
    const targetCol = colToIndex(target.col);
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
      if (syncWithViewer) syncSelectionToViewer(null);
      return;
    }

    let deltaRow = 0;
    let deltaCol = 0;
    if (direction === "up") deltaRow = -1;
    if (direction === "down") deltaRow = 1;
    if (direction === "left") deltaCol = -1;
    if (direction === "right") deltaCol = 1;
    if (direction === "tab") deltaCol = shift ? -1 : 1;

    const navCols = cell.surface === "sheet" ? SHEET_COLUMNS : getNavCols();
    const currentColIndex = navCols.indexOf(cell.col);
    if (currentColIndex < 0) return;
    const targetColIndex = Math.max(0, Math.min(navCols.length - 1, currentColIndex + deltaCol));
    const minRow = 2;
    const maxRow = Math.max(sheetRowStart() + activeSheet.entries.length - 1, products.length + 1);
    const targetRow = Math.max(minRow, Math.min(maxRow, cell.row + deltaRow));
    const nextRef = `${navCols[targetColIndex]}${targetRow}`;
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
    if (activeHeaderColumnId != null) {
      if (showFormulaDropdown && formulaSuggestionsList.length > 0) {
        const idx = Math.max(0, Math.min(formulaSuggestionIndex, formulaSuggestionsList.length - 1));
        applyFormulaSuggestion(formulaSuggestionsList[idx]);
        formulaSuggestionIndex = 0;
        return;
      }
      commitHeaderFormula(activeHeaderColumnId, formulaInput);
      activeHeaderColumnId = null;
      return;
    }
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
    if (activeHeaderColumnId != null) {
      const col = topColumns.find((c) => c.id === activeHeaderColumnId);
      const id = activeHeaderColumnId;
      activeHeaderColumnId = null;
      formulaInput = col
        ? col.headerFormula.trim()
          ? `[${col.label}](${col.headerFormula})`
          : ""
        : "";
      const nextDrafts = { ...headerDrafts };
      delete nextDrafts[id];
      headerDrafts = nextDrafts;
      return;
    }
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

  function onSortChange(column: SortKey, direction: "asc" | "desc") {
    sortBy = column;
    sortDir = direction;
  }

  function onSheetEntriesChange(nextEntries: SheetEntry[]) {
    if (nextEntries.length !== activeSheet.entries.length) {
      pushHistory();
    }
    const nextIds = new Set(nextEntries.map((entry) => entry.id));
    const nextLockedIds = new Set(
      Array.from(activeSheet.lockedIds).filter((id) => nextIds.has(id)),
    );
    updateActiveSheet({ entries: nextEntries, lockedIds: nextLockedIds });
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
      window.addEventListener("mousemove", onResizeSplitMove);
      window.addEventListener("mouseup", endResizeSplit);
      const h = loadTopSegmentHeight();
      if (h != null) topSegmentHeightPx = h;
    }
  });

  onDestroy(() => {
    if (syncWithViewer) {
      channel?.postMessage({ type: "sync-mode", enabled: false } satisfies TableMessage);
    }
    channel?.close();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
    if (toastTimeoutId != null) clearTimeout(toastTimeoutId);
    if (typeof window !== "undefined") {
      window.removeEventListener("keydown", handleGlobalKeydown);
      window.removeEventListener("mouseup", handleGlobalPointerUp);
      window.removeEventListener("mousemove", onResizeSplitMove);
      window.removeEventListener("mouseup", endResizeSplit);
    }
  });
</script>

<svelte:head>
  <title>Table • BimAtlas</title>
</svelte:head>

<div class="table-page">
  <header class="page-header">
    <div class="page-header-title-row">
      <h2>Table</h2>
    </div>
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
    <span class="formula-cell-ref mono">
      {activeHeaderColumnId
        ? (topColumns.find((c) => c.id === activeHeaderColumnId)?.col ?? "—")
        : activeCell?.ref ?? "—"}
    </span>
    <div class="formula-input-wrap">
      <input
        type="text"
        class="formula-input"
        value={formulaInput}
        placeholder="Enter value or formula (e.g. =D2+E2, =SUM(D2:D4), =ENTITY.PropertySets.PsetWallCommon)"
        disabled={activeCell == null && activeHeaderColumnId == null}
        readonly={activeCell != null && !activeCell.editable && activeHeaderColumnId == null}
        autocomplete="off"
        oninput={(e) => {
          formulaInput = e.currentTarget.value;
          formulaSuggestionIndex = 0;
          if (activeHeaderColumnId != null) {
            headerDrafts = { ...headerDrafts, [activeHeaderColumnId]: formulaInput };
          } else if (activeCell != null) {
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
    <button
      type="button"
      class="formula-btn"
      onclick={() => (showCellContentOverlay = true)}
      disabled={activeCell == null}
      aria-label="View full cell contents"
    >
      View full
    </button>
  </div>

  <div
    class="table-split"
    class:resizing={isResizingSplit}
    style={topSegmentHeightPx != null ? `--top-height: ${topSegmentHeightPx}px` : undefined}
    bind:this={tableSplitRef}
  >
    <section
      class="table-segment table-segment-top"
      aria-label="IFC entities"
      bind:this={segmentTopRef}
    >
      <div class="segment-toolbar">
        <p class="segment-label">Total entities: {products.length}</p>
        <button
          type="button"
          class="btn btn-primary formula-guide-btn"
          class:active={syncWithViewer}
          onclick={() => setSyncWithViewer(!syncWithViewer)}
          disabled={!hasChannelContext}
          title={hasChannelContext
            ? (syncWithViewer ? "Sync on: table and viewer selection stay in sync" : "Sync off: click to enable two-way selection sync")
            : "Open the table from the main BimAtlas view to use this feature"}
          aria-label={syncWithViewer ? "Sync with viewer (on)" : "Sync with viewer (off)"}
          aria-pressed={syncWithViewer}
        >
          Sync with viewer
        </button>
        <button
          type="button"
          class="btn btn-primary formula-guide-btn"
          onclick={toggleLockAll}
          disabled={products.length === 0 && activeSheet.entries.length === 0}
          aria-label={allEntitiesLocked ? "Unlock all rows" : "Lock all rows"}
        >
          {allEntitiesLocked ? "Unlock all" : "Lock all"}
        </button>
        <button
          type="button"
          class="btn btn-primary formula-guide-btn"
          onclick={addCustomColumn}
          aria-label="Add custom column"
        >
          Add column
        </button>
        <button
          type="button"
          class="btn btn-primary formula-guide-btn"
          onclick={() => (showFormulaGuideOverlay = true)}
          aria-label="Open formula guide"
        >
          Formula guide
        </button>
        <button
          type="button"
          class="btn btn-primary formula-guide-btn"
          data-testid="export-csv-btn"
          onclick={exportCsv}
          disabled={products.length === 0 && activeSheet.entries.length === 0}
          aria-label="Export full table as CSV"
        >
          Export CSV
        </button>
      </div>
      <EntityGridDynamic
        products={displayProducts}
        columns={topColumns}
        getColumnWidthPx={getColumnWidthPx}
        onColumnWidthChange={setColumnWidth}
        lockedIds={lockedIds}
        onToggleLock={toggleLock}
        onAddCustomColumn={addCustomColumn}
        onDeleteCustomColumn={deleteCustomColumn}
        getHeaderFormulaInput={getHeaderFormulaInput}
        onHeaderFormulaInput={onHeaderFormulaInput}
        onHeaderFormulaCommit={commitHeaderFormula}
        onHeaderFormulaCancel={onHeaderFormulaCancel}
        onHeaderFormulaFocus={(id) => {
          headerFormulaFocusedColumnId = id;
          activeHeaderColumnId = id;
          activeCell = null;
          const col = topColumns.find((c) => c.id === id);
          formulaInput = col
            ? col.headerFormula.trim()
              ? `[${col.label}](${col.headerFormula})`
              : ""
            : "";
          tick().then(() => document.querySelector<HTMLInputElement>(".formula-input")?.focus());
        }}
        onHeaderFormulaBlur={() => (headerFormulaFocusedColumnId = null)}
        activeCellRef={activeCell?.ref ?? null}
        selectedRowGlobalId={selectedRowGlobalId}
        getCellDisplayValue={getCellDisplayValue}
        onCellFocus={onCellFocus}
        onCellInput={onCellInput}
        onCellCommit={onCellCommit}
        onCellCancel={onCellCancel}
        onCellNavigate={onCellNavigate}
        onFillDown={onFillDownRequest}
        sortBy={sortBy}
        sortDir={sortDir}
        onSortChange={onSortChange}
        isCellInSelection={isCellInSelection}
        onCellPointerDown={onCellPointerDown}
        onCellPointerEnter={onCellPointerEnter}
        onCellPointerUp={onCellPointerUp}
      />
    </section>
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="split-resize-handle"
      role="separator"
      aria-label="Resize top and bottom sections"
      onmousedown={startResizeSplit}
    ></div>
    <section class="table-segment table-segment-bottom" aria-label="Sheet interactions">
      {#if !sheetsReady}
        <div class="sheets-loading-overlay">
          <span class="sheets-loading-text">Loading sheets…</span>
        </div>
      {:else}
      <BottomSheet
        entries={activeSheet.entries}
        rowStart={products.length + 2}
        getColumnWidthPx={getColumnWidthPx}
        onEntriesChange={onSheetEntriesChange}
        lockedEntryIds={activeSheet.lockedIds}
        onToggleEntryLock={toggleSheetEntryLock}
        projectId={projectId}
        templateSearchQuery={templateSearchQuery}
        onTemplateSearchChange={(q) => (templateSearchQuery = q)}
        templateResults={templateResults}
        loadingTemplates={loadingTemplates}
        onLoadTemplate={handleLoadTemplate}
        onSaveTemplate={handleSaveTemplate}
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
      <div class="sheet-tabs">
        {#each sheets as sheet (sheet.id)}
          {#if editingSheetId === sheet.id}
            <input
              type="text"
              class="sheet-tab-edit"
              value={editingSheetName}
              onblur={commitSheetRename}
              onkeydown={(e) => {
                if (e.key === "Enter") commitSheetRename();
                if (e.key === "Escape") {
                  editingSheetId = null;
                  editingSheetName = "";
                }
              }}
              oninput={(e) => (editingSheetName = e.currentTarget.value)}
              bind:this={editingSheetInputRef}
            />
          {:else}
            <div
              role="tab"
              class="sheet-tab"
              class:active={sheet.id === activeSheetId}
              tabindex="0"
              onclick={() => setActiveSheet(sheet.id)}
              ondblclick={(e) => {
                e.preventDefault();
                startEditingSheet(sheet);
              }}
              oncontextmenu={(e) => {
                e.preventDefault();
                if (sheets.length <= 1) return;
                sheetTabContextMenu = { x: e.clientX, y: e.clientY, sheet };
              }}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setActiveSheet(sheet.id);
                }
              }}
              aria-label="Switch to {sheet.name}"
            >
              <span class="sheet-tab-label">{sheet.name}</span>
              {#if sheets.length > 1}
                <button
                  type="button"
                  class="sheet-tab-close"
                  onclick={(e) => requestCloseSheet(sheet, e)}
                  aria-label="Close {sheet.name}"
                >
                  ×
                </button>
              {/if}
            </div>
          {/if}
        {/each}
        <button
          type="button"
          class="sheet-tab-add"
          onclick={addSheet}
          aria-label="Add sheet"
        >
          + Sheet
        </button>
      </div>
      {/if}
    </section>
  </div>

  {#if sheetTabContextMenu}
    <div
      data-sheet-tab-context-menu
      class="sheet-tab-context-menu"
      style="left: {sheetTabContextMenu.x}px; top: {sheetTabContextMenu.y}px;"
      role="menu"
    >
      <button
        type="button"
        role="menuitem"
        class="sheet-tab-context-item"
        onclick={() => {
          performCloseSheet(sheetTabContextMenu!.sheet);
          sheetTabContextMenu = null;
        }}
      >
        Close sheet
      </button>
      <button
        type="button"
        role="menuitem"
        class="sheet-tab-context-item sheet-tab-context-item-danger"
        onclick={() => {
          performDeleteSheet(sheetTabContextMenu!.sheet);
          sheetTabContextMenu = null;
        }}
      >
        Delete sheet
      </button>
    </div>
  {/if}

  {#if closeSheetConfirmDialog}
    <div
      class="formula-guide-backdrop"
      role="presentation"
      onclick={handleCloseSheetCancel}
      onkeydown={(e) => e.key === "Escape" && handleCloseSheetCancel()}
    >
      <div
        class="close-sheet-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="close-sheet-dialog-title"
        tabindex="-1"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.key === "Escape" && handleCloseSheetCancel()}
      >
        <h2 id="close-sheet-dialog-title">Unsaved sheet</h2>
        <p>
          <strong>{closeSheetConfirmDialog.name}</strong> has not been saved. Save before closing?
        </p>
        <div class="close-sheet-dialog-actions">
          <button type="button" onclick={handleCloseSheetCancel}>
            Cancel closing
          </button>
          <button type="button" onclick={() => handleCloseSheetSaveAndClose()}>
            Save and Close
          </button>
        </div>
      </div>
    </div>
  {/if}

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

  {#if showCellContentOverlay && activeCell}
    {@const rawContent = getCommittedValue(activeCell.ref)}
    {@const formattedContent = (() => {
      if (rawContent == null || rawContent === "") return "(empty)";
      const trimmed = String(rawContent).trim();
      if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
        try {
          return JSON.stringify(JSON.parse(trimmed), null, 2);
        } catch {
          return rawContent;
        }
      }
      return rawContent;
    })()}
    <div
      class="cell-content-backdrop"
      role="presentation"
      onclick={() => (showCellContentOverlay = false)}
      onkeydown={(e) => e.key === "Escape" && (showCellContentOverlay = false)}
    >
      <div
        class="cell-content-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cell-content-title"
        tabindex="-1"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.key === "Escape" && (showCellContentOverlay = false)}
      >
        <div class="cell-content-header">
          <h2 id="cell-content-title" class="cell-content-title mono">{activeCell.ref}</h2>
          <button
            type="button"
            class="formula-guide-close"
            onclick={() => (showCellContentOverlay = false)}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div class="cell-content-body">
          <pre class="cell-content-pre">{formattedContent}</pre>
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
    --table-grid-border-color: var(--color-border-subtle);
    --table-header-height: 28px;
    --table-subheader-height: 34px;
    --table-row-height: 34px;
    --lock-rail-width: 3rem;

    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
    font-family: system-ui, -apple-system, sans-serif;
    overflow: hidden;
  }

  .context-pill {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-secondary);
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
    color: var(--color-success);
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
  }

  .table-split {
    flex: 1 1 0;
    min-height: 0;
    display: grid;
    grid-template-rows: var(--top-height, minmax(0, 1fr)) 6px minmax(190px, 1fr);
  }

  .table-split.resizing {
    user-select: none;
  }

  .split-resize-handle {
    grid-column: 1;
    cursor: row-resize;
    background: var(--color-bg-elevated);
    border-top: 1px solid var(--color-border-subtle);
  }

  .split-resize-handle:hover {
    background: color-mix(in srgb, var(--color-brand-500) 15%, transparent);
    border-top-color: color-mix(in srgb, var(--color-brand-500) 35%, transparent);
  }

  .table-split.resizing .split-resize-handle {
    background: color-mix(in srgb, var(--color-brand-500) 20%, transparent);
  }

  .formula-bar {
    flex-shrink: 0;
    display: grid;
    grid-template-columns: auto 1fr repeat(3, auto);
    gap: 0.4rem;
    align-items: center;
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background: var(--color-bg-elevated);
  }

  .formula-cell-ref {
    min-width: 2.8rem;
    text-align: center;
    padding: 0.35rem 0.5rem;
    border-radius: 0.25rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    font-size: 0.78rem;
    color: var(--color-text-primary);
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
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
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
    background: color-mix(in srgb, var(--color-brand-500) 15%, transparent);
    color: var(--color-brand-400);
  }

  .formula-suggestion-sig {
    color: var(--color-text-primary);
    font-weight: 500;
  }

  .formula-suggestion-desc {
    font-size: 0.72rem;
    color: var(--color-text-muted);
  }

  .formula-suggestion-item:hover .formula-suggestion-desc,
  .formula-suggestion-item.selected .formula-suggestion-desc {
    color: var(--color-text-secondary);
  }

  .formula-input {
    width: 100%;
    height: 2rem;
    box-sizing: border-box;
    border-radius: 0.35rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    padding: 0 0.6rem;
    font-size: 0.82rem;
  }

  .formula-input:focus {
    outline: none;
    border-color: color-mix(in srgb, var(--color-brand-500) 55%, transparent);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand-500) 20%, transparent);
  }

  .formula-input[readonly] {
    opacity: 0.8;
    color: var(--color-text-muted);
  }

  .formula-btn {
    height: 2rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
    font-size: 0.75rem;
    padding: 0 0.6rem;
    cursor: pointer;
  }

  .formula-btn:hover:enabled {
    background: color-mix(in srgb, var(--color-brand-500) 18%, transparent);
    border-color: color-mix(in srgb, var(--color-brand-500) 45%, transparent);
    color: var(--color-brand-400);
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
    border-top: 1px solid var(--color-border-subtle);
  }

  .segment-toolbar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background: var(--color-bg-elevated);
  }

  .segment-label {
    margin: 0;
    font-size: 0.8rem;
    color: var(--color-text-muted);
  }

  .formula-guide-btn {
    margin-left: auto;
    padding: 0.35rem 0.65rem;
    font-size: 0.78rem;
    border-radius: 0.5rem;
  }

  .formula-guide-btn.active {
    background: var(--color-brand-500);
    border-color: var(--color-brand-500);
    color: var(--color-bg-surface);
  }

  .formula-guide-btn.active:hover:not(:disabled) {
    background: var(--color-brand-500);
    border-color: var(--color-brand-500);
    opacity: 0.9;
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
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
    overflow: hidden;
  }

  .formula-guide-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .formula-guide-header h2 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-brand-500);
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
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .formula-guide-close:hover {
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
  }

  .formula-guide-body {
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem;
  }

  .cell-content-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
  }

  .cell-content-overlay {
    width: 75%;
    height: 75%;
    min-width: 18rem;
    min-height: 12rem;
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
    overflow: hidden;
  }

  .cell-content-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .cell-content-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-brand-500);
  }

  .cell-content-body {
    flex: 1 1 0;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem;
  }

  .cell-content-pre {
    margin: 0;
    font-size: 0.82rem;
    line-height: 1.45;
    color: var(--color-text-primary);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .close-sheet-dialog {
    padding: 1.25rem;
    border-radius: 0.5rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
    min-width: 18rem;
  }

  .close-sheet-dialog h2 {
    margin: 0 0 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-brand-500);
  }

  .close-sheet-dialog p {
    margin: 0 0 1rem;
    font-size: 0.9rem;
    color: var(--color-text-secondary);
  }

  .close-sheet-dialog-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }

  .close-sheet-dialog-actions button {
    padding: 0.4rem 0.75rem;
    font-size: 0.85rem;
    border-radius: 0.3rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
    cursor: pointer;
  }

  .close-sheet-dialog-actions button:hover {
    background: color-mix(in srgb, var(--color-text-primary) 8%, transparent);
  }

  .close-sheet-dialog-actions button:last-child {
    background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
    border-color: color-mix(in srgb, var(--color-brand-500) 40%, transparent);
    color: var(--color-brand-500);
  }

  .close-sheet-dialog-actions button:last-child:hover {
    background: color-mix(in srgb, var(--color-brand-500) 18%, transparent);
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
    color: var(--color-text-primary);
  }

  .formula-guide-usage {
    margin: 0 0 0.35rem;
    font-size: 0.82rem;
    color: var(--color-brand-500);
  }

  .formula-guide-desc {
    margin: 0;
    font-size: 0.8rem;
    color: var(--color-text-muted);
    line-height: 1.4;
  }

  .table-segment-top {
    min-height: 0;
    overflow: auto;
  }

  .table-segment-bottom {
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
  }

  .sheets-loading-overlay {
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-elevated);
  }

  .sheets-loading-text {
    font-size: 0.9rem;
    color: var(--color-text-muted);
  }

  .sheet-tabs {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.2rem;
    padding: 0.25rem 0.5rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background: var(--color-bg-elevated);
  }

  .sheet-tab {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.6rem;
    font-size: 0.78rem;
    border-radius: 0.25rem;
    border: 1px solid transparent;
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .sheet-tab-label {
    flex: 0 1 auto;
    min-width: 0;
  }

  .sheet-tab-close {
    flex-shrink: 0;
    padding: 0 0.15rem;
    font-size: 1rem;
    line-height: 1;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
    border-radius: 0.15rem;
  }

  .sheet-tab-close:hover {
    color: var(--color-danger);
    background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  }

  .sheet-tab:hover {
    color: var(--color-text-secondary);
    background: color-mix(in srgb, var(--color-text-primary) 5%, transparent);
  }

  .sheet-tab.active {
    color: var(--color-brand-500);
    background: color-mix(in srgb, var(--color-brand-500) 12%, transparent);
    border-color: color-mix(in srgb, var(--color-brand-500) 30%, transparent);
  }

  .sheet-tab-add {
    padding: 0.2rem 0.5rem;
    font-size: 0.75rem;
    border-radius: 0.25rem;
    border: 1px dashed var(--color-border-default);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
    margin-left: 0.25rem;
  }

  .sheet-tab-add:hover {
    color: var(--color-brand-500);
    border-color: color-mix(in srgb, var(--color-brand-500) 40%, transparent);
  }

  .sheet-tab-context-menu {
    position: fixed;
    z-index: 1000;
    min-width: 10rem;
    padding: 0.25rem 0;
    border-radius: 0.35rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }
  .sheet-tab-context-item {
    display: block;
    width: 100%;
    padding: 0.4rem 0.75rem;
    border: none;
    border-radius: 0;
    background: transparent;
    color: var(--color-text-primary);
    font-size: 0.8rem;
    text-align: left;
    cursor: pointer;
  }
  .sheet-tab-context-item:hover {
    background: var(--color-bg-elevated);
  }
  .sheet-tab-context-item-danger:hover {
    background: color-mix(in srgb, var(--color-danger) 12%, transparent);
    color: var(--color-danger);
  }

  .sheet-tab-edit {
    padding: 0.25rem 0.5rem;
    font-size: 0.78rem;
    border-radius: 0.25rem;
    border: 1px solid color-mix(in srgb, var(--color-brand-500) 40%, transparent);
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
    min-width: 4rem;
  }

  .table-segment-bottom :global(.bottom-sheet) {
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .table-toast {
    position: fixed;
    bottom: 1.5rem;
    left: 50%;
    transform: translateX(-50%);
    padding: 0.6rem 1rem;
    border-radius: 0.35rem;
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
    font-size: 0.875rem;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    border: 1px solid var(--color-border-subtle);
    z-index: 100;
  }
</style>
