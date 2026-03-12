<script lang="ts">
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
  <title>BimAtlas</title>
  <meta
    name="description"
    content="Extensible Spatial-Graph Engine for IFC models"
  />
</svelte:head>

{@render children()}

<style>
  :root {
    /* Brand: Deep Slate & Architectural Bronze */
    --color-brand-500: #1e293b;
    --color-brand-400: #334155;
    --color-brand-gradient-start: #0f172a;
    --color-brand-gradient-end: #334155;

    /* Backgrounds: Warm Sand & Stone */
    --color-bg-canvas: #f8f8f2;
    --color-bg-surface: #ffffff;
    --color-bg-elevated: #f1f1eb;

    /* Typography: Technical Ink */
    --color-text-primary: #0f172a;
    --color-text-secondary: #64748b;
    --color-text-muted: #94a3b8;

    /* Borders & Geometry: Technical Graphite */
    --color-border-subtle: #e2e2da;
    --color-border-default: #cbd5e1;
    --color-border-strong: #1e293b;

    /* Functional: Muted Professional Tones */
    --color-action-primary: #334155;
    --color-warning: #b45309;
    --color-danger: #991b1b;
    --color-danger-soft: #fee2e2;
    --color-info: #475569;

    /* IFC & Graph Specifics */
    --color-success: #334155;
    --color-graph-node: #78350f;
    --color-graph-edge: #d4d4ce;

    /* Chevrons */
    --chevron-size: 0.75rem;
    --chevron-color: var(--color-text-muted);
  }

  :global(*),
  :global(*::-webkit-scrollbar) {
    scrollbar-width: thin;
    scrollbar-color: rgba(0, 0, 0, 0.18) transparent;
  }

  :global(html) {
    color-scheme: light;
  }

  :global(html, body) {
    margin: 0;
    padding: 0;
    height: 100%;
    overflow: hidden;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
  }

  :global(h1, h2, h3, h4, h5, h6) {
    margin: 0;
    margin-block: 0;
  }

  :global(::-webkit-scrollbar) {
    width: 8px;
    height: 8px;
  }

  :global(::-webkit-scrollbar-track) {
    background: transparent;
  }

  :global(::-webkit-scrollbar-thumb) {
    background: rgba(0, 0, 0, 0.18);
    border-radius: 4px;
  }

  :global(::-webkit-scrollbar-thumb:hover) {
    background: rgba(0, 0, 0, 0.28);
  }

  :global(::-webkit-scrollbar-corner) {
    background: transparent;
  }

  /* ---- Global form controls (input, select) ---- */
  :global(.input),
  :global(.input-sm) {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-primary);
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s;
  }

  :global(.input) {
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
  }

  :global(.input-sm) {
    padding: 0.35rem 0.5rem;
    font-size: 0.8rem;
  }

  /* Selector / scope-trigger: rounded panels per style.md (border-radius 12px, bg-surface) */
  :global(.selector),
  :global(.scope-trigger),
  :global(.dropdown-trigger) {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 0.75rem;
    color: var(--color-text-primary);
    padding: 0.35rem 0.5rem;
    font-size: 0.8rem;
    font-family: inherit;
    cursor: pointer;
    outline: none;
    transition: border-color 0.15s;
  }

  :global(.scope-trigger),
  :global(.dropdown-trigger) {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    min-width: 6rem;
  }

  :global(select.selector) {
    min-width: 6rem;
  }

  :global(.input:focus),
  :global(.input-sm:focus),
  :global(.selector:focus) {
    border-color: var(--color-border-strong);
  }

  :global(.input:focus-visible),
  :global(.input-sm:focus-visible),
  :global(.selector:focus-visible) {
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 25%, transparent);
  }

  :global(.input::placeholder),
  :global(.input-sm::placeholder) {
    color: var(--color-text-muted);
  }

  /* Select: remove native appearance, add custom arrow */
  :global(select.input),
  :global(select.input-sm),
  :global(select.selector) {
    appearance: none;
    -webkit-appearance: none;
    -moz-appearance: none;
    cursor: pointer;
    padding-right: 1.75rem;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2364748b' d='M3 4.5l3 3 3-3'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.5rem center;
  }

  :global(select.input option),
  :global(select.input-sm option),
  :global(select.selector option) {
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
  }

  /* ---- Global dropdown (custom select / listbox panel) ---- */
  :global(.dropdown),
  :global(.scope-dropdown) {
    margin: 0;
    padding: 0.25rem 0;
    list-style: none;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 0.75rem;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    min-width: 100%;
    font-family: inherit;
  }

  :global(.scope-selector) {
    position: relative;
    flex-shrink: 0;
  }

  :global(.scope-dropdown) {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 0.2rem;
    z-index: 100;
  }

  :global(.dropdown-option),
  :global(.scope-option) {
    padding: 0.35rem 0.5rem;
    font-size: 0.8rem;
    color: var(--color-text-primary);
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }

  :global(.dropdown-option:hover),
  :global(.scope-option:hover) {
    background: color-mix(in srgb, var(--color-action-primary) 10%, transparent);
    color: var(--color-action-primary);
  }

  :global(.dropdown-option.selected),
  :global(.scope-option.selected) {
    background: color-mix(in srgb, var(--color-action-primary) 12%, transparent);
    color: var(--color-action-primary);
  }

  :global(.scope-trigger:hover),
  :global(.dropdown-trigger:hover),
  :global(.selector:hover) {
    border-color: var(--color-border-strong);
  }

  :global(.scope-trigger:focus-visible),
  :global(.dropdown-trigger:focus-visible),
  :global(.selector:focus-visible) {
    border-color: var(--color-border-strong);
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 25%, transparent);
  }

  /* ---- Global buttons ---- */
  :global(.btn) {
    padding: 0.55rem 1.15rem;
    font-size: 0.82rem;
    border: 1px solid transparent;
    border-radius: 0.5rem;
    cursor: pointer;
    font-weight: 500;
    transition:
      background 0.15s,
      opacity 0.15s,
      border-color 0.15s;
  }

  :global(.btn:disabled) {
    opacity: 0.4;
    cursor: not-allowed;
  }

  :global(.btn-sm) {
    padding: 0.35rem 0.65rem;
    font-size: 0.78rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    background: var(--color-bg-elevated);
    color: var(--color-text-secondary);
    cursor: pointer;
    font-weight: 500;
    transition:
      background 0.15s,
      opacity 0.15s,
      border-color 0.15s;
  }

  :global(.btn-sm:hover) {
    background: color-mix(
      in srgb,
      var(--color-text-primary) 6%,
      var(--color-bg-elevated)
    );
    color: var(--color-text-primary);
  }

  :global(.btn-sm:focus-visible) {
    outline: 2px solid var(--color-border-strong);
    outline-offset: 2px;
  }

  :global(.btn-sm:disabled) {
    opacity: 0.6;
    cursor: not-allowed;
  }

  :global(.btn-primary) {
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
    border-color: var(--color-action-primary);
  }

  :global(.btn-primary:hover:not(:disabled)) {
    background: var(--color-brand-500);
    border-color: var(--color-brand-500);
    color: var(--color-bg-surface);
  }

  :global(.btn-secondary) {
    background: var(--color-bg-elevated);
    border-color: var(--color-border-default);
    color: var(--color-text-secondary);
  }

  :global(.btn-secondary:hover:not(:disabled)) {
    background: color-mix(
      in srgb,
      var(--color-text-primary) 8%,
      var(--color-bg-elevated)
    );
    color: var(--color-text-primary);
  }

  :global(.btn-success) {
    background: var(--color-success);
    color: var(--color-bg-surface);
    border-color: var(--color-success);
  }

  :global(.btn-success:hover:not(:disabled)) {
    background: var(--color-brand-500);
    border-color: var(--color-brand-500);
    color: var(--color-bg-surface);
  }

  :global(.btn-danger) {
    background: color-mix(in srgb, var(--color-danger) 10%, transparent);
    border-color: color-mix(in srgb, var(--color-danger) 30%, transparent);
    color: var(--color-danger);
  }

  :global(.btn-danger:hover:not(:disabled)) {
    background: color-mix(in srgb, var(--color-danger) 18%, transparent);
    color: var(--color-danger);
  }

  :global(.btn-icon) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0.35rem 0.5rem;
    font-size: 0.75rem;
    border-radius: 0.25rem;
  }

  :global(.btn-icon:hover) {
    color: var(--color-text-secondary);
  }

  :global(.btn-icon:focus-visible) {
    outline: 2px solid var(--color-border-strong);
    outline-offset: 2px;
  }

  :global(.btn-icon.btn-danger) {
    background: none;
    border: none;
    color: var(--color-text-muted);
  }

  :global(.btn-icon.btn-danger:hover:not(:disabled)) {
    color: var(--color-danger);
  }

  :global(.btn-icon-primary) {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    border: none;
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
  }

  :global(.btn-icon-primary:disabled) {
    opacity: 0.5;
    cursor: default;
  }

  :global(.toolbar-btn) {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.4rem 0.8rem;
    font-size: 0.78rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    background: color-mix(in srgb, var(--color-bg-surface) 95%, transparent);
    color: var(--color-text-secondary);
    cursor: pointer;
    font-weight: 500;
    backdrop-filter: blur(8px);
    transition: background 0.15s, color 0.15s;
  }

  :global(.toolbar-btn:hover) {
    background: color-mix(in srgb, var(--color-brand-500) 8%, transparent);
    color: var(--color-brand-500);
  }

  :global(.btn-close) {
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s;
  }

  :global(.btn-close:hover) {
    color: var(--color-text-secondary);
  }

  :global(.toast-close) {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0.15rem;
    display: flex;
    opacity: 0.6;
    transition: opacity 0.15s;
  }

  :global(.toast-close:hover) {
    opacity: 1;
  }

  :global(.btn-guide) {
    font-size: 0.72rem;
    padding: 0.35rem 0.65rem;
    background: var(--color-bg-elevated);
    color: var(--color-text-muted);
  }

  :global(.btn-guide:hover) {
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    color: var(--color-action-primary);
  }

  :global(.btn-mode) {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.25rem;
    color: var(--color-text-muted);
    padding: 0.35rem 0.5rem;
    font-size: 0.78rem;
    cursor: pointer;
    font-weight: 500;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }

  :global(.btn-mode:hover) {
    color: var(--color-text-secondary);
  }

  :global(.btn-mode.active) {
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    color: var(--color-action-primary);
    border-color: color-mix(in srgb, var(--color-action-primary) 35%, transparent);
  }

  :global(.btn-add) {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: var(--color-bg-elevated);
    border: 1px dashed var(--color-border-default);
    border-radius: 0.35rem;
    color: var(--color-text-muted);
    padding: 0.35rem 0.65rem;
    font-size: 0.78rem;
    cursor: pointer;
    font-weight: 500;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }

  :global(.btn-add:hover) {
    background: color-mix(in srgb, var(--color-action-primary) 12%, transparent);
    color: var(--color-action-primary);
    border-color: color-mix(in srgb, var(--color-action-primary) 35%, transparent);
  }

  /* ---- Global chevrons ---- */
  :global(.chevron),
  :global(.section-chevron),
  :global(.scope-chevron),
  :global(.revision-filter-group-chevron),
  :global(.tool-chevron),
  :global(.meta-chevron) {
    font-size: var(--chevron-size);
    color: var(--chevron-color);
    transition: transform 0.15s;
    flex-shrink: 0;
    display: inline-block;
    line-height: 1;
  }

  :global(.chevron.open),
  :global(.section-chevron.open),
  :global(.tool-chevron.open),
  :global(.meta-chevron.open) {
    transform: rotate(90deg);
  }

  :global(.scope-chevron.open) {
    transform: rotate(180deg);
  }

  :global(.revision-filter-group-chevron.collapsed) {
    transform: rotate(90deg);
  }

  /* ---- Standardised page headers ---- */
  :global(.page-header),
  :global(.table-header) {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: var(--color-bg-surface);
    border-bottom: 1px solid var(--color-border-subtle);
  }

  :global(.page-header h2),
  :global(.table-header h2) {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-action-primary);
  }

  :global(.page-header-title-row) {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }

  :global(.page-header.page-header--stacked) {
    align-items: flex-start;
  }
</style>
