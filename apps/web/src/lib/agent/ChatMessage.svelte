<script lang="ts">
	import type { ChatMsg } from './protocol';
	import ToolCallBadge from './ToolCallBadge.svelte';

	let { message }: { message: ChatMsg } = $props();
	const isUser = $derived(message.role === 'user');
	const isError = $derived(message.role === 'tool');
	let metadataExpanded = $state(false);

	$effect(() => {
		if (message.isStreaming) metadataExpanded = true;
	});

	const hasMetadata = $derived(
		(message.thinkingSteps && message.thinkingSteps.length > 0) ||
		(message.toolCalls && message.toolCalls.length > 0)
	);
</script>

<div class="chat-msg" class:user={isUser} class:assistant={!isUser && !isError} class:error={isError}>
	<div class="msg-bubble">
		{#if isError}
			<span class="error-icon">⚠</span>
		{/if}
		{#if hasMetadata}
			<div class="meta-bubble">
				<button
					type="button"
					class="meta-toggle"
					onclick={() => (metadataExpanded = !metadataExpanded)}
					aria-expanded={metadataExpanded}
				>
					<span>Agent metadata</span>
					<span class="meta-chevron" class:open={metadataExpanded}>▸</span>
				</button>
				{#if metadataExpanded}
					<div class="meta-content">
						{#if message.thinkingSteps && message.thinkingSteps.length > 0}
							<div class="thinking-steps">
								<span class="meta-label">Thinking</span>
								<div class="thinking-text">{message.thinkingSteps.join('')}</div>
							</div>
						{/if}
						{#if message.toolCalls && message.toolCalls.length > 0}
							<div class="tool-calls">
								<span class="meta-label">Tool Calls</span>
								<div class="tool-call-list">
									{#each message.toolCalls as tool}
										<ToolCallBadge {tool} />
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
		{#if message.content || !message.isStreaming}
			<p class="msg-text">{message.content}</p>
		{/if}
	</div>
</div>

<style>
	.chat-msg {
		display: flex;
		min-width: 0;
		max-width: 100%;
	}

	.chat-msg.user {
		justify-content: flex-end;
	}

	.chat-msg.assistant {
		justify-content: flex-start;
	}

	.chat-msg.error {
		justify-content: flex-start;
	}

	.msg-bubble {
		max-width: 85%;
		min-width: 0;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		font-size: 0.82rem;
		line-height: 1.45;
		word-break: break-word;
		overflow-wrap: break-word;
	}

	.user .msg-bubble {
		background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
		color: var(--color-text-primary, #0f172a);
		border-bottom-right-radius: 0.15rem;
	}

	.assistant .msg-bubble {
		background: var(--color-bg-elevated, #efefe9);
		color: var(--color-text-primary, #0f172a);
		border-bottom-left-radius: 0.15rem;
	}

	.error .msg-bubble {
		background: color-mix(in srgb, var(--color-danger) 8%, transparent);
		border: 1px solid color-mix(in srgb, var(--color-danger) 20%, transparent);
		color: var(--color-danger);
		border-bottom-left-radius: 0.15rem;
	}

	.error-icon {
		margin-right: 0.35rem;
		font-size: 0.85rem;
	}

	.msg-text {
		margin: 0;
		white-space: pre-wrap;
	}

	.error .msg-text {
		display: inline;
	}

	.tool-calls {
		display: flex;
		flex-direction: column;
		margin-top: 0.4rem;
	}

	.tool-call-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.meta-bubble {
		margin-bottom: 0.45rem;
		border: 1px solid color-mix(in srgb, var(--color-brand-500, #334155) 22%, transparent);
		border-radius: 0.45rem;
		background: color-mix(in srgb, var(--color-brand-500, #334155) 8%, transparent);
	}

	.meta-toggle {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: none;
		border: 0;
		padding: 0.35rem 0.5rem;
		color: var(--color-text-secondary, #ccc);
		font-size: 0.72rem;
		font-family: inherit;
		cursor: pointer;
	}

	.meta-content {
		padding: 0 0.5rem 0.5rem;
	}

	.meta-label {
		display: block;
		margin-bottom: 0.25rem;
		font-size: 0.62rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted, #9a9a9a);
	}

	.thinking-steps {
		margin-bottom: 0.4rem;
	}

	.thinking-text {
		margin: 0;
		color: var(--color-text-secondary, #ccc);
		font-size: 0.72rem;
		line-height: 1.45;
		white-space: pre-wrap;
		word-break: break-word;
	}
</style>
