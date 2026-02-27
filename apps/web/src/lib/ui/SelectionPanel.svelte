<script lang="ts">
	/**
	 * Overlay panel that shows details of the currently selected IFC element.
	 * Fetches product details from the GraphQL API when a globalId is selected.
	 */
	import { getSelection, getRevisionState, getProjectState } from '$lib/state/selection.svelte';
	import { client, IFC_PRODUCT_QUERY } from '$lib/api/client';

	const selection = getSelection();
	const revisionState = getRevisionState();
	const projectState = getProjectState();

	async function copyValue(text: string): Promise<void> {
		try {
			await navigator.clipboard.writeText(text);
		} catch (_) {}
	}

	interface ProductData {
		globalId: string;
		ifcClass: string;
		name: string | null;
		description: string | null;
		objectType: string | null;
		tag: string | null;
		containedIn: { globalId: string; ifcClass: string; name: string | null } | null;
		relations: { globalId: string; ifcClass: string; name: string | null; relationship: string }[];
		predefinedType: string | null;
		attributes: Record<string, unknown> | null;
		representations: {
			globalId: string;
			representationIdentifier: string | null;
			representationType: string | null;
		}[];
		propertySets: Record<string, Record<string, unknown>> | null;
	}

	let product = $state<ProductData | null>(null);
	let loading = $state(false);
	let fetchError = $state<string | null>(null);

	let typeRelation = $state<ProductData['relations'][number] | null>(null);

	function objectEntries<T extends Record<string, unknown>>(obj: T | null | undefined): [string, unknown][] {
		return obj ? Object.entries(obj) : [];
	}

	// Fetch product details when selection changes
	$effect(() => {
		const gid = selection.activeGlobalId;
		const branchId = projectState.activeBranchId;
		if (!gid || !branchId) {
			product = null;
			fetchError = null;
			return;
		}

		loading = true;
		fetchError = null;

		client
			.query(IFC_PRODUCT_QUERY, {
				branchId,
				globalId: gid,
				revision: revisionState.activeRevision ?? undefined
			})
			.toPromise()
			.then((result) => {
				if (result.error) {
					fetchError = result.error.message;
					product = null;
				} else if (result.data?.ifcProduct) {
					product = result.data.ifcProduct;
				} else {
					product = null;
				}
			})
			.catch(() => {
				fetchError = 'Network error';
				product = null;
			})
			.finally(() => {
				loading = false;
			});
	});

	$effect(() => {
		typeRelation =
			product?.relations.find((r) => r.relationship === 'IfcRelDefinesByType') ?? null;
	});
</script>

{#if selection.activeGlobalId}
	<aside
		class="selection-panel"
		onclick={(e) => e.stopPropagation()}
		onmousedown={(e) => e.stopPropagation()}
		onmouseup={(e) => e.stopPropagation()}
	>
		<header class="panel-header">
			<h3>Selected Element</h3>
			<button class="close-btn" onclick={() => (selection.activeGlobalId = null)}>
				&times;
			</button>
		</header>

		<div class="panel-body">
		{#if loading}
			<p class="status-msg">Loading details&hellip;</p>
		{:else if fetchError}
			<!-- Graceful degradation: show globalId even if API is down -->
			<div class="detail">
				<span class="label">GlobalId</span>
				<div class="value-row">
					<span class="value mono">{selection.activeGlobalId}</span>
					<button
						type="button"
						class="copy-btn"
						title="Copy value"
						aria-label="Copy value"
						onclick={() => copyValue(selection.activeGlobalId ?? '')}
					>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
							<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
							<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
						</svg>
					</button>
				</div>
			</div>
			<p class="status-msg error">API unavailable</p>
		{:else if product}
			<div class="detail">
				<span class="label">Class</span>
				<div class="value-row">
					<span class="value badge">{product.ifcClass}</span>
					<button
						type="button"
						class="copy-btn"
						title="Copy value"
						aria-label="Copy value"
						onclick={() => copyValue(product!.ifcClass)}
					>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
							<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
							<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
						</svg>
					</button>
				</div>
			</div>
			{#if product.predefinedType}
				<div class="detail">
					<span class="label">Predefined Type</span>
					<div class="value-row">
						<span class="value badge secondary">{product.predefinedType}</span>
					</div>
				</div>
			{/if}
			<div class="detail">
				<span class="label">GlobalId</span>
				<div class="value-row">
					<span class="value mono">{product.globalId}</span>
					<button
						type="button"
						class="copy-btn"
						title="Copy value"
						aria-label="Copy value"
						onclick={() => copyValue(product!.globalId)}
					>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
							<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
							<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
						</svg>
					</button>
				</div>
			</div>
			{#if product.name}
				<div class="detail">
					<span class="label">Name</span>
					<div class="value-row">
						<span class="value">{product.name}</span>
						<button
							type="button"
							class="copy-btn"
							title="Copy value"
							aria-label="Copy value"
							onclick={() => copyValue(product!.name ?? '')}
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
								<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
								<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
							</svg>
						</button>
					</div>
				</div>
			{/if}
			{#if product.description}
				<div class="detail">
					<span class="label">Description</span>
					<div class="value-row">
						<span class="value">{product.description}</span>
						<button
							type="button"
							class="copy-btn"
							title="Copy value"
							aria-label="Copy value"
							onclick={() => copyValue(product!.description ?? '')}
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
								<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
								<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
							</svg>
						</button>
					</div>
				</div>
			{/if}
			{#if product.objectType}
				<div class="detail">
					<span class="label">Type</span>
					<div class="value-row">
						<span class="value">{product.objectType}</span>
						<button
							type="button"
							class="copy-btn"
							title="Copy value"
							aria-label="Copy value"
							onclick={() => copyValue(product!.objectType ?? '')}
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
								<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
								<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
							</svg>
						</button>
					</div>
				</div>
			{/if}
			{#if product.tag}
				<div class="detail">
					<span class="label">Tag</span>
					<div class="value-row">
						<span class="value mono">{product.tag}</span>
						<button
							type="button"
							class="copy-btn"
							title="Copy value"
							aria-label="Copy value"
							onclick={() => copyValue(product!.tag ?? '')}
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
								<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
								<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
							</svg>
						</button>
					</div>
				</div>
			{/if}
			{#if product.containedIn}
				<div class="detail">
					<span class="label">Container</span>
					<div class="value-row">
						<span class="value">
							<button
								class="link-btn"
								onclick={() => (selection.activeGlobalId = product!.containedIn!.globalId)}
							>
								{product.containedIn.name ?? product.containedIn.ifcClass}
							</button>
						</span>
						<button
							type="button"
							class="copy-btn"
							title="Copy value"
							aria-label="Copy value"
							onclick={() => copyValue(product!.containedIn!.name ?? product!.containedIn!.ifcClass)}
						>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
								<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
								<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
							</svg>
						</button>
					</div>
				</div>
			{/if}
			{#if typeRelation}
				<div class="detail">
					<span class="label">Type Definition</span>
					<div class="value-row">
						<button
							class="link-btn"
							onclick={() => (selection.activeGlobalId = typeRelation!.globalId)}
						>
							{typeRelation.name ?? typeRelation.ifcClass}
						</button>
					</div>
				</div>
			{/if}
			{#if product.representations?.length}
				<div class="relations-section">
					<span class="label">Representations ({product.representations.length})</span>
					<ul class="relation-list">
						{#each product.representations as rep}
							<li>
								<button
									class="link-btn"
									onclick={() => (selection.activeGlobalId = rep.globalId)}
								>
									{rep.representationIdentifier ?? rep.representationType ?? 'Shape Representation'}
								</button>
								{#if rep.representationType}
									<span class="rel-type">{rep.representationType}</span>
								{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if product.attributes}
				<div class="relations-section">
					<span class="label">Attributes</span>
					<ul class="pset-props">
						{#each objectEntries(product.attributes ?? {}) as [key, value]}
							<li>
								<span class="pset-key">{key}</span>
								<span class="pset-value">{String(value)}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if product.relations.length > 0}
				<div class="relations-section">
					<span class="label">Relations ({product.relations.length})</span>
					<ul class="relation-list">
						{#each product.relations as n}
							<li>
								<button
									class="link-btn"
									onclick={() => (selection.activeGlobalId = n.globalId)}
								>
									{n.name ?? n.ifcClass}
								</button>
								<span class="rel-type">{n.relationship}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if product.propertySets}
				<div class="relations-section">
					<span class="label">Property Sets</span>
					<div class="pset-list">
						{#each objectEntries(product.propertySets ?? {}) as [psetName, props]}
							<details>
								<summary>{psetName}</summary>
								<ul class="pset-props">
									{#each objectEntries(props as Record<string, unknown>) as [key, value]}
										<li>
											<span class="pset-key">{key}</span>
											<span class="pset-value">{String(value)}</span>
										</li>
									{/each}
								</ul>
							</details>
						{/each}
					</div>
				</div>
			{/if}
		{:else}
			<div class="detail">
				<span class="label">GlobalId</span>
				<div class="value-row">
					<span class="value mono">{selection.activeGlobalId}</span>
					<button
						type="button"
						class="copy-btn"
						title="Copy value"
						aria-label="Copy value"
						onclick={() => copyValue(selection.activeGlobalId ?? '')}
					>
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
							<rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
							<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
						</svg>
					</button>
				</div>
			</div>
		{/if}
		</div>
	</aside>
{/if}

<style>
	.selection-panel {
		position: absolute;
		top: 1rem;
		right: 1rem;
		bottom: 1rem;
		background: rgba(26, 26, 46, 0.92);
		color: #e0e0e0;
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
		box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
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
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
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
		color: #ff6644;
	}

	.close-btn {
		background: none;
		border: none;
		color: #888;
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0 0.25rem;
		line-height: 1;
	}
	.close-btn:hover {
		color: #fff;
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
		color: #888;
		cursor: pointer;
		padding: 0.2rem;
		line-height: 0;
		border-radius: 0.25rem;
	}
	.copy-btn:hover {
		color: #ff6644;
		background: rgba(255, 102, 68, 0.1);
	}

	.label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: #888;
	}

	.value {
		color: #ddd;
		word-break: break-all;
	}

	.mono {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.78rem;
	}

	.badge {
		display: inline-block;
		background: rgba(255, 102, 68, 0.15);
		color: #ff8866;
		padding: 0.1rem 0.4rem;
		border-radius: 0.25rem;
		font-size: 0.78rem;
		width: fit-content;
	}

	.badge.secondary {
		background: rgba(100, 181, 246, 0.18);
		color: #64b5f6;
	}

	.link-btn {
		background: none;
		border: none;
		color: #5dade2;
		cursor: pointer;
		padding: 0;
		font-size: 0.82rem;
		text-align: left;
	}
	.link-btn:hover {
		text-decoration: underline;
		color: #85c1e9;
	}

	.relations-section {
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(255, 255, 255, 0.08);
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
		color: #666;
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
		background: rgba(255, 255, 255, 0.02);
		border-radius: 0.25rem;
		padding: 0.25rem 0.4rem;
	}

	.pset-list summary {
		cursor: pointer;
		color: #ccc;
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
		color: #aaa;
		margin-right: 0.4rem;
	}

	.pset-value {
		font-size: 0.8rem;
		color: #ddd;
		word-break: break-all;
	}

	.panel-body .status-msg {
		flex-shrink: 0;
		color: #888;
		margin: 0.5rem 0;
		font-size: 0.82rem;
	}

	.error {
		color: #e57373;
	}
</style>
