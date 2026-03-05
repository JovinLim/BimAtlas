<script lang="ts">
	import type { ToolCallInfo } from './protocol';

	let { tool }: { tool: ToolCallInfo } = $props();
	let expanded = $state(false);

	const statusColor: Record<string, string> = {
		complete: 'var(--color-brand-500, #ff8866)',
		pending: 'var(--color-warning, #c9a227)',
		error: 'var(--color-danger, #ff6b6b)'
	};
</script>

<button
	type="button"
	class="tool-badge"
	style="border-color: {statusColor[tool.status] ?? statusColor.complete}"
	onclick={() => (expanded = !expanded)}
	aria-expanded={expanded}
>
	<span class="tool-icon">⚙</span>
	<span class="tool-name">{tool.name}</span>
	<span class="tool-chevron" class:open={expanded}>▸</span>
</button>

{#if expanded}
	<div class="tool-detail">
		{#if Object.keys(tool.arguments).length > 0}
			<div class="tool-section">
				<span class="tool-section-label">Arguments</span>
				<pre class="tool-json">{JSON.stringify(tool.arguments, null, 2)}</pre>
			</div>
		{/if}
		{#if tool.result}
			<div class="tool-section">
				<span class="tool-section-label">Result</span>
				<pre class="tool-json">{tool.result}</pre>
			</div>
		{/if}
	</div>
{/if}

<style>
	.tool-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.2rem 0.5rem;
		background: var(--color-bg-elevated);
		border: 1px solid;
		border-radius: 0.25rem;
		color: var(--color-text-secondary, #ccc);
		font-size: 0.7rem;
		cursor: pointer;
		font-family: inherit;
	}

	.tool-badge:hover {
		background: color-mix(in srgb, var(--color-text-primary) 6%, var(--color-bg-elevated));
	}

	.tool-icon {
		font-size: 0.65rem;
	}

	.tool-name {
		font-family: monospace;
		font-size: 0.68rem;
	}

	.tool-chevron {
		font-size: 0.6rem;
		transition: transform 0.15s;
	}

	.tool-chevron.open {
		transform: rotate(90deg);
	}

	.tool-detail {
		margin-top: 0.35rem;
		padding: 0.5rem;
		background: var(--color-bg-elevated);
		border-radius: 0.25rem;
		font-size: 0.7rem;
	}

	.tool-section {
		margin-bottom: 0.4rem;
	}

	.tool-section:last-child {
		margin-bottom: 0;
	}

	.tool-section-label {
		display: block;
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted, #888);
		margin-bottom: 0.2rem;
	}

	.tool-json {
		margin: 0;
		padding: 0.3rem;
		background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
		border-radius: 0.2rem;
		font-size: 0.65rem;
		color: var(--color-text-secondary, #ccc);
		overflow-x: auto;
		max-height: 10rem;
		overflow-y: auto;
		white-space: pre-wrap;
		word-break: break-word;
	}
</style>
