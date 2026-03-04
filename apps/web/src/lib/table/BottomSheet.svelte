<script lang="ts">
  import type { SpreadsheetCellState } from "$lib/table/engine";
  import type { SheetEntry } from "$lib/table/types";

  type Props = {
    entries?: SheetEntry[];
    rowStart?: number;
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
  };

  let {
    entries = $bindable([]),
    rowStart = 2,
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
  }: Props = $props();

  function addEntry() {
    const id = crypto.randomUUID?.() ?? `sheet-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    entries = [
      ...entries,
      { id, entityGlobalId: null, category: "", label: "", value: "", notes: "", tag: "" },
    ];
    onEntriesChange?.(entries);
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
  </div>
  <div class="sheet-table-wrap">
    <div class="sheet-grid-content">
      <div class="lock-rail" aria-label="Sheet row actions">
        <div class="lock-rail-corner mono">LOCK</div>
        {#if entries.length > 0}
          {#each entries as entry (entry.id)}
            {@const locked = isEntryLocked(entry.id)}
            <button
              type="button"
              class="sheet-lock-btn"
              aria-label={locked ? "Unlock row" : "Lock row"}
              title={locked ? "Unlock row" : "Lock row"}
              onclick={() => onToggleEntryLock(entry.id)}
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
        </thead>
        <tbody>
          {#if entries.length > 0}
            {#each entries as entry, idx (entry.id)}
              {@const row = rowStart + idx}
              {@const rowLocked = isEntryLocked(entry.id)}
              <tr class="sheet-row">
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
</div>

<style>
  .bottom-sheet { display: flex; flex-direction: column; flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: hidden; }
  .sheet-toolbar { flex-shrink: 0; padding: 0.35rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06); background: rgba(255,255,255,0.02); }
  .sheet-add-btn { padding: 0.3rem 0.6rem; font-size: 0.78rem; background: rgba(255,136,102,0.15); border: 1px solid rgba(255,136,102,0.35); border-radius: 0.3rem; color: #ff8866; cursor: pointer; }
  .sheet-add-btn:hover { background: rgba(255,136,102,0.25); }

  .sheet-table-wrap { flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: auto; }
  .sheet-grid-content { display: grid; grid-template-columns: var(--lock-rail-width, 3rem) minmax(0, 1fr); width: max-content; min-width: 100%; }

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
  .mono { font-family: "SF Mono", "Fira Code", monospace; }

  .sheet-lock-btn {
    box-sizing: border-box;
    width: 100%;
    height: calc(var(--table-row-height, 34px) + var(--table-grid-border-width, 1px));
    border: none;
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    background: transparent;
    color: #a0a0b0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    line-height: 1;
  }
  .sheet-lock-btn:hover {
    background: rgba(255,255,255,0.08);
    color: #ff8866;
  }
  .lock-icon { display: block; }

  .sheet-table { width: max-content; min-width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.78rem; }
  .sheet-table col.col-rownum { width: 2.8rem; }
  .sheet-table col.col-globalId { width: 16rem; }
  .sheet-table col.col-ifcClass { width: 10rem; }
  .sheet-table col.col-name { width: 10rem; }
  .sheet-table col.col-description { width: 14rem; }
  .sheet-table col.col-objectType { width: 10rem; }
  .sheet-table col.col-tag { width: 8rem; }

  .sheet-table th, .sheet-table td {
    border-right: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    border-bottom: var(--table-grid-border-width, 1px) solid var(--table-grid-border-color, rgba(255,255,255,0.06));
    padding: 0;
    height: var(--table-row-height, 34px);
  }
  .letters-row th {
    position: sticky;
    top: 0;
    z-index: 2;
    height: var(--table-header-height, 28px);
    background: #1a1a2e;
    color: #c0c0d0;
    text-align: center;
    font-weight: 600;
  }
  .corner { background: #1a1a2e; }
  .row-index { background: #1a1a2e; color: #c0c0d0; text-align: center; font-weight: 500; }
  .sheet-row:hover td { background: rgba(255,255,255,0.02); }

  .sheet-input { box-sizing: border-box; width: 100%; height: 100%; border: none; background: transparent; color: #e0e0e0; font-size: 0.78rem; padding: 0 0.5rem; }
  .sheet-input:focus { outline: none; background: rgba(255,136,102,0.08); box-shadow: inset 0 0 0 1px rgba(255,136,102,0.45); }
  .sheet-input.active-cell { box-shadow: inset 0 0 0 1px rgba(102, 171, 255, 0.65); background: rgba(102, 171, 255, 0.09); }
  .sheet-input.selected-range { background: rgba(102, 171, 255, 0.12); }
  .sheet-input[readonly] { color: #b9b9c5; }

</style>
