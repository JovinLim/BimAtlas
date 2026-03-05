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
		collapsed = $bindable(false),
		savedAgents = [],
		selectedAgentId = null,
		onselectAgent,
		onsaveAgent,
		ondeleteAgent,
		savingAgent = false
	}: {
		config: AgentConfigDraft;
		collapsed: boolean;
		savedAgents: AgentConfig[];
		selectedAgentId: string | null;
		onselectAgent: (agent: AgentConfig) => void;
		onsaveAgent: () => void;
		ondeleteAgent: (id: string) => void;
		savingAgent: boolean;
	} = $props();

	let showApiKey = $state(false);
	let modelSuggestions = $derived(DEFAULT_MODELS[config.provider] ?? []);
</script>

<section class="model-config" aria-label="LLM Configuration">
	<button
		type="button"
		class="config-header"
		onclick={() => (collapsed = !collapsed)}
		aria-expanded={!collapsed}
	>
		<span class="config-title">Model</span>
		<span class="config-summary">
			{PROVIDER_OPTIONS.find((p) => p.value === config.provider)?.label ?? config.provider}
			/ {config.model || '(none)'}
		</span>
		<span class="config-chevron" class:open={!collapsed}>▸</span>
	</button>

	{#if !collapsed}
		<div class="config-body">
			<!-- Saved agents -->
			{#if savedAgents.length > 0}
				<div class="saved-agents">
					<span class="config-label">Saved Agents</span>
					<div class="agent-list">
						{#each savedAgents as agent}
							<div class="agent-item" class:selected={agent.agent_config_id === selectedAgentId}>
								<button
									class="agent-item-name"
									onclick={() => onselectAgent(agent)}
								>
									{agent.name}
								</button>
								<button
									class="agent-item-delete"
									onclick={() => ondeleteAgent(agent.agent_config_id)}
									title="Delete"
								>×</button>
							</div>
						{/each}
					</div>
				</div>
			{/if}

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

			<button
				type="button"
				class="save-agent-btn"
				onclick={onsaveAgent}
				disabled={savingAgent || !config.model}
			>
				{savingAgent ? 'Saving...' : 'Save as Agent'}
			</button>
		</div>
	{/if}
</section>

<style>
	.model-config {
		border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
	}

	.config-header {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		width: 100%;
		padding: 0.5rem 0.6rem;
		background: none;
		border: none;
		color: var(--color-text-secondary, #ccc);
		font-size: 0.78rem;
		cursor: pointer;
		text-align: left;
		font-family: inherit;
	}

	.config-header:hover {
		background: rgba(255, 255, 255, 0.03);
	}

	.config-title {
		font-weight: 600;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted, #888);
	}

	.config-summary {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.72rem;
		color: var(--color-text-muted, #888);
	}

	.config-chevron {
		font-size: 0.6rem;
		transition: transform 0.15s;
	}

	.config-chevron.open {
		transform: rotate(90deg);
	}

	.config-body {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0 0.6rem 0.6rem;
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
		color: var(--color-text-muted, #888);
	}

	.config-select,
	.config-input {
		background: var(--color-bg-elevated, rgba(255, 255, 255, 0.06));
		border: 1px solid var(--color-border-default, rgba(255, 255, 255, 0.1));
		border-radius: 0.3rem;
		color: var(--color-text-primary, #e0e0e0);
		padding: 0.35rem 0.5rem;
		font-size: 0.78rem;
		outline: none;
		font-family: inherit;
	}

	.config-select:focus,
	.config-input:focus {
		border-color: var(--color-border-strong, rgba(255, 136, 102, 0.3));
	}

	.config-select option {
		background: var(--color-bg-surface, #1a1a2e);
		color: var(--color-text-primary, #e0e0e0);
	}

	.config-input::placeholder {
		color: var(--color-text-muted, #555);
	}

	.key-row {
		display: flex;
		gap: 0.3rem;
	}

	.key-input {
		flex: 1;
	}

	.key-toggle {
		background: var(--color-bg-elevated, rgba(255, 255, 255, 0.06));
		border: 1px solid var(--color-border-default, rgba(255, 255, 255, 0.1));
		border-radius: 0.3rem;
		color: var(--color-text-muted, #888);
		cursor: pointer;
		padding: 0 0.4rem;
		font-size: 0.75rem;
	}

	.key-toggle:hover {
		background: rgba(255, 255, 255, 0.1);
	}

	.saved-agents {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.agent-list {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.agent-item {
		display: flex;
		align-items: center;
		padding: 0.2rem 0.35rem;
		border-radius: 0.25rem;
		background: rgba(255, 255, 255, 0.03);
	}

	.agent-item.selected {
		background: rgba(255, 136, 102, 0.12);
		border: 1px solid rgba(255, 136, 102, 0.25);
	}

	.agent-item-name {
		flex: 1;
		background: none;
		border: none;
		color: var(--color-text-secondary, #ccc);
		font-size: 0.72rem;
		text-align: left;
		cursor: pointer;
		font-family: inherit;
		padding: 0.15rem 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.agent-item-delete {
		background: none;
		border: none;
		color: var(--color-text-muted, #666);
		cursor: pointer;
		font-size: 0.8rem;
		padding: 0 0.15rem;
	}

	.agent-item-delete:hover {
		color: var(--color-danger, #ff6b6b);
	}

	.save-agent-btn {
		padding: 0.35rem 0.6rem;
		font-size: 0.72rem;
		background: rgba(255, 136, 102, 0.15);
		border: 1px solid rgba(255, 136, 102, 0.25);
		border-radius: 0.3rem;
		color: var(--color-brand-500, #ff8866);
		cursor: pointer;
		font-family: inherit;
	}

	.save-agent-btn:hover:not(:disabled) {
		background: rgba(255, 136, 102, 0.3);
	}

	.save-agent-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
</style>
