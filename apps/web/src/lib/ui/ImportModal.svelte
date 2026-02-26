<script lang="ts">
	/**
	 * Import IFC modal with drag-and-drop file support.
	 * Fires `onsubmit` with the selected File when the user confirms,
	 * or `onclose` when dismissed. The parent handles the actual upload.
	 */

	let {
		open = false,
		onclose,
		onsubmit
	}: {
		open: boolean;
		onclose: () => void;
		onsubmit: (file: File) => void;
	} = $props();

	let dragOver = $state(false);
	let error = $state<string | null>(null);
	let selectedFile = $state<File | null>(null);

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		dragOver = true;
	}

	function handleDragLeave(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		const file = e.dataTransfer?.files[0];
		if (file) selectFile(file);
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (file) selectFile(file);
	}

	function selectFile(file: File) {
		if (!file.name.toLowerCase().endsWith('.ifc')) {
			error = 'Only .ifc files are accepted.';
			selectedFile = null;
			return;
		}
		error = null;
		selectedFile = file;
	}

	function submit() {
		if (!selectedFile) return;
		onsubmit(selectedFile);
		selectedFile = null;
		error = null;
		const input = document.getElementById('ifc-file-input') as HTMLInputElement | null;
		if (input) input.value = '';
	}

	function close() {
		selectedFile = null;
		error = null;
		dragOver = false;
		onclose();
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) close();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		class="backdrop"
		role="dialog"
		aria-modal="true"
		aria-label="Import IFC file"
		tabindex="-1"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
	>
		<div class="modal">
			<header class="modal-header">
				<h2>Import IFC File</h2>
				<button class="close-btn" onclick={close} aria-label="Close">
					<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
						<path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</button>
			</header>

			<div
				class="drop-zone"
				class:drag-over={dragOver}
				class:has-file={selectedFile !== null}
				role="button"
				tabindex="0"
				ondragover={handleDragOver}
				ondragleave={handleDragLeave}
				ondrop={handleDrop}
				onclick={() => document.getElementById('ifc-file-input')?.click()}
				onkeydown={(e) => {
					if (e.key === 'Enter' || e.key === ' ') {
						e.preventDefault();
						document.getElementById('ifc-file-input')?.click();
					}
				}}
			>
				<input
					id="ifc-file-input"
					type="file"
					accept=".ifc"
					onchange={handleFileInput}
					hidden
				/>

				{#if selectedFile}
					<div class="file-info">
						<svg class="file-icon" width="32" height="32" viewBox="0 0 24 24" fill="none">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" stroke="#ff8866" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
							<path d="M14 2v6h6" stroke="#ff8866" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
						<span class="file-name">{selectedFile.name}</span>
						<span class="file-size">{formatSize(selectedFile.size)}</span>
					</div>
				{:else}
					<svg class="upload-icon" width="40" height="40" viewBox="0 0 24 24" fill="none">
						<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
						<polyline points="17 8 12 3 7 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
						<line x1="12" y1="3" x2="12" y2="15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
					<p class="drop-label">Drag & drop an IFC file here</p>
					<p class="drop-hint">or click to browse</p>
				{/if}
			</div>

			{#if error}
				<p class="error-message">{error}</p>
			{/if}

			<footer class="modal-footer">
				<button class="btn btn-secondary" onclick={close}>Cancel</button>
				<button class="btn btn-primary" disabled={!selectedFile} onclick={submit}>
					Import
				</button>
			</footer>
		</div>
	</div>
{/if}

<script lang="ts" module>
	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

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
		background: #1e1e30;
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 0.75rem;
		width: 90%;
		max-width: 480px;
		padding: 1.5rem;
		box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
	}

	/* ---- Header ---- */

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 1.25rem;
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 600;
		color: #e0e0e0;
	}

	.close-btn {
		background: none;
		border: none;
		color: #666;
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 0.25rem;
		display: flex;
		align-items: center;
		transition: color 0.15s;
	}

	.close-btn:hover {
		color: #ccc;
	}

	/* ---- Drop zone ---- */

	.drop-zone {
		border: 2px dashed rgba(255, 255, 255, 0.12);
		border-radius: 0.6rem;
		padding: 2.5rem 1.5rem;
		text-align: center;
		cursor: pointer;
		transition:
			border-color 0.2s,
			background 0.2s;
		color: #888;
		outline: none;
	}

	.drop-zone:hover,
	.drop-zone:focus-visible {
		border-color: rgba(255, 136, 102, 0.3);
		background: rgba(255, 136, 102, 0.04);
	}

	.drop-zone.drag-over {
		border-color: #ff8866;
		background: rgba(255, 136, 102, 0.08);
	}

	.drop-zone.has-file {
		border-style: solid;
		border-color: rgba(255, 136, 102, 0.25);
		background: rgba(255, 136, 102, 0.04);
	}

	.upload-icon {
		margin-bottom: 0.75rem;
		opacity: 0.5;
	}

	.drop-label {
		margin: 0 0 0.25rem;
		font-size: 0.9rem;
		color: #bbb;
	}

	.drop-hint {
		margin: 0;
		font-size: 0.78rem;
		color: #666;
	}

	/* ---- File info ---- */

	.file-info {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.4rem;
	}

	.file-icon {
		margin-bottom: 0.25rem;
	}

	.file-name {
		font-size: 0.9rem;
		color: #e0e0e0;
		word-break: break-all;
	}

	.file-size {
		font-size: 0.75rem;
		color: #666;
	}

	/* ---- Error ---- */

	.error-message {
		margin: 0.75rem 0 0;
		padding: 0.5rem 0.75rem;
		font-size: 0.8rem;
		color: #ff6b6b;
		background: rgba(255, 107, 107, 0.08);
		border-radius: 0.35rem;
	}

	/* ---- Footer ---- */

	.modal-footer {
		display: flex;
		justify-content: flex-end;
		gap: 0.6rem;
		margin-top: 1.25rem;
	}

	.btn {
		padding: 0.5rem 1.1rem;
		font-size: 0.82rem;
		border: none;
		border-radius: 0.4rem;
		cursor: pointer;
		font-weight: 500;
		transition:
			background 0.15s,
			opacity 0.15s;
	}

	.btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.btn-secondary {
		background: rgba(255, 255, 255, 0.06);
		color: #aaa;
	}

	.btn-secondary:hover:not(:disabled) {
		background: rgba(255, 255, 255, 0.1);
		color: #ccc;
	}

	.btn-primary {
		background: rgba(255, 136, 102, 0.2);
		color: #ff8866;
	}

	.btn-primary:hover:not(:disabled) {
		background: rgba(255, 136, 102, 0.35);
		color: #ffaa88;
	}
</style>
