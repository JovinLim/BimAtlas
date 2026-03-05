<script lang="ts">
  /**
   * Overlay panel that shows details of the currently selected IFC element.
   * Now delegates rendering and data-fetch to AttributePanelContent so the
   * same content can be used in a pop-out tab.
   */
  import {
    getSelection,
    getRevisionState,
    getProjectState,
  } from "$lib/state/selection.svelte";
  import AttributePanelContent from "$lib/ui/AttributePanelContent.svelte";

  const selection = getSelection();
  const revisionState = getRevisionState();
  const projectState = getProjectState();
</script>

{#if selection.activeGlobalId}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_click_events_have_key_events -->
  <aside class="selection-panel">
    <header class="panel-header">
      <h3>Attribute Panel</h3>
      <button class="close-btn" onclick={() => (selection.activeGlobalId = null)}>
        &times;
      </button>
    </header>

    <AttributePanelContent
      branchId={projectState.activeBranchId}
      revision={revisionState.activeRevision}
      globalId={selection.activeGlobalId}
      onSelectGlobalId={(id: string | null) => (selection.activeGlobalId = id)}
    />
  </aside>
{/if}

<style>
	.selection-panel {
		position: absolute;
		top: 1rem;
		right: 1rem;
		bottom: 1rem;
		background: rgba(255, 255, 255, 0.96);
		color: var(--color-text-primary);
		padding: 1rem;
		border-radius: 0.5rem;
		min-width: 260px;
		max-width: 360px;
		max-height: calc(100% - 2rem);
		display: flex;
		flex-direction: column;
		min-height: 0;
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 0.85rem;
		box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
		backdrop-filter: blur(8px);
		z-index: 10;
		user-select: text;
		-webkit-user-select: text;
		pointer-events: auto;
	}

	.panel-header {
		flex-shrink: 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
		border-bottom: 1px solid var(--color-border-default);
		padding-bottom: 0.5rem;
	}

	.panel-body {
		flex: 1 1 0;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		overflow-x: hidden;
	}

	h3 {
		margin: 0;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--color-brand-500);
	}

	.close-btn {
		background: none;
		border: none;
		color: var(--color-text-muted);
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0 0.25rem;
		line-height: 1;
	}
	.close-btn:hover {
		color: var(--color-text-primary);
	}

	.panel-body .detail {
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		margin-bottom: 0.6rem;
	}

	.value-row {
		display: flex;
		align-items: flex-start;
		gap: 0.35rem;
		min-width: 0;
	}

	.value-row .value {
		flex: 1;
		min-width: 0;
	}

	.copy-btn {
		flex-shrink: 0;
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.2rem;
		line-height: 0;
		border-radius: 0.25rem;
	}
	.copy-btn:hover {
		color: var(--color-brand-500);
		background: color-mix(in srgb, var(--color-brand-500) 8%, transparent);
	}

	.label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted);
	}

	.value {
		color: var(--color-text-primary);
		word-break: break-all;
	}

	.mono {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.78rem;
	}

	.badge {
		display: inline-block;
		background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
		color: var(--color-brand-500);
		padding: 0.1rem 0.4rem;
		border-radius: 0.25rem;
		font-size: 0.78rem;
		width: fit-content;
	}

	.badge.secondary {
		background: color-mix(in srgb, var(--color-info) 12%, transparent);
		color: var(--color-info);
	}

	.link-btn {
		background: none;
		border: none;
		color: var(--color-info);
		cursor: pointer;
		padding: 0;
		font-size: 0.82rem;
		text-align: left;
	}
	.link-btn:hover {
		text-decoration: underline;
		color: color-mix(in srgb, var(--color-info) 70%, white);
	}

	.relations-section {
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--color-border-subtle);
	}

	.relation-list {
		list-style: none;
		padding: 0;
		margin: 0.3rem 0 0;
	}

	.relation-list li {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 0.5rem;
		padding: 0.2rem 0;
		min-height: 1.5em;
	}

	.relation-list li .link-btn {
		flex: 1;
		min-width: 0;
		word-break: break-word;
	}

	.rel-type {
		font-size: 0.65rem;
		color: var(--color-text-muted);
		text-align: right;
		white-space: normal;
		word-break: break-word;
		flex-shrink: 0;
		max-width: 55%;
	}

	.pset-list {
		margin-top: 0.4rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.pset-list details {
		background: var(--color-bg-elevated);
		border-radius: 0.25rem;
		padding: 0.25rem 0.4rem;
	}

	.pset-list summary {
		cursor: pointer;
		color: var(--color-text-secondary);
	}

	.pset-props {
		list-style: none;
		padding: 0.25rem 0 0.35rem 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.pset-key {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-right: 0.4rem;
	}

	.pset-value {
		font-size: 0.8rem;
		color: var(--color-text-primary);
		word-break: break-all;
	}

	.panel-body .status-msg {
		flex-shrink: 0;
		color: var(--color-text-muted);
		margin: 0.5rem 0;
		font-size: 0.82rem;
	}

	.error {
		color: var(--color-danger);
	}
</style>
