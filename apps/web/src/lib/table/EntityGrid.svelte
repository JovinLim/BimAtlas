<script lang="ts">
  import type { ProductMeta } from "$lib/search/protocol";
  import type { SpreadsheetCellState } from "$lib/table/engine";

  type EditableKey = "name" | "description" | "objectType" | "tag";
  const EDITABLE_KEYS: EditableKey[] = ["name", "description", "objectType", "tag"];
  const EDITABLE_COL: Record<EditableKey, string> = {
    name: "C",
    description: "D",
    objectType: "E",
    tag: "F",
  };
  const COLUMN_KEYS = {
    A: "globalId",
    B: "ifcClass",
  } as const;

  const HEADER_COLUMNS: { col: "A" | "B" | "C" | "D" | "E" | "F"; key: keyof ProductMeta; label: string }[] = [
    { col: "A", key: "globalId", label: "Global ID" },
    { col: "B", key: "ifcClass", label: "IFC CLASS" },
    { col: "C", key: "name", label: "Name" },
    { col: "D", key: "description", label: "Description" },
    { col: "E", key: "objectType", label: "Object Type" },
    { col: "F", key: "tag", label: "Tag" },
  ];

  type Props = {
    products: ProductMeta[];
    lockedIds: Set<string>;
    onToggleLock: (globalId: string) => void;
    activeCellRef: string | null;
    /** When set, the row with this globalId is shown as selected (whole-row highlight). */
    selectedRowGlobalId: string | null;
    /** When set, the row with this globalId is shown with orange "find" highlight and scrolled into view by parent. */
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
    sortBy: keyof ProductMeta;
    sortDir: "asc" | "desc";
    onSortChange: (column: keyof ProductMeta, direction: "asc" | "desc") => void;
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
    lockedIds,
    onToggleLock,
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

  let openSortColumn = $state<keyof ProductMeta | null>(null);

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

  function buildCell(
    row: number,
    col: string,
    editable: boolean,
    isProtected: boolean,
  ): SpreadsheetCellState {
    return {
      surface: "entity",
      row,
      col,
      ref: `${col}${row}`,
      editable,
      protected: isProtected,
    };
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
        <col class="col-globalId" />
        <col class="col-ifcClass" />
        <col class="col-name" />
        <col class="col-description" />
        <col class="col-objectType" />
        <col class="col-tag" />
      </colgroup>
      <thead>
        <tr class="letters-row">
          <th class="corner" scope="col"></th>
          <th scope="col">A</th>
          <th scope="col">B</th>
          <th scope="col">C</th>
          <th scope="col">D</th>
          <th scope="col">E</th>
          <th scope="col">F</th>
        </tr>
        <tr class="labels-row">
          <th class="row-index" scope="row">1</th>
          {#each HEADER_COLUMNS as { col, key, label }}
            <th scope="col" class="th-sort" data-sort-column={key}>
              <div class="th-sort-inner">
                <span class="th-sort-label">{label}</span>
                <button
                  type="button"
                  class="th-sort-btn"
                  aria-label="Sort column"
                  aria-expanded={openSortColumn === key}
                  aria-haspopup="menu"
                  onclick={() => (openSortColumn = openSortColumn === key ? null : key)}
                >
                  <svg class="th-sort-icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path fill="currentColor" d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/>
                  </svg>
                </button>
                {#if openSortColumn === key}
                  <div class="th-sort-dropdown" role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      class="th-sort-option"
                      class:active={sortBy === key && sortDir === "asc"}
                      onclick={() => {
                        onSortChange(key, "asc");
                        openSortColumn = null;
                      }}
                    >
                      Sort A–Z
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      class="th-sort-option"
                      class:active={sortBy === key && sortDir === "desc"}
                      onclick={() => {
                        onSortChange(key, "desc");
                        openSortColumn = null;
                      }}
                    >
                      Sort Z–A
                    </button>
                  </div>
                {/if}
              </div>
            </th>
          {/each}
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
            <td class="col-globalId">
            <input
              class="cell-input readonly-cell"
              class:active-cell={activeCellRef === `A${row}`}
              class:selected-range={isCellInSelection(`A${row}`)}
              type="text"
              data-cell-ref={`A${row}`}
              value={getCellDisplayValue(`A${row}`, product[COLUMN_KEYS.A] ?? "")}
              readonly
              onmousedown={(e) => {
                if (onCellPointerDown(buildCell(row, "A", false, true), e)) return;
              }}
              onmouseenter={(e) => onCellPointerEnter(buildCell(row, "A", false, true), e)}
              onmouseup={(e) => onCellPointerUp(buildCell(row, "A", false, true), e)}
              onfocus={() => onCellFocus(buildCell(row, "A", false, true))}
              onkeydown={(e) =>
                onCellKeydown(
                  e,
                  buildCell(row, "A", false, true),
                  getCellDisplayValue(`A${row}`, product[COLUMN_KEYS.A] ?? ""),
                )}
            />
            </td>
            <td class="col-ifcClass">
            <input
              class="cell-input readonly-cell"
              class:active-cell={activeCellRef === `B${row}`}
              class:selected-range={isCellInSelection(`B${row}`)}
              type="text"
              data-cell-ref={`B${row}`}
              value={getCellDisplayValue(`B${row}`, product[COLUMN_KEYS.B] ?? "")}
              readonly
              onmousedown={(e) => {
                if (onCellPointerDown(buildCell(row, "B", false, true), e)) return;
              }}
              onmouseenter={(e) => onCellPointerEnter(buildCell(row, "B", false, true), e)}
              onmouseup={(e) => onCellPointerUp(buildCell(row, "B", false, true), e)}
              onfocus={() => onCellFocus(buildCell(row, "B", false, true))}
              onkeydown={(e) =>
                onCellKeydown(
                  e,
                  buildCell(row, "B", false, true),
                  getCellDisplayValue(`B${row}`, product[COLUMN_KEYS.B] ?? ""),
                )}
            />
            </td>
            {#each EDITABLE_KEYS as key}
              {@const col = EDITABLE_COL[key]}
              <td class={"col-" + key}>
                <input
                  class="cell-input"
                  type="text"
                  class:active-cell={activeCellRef === `${col}${row}`}
                  class:selected-range={isCellInSelection(`${col}${row}`)}
                  data-cell-ref={`${col}${row}`}
                  value={getCellDisplayValue(`${col}${row}`, product[key] ?? "")}
                  readonly={locked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, col, !locked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, col, !locked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, col, !locked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, col, !locked, false))}
                  oninput={(e) => onCellInput(buildCell(row, col, !locked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, col, !locked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, col, !locked, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
            {/each}
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
  .entity-grid col.col-globalId { width: 16rem; }
  .entity-grid col.col-ifcClass { width: 10rem; }
  .entity-grid col.col-name { width: 10rem; }
  .entity-grid col.col-description { width: 14rem; }
  .entity-grid col.col-objectType { width: 10rem; }
  .entity-grid col.col-tag { width: 8rem; }

  .entity-grid th, .entity-grid td {
    border-right: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    padding: 0;
    height: var(--table-row-height, 34px);
  }
  .letters-row th {
    position: sticky;
    top: 0;
    z-index: 4;
    height: var(--table-header-height, 28px);
    background: #1a1a2e;
    color: #c0c0d0;
    font-weight: 600;
    text-align: center;
    /* Extend coverage so no content shows through between this row and the labels row when scrolling */
    box-shadow: 0 calc(var(--table-grid-border-width, 1px) + 1px) 0 0 #1a1a2e;
  }
  /* First column (corner + row numbers) stays fixed when scrolling horizontally, next to lock-rail. */
  .corner {
    left: var(--lock-rail-width, 3rem);
    z-index: 8;
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.15);
  }
  .labels-row th {
    position: sticky;
    /* Sit flush under the letters row so no gap shows when scrolling (letters row has shadow to cover any sub-pixel gap) */
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
  }
  .th-sort {
    vertical-align: middle;
    overflow: visible;
  }
  .th-sort-inner {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    position: relative;
    min-height: 1.5rem;
    overflow: visible;
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
