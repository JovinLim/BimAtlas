<script lang="ts">
	import {
		PROVIDER_OPTIONS,
		DEFAULT_MODELS,
		needsApiKey,
		needsBaseUrl,
		type AgentConfigDraft,
		type AgentConfig
	} from './protocol';

	let {
		config = $bindable(),
		modalOpen = $bindable(false),
		savedAgents = [],
		selectedAgentId = null,
		onselectAgent,
		onclearAgent,
		onsaveAgent,
		savingAgent = false
	}: {
		config: AgentConfigDraft;
		modalOpen: boolean;
		savedAgents: AgentConfig[];
		selectedAgentId: string | null;
		onselectAgent: (agent: AgentConfig) => void;
		onclearAgent?: () => void;
		onsaveAgent: () => void;
		savingAgent: boolean;
	} = $props();

	let showApiKey = $state(false);
	let modelSuggestions = $derived(DEFAULT_MODELS[config.provider] ?? []);

	function closeModal() {
		modalOpen = false;
	}
</script>

<svelte:window onkeydown={(e) => modalOpen && e.key === 'Escape' && closeModal()} />

<section class="model-config" aria-label="LLM Configuration">
	<div class="config-header">
		<span class="config-title">Model</span>
		<select
			class="config-agent-select"
			value={selectedAgentId ?? ''}
			onchange={(e) => {
				const v = (e.target as HTMLSelectElement).value;
				if (v === '') {
					onclearAgent?.();
				} else {
					const agent = savedAgents.find((a) => a.entity_id === v);
					if (agent) onselectAgent(agent);
				}
			}}
		>
			<option value="">Select agent</option>
			{#each savedAgents as agent}
				<option value={agent.entity_id}>{agent.name}</option>
			{/each}
		</select>
		<button
			type="button"
			class="config-toggle"
			onclick={() => (modalOpen = true)}
			aria-expanded={modalOpen}
			aria-label="Edit agent config"
		>
			<span class="config-chevron">✎</span>
		</button>
	</div>
</section>

{#if modalOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
	<div
		class="config-modal-backdrop"
		role="dialog"
		aria-modal="true"
		aria-labelledby="config-modal-title"
		tabindex="-1"
		onclick={closeModal}
	>
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_click_events_have_key_events -->
		<div class="config-modal" onclick={(e) => e.stopPropagation()} role="document">
			<h2 id="config-modal-title" class="config-modal-title">Agent Configuration</h2>
			<div class="config-body">
			<label class="config-field">
				<span class="config-label">Agent Name</span>
				<input
					class="config-input"
					type="text"
					placeholder="e.g. Wall Filter Assistant"
					bind:value={config.name}
				/>
			</label>

			<label class="config-field">
				<span class="config-label">Provider</span>
				<select class="config-select" bind:value={config.provider}>
					{#each PROVIDER_OPTIONS as opt}
						<option value={opt.value}>{opt.label}</option>
					{/each}
				</select>
			</label>

			<label class="config-field">
				<span class="config-label">Model</span>
				<input
					class="config-input"
					type="text"
					list="model-suggestions"
					placeholder="e.g. gpt-4o"
					bind:value={config.model}
				/>
				<datalist id="model-suggestions">
					{#each modelSuggestions as m}
						<option value={m}></option>
					{/each}
				</datalist>
			</label>

			{#if needsApiKey(config.provider)}
				<label class="config-field">
					<span class="config-label">API Key</span>
					<div class="key-row">
						<input
							class="config-input key-input"
							type={showApiKey ? 'text' : 'password'}
							placeholder="sk-..."
							bind:value={config.apiKey}
						/>
						<button
							type="button"
							class="key-toggle"
							onclick={() => (showApiKey = !showApiKey)}
							aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
						>
							{showApiKey ? '🙈' : '👁'}
						</button>
					</div>
				</label>
			{/if}

			{#if needsBaseUrl(config.provider)}
				<label class="config-field">
					<span class="config-label">Base URL</span>
					<input
						class="config-input"
						type="url"
						placeholder="http://localhost:11434"
						bind:value={config.baseUrl}
					/>
				</label>
			{/if}

			<label class="config-field">
				<span class="config-label">Pre-Prompt</span>
				<textarea
					class="config-input config-textarea"
					rows="4"
					placeholder="Optional system instructions applied before each message."
					bind:value={config.prePrompt}
				></textarea>
			</label>
		</div>
		<div class="config-modal-actions">
			<button
				type="button"
				class="save-agent-btn"
				onclick={onsaveAgent}
				disabled={savingAgent || !config.model || !config.name.trim()}
			>
				{savingAgent ? 'Saving...' : 'Save Agent'}
			</button>
			<button type="button" class="cancel-btn" onclick={closeModal}>Cancel</button>
		</div>
	</div>
</div>
{/if}

<style>
	.model-config {
		border-bottom: 1px solid var(--color-border-subtle);
	}

	.config-header {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		width: 100%;
		padding: 0.5rem 0.6rem;
		color: var(--color-text-secondary);
		font-size: 0.78rem;
		font-family: inherit;
	}

	.config-agent-select {
		flex: 1;
		min-width: 0;
		background: var(--color-bg-elevated);
		border: 1px solid var(--color-border-default);
		border-radius: 0.3rem;
		color: var(--color-text-primary);
		padding: 0.35rem 0.5rem;
		font-size: 0.72rem;
		outline: none;
		font-family: inherit;
		cursor: pointer;
	}

	.config-agent-select:focus,
	.config-agent-select:focus-visible {
		border-color: var(--color-border-strong);
	}

	.config-toggle {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.2rem;
	}

	.config-toggle:hover,
	.config-toggle:focus-visible {
		background: color-mix(in srgb, var(--color-text-primary) 3%, transparent);
	}

	.config-title {
		font-weight: 600;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted);
	}

	.config-chevron {
		font-size: 0.75rem;
	}

	.config-modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.config-modal {
		width: 75vw;
		height: 75vh;
		background: var(--color-bg-surface);
		border: 1px solid var(--color-border-default);
		border-radius: 0.5rem;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
		overflow: hidden;
		box-shadow: 0 0.5rem 2rem rgba(0, 0, 0, 0.4);
	}

	.config-modal-title {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-text-primary);
		flex-shrink: 0;
	}

	.config-body {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		overflow-y: auto;
		flex: 1;
		min-height: 0;
	}

	.config-field {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.config-label {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-text-muted);
	}

	.config-select,
	.config-input {
		background: var(--color-bg-elevated);
		border: 1px solid var(--color-border-default);
		border-radius: 0.3rem;
		color: var(--color-text-primary);
		padding: 0.35rem 0.5rem;
		font-size: 0.78rem;
		outline: none;
		font-family: inherit;
	}

	.config-textarea {
		resize: vertical;
		min-height: 4.5rem;
	}

	.config-select:focus,
	.config-select:focus-visible,
	.config-input:focus,
	.config-input:focus-visible {
		border-color: var(--color-border-strong);
	}

	.config-select option {
		background: var(--color-bg-surface);
		color: var(--color-text-primary);
	}

	.config-input::placeholder {
		color: var(--color-text-muted);
	}

	.key-row {
		display: flex;
		gap: 0.3rem;
	}

	.key-input {
		flex: 1;
	}

	.key-toggle {
		background: var(--color-bg-elevated);
		border: 1px solid var(--color-border-default);
		border-radius: 0.3rem;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0 0.4rem;
		font-size: 0.75rem;
	}

	.key-toggle:hover,
	.key-toggle:focus-visible {
		background: color-mix(in srgb, var(--color-text-primary) 10%, var(--color-bg-elevated));
	}

	.save-agent-btn {
		padding: 0.35rem 0.6rem;
		font-size: 0.72rem;
		background: color-mix(in srgb, var(--color-brand-500) 15%, transparent);
		border: 1px solid color-mix(in srgb, var(--color-brand-500) 25%, transparent);
		border-radius: 0.3rem;
		color: var(--color-brand-500);
		cursor: pointer;
		font-family: inherit;
	}

	.save-agent-btn:hover:not(:disabled),
	.save-agent-btn:focus-visible:not(:disabled) {
		background: color-mix(in srgb, var(--color-brand-500) 30%, transparent);
	}

	.save-agent-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.config-modal-actions {
		display: flex;
		justify-content: flex-start;
		gap: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--color-border-subtle);
		flex-shrink: 0;
	}

	.config-modal-actions .cancel-btn {
		padding: 0.4rem 0.8rem;
		font-size: 0.82rem;
		background: var(--color-bg-elevated);
		border: 1px solid var(--color-border-default);
		border-radius: 0.35rem;
		color: var(--color-text-secondary);
		cursor: pointer;
		font-family: inherit;
	}

	.config-modal-actions .cancel-btn:hover,
	.config-modal-actions .cancel-btn:focus-visible {
		background: color-mix(in srgb, var(--color-text-primary) 10%, var(--color-bg-elevated));
	}
</style>
