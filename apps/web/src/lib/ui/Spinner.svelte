<script lang="ts">
	/**
	 * Shared loading spinner used across the entire app.
	 * Accepts optional `size` (CSS dimension) and `message` props.
	 */
	let {
		size = '2.5rem',
		message = ''
	}: {
		size?: string;
		message?: string;
	} = $props();
</script>

<div class="spinner-wrapper">
	<div class="spinner" style:width={size} style:height={size}></div>
	{#if message}
		<p class="spinner-message">{message}</p>
	{/if}
</div>

<style>
	.spinner-wrapper {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
	}

	.spinner {
		border: 3px solid var(--color-border-default);
		border-top-color: var(--color-brand-500);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.spinner-message {
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		text-align: center;
	}
</style>
