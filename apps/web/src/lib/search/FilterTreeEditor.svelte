<script lang="ts">
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import {
    type FilterGroup,
    type FilterLeaf,
    type SearchFilter,
  } from "$lib/search/protocol";

  let {
    root,
    onUpdateRootOp,
    onAddFilter,
    onAddSubgroup,
    onUpdateLeaf,
    onUpdateSubgroup,
    onRemoveSubgroup,
    onRemoveLeaf,
    openMenuPath,
    onToggleMenu,
  }: {
    root: FilterGroup;
    onUpdateRootOp: (op: "ALL" | "ANY") => void;
    onAddFilter: (parentPath: string) => void;
    onAddSubgroup: (parentPath: string) => void;
    onUpdateLeaf: (path: string, patch: Partial<SearchFilter>) => void;
    onUpdateSubgroup: (path: string, op: "ALL" | "ANY") => void;
    onRemoveSubgroup: (path: string) => void;
    onRemoveLeaf: (path: string) => void;
    openMenuPath: string | null;
    onToggleMenu: (path: string | null) => void;
  } = $props();

  function leafToSearchFilter(leaf: FilterLeaf, id: string): SearchFilter {
    return {
      id,
      mode: leaf.mode,
      ifcClass: leaf.ifcClass,
      attribute: leaf.attribute,
      value: leaf.value,
      relation: leaf.relation,
      operator: leaf.operator,
      valueType: leaf.valueType,
      relationTargetClass: leaf.relationTargetClass,
      relationTargetAttribute: leaf.relationTargetAttribute,
      relationTargetOperator: leaf.relationTargetOperator,
      relationTargetValue: leaf.relationTargetValue,
      relationTargetValueType: leaf.relationTargetValueType,
    };
  }

  function leafFromSearchFilter(sf: SearchFilter): FilterLeaf {
    return {
      kind: "leaf",
      mode: sf.mode,
      ifcClass: sf.ifcClass,
      attribute: sf.attribute,
      value: sf.value,
      relation: sf.relation,
      operator: sf.operator,
      valueType: sf.valueType,
      relationTargetClass: sf.relationTargetClass,
      relationTargetAttribute: sf.relationTargetAttribute,
      relationTargetOperator: sf.relationTargetOperator,
      relationTargetValue: sf.relationTargetValue,
      relationTargetValueType: sf.relationTargetValueType,
    };
  }

  let collapsedPaths = $state<Set<string>>(new Set());

  function toggleCollapsed(path: string) {
    collapsedPaths = new Set(collapsedPaths);
    if (collapsedPaths.has(path)) collapsedPaths.delete(path);
    else collapsedPaths.add(path);
  }

  $effect(() => {
    if (!openMenuPath) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      const wrap = document.querySelector(`[data-menu-path="${openMenuPath}"]`);
      if (wrap?.contains(target)) return;
      onToggleMenu(null);
    }
    document.addEventListener("click", handleClick, true);
    return () => document.removeEventListener("click", handleClick, true);
  });
</script>

<div class="filter-tree">
  <div class="root-group">
    <div class="group-header group-header-root">
      <span class="group-label">Match</span>
      <div class="logic-toggle">
        <button
          type="button"
          class="btn-mode"
          class:active={root.op === "ALL"}
          onclick={() => onUpdateRootOp("ALL")}
        >ALL</button>
        <button
          type="button"
          class="btn-mode"
          class:active={root.op === "ANY"}
          onclick={() => onUpdateRootOp("ANY")}
        >ANY</button>
      </div>
      <span class="group-label">of the following:</span>
    </div>
  {#if root.children.length === 0}
    <div class="empty-row add-row depth-0">
      <div class="row-content add-row-buttons">
        <button class="btn-add" type="button" onclick={() => onAddFilter("")}>
          Add Filter
        </button>
        <button class="btn-add" type="button" onclick={() => onAddSubgroup("")}>
          Add Subgroup
        </button>
      </div>
    </div>
  {:else}
  <div class="root-branch">
    <div class="indent-rail">
      <span class="indent-v"></span>
    </div>
    <div class="root-children">
  {#each root.children as child, idx (idx)}
    {@const path = String(idx)}
    {#if child.kind === "leaf"}
      <div class="tree-row depth-0" data-path={path}>
        <div class="indent-branch indent-branch-h">
          <span class="indent-h"></span>
        </div>
        <div class="row-content">
          <SearchFilterRow
            filter={leafToSearchFilter(child, `f-${path}`)}
            onupdate={(p: Partial<SearchFilter>) => onUpdateLeaf(path, p)}
            onremove={() => onRemoveLeaf(path)}
          />
        </div>
      </div>
    {:else}
      <!-- Subgroup at depth 1 -->
      <div class="tree-group depth-1">
        <div class="group-header-row">
          <div class="indent-branch indent-branch-h">
            <span class="indent-h"></span>
          </div>
          <div class="group-header">
            <button
              type="button"
              class="group-chevron"
              class:collapsed={collapsedPaths.has(path)}
              aria-label={collapsedPaths.has(path) ? "Expand subgroup" : "Collapse subgroup"}
              onclick={() => toggleCollapsed(path)}
            >
              <span class="section-chevron" class:open={!collapsedPaths.has(path)}>▸</span>
            </button>
            <span class="group-label">Match</span>
            <div class="logic-toggle">
              <button
                type="button"
                class="btn-mode"
                class:active={child.op === "ALL"}
                onclick={() => onUpdateSubgroup(path, "ALL")}
              >ALL</button>
              <button
                type="button"
                class="btn-mode"
                class:active={child.op === "ANY"}
                onclick={() => onUpdateSubgroup(path, "ANY")}
              >ANY</button>
            </div>
            <span class="group-label">of the following:</span>
            <button
              type="button"
              class="btn-icon btn-danger group-delete-btn"
              aria-label="Delete subgroup"
              title="Delete subgroup"
              onclick={() => onRemoveSubgroup(path)}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
              </svg>
            </button>
          </div>
        </div>
          {#if !collapsedPaths.has(path)}
          <div class="group-children">
            <div class="indent-rail">
              <span class="indent-v"></span>
            </div>
            <div class="group-rows">
          {#each child.children as subChild, subIdx (subIdx)}
            {@const subPath = `${path}.${subIdx}`}
            {#if subChild.kind === "leaf"}
              <div class="tree-row depth-1" data-path={subPath}>
                <div class="indent-branch indent-branch-h">
                  <span class="indent-h"></span>
                </div>
                <div class="row-content">
                  <SearchFilterRow
                    filter={leafToSearchFilter(subChild, `f-${subPath}`)}
                    onupdate={(p: Partial<SearchFilter>) => onUpdateLeaf(subPath, p)}
                    onremove={() => onRemoveLeaf(subPath)}
                  />
                </div>
              </div>
            {:else}
              <!-- Nested subgroup (filter && subgroup) -->
              <div class="tree-group depth-2">
                <div class="group-header-row">
                  <div class="indent-branch indent-branch-h">
                    <span class="indent-h"></span>
                  </div>
                  <div class="group-header">
                    <button
                      type="button"
                      class="group-chevron"
                      class:collapsed={collapsedPaths.has(subPath)}
                      aria-label={collapsedPaths.has(subPath) ? "Expand subgroup" : "Collapse subgroup"}
                      onclick={() => toggleCollapsed(subPath)}
                    >
                      <span class="section-chevron" class:open={!collapsedPaths.has(subPath)}>▸</span>
                    </button>
                    <span class="group-label">Match</span>
                    <div class="logic-toggle">
                      <button
                        type="button"
                        class="btn-mode"
                        class:active={subChild.op === "ALL"}
                        onclick={() => onUpdateSubgroup(subPath, "ALL")}
                      >ALL</button>
                      <button
                        type="button"
                        class="btn-mode"
                        class:active={subChild.op === "ANY"}
                        onclick={() => onUpdateSubgroup(subPath, "ANY")}
                      >ANY</button>
                    </div>
                    <span class="group-label">of the following:</span>
                    <button
                      type="button"
                      class="btn-icon btn-danger group-delete-btn"
                      aria-label="Delete subgroup"
                      title="Delete subgroup"
                      onclick={() => onRemoveSubgroup(subPath)}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                        <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
                      </svg>
                    </button>
                  </div>
                </div>
                  {#if !collapsedPaths.has(subPath)}
                  <div class="group-children">
                    <div class="indent-rail">
                      <span class="indent-v"></span>
                    </div>
                    <div class="group-rows">
                    {#each subChild.children as subSubChild, subSubIdx (subSubIdx)}
                      {@const subSubPath = `${subPath}.${subSubIdx}`}
                      {#if subSubChild.kind === "leaf"}
                        <div class="tree-row depth-2" data-path={subSubPath}>
                          <div class="indent-branch indent-branch-h">
                            <span class="indent-h"></span>
                          </div>
                          <div class="row-content">
                            <SearchFilterRow
                              filter={leafToSearchFilter(subSubChild, `f-${subSubPath}`)}
                              onupdate={(p: Partial<SearchFilter>) => onUpdateLeaf(subSubPath, p)}
                              onremove={() => onRemoveLeaf(subSubPath)}
                            />
                          </div>
                        </div>
                      {/if}
                    {/each}
                    <div class="add-row depth-2">
                      <div class="indent-branch indent-branch-h">
                        <span class="indent-h"></span>
                      </div>
                      <div class="row-content add-row-buttons">
                        <button class="btn-add" type="button" onclick={() => onAddFilter(subPath)}>
                          Add Filter
                        </button>
                        <button class="btn-add" type="button" onclick={() => onAddSubgroup(subPath)}>
                          Add Subgroup
                        </button>
                      </div>
                    </div>
                    </div>
                  </div>
                  {/if}
              </div>
            {/if}
          {/each}
          <!-- Add row within subgroup -->
          <div class="add-row depth-1">
            <div class="indent-branch indent-branch-h">
              <span class="indent-h"></span>
            </div>
            <div class="row-content add-row-buttons">
              <button class="btn-add" type="button" onclick={() => onAddFilter(path)}>
                Add Filter
              </button>
              <button class="btn-add" type="button" onclick={() => onAddSubgroup(path)}>
                Add Subgroup
              </button>
            </div>
          </div>
            </div>
          </div>
          {/if}
      </div>
    {/if}
  {/each}
  <!-- Add row at root level -->
  <div class="add-row depth-0">
    <div class="indent-branch indent-branch-h">
      <span class="indent-h"></span>
    </div>
    <div class="row-content add-row-buttons">
      <button class="btn-add" type="button" onclick={() => onAddFilter("")}>
        Add Filter
      </button>
      <button class="btn-add" type="button" onclick={() => onAddSubgroup("")}>
        Add Subgroup
      </button>
    </div>
  </div>
    </div>
  </div>
  {/if}
  </div>
</div>

<style>
  .filter-tree {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .root-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .root-branch {
    display: flex;
    align-items: stretch;
    gap: 0.5rem;
  }

  .indent-rail {
    flex-shrink: 0;
    position: relative;
    width: 1rem;
    min-height: 2.5rem;
  }

  .indent-rail .indent-v {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--color-border-subtle);
    border-radius: 1px;
  }

  .root-children {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .tree-row {
    display: flex;
    align-items: flex-start;
    gap: 0;
    min-height: 0;
    min-width: 0;
  }

  .tree-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-height: 0;
  }

  .group-header-row {
    display: flex;
    align-items: center;
    gap: 0;
    min-height: 0;
  }

  .group-header-row .indent-branch-h {
    min-height: 0;
  }

  .empty-row {
    display: flex;
    align-items: center;
    gap: 0;
    padding: 1rem 0.75rem;
    min-height: 2.5rem;
  }

  .indent-branch {
    flex-shrink: 0;
    display: flex;
    align-items: stretch;
    position: relative;
    width: 1rem;
    min-height: 2.5rem;
    margin-right: 0.5rem;
  }

  .indent-branch .indent-h {
    position: absolute;
    left: 0;
    top: 50%;
    width: 0.75rem;
    height: 2px;
    margin-top: -1px;
    background: var(--color-border-subtle);
    border-radius: 1px;
  }

  .add-row {
    display: flex;
    align-items: center;
    gap: 0;
    min-height: 2rem;
  }

  .row-content {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .row-content :global(.filter-row) {
    flex: 1;
    min-width: 0;
  }

  .row-menu {
    position: relative;
    flex-shrink: 0;
  }

  .btn-menu {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 8px;
    padding: 0.35rem 0.5rem;
    color: var(--color-text-muted);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-menu:hover {
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
  }

  .menu-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 0.25rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 50;
    min-width: 140px;
  }

  .menu-dropdown-left {
    right: auto;
    left: 0;
  }

  .menu-item {
    display: block;
    width: 100%;
    padding: 0.5rem 0.75rem;
    text-align: left;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    background: none;
    border: none;
    cursor: pointer;
  }

  .menu-item:hover {
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
  }

  .group-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .group-children {
    display: flex;
    align-items: stretch;
    gap: 0.5rem;
  }

  .group-children .indent-rail {
    flex-shrink: 0;
    position: relative;
    width: 1rem;
    min-height: 2.5rem;
    /* Align vertical rail under the "M" in Match (indent-branch + margin + chevron + gap) */
    margin-left: calc(1rem + 0.5rem + 1rem + 0.5rem);
  }

  .group-children .indent-rail .indent-v {
    position: absolute;
    left: 0;
    top: 0.5rem;
    bottom: 0;
    width: 2px;
    background: var(--color-border-subtle);
    border-radius: 1px;
  }

  .group-rows {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .indent-branch-h {
    flex-shrink: 0;
    position: relative;
    width: 1rem;
    min-height: 2.5rem;
    margin-right: 0.5rem;
  }

  .indent-branch-h .indent-h {
    left: -1.5rem;
    width: 1.75rem;
  }

  .group-header,
  .group-header-root {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0;
    font-size: 0.75rem;
    color: var(--color-text-muted);
    font-weight: 600;
  }

  .group-header .logic-toggle,
  .group-header-root .logic-toggle {
    display: flex;
    gap: 0.25rem;
  }

  .group-label {
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }

  .group-delete-btn {
    margin-left: auto;
  }

  .group-chevron {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    color: var(--color-text-muted);
  }

  .group-chevron .section-chevron {
    font-size: 1rem;
    font-weight: 600;
  }

  .group-chevron:hover {
    color: var(--color-text-secondary);
  }

  .add-row-buttons {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
</style>
