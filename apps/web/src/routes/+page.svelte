<script lang="ts">
	/**
	 * Main BimAtlas page -- integrates the 3D viewport, force graph, and selection panel.
	 * Toggle between 3D View and Graph View via the header toolbar.
	 */
	import Viewport from '$lib/ui/Viewport.svelte';
	import SelectionPanel from '$lib/ui/SelectionPanel.svelte';
	import ForceGraph from '$lib/graph/ForceGraph.svelte';
	import ImportModal from '$lib/ui/ImportModal.svelte';
	import Spinner from '$lib/ui/Spinner.svelte';
	import { getSelection, getRevisionState } from '$lib/state/selection.svelte';
	import { getGraphStore } from '$lib/graph/graphStore.svelte';
	import type { SceneManager } from '$lib/engine/SceneManager';

	const selection = getSelection();
	const revisionState = getRevisionState();
	const graphStore = getGraphStore();

	let sceneManager: SceneManager | undefined = $state(undefined);
	let activeView: 'viewport' | 'graph' = $state('viewport');

	const API_BASE = import.meta.env.VITE_API_URL
		? (import.meta.env.VITE_API_URL as string).replace('/graphql', '')
		: 'http://localhost:8000';

	let showImportModal = $state(false);
	let importing = $state(false);
	let importError = $state<string | null>(null);

	// Load graph data when switching to graph view
	$effect(() => {
		if (activeView === 'graph' && graphStore.data.nodes.length === 0 && !graphStore.loading) {
			graphStore.fetchGraph(revisionState.activeRevision);
		}
	});

	async function handleImportSubmit(file: File) {
		showImportModal = false;
		importing = true;
		importError = null;

		try {
			const formData = new FormData();
			formData.append('file', file);

			const res = await fetch(`${API_BASE}/upload-ifc`, {
				method: 'POST',
				body: formData
			});

			if (!res.ok) {
				const text = await res.text();
				throw new Error(text || `Upload failed (${res.status})`);
			}

			const result = await res.json();
			// Update the active revision to the newly imported one
			revisionState.activeRevision = result.revision_id;
		} catch (err) {
			importError = err instanceof Error ? err.message : 'Import failed';
		} finally {
			importing = false;
		}
	}
</script>

<main>
	<header class="app-header">
		<div class="brand">
			<h1>BimAtlas</h1>
		</div>
		<nav class="view-toggle" role="tablist">
			<button
				class="tab-btn"
				class:active={activeView === 'viewport'}
				role="tab"
				aria-selected={activeView === 'viewport'}
				onclick={() => (activeView = 'viewport')}
			>
				3D View
			</button>
			<button
				class="tab-btn"
				class:active={activeView === 'graph'}
				role="tab"
				aria-selected={activeView === 'graph'}
				onclick={() => (activeView = 'graph')}
			>
				Graph
			</button>
		</nav>
		<div class="header-spacer"></div>
	</header>

	<div class="content">
		{#if activeView === 'viewport'}
			<Viewport bind:manager={sceneManager}>
				{#snippet overlay()}
					<SelectionPanel />
				{/snippet}
				{#snippet toolbar()}
					<div class="viewport-toolbar">
						<button class="toolbar-btn import-btn" onclick={() => (showImportModal = true)}>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="margin-right:0.35rem">
								<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
								<polyline points="17 8 12 3 7 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
								<line x1="12" y1="3" x2="12" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
							</svg>
							Import IFC
						</button>
						{#if sceneManager}
							<button class="toolbar-btn" onclick={() => sceneManager?.fitToContent()}>
								Fit View
							</button>
							<span class="element-count">{sceneManager.elementCount} elements</span>
						{/if}
					</div>
				{/snippet}
			</Viewport>
		{:else}
			<div class="graph-wrapper">
				<ForceGraph />
				{#if selection.activeGlobalId}
					<SelectionPanel />
				{/if}
			</div>
		{/if}

		<!-- Import modal -->
		<ImportModal
			open={showImportModal}
			onclose={() => (showImportModal = false)}
			onsubmit={handleImportSubmit}
		/>

		<!-- Full-screen loading overlay while importing -->
		{#if importing}
			<div class="loading-overlay">
				<Spinner size="3.5rem" message="Parsing and importing IFC model..." />
			</div>
		{/if}

		<!-- Import error toast -->
		{#if importError}
			<div class="error-toast">
				<span>{importError}</span>
				<button class="toast-close" onclick={() => (importError = null)} aria-label="Dismiss">
					<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
						<path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</button>
			</div>
		{/if}
	</div>
</main>

<style>
	:global(html, body) {
		margin: 0;
		padding: 0;
		height: 100%;
		overflow: hidden;
		background: #12121e;
	}

	main {
		display: flex;
		flex-direction: column;
		height: 100vh;
		margin: 0;
		padding: 0;
		color: #e0e0e0;
		font-family: system-ui, -apple-system, sans-serif;
	}

	/* ---- Header ---- */

	.app-header {
		display: flex;
		align-items: center;
		padding: 0 1rem;
		height: 48px;
		min-height: 48px;
		background: #1a1a2e;
		border-bottom: 1px solid rgba(255, 255, 255, 0.06);
		gap: 1.5rem;
	}

	.brand h1 {
		margin: 0;
		font-size: 1.1rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		background: linear-gradient(135deg, #ff6644, #ff9966);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
	}

	.header-spacer {
		flex: 1;
	}

	/* ---- View toggle tabs ---- */

	.view-toggle {
		display: flex;
		gap: 0;
		background: rgba(255, 255, 255, 0.04);
		border-radius: 0.4rem;
		padding: 0.2rem;
	}

	.tab-btn {
		background: none;
		border: none;
		color: #888;
		padding: 0.35rem 0.9rem;
		font-size: 0.8rem;
		cursor: pointer;
		border-radius: 0.3rem;
		transition:
			background 0.15s,
			color 0.15s;
	}

	.tab-btn:hover {
		color: #ccc;
	}

	.tab-btn.active {
		background: rgba(255, 102, 68, 0.15);
		color: #ff8866;
	}

	/* ---- Content area ---- */

	.content {
		flex: 1;
		display: flex;
		min-height: 0;
		position: relative;
	}

	.graph-wrapper {
		flex: 1;
		position: relative;
		min-height: 0;
	}

	/* ---- Viewport toolbar overlay ---- */

	.viewport-toolbar {
		position: absolute;
		bottom: 1rem;
		left: 1rem;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		z-index: 5;
	}

	.toolbar-btn {
		background: rgba(26, 26, 46, 0.85);
		border: 1px solid rgba(255, 255, 255, 0.1);
		color: #ccc;
		padding: 0.4rem 0.8rem;
		border-radius: 0.35rem;
		cursor: pointer;
		font-size: 0.78rem;
		backdrop-filter: blur(8px);
		transition:
			background 0.15s,
			color 0.15s;
	}

	.toolbar-btn:hover {
		background: rgba(255, 102, 68, 0.2);
		color: #fff;
	}

	.element-count {
		font-size: 0.72rem;
		color: #666;
	}

	.import-btn {
		display: inline-flex;
		align-items: center;
	}

	/* ---- Loading overlay ---- */

	.loading-overlay {
		position: fixed;
		inset: 0;
		z-index: 200;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(18, 18, 30, 0.85);
		backdrop-filter: blur(6px);
	}

	/* ---- Error toast ---- */

	.error-toast {
		position: fixed;
		bottom: 1.5rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 300;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.65rem 1rem;
		background: rgba(255, 107, 107, 0.12);
		border: 1px solid rgba(255, 107, 107, 0.25);
		border-radius: 0.5rem;
		color: #ff8888;
		font-size: 0.82rem;
		backdrop-filter: blur(8px);
		max-width: 90%;
	}

	.toast-close {
		background: none;
		border: none;
		color: inherit;
		cursor: pointer;
		padding: 0.15rem;
		display: flex;
		opacity: 0.6;
		transition: opacity 0.15s;
	}

	.toast-close:hover {
		opacity: 1;
	}
</style>
