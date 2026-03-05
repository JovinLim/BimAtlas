<script lang="ts">
	import type { ChatMsg } from './protocol';
	import ToolCallBadge from './ToolCallBadge.svelte';

	let { message }: { message: ChatMsg } = $props();
	const isUser = message.role === 'user';
	const isError = message.role === 'tool';
</script>

<div class="chat-msg" class:user={isUser} class:assistant={!isUser && !isError} class:error={isError}>
	<div class="msg-bubble">
		{#if isError}
			<span class="error-icon">⚠</span>
		{/if}
		<p class="msg-text">{message.content}</p>
		{#if message.toolCalls && message.toolCalls.length > 0}
			<div class="tool-calls">
				{#each message.toolCalls as tool}
					<ToolCallBadge {tool} />
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.chat-msg {
		display: flex;
		margin-bottom: 0.5rem;
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
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		font-size: 0.82rem;
		line-height: 1.45;
		word-break: break-word;
	}

	.user .msg-bubble {
		background: rgba(255, 136, 102, 0.18);
		color: var(--color-text-primary, #e0e0e0);
		border-bottom-right-radius: 0.15rem;
	}

	.assistant .msg-bubble {
		background: var(--color-bg-elevated, rgba(255, 255, 255, 0.06));
		color: var(--color-text-primary, #e0e0e0);
		border-bottom-left-radius: 0.15rem;
	}

	.error .msg-bubble {
		background: rgba(255, 107, 107, 0.12);
		border: 1px solid rgba(255, 107, 107, 0.25);
		color: var(--color-danger-soft, #ee8888);
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
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-top: 0.4rem;
	}
</style>
