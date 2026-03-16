<script lang="ts">
	/**
	 * Modal to save the current view (camera + filter sets + projection mode).
	 * Fires onsubmit with the view name when the user confirms, or onclose when dismissed.
	 */
	let {
		open = false,
		appliedFilterSetCount = 0,
		projectionMode = "perspective",
		error = null,
		onclose,
		onsubmit,
	}: {
		open: boolean;
		appliedFilterSetCount?: number;
		projectionMode?: "perspective" | "orthographic";
		error?: string | null;
		onclose: () => void;
		onsubmit: (name: string) => void;
	} = $props();

	let viewName = $state("");

	function submit() {
		const name = viewName.trim();
		if (!name) return;
		onsubmit(name);
		viewName = "";
		onclose();
	}

	function close() {
		viewName = "";
		onclose();
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) close();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === "Escape") close();
		if (e.key === "Enter") submit();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="backdrop"
		role="dialog"
		aria-modal="true"
		aria-label="Save as view"
		tabindex="-1"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
	>
		<div class="modal">
			<header class="modal-header">
				<h2>Save as view</h2>
				<button class="close-btn" onclick={close} aria-label="Close">
					<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
						<path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</button>
			</header>

			<p class="info-text">
				The applied filter sets and camera projection mode will be saved.
			</p>

			{#if appliedFilterSetCount > 0}
				<p class="detail-text">
					{appliedFilterSetCount} filter set{appliedFilterSetCount === 1 ? "" : "s"} applied · {projectionMode === "orthographic" ? "Isometric" : "Perspective"} view
				</p>
			{:else}
				<p class="detail-text">
					{projectionMode === "orthographic" ? "Isometric" : "Perspective"} view
				</p>
			{/if}

			{#if error}
				<p class="error-message">{error}</p>
			{/if}

			<div class="form-row">
				<label for="view-name-input">View name</label>
				<input
					id="view-name-input"
					type="text"
					class="input"
					placeholder="e.g. Level 2 overview"
					bind:value={viewName}
					onkeydown={(e) => e.stopPropagation()}
				/>
			</div>

			<footer class="modal-footer">
				<button class="btn btn-secondary" onclick={close}>Cancel</button>
				<button class="btn btn-primary" disabled={!viewName.trim()} onclick={submit}>
					Save
				</button>
			</footer>
		</div>
	</div>
{/if}

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		z-index: 1100;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
	}

	.modal {
		background: var(--color-bg-surface);
		border: 1px solid var(--color-border-default);
		border-radius: 0.75rem;
		width: 90%;
		max-width: 400px;
		padding: 1.5rem;
		box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 1rem;
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 600;
		color: var(--color-text-primary);
	}

	.close-btn {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 0.25rem;
		display: flex;
		align-items: center;
		transition: color 0.15s;
	}

	.close-btn:hover {
		color: var(--color-text-primary);
	}

	.info-text {
		margin: 0 0 0.5rem;
		font-size: 0.9rem;
		color: var(--color-text-secondary);
	}

	.detail-text {
		margin: 0 0 1rem;
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.form-row {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		margin-bottom: 1.25rem;
	}

	.form-row label {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}

	.input {
		padding: 0.5rem 0.75rem;
		font-size: 0.9rem;
		border: 1px solid var(--color-border-default);
		border-radius: 0.35rem;
		background: var(--color-bg-surface);
		color: var(--color-text-primary);
	}

	.input:focus {
		outline: none;
		border-color: var(--color-brand-500);
	}

	.input::placeholder {
		color: var(--color-text-muted);
	}

	.error-message {
		margin: 0 0 1rem;
		padding: 0.5rem 0.75rem;
		font-size: 0.8rem;
		color: var(--color-danger);
		background: color-mix(in srgb, var(--color-danger) 6%, transparent);
		border-radius: 0.35rem;
	}

	.modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: 0.6rem;
	}
</style>
