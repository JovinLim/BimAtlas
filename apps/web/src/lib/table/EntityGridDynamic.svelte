<script lang="ts">
  import type { ProductMeta } from "$lib/search/protocol";
  import type {
    DefaultTopColumnKey,
    SpreadsheetCellState,
    TopTableColumn,
  } from "$lib/table/engine";

  type SortableColumn = DefaultTopColumnKey;
  const SORTABLE_KEYS: Set<string> = new Set([
    "globalId",
    "ifcClass",
    "name",
    "description",
    "objectType",
    "tag",
  ]);

  const MIN_COLUMN_WIDTH_PX = 48;

  type Props = {
    products: ProductMeta[];
    columns: TopTableColumn[];
    getColumnWidthPx: (col: string) => number;
    onColumnWidthChange: (col: string, widthPx: number) => void;
    lockedIds: Set<string>;
    onToggleLock: (globalId: string) => void;
    onAddCustomColumn: () => void;
    onDeleteCustomColumn: (columnId: string) => void;
    getHeaderFormulaInput: (columnId: string) => string;
    onHeaderFormulaInput: (columnId: string, value: string) => void;
    onHeaderFormulaCommit: (columnId: string, value: string) => void;
    onHeaderFormulaCancel: (columnId: string) => void;
    onHeaderFormulaFocus?: (columnId: string) => void;
    onHeaderFormulaBlur?: () => void;
    activeCellRef: string | null;
    selectedRowGlobalId: string | null;
    findHighlightGlobalId: string | null;
    getCellDisplayValue: (ref: string, fallback: string) => string;
    onCellFocus: (cell: SpreadsheetCellState) => void;
    onCellInput: (cell: SpreadsheetCellState, value: string) => void;
    onCellCommit: (cell: SpreadsheetCellState, value: string) => void;
    onCellCancel: (cell: SpreadsheetCellState) => void;
    onCellNavigate: (
      cell: SpreadsheetCellState,
      direction: "up" | "down" | "left" | "right" | "enter" | "tab",
      shift: boolean,
    ) => void;
    onFillDown: (cell: SpreadsheetCellState) => void;
    sortBy: SortableColumn;
    sortDir: "asc" | "desc";
    onSortChange: (column: SortableColumn, direction: "asc" | "desc") => void;
    isCellInSelection: (ref: string) => boolean;
    onCellPointerDown: (
      cell: SpreadsheetCellState,
      event: MouseEvent,
    ) => boolean | void;
    onCellPointerEnter: (cell: SpreadsheetCellState, event: MouseEvent) => void;
    onCellPointerUp: (cell: SpreadsheetCellState, event: MouseEvent) => void;
  };

  let {
    products,
    columns,
    getColumnWidthPx,
    onColumnWidthChange,
    lockedIds,
    onToggleLock,
    onAddCustomColumn,
    onDeleteCustomColumn,
    getHeaderFormulaInput,
    onHeaderFormulaInput,
    onHeaderFormulaCommit,
    onHeaderFormulaCancel,
    onHeaderFormulaFocus,
    onHeaderFormulaBlur,
    activeCellRef,
    selectedRowGlobalId,
    findHighlightGlobalId,
    getCellDisplayValue,
    onCellFocus,
    onCellInput,
    onCellCommit,
    onCellCancel,
    onCellNavigate,
    onFillDown,
    sortBy,
    sortDir,
    onSortChange,
    isCellInSelection,
    onCellPointerDown,
    onCellPointerEnter,
    onCellPointerUp,
  }: Props = $props();

  let openSortColumn = $state<SortableColumn | null>(null);

  $effect(() => {
    const key = openSortColumn;
    if (key == null) return;
    const el = document.querySelector(`[data-sort-column="${key}"]`);
    if (!el) return;
    const close = (e: MouseEvent) => {
      if (!el.contains(e.target as Node)) openSortColumn = null;
    };
    document.addEventListener("mousedown", close, true);
    return () => document.removeEventListener("mousedown", close, true);
  });

  function isLocked(globalId: string): boolean {
    return lockedIds.has(globalId);
  }

  function buildCell(row: number, column: TopTableColumn, product: ProductMeta): SpreadsheetCellState {
    const editable = column.editableCells && !isLocked(product.globalId);
    return {
      surface: "entity",
      row,
      col: column.col,
      ref: `${column.col}${row}`,
      editable,
      protected: column.protected,
    };
  }

  function getColumnClass(column: TopTableColumn): string {
    if (column.defaultKey) return `col-${column.defaultKey}`;
    return "col-custom";
  }

  let resizingCol = $state<string | null>(null);
  let resizeStartX = 0;
  let resizeStartWidth = 0;

  function startResize(e: MouseEvent, col: string) {
    e.preventDefault();
    e.stopPropagation();
    resizingCol = col;
    resizeStartX = e.clientX;
    resizeStartWidth = getColumnWidthPx(col);
  }

  /** Measure the top grid’s rendered column width (respects content/styling minimum) and sync to shared state. */
  function syncColumnWidthFromTop(col: string) {
    requestAnimationFrame(() => {
      const el = document.querySelector(
        `.labels-row th[data-col="${col}"]`,
      ) as HTMLElement | null;
      const w = el?.getBoundingClientRect().width;
      if (w != null && w > 0) {
        onColumnWidthChange(col, Math.round(w));
      }
    });
  }

  $effect(() => {
    if (resizingCol == null) return;
    const col = resizingCol;
    const onMove = (e: MouseEvent) => {
      const delta = e.clientX - resizeStartX;
      const width = Math.max(MIN_COLUMN_WIDTH_PX, resizeStartWidth + delta);
      onColumnWidthChange(col, width);
    };
    const onUp = () => {
      resizingCol = null;
      syncColumnWidthFromTop(col);
    };
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("mouseup", onUp, true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("mousemove", onMove, true);
      document.removeEventListener("mouseup", onUp, true);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  });

  function onHeaderKeydown(e: KeyboardEvent, columnId: string, value: string) {
    if (e.key === "Enter") {
      e.preventDefault();
      onHeaderFormulaCommit(columnId, value);
      (e.currentTarget as HTMLInputElement).blur();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      onHeaderFormulaCancel(columnId);
      (e.currentTarget as HTMLInputElement).blur();
    }
  }

  function onCellKeydown(
    e: KeyboardEvent,
    cell: SpreadsheetCellState,
    value: string,
  ) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "d") {
      e.preventDefault();
      onFillDown(cell);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      onCellNavigate(cell, "up", e.shiftKey);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      onCellNavigate(cell, "down", e.shiftKey);
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      onCellNavigate(cell, "left", e.shiftKey);
      return;
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      onCellNavigate(cell, "right", e.shiftKey);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      onCellCommit(cell, value);
      onCellNavigate(cell, "enter", e.shiftKey);
      (e.currentTarget as HTMLInputElement).blur();
      return;
    }
    if (e.key === "Tab") {
      e.preventDefault();
      onCellCommit(cell, value);
      onCellNavigate(cell, "tab", e.shiftKey);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      onCellCancel(cell);
      (e.currentTarget as HTMLInputElement).blur();
    }
  }
</script>

<div class="entity-grid-wrap">
  <div class="entity-grid-content">
    <div class="lock-rail" aria-label="Entity lock controls">
      <div class="lock-rail-corner"></div>
      <div class="lock-rail-header mono">LOCK</div>
      {#each products as product (product.globalId)}
        {@const locked = isLocked(product.globalId)}
        <button
          type="button"
          class="lock-btn"
          aria-label={locked ? "Unlock row" : "Lock row"}
          title={locked ? "Unlock row" : "Lock row"}
          onclick={() => onToggleLock(product.globalId)}
        >
          {#if locked}
            <svg class="lock-icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <rect x="6.5" y="10" width="11" height="9" rx="2" ry="2" stroke="currentColor" stroke-width="1.8" fill="none" />
              <path d="M9 10V8.5C9 6.6 10.6 5 12.5 5C14.4 5 16 6.6 16 8.5V10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none" />
            </svg>
          {:else}
            <svg class="lock-icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <rect x="6.5" y="10" width="11" height="9" rx="2" ry="2" stroke="currentColor" stroke-width="1.8" fill="none" />
              <path d="M9 10V8.5C9 6.6 10.6 5 12.5 5C13.6 5 14.6 5.5 15.3 6.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none" />
            </svg>
          {/if}
        </button>
      {/each}
    </div>
    <table class="entity-grid" role="grid" aria-label="IFC entities">
      <colgroup>
        <col class="col-rownum" />
        {#each columns as column (column.id)}
          <col class={getColumnClass(column)} style="width: {getColumnWidthPx(column.col)}px; min-width: {getColumnWidthPx(column.col)}px; max-width: {getColumnWidthPx(column.col)}px;" />
        {/each}
        <col class="header-add-col" />
      </colgroup>
      <thead>
        <tr class="letters-row">
          <th class="corner" scope="col"></th>
          {#each columns as column (column.id)}
            <th scope="col" class="th-with-resize">
              <span>{column.col}</span>
              <button
                type="button"
                class="col-resize-handle col-resize-handle-letters"
                aria-label="Resize column {column.col}"
                onmousedown={(e) => startResize(e, column.col)}
              ></button>
            </th>
          {/each}
          <th scope="col"></th>
        </tr>
        <tr class="labels-row">
          <th class="row-index" scope="row">1</th>
          {#each columns as column (column.id)}
            <th
              scope="col"
              class="th-sort th-with-resize"
              data-col={column.col}
              data-sort-column={column.defaultKey ?? column.id}
            >
              <div class="th-sort-inner">
                {#if column.isDefault}
                  <span class="th-sort-label">{column.label}</span>
                  {@const sortKey = column.defaultKey}
                  {#if sortKey && SORTABLE_KEYS.has(sortKey)}
                    <button
                      type="button"
                      class="th-sort-btn"
                      aria-label="Sort column"
                      aria-expanded={openSortColumn === sortKey}
                      aria-haspopup="menu"
                      onclick={() =>
                        (openSortColumn = openSortColumn === sortKey ? null : sortKey)}
                    >
                      <svg class="th-sort-icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                        <path fill="currentColor" d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/>
                      </svg>
                    </button>
                    {#if openSortColumn === sortKey}
                      <div class="th-sort-dropdown" role="menu">
                        <button
                          type="button"
                          role="menuitem"
                          class="th-sort-option"
                          class:active={sortBy === sortKey && sortDir === "asc"}
                          onclick={() => {
                            onSortChange(sortKey, "asc");
                            openSortColumn = null;
                          }}
                        >
                          Sort A–Z
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          class="th-sort-option"
                          class:active={sortBy === sortKey && sortDir === "desc"}
                          onclick={() => {
                            onSortChange(sortKey, "desc");
                            openSortColumn = null;
                          }}
                        >
                          Sort Z–A
                        </button>
                      </div>
                    {/if}
                  {/if}
                {:else}
                  <input
                    class="header-formula-input"
                    aria-label={`Custom column formula for ${column.col}`}
                    value={getHeaderFormulaInput(column.id)}
                    oninput={(e) => onHeaderFormulaInput(column.id, e.currentTarget.value)}
                    onfocus={() => onHeaderFormulaFocus?.(column.id)}
                    onblur={(e) => {
                      onHeaderFormulaCommit(column.id, e.currentTarget.value);
                      onHeaderFormulaBlur?.();
                    }}
                    onkeydown={(e) => onHeaderKeydown(e, column.id, e.currentTarget.value)}
                  />
                  <button
                    type="button"
                    class="header-delete-btn"
                    aria-label="Delete custom column"
                    onclick={() => onDeleteCustomColumn(column.id)}
                  >
                    ×
                  </button>
                {/if}
              </div>
              <button
                type="button"
                class="col-resize-handle"
                aria-label="Resize column {column.col}"
                onmousedown={(e) => startResize(e, column.col)}
              ></button>
            </th>
          {/each}
          <th scope="col" class="header-add-col">
            <button
              type="button"
              class="header-add-btn"
              aria-label="Add custom column"
              onclick={onAddCustomColumn}
            >
              + Column
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each products as product, idx (product.globalId)}
          {@const locked = isLocked(product.globalId)}
          {@const row = idx + 2}
          <tr
            class="entity-row"
            class:selected={selectedRowGlobalId != null && product.globalId === selectedRowGlobalId}
            class:find-highlight={findHighlightGlobalId != null && product.globalId === findHighlightGlobalId}
            data-global-id={product.globalId}
            data-locked={locked}
          >
            <th class="row-index" scope="row">{idx + 2}</th>
            {#each columns as column (column.id)}
              {@const cell = buildCell(row, column, product)}
              <td class={getColumnClass(column)}>
                <input
                  class="cell-input"
                  class:readonly-cell={!cell.editable}
                  type="text"
                  class:active-cell={activeCellRef === cell.ref}
                  class:selected-range={isCellInSelection(cell.ref)}
                  data-cell-ref={cell.ref}
                  value={getCellDisplayValue(cell.ref, "")}
                  readonly={!cell.editable}
                  onmousedown={(e) => {
                    if (onCellPointerDown(cell, e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(cell, e)}
                  onmouseup={(e) => onCellPointerUp(cell, e)}
                  onfocus={() => onCellFocus(cell)}
                  oninput={(e) => onCellInput(cell, e.currentTarget.value)}
                  onblur={(e) => onCellCommit(cell, e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      cell,
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
            {/each}
            <td class="header-add-col"></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .entity-grid-wrap { flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: auto; }
  .entity-grid-content { display: grid; grid-template-columns: var(--lock-rail-width, 3rem) minmax(0, 1fr); width: max-content; min-width: 100%; }

  .lock-rail {
    position: sticky;
    left: 0;
    z-index: 6;
    background: #1a1a2e;
    border-right: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    flex-shrink: 0;
  }
  .lock-rail-corner {
    position: sticky;
    top: 0;
    z-index: 7;
    height: calc(var(--table-header-height, 28px) + var(--table-grid-border-width, 1px));
    min-height: calc(var(--table-header-height, 28px) + var(--table-grid-border-width, 1px));
    background: #1a1a2e;
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    box-sizing: border-box;
  }
  .lock-rail-header {
    position: sticky;
    top: calc(var(--table-header-height, 28px) + var(--table-grid-border-width, 1px));
    z-index: 7;
    height: calc(var(--table-subheader-height, 34px) + var(--table-grid-border-width, 1px));
    min-height: calc(var(--table-subheader-height, 34px) + var(--table-grid-border-width, 1px));
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    color: #ccccd8;
    background: #1a1a2e;
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
  }

  .entity-grid { width: max-content; min-width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.78rem; }
  .entity-grid col.col-rownum { width: 2.8rem; }

  .entity-grid th, .entity-grid td {
    border-right: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    padding: 0;
    height: var(--table-row-height, 34px);
    overflow: hidden;
  }
  .th-with-resize { position: relative; }
  .col-resize-handle {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 6px;
    cursor: col-resize;
    z-index: 1;
    border: none;
    padding: 0;
    margin: 0;
    background: transparent;
    font: inherit;
  }
  .col-resize-handle:hover { background: rgba(255, 136, 102, 0.2); }
  .col-resize-handle-letters { bottom: calc(-1 * (var(--table-subheader-height, 34px) + var(--table-grid-border-width, 1px))); }
  .letters-row th {
    position: sticky;
    top: 0;
    z-index: 4;
    height: var(--table-header-height, 28px);
    background: #1a1a2e;
    color: #c0c0d0;
    font-weight: 600;
    text-align: center;
    box-shadow: 0 calc(var(--table-grid-border-width, 1px) + 1px) 0 0 #1a1a2e;
  }
  .corner {
    left: var(--lock-rail-width, 3rem);
    z-index: 8;
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.15);
  }
  .labels-row th {
    position: sticky;
    top: var(--table-header-height, 28px);
    z-index: 3;
    background: #1a1a2e;
    color: #ccccd8;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 0 0.5rem;
    text-align: left;
    height: var(--table-subheader-height, 34px);
    min-width: 0;
  }
  .th-sort {
    vertical-align: middle;
    overflow: hidden;
  }
  .th-sort-inner {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    position: relative;
    min-height: 1.5rem;
    min-width: 0;
    overflow: hidden;
  }
  .th-sort-label {
    flex: 1;
    min-width: 0;
  }
  .th-sort-btn {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    border: none;
    border-radius: 0.25rem;
    background: transparent;
    color: #a0a0b0;
    cursor: pointer;
  }
  .th-sort-btn:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #e0e0e0;
  }
  .th-sort-btn[aria-expanded="true"] {
    background: rgba(255, 136, 102, 0.15);
    color: #ff8866;
  }
  .th-sort-icon {
    display: block;
  }
  .th-sort-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 0.2rem;
    min-width: 8rem;
    padding: 0.25rem 0;
    border-radius: 0.35rem;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: #252538;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    z-index: 20;
    list-style: none;
  }
  .th-sort-option {
    display: block;
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: none;
    border-radius: 0;
    background: transparent;
    color: #e0e0e0;
    font-size: 0.8rem;
    text-align: left;
    cursor: pointer;
  }
  .th-sort-option:hover {
    background: rgba(255, 255, 255, 0.08);
  }
  .th-sort-option.active {
    background: rgba(255, 136, 102, 0.15);
    color: #ff8866;
  }

  .header-formula-input {
    flex: 1;
    min-width: 0;
    width: 100%;
    height: 1.6rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0.25rem;
    background: rgba(255, 255, 255, 0.04);
    color: #e0e0e0;
    font-size: 0.75rem;
    padding: 0 0.45rem;
    font-family: inherit;
    text-transform: none;
    letter-spacing: 0;
  }
  .header-formula-input:focus {
    outline: none;
    border-color: rgba(255, 136, 102, 0.55);
    box-shadow: 0 0 0 2px rgba(255, 136, 102, 0.15);
  }
  .header-delete-btn {
    width: 1.6rem;
    height: 1.6rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 0.25rem;
    background: rgba(255, 255, 255, 0.04);
    color: #d8d8e2;
    cursor: pointer;
    padding: 0;
    line-height: 1;
  }
  .header-delete-btn:hover {
    color: #ff8866;
    border-color: rgba(255, 136, 102, 0.45);
    background: rgba(255, 136, 102, 0.12);
  }
  .header-add-col {
    width: 8rem;
    min-width: 8rem;
    background: #1a1a2e;
  }
  .header-add-btn {
    width: calc(100% - 0.7rem);
    margin: 0.2rem 0.35rem;
    height: 1.8rem;
    border: 1px dashed rgba(255, 255, 255, 0.25);
    border-radius: 0.3rem;
    background: rgba(255, 255, 255, 0.02);
    color: #d0d0de;
    font-size: 0.72rem;
    cursor: pointer;
  }
  .header-add-btn:hover {
    border-color: rgba(255, 136, 102, 0.5);
    background: rgba(255, 136, 102, 0.1);
    color: #ffd8cf;
  }

  .entity-grid thead th.row-index {
    left: var(--lock-rail-width, 3rem);
    z-index: 5;
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.15);
  }
  .entity-grid tbody th.row-index {
    position: sticky;
    left: var(--lock-rail-width, 3rem);
    z-index: 2;
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.15);
  }
  .row-index {
    background: #1a1a2e;
    color: #c0c0d0;
    text-align: center !important;
    font-weight: 500;
    padding: 0;
  }
  .corner { background: #1a1a2e; }
  .entity-row:hover td { background: rgba(255,255,255,0.02); }
  .entity-row.selected td,
  .entity-row.selected th.row-index { background: rgba(102, 171, 255, 0.12); }
  .entity-row.selected:hover td,
  .entity-row.selected:hover th.row-index { background: rgba(102, 171, 255, 0.16); }
  .entity-row.find-highlight td,
  .entity-row.find-highlight th.row-index { background: rgba(255, 136, 102, 0.18); }
  .entity-row.find-highlight:hover td,
  .entity-row.find-highlight:hover th.row-index { background: rgba(255, 136, 102, 0.24); }

  .cell-input { box-sizing: border-box; width: 100%; height: 100%; border: none; background: transparent; color: #e0e0e0; font-size: 0.78rem; padding: 0 0.5rem; font-family: inherit; }
  .cell-input:focus { outline: none; background: rgba(255,136,102,0.08); box-shadow: inset 0 0 0 1px rgba(255,136,102,0.45); }
  .cell-input.active-cell { box-shadow: inset 0 0 0 1px rgba(102, 171, 255, 0.65); background: rgba(102, 171, 255, 0.09); }
  .cell-input.selected-range { background: rgba(102, 171, 255, 0.12); }
  .cell-input[readonly] { color: #b9b9c5; }
  .readonly-cell { background: rgba(255,255,255,0.02); }

  .lock-btn {
    box-sizing: border-box;
    width: 100%;
    height: calc(var(--table-row-height, 34px) + var(--table-grid-border-width, 1px));
    border: none;
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    background: transparent;
    color: #c8c8d3;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .lock-btn:hover { background: rgba(255,255,255,0.08); color: #ff8866; }
  .lock-icon { display: block; }
</style>
