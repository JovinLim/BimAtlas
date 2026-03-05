<script lang="ts">
  import type { SpreadsheetCellState } from "$lib/table/engine";
  import type { SheetEntry } from "$lib/table/types";

  function closeContextMenuOnOutsideClick() {
    const menu = contextMenu;
    if (menu == null) return;
    const el = document.querySelector("[data-sheet-context-menu]");
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (el && !el.contains(target)) closeContextMenu();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeContextMenu();
    };
    document.addEventListener("mousedown", onMouseDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("mousedown", onMouseDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }
  $effect(closeContextMenuOnOutsideClick);

  type Props = {
    entries: SheetEntry[];
    rowStart?: number;
    /** Column widths from the top grid’s calculated (rendered) widths; bottom sheet follows these only. */
    getColumnWidthPx: (col: string) => number;
    onEntriesChange?: (entries: SheetEntry[]) => void;
    lockedEntryIds: Set<string>;
    onToggleEntryLock: (entryId: string) => void;
    activeCellRef: string | null;
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
    isCellInSelection: (ref: string) => boolean;
    onCellPointerDown: (
      cell: SpreadsheetCellState,
      event: MouseEvent,
    ) => boolean | void;
    onCellPointerEnter: (cell: SpreadsheetCellState, event: MouseEvent) => void;
    onCellPointerUp: (cell: SpreadsheetCellState, event: MouseEvent) => void;
    /** Template save/load (optional). When projectId is set, toolbar shows template controls. */
    projectId?: string | null;
    templateSearchQuery?: string;
    onTemplateSearchChange?: (query: string) => void;
    templateResults?: { id: string; name: string }[];
    loadingTemplates?: boolean;
    onLoadTemplate?: (template: { id: string; name: string }) => void;
    onSaveTemplate?: () => void;
  };

  let {
    entries,
    rowStart = 2,
    getColumnWidthPx,
    onEntriesChange,
    lockedEntryIds,
    onToggleEntryLock,
    activeCellRef,
    getCellDisplayValue,
    onCellFocus,
    onCellInput,
    onCellCommit,
    onCellCancel,
    onCellNavigate,
    onFillDown,
    isCellInSelection,
    onCellPointerDown,
    onCellPointerEnter,
    onCellPointerUp,
    projectId = null,
    templateSearchQuery = "",
    onTemplateSearchChange,
    templateResults = [],
    loadingTemplates = false,
    onLoadTemplate,
    onSaveTemplate,
  }: Props = $props();

  let templateSearchFocused = $state(false);
  let templateDropdownRef = $state<HTMLDivElement | null>(null);

  function newEntry(): SheetEntry {
    const id = crypto.randomUUID?.() ?? `sheet-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    return { id, entityGlobalId: null, category: "", label: "", value: "", notes: "", tag: "" };
  }

  function addEntry() {
    onEntriesChange?.([...entries, newEntry()]);
  }

  let contextMenu = $state<{ x: number; y: number; rowIndex: number } | null>(null);

  function addRowAbove(rowIndex: number) {
    const idx = rowIndex;
    const entry = newEntry();
    onEntriesChange?.([...entries.slice(0, idx), entry, ...entries.slice(idx)]);
    contextMenu = null;
  }

  function addRowBelow(rowIndex: number) {
    const idx = rowIndex + 1;
    const entry = newEntry();
    onEntriesChange?.([...entries.slice(0, idx), entry, ...entries.slice(idx)]);
    contextMenu = null;
  }

  function deleteRow(rowIndex: number) {
    onEntriesChange?.(entries.filter((_, i) => i !== rowIndex));
    contextMenu = null;
  }

  function openContextMenu(e: MouseEvent, rowIndex: number) {
    e.preventDefault();
    contextMenu = { x: e.clientX, y: e.clientY, rowIndex };
  }

  function closeContextMenu() {
    contextMenu = null;
  }

  function isEntryLocked(entryId: string): boolean {
    return lockedEntryIds.has(entryId);
  }

  function buildCell(
    row: number,
    col: string,
    editable: boolean,
    isProtected: boolean,
  ): SpreadsheetCellState {
    return {
      surface: "sheet",
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

<div class="bottom-sheet">
  <div class="sheet-toolbar">
    <button type="button" class="sheet-add-btn" onclick={addEntry}>+ Add row</button>
    {#if projectId}
      <button
        type="button"
        class="sheet-save-btn"
        onclick={onSaveTemplate}
        disabled={!onSaveTemplate}
        aria-label="Save Sheet Template"
      >
        Save Sheet Template
      </button>
      <div class="template-search-wrap">
        <input
          type="text"
          class="template-search-input"
          placeholder="Search Sheet Templates"
          value={templateSearchQuery}
          oninput={(e) => onTemplateSearchChange?.(e.currentTarget.value)}
          onfocus={() => (templateSearchFocused = true)}
          onblur={() => setTimeout(() => (templateSearchFocused = false), 150)}
          aria-label="Search Sheet Templates"
        />
        {#if templateSearchFocused || (templateSearchQuery && templateResults.length > 0)}
          <div class="template-dropdown" bind:this={templateDropdownRef} role="listbox">
            {#if loadingTemplates}
              <div class="template-dropdown-item muted">Loading...</div>
            {:else if templateResults.length === 0 && templateSearchQuery}
              <div class="template-dropdown-item muted">No templates found</div>
            {:else}
              {#each templateResults as t (t.id)}
                <button
                  type="button"
                  class="template-dropdown-item"
                  role="option"
                  aria-selected="false"
                  onmousedown={(e) => {
                    e.preventDefault();
                    onLoadTemplate?.(t);
                  }}
                >
                  {t.name}
                </button>
              {/each}
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>
  <div class="sheet-table-wrap">
    <div class="sheet-grid-content">
      <div class="lock-rail" aria-label="Sheet row actions">
        <div class="lock-rail-corner mono">LOCK</div>
        {#if entries.length > 0}
          {#each entries as entry, idx (entry.id)}
            {@const locked = isEntryLocked(entry.id)}
            <button
              type="button"
              class="sheet-lock-btn"
              aria-label={locked ? "Unlock row" : "Lock row"}
              title={locked ? "Unlock row" : "Lock row"}
              onclick={() => onToggleEntryLock(entry.id)}
              oncontextmenu={(e) => openContextMenu(e, idx)}
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
        {/if}
      </div>
      <table class="sheet-table" role="grid" aria-label="Sheet interactions">
        <colgroup>
          <col class="col-rownum" />
          <col class="col-globalId" style="width: {getColumnWidthPx('A')}px; min-width: {getColumnWidthPx('A')}px; max-width: {getColumnWidthPx('A')}px;" />
          <col class="col-ifcClass" style="width: {getColumnWidthPx('B')}px; min-width: {getColumnWidthPx('B')}px; max-width: {getColumnWidthPx('B')}px;" />
          <col class="col-name" style="width: {getColumnWidthPx('C')}px; min-width: {getColumnWidthPx('C')}px; max-width: {getColumnWidthPx('C')}px;" />
          <col class="col-description" style="width: {getColumnWidthPx('D')}px; min-width: {getColumnWidthPx('D')}px; max-width: {getColumnWidthPx('D')}px;" />
          <col class="col-objectType" style="width: {getColumnWidthPx('E')}px; min-width: {getColumnWidthPx('E')}px; max-width: {getColumnWidthPx('E')}px;" />
          <col class="col-tag" style="width: {getColumnWidthPx('F')}px; min-width: {getColumnWidthPx('F')}px; max-width: {getColumnWidthPx('F')}px;" />
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
        </thead>
        <tbody>
          {#if entries.length > 0}
            {#each entries as entry, idx (entry.id)}
              {@const row = rowStart + idx}
              {@const rowLocked = isEntryLocked(entry.id)}
              <tr
                class="sheet-row"
                oncontextmenu={(e) => openContextMenu(e, idx)}
              >
                <th class="row-index" scope="row">{row}</th>
                <td class="col-globalId">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `A${row}`}
                  class:selected-range={isCellInSelection(`A${row}`)}
                  data-cell-ref={`A${row}`}
                  value={getCellDisplayValue(`A${row}`, entry.entityGlobalId ?? "")}
                  readonly={rowLocked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "A", !rowLocked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "A", !rowLocked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "A", !rowLocked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "A", !rowLocked, false))}
                  oninput={(e) => onCellInput(buildCell(row, "A", !rowLocked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "A", !rowLocked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "A", !rowLocked, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-ifcClass">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `B${row}`}
                  class:selected-range={isCellInSelection(`B${row}`)}
                  data-cell-ref={`B${row}`}
                  value={getCellDisplayValue(`B${row}`, entry.category)}
                  readonly={rowLocked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "B", !rowLocked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "B", !rowLocked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "B", !rowLocked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "B", !rowLocked, false))}
                  oninput={(e) => onCellInput(buildCell(row, "B", !rowLocked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "B", !rowLocked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "B", !rowLocked, false),
                      getCellDisplayValue(`B${row}`, entry.category),
                    )}
                />
              </td>
              <td class="col-name">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `C${row}`}
                  class:selected-range={isCellInSelection(`C${row}`)}
                  data-cell-ref={`C${row}`}
                  value={getCellDisplayValue(`C${row}`, entry.label)}
                  readonly={rowLocked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "C", !rowLocked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "C", !rowLocked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "C", !rowLocked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "C", !rowLocked, false))}
                  oninput={(e) => onCellInput(buildCell(row, "C", !rowLocked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "C", !rowLocked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "C", !rowLocked, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-description">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `D${row}`}
                  class:selected-range={isCellInSelection(`D${row}`)}
                  data-cell-ref={`D${row}`}
                  value={getCellDisplayValue(`D${row}`, entry.value)}
                  readonly={rowLocked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "D", !rowLocked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "D", !rowLocked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "D", !rowLocked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "D", !rowLocked, false))}
                  oninput={(e) => onCellInput(buildCell(row, "D", !rowLocked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "D", !rowLocked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "D", !rowLocked, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-objectType">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `E${row}`}
                  class:selected-range={isCellInSelection(`E${row}`)}
                  data-cell-ref={`E${row}`}
                  value={getCellDisplayValue(`E${row}`, entry.notes)}
                  readonly={rowLocked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "E", !rowLocked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "E", !rowLocked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "E", !rowLocked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "E", !rowLocked, false))}
                  oninput={(e) => onCellInput(buildCell(row, "E", !rowLocked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "E", !rowLocked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "E", !rowLocked, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-tag">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `F${row}`}
                  class:selected-range={isCellInSelection(`F${row}`)}
                  data-cell-ref={`F${row}`}
                  value={getCellDisplayValue(`F${row}`, entry.tag)}
                  readonly={rowLocked}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "F", !rowLocked, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "F", !rowLocked, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "F", !rowLocked, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "F", !rowLocked, false))}
                  oninput={(e) => onCellInput(buildCell(row, "F", !rowLocked, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "F", !rowLocked, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "F", !rowLocked, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  </div>

  {#if contextMenu}
    <div
      data-sheet-context-menu
      class="sheet-context-menu"
      style="left: {contextMenu.x}px; top: {contextMenu.y}px;"
      role="menu"
    >
      <button
        type="button"
        role="menuitem"
        class="sheet-context-item"
        onclick={() => addRowAbove(contextMenu!.rowIndex)}
      >
        Add row above
      </button>
      <button
        type="button"
        role="menuitem"
        class="sheet-context-item"
        onclick={() => addRowBelow(contextMenu!.rowIndex)}
      >
        Add row below
      </button>
      <button
        type="button"
        role="menuitem"
        class="sheet-context-item sheet-context-item-danger"
        onclick={() => deleteRow(contextMenu!.rowIndex)}
      >
        Delete row
      </button>
    </div>
  {/if}
</div>

<style>
  .bottom-sheet { display: flex; flex-direction: column; flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: hidden; }
  .sheet-toolbar { flex-shrink: 0; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
  .sheet-add-btn { padding: 0.3rem 0.6rem; font-size: 0.78rem; background: color-mix(in srgb, var(--color-brand-500) 10%, transparent); border: 1px solid color-mix(in srgb, var(--color-brand-500) 25%, transparent); border-radius: 0.3rem; color: var(--color-brand-500); cursor: pointer; }
  .sheet-add-btn:hover { background: color-mix(in srgb, var(--color-brand-500) 18%, transparent); }
  .sheet-save-btn { padding: 0.3rem 0.6rem; font-size: 0.78rem; background: var(--color-bg-elevated); border: 1px solid var(--color-border-default); border-radius: 0.3rem; color: var(--color-text-secondary); cursor: pointer; }
  .sheet-save-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--color-text-primary) 6%, var(--color-bg-elevated)); color: var(--color-text-primary); }
  .sheet-save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .template-search-wrap { position: relative; min-width: 10rem; width: 12rem; }
  .template-search-input { width: 100%; box-sizing: border-box; padding: 0.25rem 0.5rem; font-size: 0.78rem; border-radius: 0.25rem; border: 1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-text-primary); }
  .template-search-input::placeholder { color: var(--color-text-muted); }
  .template-dropdown { position: absolute; top: 100%; left: 0; width: 100%; box-sizing: border-box; margin-top: 0.15rem; padding: 0.25rem 0; max-height: 12rem; overflow-y: auto; border-radius: 0.3rem; border: 1px solid var(--color-border-default); background: var(--color-bg-surface); box-shadow: 0 4px 12px rgba(0,0,0,0.08); z-index: 100; }
  .template-dropdown-item { display: block; width: 100%; padding: 0.35rem 0.6rem; font-size: 0.8rem; text-align: left; border: none; background: transparent; color: var(--color-text-primary); cursor: pointer; }
  .template-dropdown-item:hover { background: color-mix(in srgb, var(--color-brand-500) 10%, transparent); color: var(--color-brand-500); }
  .template-dropdown-item.muted { color: var(--color-text-muted); cursor: default; }

  .sheet-table-wrap { flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: auto; }
  .sheet-grid-content { display: grid; grid-template-columns: var(--lock-rail-width, 3rem) minmax(0, 1fr); width: max-content; min-width: 100%; }

  .lock-rail {
    position: sticky;
    left: 0;
    z-index: 6;
    background: var(--color-bg-surface);
    border-right: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, var(--color-border-subtle));
    flex-shrink: 0;
  }
  .lock-rail-corner {
    position: sticky;
    top: 0;
    z-index: 7;
    height: calc(var(--table-header-height, 28px) + var(--table-grid-border-width, 1px));
    min-height: calc(var(--table-header-height, 28px) + var(--table-grid-border-width, 1px));
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    color: var(--color-text-secondary);
    background: var(--color-bg-surface);
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, var(--color-border-subtle));
  }
  .mono { font-family: "SF Mono", "Fira Code", monospace; }

  .sheet-lock-btn {
    box-sizing: border-box;
    width: 100%;
    height: calc(var(--table-row-height, 34px) + var(--table-grid-border-width, 1px));
    border: none;
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, var(--color-border-subtle));
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    line-height: 1;
  }
  .sheet-lock-btn:hover {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
    color: var(--color-brand-500);
  }
  .lock-icon { display: block; }

  .sheet-table { width: max-content; min-width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.78rem; }
  .sheet-table col.col-rownum { width: 2.8rem; }
  /* Column widths come from top grid’s calculated widths via getColumnWidthPx; no local width rules. */

  .sheet-table th, .sheet-table td {
    border-right: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, var(--color-border-subtle));
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, var(--color-border-subtle));
    padding: 0;
    height: var(--table-row-height, 34px);
    overflow: hidden;
  }
  .letters-row th {
    position: sticky;
    top: 0;
    z-index: 2;
    height: var(--table-header-height, 28px);
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
    text-align: center;
    font-weight: 600;
  }
  .corner { background: var(--color-bg-surface); }
  .row-index { background: var(--color-bg-surface); color: var(--color-text-secondary); text-align: center; font-weight: 500; }
  .sheet-row:hover td { background: color-mix(in srgb, var(--color-text-primary) 2%, transparent); }

  .sheet-input { box-sizing: border-box; width: 100%; height: 100%; border: none; background: transparent; color: var(--color-text-primary); font-size: 0.78rem; padding: 0 0.5rem; }
  .sheet-input:focus { outline: none; background: color-mix(in srgb, var(--color-brand-500) 6%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--color-brand-500) 35%, transparent); }
  .sheet-input.active-cell { box-shadow: inset 0 0 0 1px rgba(102, 171, 255, 0.65); background: rgba(102, 171, 255, 0.09); }
  .sheet-input.selected-range { background: rgba(102, 171, 255, 0.12); }
  .sheet-input[readonly] { color: var(--color-text-muted); }

  .sheet-context-menu {
    position: fixed;
    z-index: 1000;
    min-width: 10rem;
    padding: 0.25rem 0;
    border-radius: 0.35rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }
  .sheet-context-item {
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
  .sheet-context-item:hover {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  .sheet-context-item-danger:hover {
    background: color-mix(in srgb, var(--color-danger) 12%, transparent);
    color: var(--color-danger);
  }
</style>
