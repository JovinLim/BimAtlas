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
	const hasAttachments = $derived((message.attachments?.length ?? 0) > 0);
	const hasGuidanceRequest = $derived(
		(message.guidanceRequest?.question?.length ?? 0) > 0
	);

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
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
		{#if hasGuidanceRequest && message.guidanceRequest}
			<div class="guidance-request">
				<span class="guidance-label">Requesting your guidance</span>
				<p class="guidance-question">{message.guidanceRequest.question}</p>
				{#if message.guidanceRequest.context}
					<p class="guidance-context">{message.guidanceRequest.context}</p>
				{/if}
				<p class="guidance-hint">Reply in the input below to provide the IFC path or schema details.</p>
			</div>
		{/if}
		{#if hasAttachments}
			<div class="attachments">
				{#each message.attachments ?? [] as item}
					{#if item.url && !isUser}
						<a class="attachment-chip link" href={item.url} target="_blank" rel="noreferrer">
							<span>{item.filename}</span>
							<span class="attachment-size">({formatBytes(item.size_bytes)})</span>
						</a>
					{:else}
						<span class="attachment-chip">
							<span>{item.filename}</span>
							<span class="attachment-size">({formatBytes(item.size_bytes)})</span>
						</span>
					{/if}
				{/each}
			</div>
		{/if}
		{#if message.content || !message.isStreaming}
			<p class="msg-text">{message.content}</p>
		{/if}
		{#if message.usage && !isUser}
			<p class="msg-usage">
				{message.usage.total_tokens.toLocaleString()} tokens
				{#if message.usage.prompt_tokens > 0 || message.usage.completion_tokens > 0}
					(prompt: {message.usage.prompt_tokens.toLocaleString()}, completion: {message.usage.completion_tokens.toLocaleString()})
				{/if}
				· {message.usage.cost_usd != null ? `~$${message.usage.cost_usd.toFixed(4)}` : '—'}
			</p>
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

	.msg-usage {
		margin: 0.4rem 0 0;
		font-size: 0.68rem;
		color: var(--color-text-muted, #94a3b8);
	}

	.attachments {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-bottom: 0.4rem;
	}

	.attachment-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		padding: 0.15rem 0.4rem;
		border-radius: 0.3rem;
		font-size: 0.7rem;
		background: color-mix(in srgb, var(--color-brand-500) 14%, transparent);
		border: 1px solid color-mix(in srgb, var(--color-brand-500) 24%, transparent);
		color: var(--color-text-primary);
	}

	.attachment-chip.link {
		text-decoration: none;
	}

	.attachment-chip.link:hover {
		text-decoration: underline;
	}

	.attachment-size {
		color: var(--color-text-muted);
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

	.guidance-request {
		margin: 0.5rem 0;
		padding: 0.6rem 0.75rem;
		border-radius: 0.45rem;
		background: color-mix(in srgb, var(--color-brand-500, #3b82f6) 12%, transparent);
		border: 1px solid color-mix(in srgb, var(--color-brand-500, #3b82f6) 28%, transparent);
	}

	.guidance-label {
		display: block;
		font-size: 0.62rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-brand-500, #3b82f6);
		margin-bottom: 0.4rem;
	}

	.guidance-question {
		margin: 0 0 0.3rem;
		font-weight: 500;
		font-size: 0.85rem;
	}

	.guidance-context {
		margin: 0 0 0.3rem;
		font-size: 0.78rem;
		color: var(--color-text-secondary, #64748b);
	}

	.guidance-hint {
		margin: 0;
		font-size: 0.7rem;
		color: var(--color-text-muted, #94a3b8);
	}
</style>
