<script lang="ts">
	import { onMount, tick } from 'svelte';
	import ChatMessage from './ChatMessage.svelte';
	import ModelConfig from './ModelConfig.svelte';
	import {
		type ChatMsg,
		type AgentSSEEvent,
		type ToolCallInfo,
		type AgentConfigDraft,
		type AgentConfig,
		type ChatSession,
		needsApiKey,
		generateMessageId
	} from './protocol';

	let {
		branchId,
		projectId,
		revision
	}: {
		branchId: string | null;
		projectId: string | null;
		revision: number | null;
	} = $props();

	const STORAGE_KEY = 'bimatlas-agent-config';
	const API_BASE = import.meta.env.VITE_API_URL
		? (import.meta.env.VITE_API_URL as string).replace('/graphql', '')
		: '/api';

	let messages = $state<ChatMsg[]>([]);
	let inputText = $state('');
	let loading = $state(false);
	let configCollapsed = $state(true);
	let messagesEl: HTMLDivElement | undefined = $state(undefined);

	let config = $state<AgentConfigDraft>({
		provider: 'openai',
		model: 'gpt-4o',
		apiKey: '',
		baseUrl: undefined
	});

	// Saved agent configs (IfcAgent)
	let savedAgents = $state<AgentConfig[]>([]);
	let selectedAgentId = $state<string | null>(null);
	let savingAgent = $state(false);

	// Chat sessions
	let chatSessions = $state<ChatSession[]>([]);
	let activeChatId = $state<string | null>(null);
	let showChatList = $state(false);

	onMount(() => {
		try {
			const saved = localStorage.getItem(STORAGE_KEY);
			if (saved) {
				const parsed = JSON.parse(saved);
				config = { ...config, ...parsed };
				if (config.apiKey) configCollapsed = true;
				else configCollapsed = false;
			} else {
				configCollapsed = false;
			}
		} catch {
			configCollapsed = false;
		}
		loadSavedAgents();
		loadChatSessions();
	});

	$effect(() => {
		if (typeof window === 'undefined') return;
		const { provider, model, apiKey, baseUrl } = config;
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify({ provider, model, apiKey, baseUrl }));
		} catch {}
	});

	$effect(() => {
		if (projectId) loadSavedAgents();
	});

	$effect(() => {
		if (projectId && branchId) loadChatSessions();
	});

	async function loadSavedAgents() {
		if (!projectId) return;
		try {
			const res = await fetch(`${API_BASE}/agent/configs?project_id=${encodeURIComponent(projectId)}`);
			if (res.ok) savedAgents = await res.json();
		} catch {}
	}

	async function loadChatSessions() {
		if (!projectId || !branchId) return;
		try {
			const url = `${API_BASE}/agent/chats?project_id=${encodeURIComponent(projectId)}&branch_id=${encodeURIComponent(branchId)}`;
			const res = await fetch(url);
			if (res.ok) chatSessions = await res.json();
		} catch {}
	}

	async function selectAgent(agent: AgentConfig) {
		selectedAgentId = agent.agent_config_id;
		config = {
			provider: agent.provider as AgentConfigDraft['provider'],
			model: agent.model,
			apiKey: agent.api_key,
			baseUrl: agent.base_url ?? undefined
		};
		configCollapsed = true;
	}

	async function saveCurrentAgent() {
		if (!projectId || !config.model) return;
		savingAgent = true;
		try {
			const body = {
				projectId,
				name: `${config.provider}/${config.model}`,
				provider: config.provider,
				model: config.model,
				apiKey: config.apiKey,
				baseUrl: config.baseUrl || null
			};
			const res = await fetch(`${API_BASE}/agent/configs`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (res.ok) {
				await loadSavedAgents();
			}
		} catch {}
		savingAgent = false;
	}

	async function deleteSavedAgent(id: string) {
		try {
			await fetch(`${API_BASE}/agent/configs/${id}`, { method: 'DELETE' });
			if (selectedAgentId === id) selectedAgentId = null;
			await loadSavedAgents();
		} catch {}
	}

	async function createNewChat() {
		if (!projectId || !branchId) return;
		try {
			const res = await fetch(`${API_BASE}/agent/chats`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ projectId, branchId, title: 'New chat' })
			});
			if (res.ok) {
				const chat: ChatSession = await res.json();
				activeChatId = chat.chat_id;
				messages = [];
				await loadChatSessions();
				showChatList = false;
			}
		} catch {}
	}

	async function switchChat(chat: ChatSession) {
		activeChatId = chat.chat_id;
		showChatList = false;
		try {
			const res = await fetch(`${API_BASE}/agent/chats/${chat.chat_id}/messages`);
			if (res.ok) {
				const msgs = await res.json();
				messages = msgs.map((m: Record<string, unknown>) => ({
					id: m.message_id as string,
					role: m.role as string,
					content: m.content as string,
					toolCalls: (m.tool_calls as ToolCallInfo[] | null) ?? undefined,
					timestamp: m.created_at as string
				}));
			}
		} catch {
			messages = [];
		}
		await scrollToBottom();
	}

	async function deleteChat(id: string) {
		try {
			await fetch(`${API_BASE}/agent/chats/${id}`, { method: 'DELETE' });
			if (activeChatId === id) {
				activeChatId = null;
				messages = [];
			}
			await loadChatSessions();
		} catch {}
	}

	async function scrollToBottom() {
		await tick();
		messagesEl?.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' });
	}

	async function sendMessage() {
		const text = inputText.trim();
		if (!text || loading) return;

		if (!branchId) {
			messages = [
				...messages,
				{
					id: generateMessageId(),
					role: 'assistant',
					content: 'Please select a project and branch first.',
					timestamp: new Date().toISOString()
				}
			];
			await scrollToBottom();
			return;
		}

		if (needsApiKey(config.provider) && !config.apiKey) {
			configCollapsed = false;
			messages = [
				...messages,
				{
					id: generateMessageId(),
					role: 'assistant',
					content: 'Please configure your API key in the Model section above.',
					timestamp: new Date().toISOString()
				}
			];
			await scrollToBottom();
			return;
		}

		if (!activeChatId && projectId && branchId) {
			try {
				const res = await fetch(`${API_BASE}/agent/chats`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({
						projectId,
						branchId,
						title: text.length > 40 ? text.slice(0, 40) + '...' : text
					})
				});
				if (res.ok) {
					const chat: ChatSession = await res.json();
					activeChatId = chat.chat_id;
					await loadChatSessions();
				}
			} catch {}
		}

		const userMsg: ChatMsg = {
			id: generateMessageId(),
			role: 'user',
			content: text,
			timestamp: new Date().toISOString()
		};
		messages = [...messages, userMsg];
		inputText = '';
		loading = true;
		await scrollToBottom();

		const body: Record<string, unknown> = {
			message: text,
			provider: config.provider,
			model: config.model,
			apiKey: config.apiKey,
			branchId,
			revision,
			baseUrl: config.baseUrl || null
		};
		if (activeChatId) body.chatId = activeChatId;

		const toolCalls: ToolCallInfo[] = [];
		let assistantContent = '';
		let hadError = false;

		try {
			const res = await fetch(`${API_BASE}/agent/chat`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});

			if (!res.ok) {
				const errText = await res.text();
				throw new Error(errText || `HTTP ${res.status}`);
			}

			const reader = res.body?.getReader();
			if (!reader) throw new Error('No response body');

			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n\n');
				buffer = lines.pop() ?? '';

				for (const chunk of lines) {
					const dataMatch = chunk.match(/^data:\s*(.+)$/s);
					if (!dataMatch) continue;
					try {
						const event: AgentSSEEvent = JSON.parse(dataMatch[1].trim());
						if (event.type === 'tool_call') {
							toolCalls.push({
								name: event.name,
								arguments: event.arguments ?? {},
								result: event.result ?? undefined,
								status: 'complete'
							});
							await scrollToBottom();
						} else if (event.type === 'message') {
							assistantContent = event.content;
						} else if (event.type === 'error') {
							hadError = true;
							assistantContent = event.content;
						}
					} catch {}
				}
			}
		} catch (err) {
			hadError = true;
			assistantContent = `Failed to reach the agent: ${err instanceof Error ? err.message : err}`;
		}

		const assistantMsg: ChatMsg = {
			id: generateMessageId(),
			role: hadError ? 'tool' : 'assistant',
			content: assistantContent || '(no response)',
			toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
			timestamp: new Date().toISOString()
		};
		messages = [...messages, assistantMsg];
		loading = false;
		await scrollToBottom();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}
</script>

<div class="chat-panel">
	<!-- Header with chat selector -->
	<header class="panel-header">
		<button class="chat-list-toggle" onclick={() => (showChatList = !showChatList)}>
			{#if activeChatId}
				{chatSessions.find((c) => c.chat_id === activeChatId)?.title ?? 'Chat'}
			{:else}
				New chat
			{/if}
			<span class="chevron" class:open={showChatList}>▸</span>
		</button>
		<button class="new-chat-btn" onclick={createNewChat} title="New chat">+</button>
	</header>

	<!-- Chat list dropdown -->
	{#if showChatList}
		<div class="chat-list">
			{#each chatSessions as chat}
				<div class="chat-list-item" class:active={chat.chat_id === activeChatId}>
					<button class="chat-list-name" onclick={() => switchChat(chat)}>
						{chat.title}
					</button>
					<button
						class="chat-list-delete"
						onclick={() => deleteChat(chat.chat_id)}
						title="Delete chat"
					>
						×
					</button>
				</div>
			{/each}
			{#if chatSessions.length === 0}
				<p class="chat-list-empty">No chats yet</p>
			{/if}
		</div>
	{/if}

	<!-- Model config (collapsible) -->
	<ModelConfig bind:config bind:collapsed={configCollapsed} {savedAgents} {selectedAgentId}
		onselectAgent={selectAgent}
		onsaveAgent={saveCurrentAgent}
		ondeleteAgent={deleteSavedAgent}
		{savingAgent}
	/>

	<!-- Messages -->
	<div class="messages" bind:this={messagesEl}>
		{#if messages.length === 0}
			<p class="empty-hint">
				Ask me to filter your IFC model. Example: "Show only entities inheriting from IfcWindow"
			</p>
		{/if}
		{#each messages as msg (msg.id)}
			<ChatMessage message={msg} />
		{/each}
		{#if loading}
			<div class="loading-indicator">
				<span class="dot"></span><span class="dot"></span><span class="dot"></span>
			</div>
		{/if}
	</div>

	<!-- Input -->
	<div class="input-area">
		<textarea
			class="chat-input"
			placeholder="Describe your filter..."
			rows="1"
			bind:value={inputText}
			onkeydown={handleKeydown}
			disabled={loading}
		></textarea>
		<button
			type="button"
			class="send-btn"
			disabled={loading || !inputText.trim()}
			onclick={sendMessage}
			aria-label="Send message"
		>
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none">
				<path
					d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
			</svg>
		</button>
	</div>
</div>

<style>
	.chat-panel {
		display: flex;
		flex-direction: column;
		height: 100%;
		background: var(--color-bg-surface, #1a1a2e);
		overflow: hidden;
	}

	.panel-header {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
		background: var(--color-bg-canvas, #12121e);
	}

	.chat-list-toggle {
		flex: 1;
		background: none;
		border: none;
		color: var(--color-text-primary, #e0e0e0);
		font-size: 0.82rem;
		font-weight: 500;
		text-align: left;
		cursor: pointer;
		font-family: inherit;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.2rem 0;
	}

	.chevron {
		font-size: 0.55rem;
		transition: transform 0.15s;
		color: var(--color-text-muted, #888);
	}

	.chevron.open {
		transform: rotate(90deg);
	}

	.new-chat-btn {
		width: 1.6rem;
		height: 1.6rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(255, 136, 102, 0.15);
		border: 1px solid rgba(255, 136, 102, 0.25);
		border-radius: 0.3rem;
		color: var(--color-brand-500, #ff8866);
		font-size: 1rem;
		cursor: pointer;
	}

	.new-chat-btn:hover {
		background: rgba(255, 136, 102, 0.3);
	}

	.chat-list {
		max-height: 12rem;
		overflow-y: auto;
		border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
		background: var(--color-bg-canvas, #12121e);
	}

	.chat-list-item {
		display: flex;
		align-items: center;
		padding: 0.3rem 0.6rem;
	}

	.chat-list-item.active {
		background: rgba(255, 136, 102, 0.1);
	}

	.chat-list-name {
		flex: 1;
		background: none;
		border: none;
		color: var(--color-text-secondary, #ccc);
		font-size: 0.75rem;
		text-align: left;
		cursor: pointer;
		font-family: inherit;
		padding: 0.2rem 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.chat-list-name:hover {
		color: var(--color-text-primary, #e0e0e0);
	}

	.chat-list-delete {
		background: none;
		border: none;
		color: var(--color-text-muted, #666);
		cursor: pointer;
		font-size: 0.9rem;
		padding: 0 0.2rem;
	}

	.chat-list-delete:hover {
		color: var(--color-danger, #ff6b6b);
	}

	.chat-list-empty {
		color: var(--color-text-muted, #666);
		font-size: 0.72rem;
		text-align: center;
		padding: 0.6rem;
		margin: 0;
	}

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 0.6rem;
		display: flex;
		flex-direction: column;
	}

	.empty-hint {
		color: var(--color-text-muted, #888);
		font-size: 0.78rem;
		text-align: center;
		margin: auto;
		padding: 1rem;
		line-height: 1.5;
	}

	.loading-indicator {
		display: flex;
		gap: 0.25rem;
		padding: 0.5rem 0.75rem;
		align-self: flex-start;
	}

	.dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--color-text-muted, #888);
		animation: bounce 1.2s infinite;
	}

	.dot:nth-child(2) {
		animation-delay: 0.2s;
	}

	.dot:nth-child(3) {
		animation-delay: 0.4s;
	}

	@keyframes bounce {
		0%,
		80%,
		100% {
			opacity: 0.3;
			transform: scale(0.8);
		}
		40% {
			opacity: 1;
			transform: scale(1);
		}
	}

	.input-area {
		display: flex;
		gap: 0.4rem;
		padding: 0.5rem 0.6rem;
		border-top: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.06));
		background: var(--color-bg-canvas, #12121e);
	}

	.chat-input {
		flex: 1;
		resize: none;
		background: var(--color-bg-elevated, rgba(255, 255, 255, 0.06));
		border: 1px solid var(--color-border-default, rgba(255, 255, 255, 0.1));
		border-radius: 0.35rem;
		color: var(--color-text-primary, #e0e0e0);
		padding: 0.45rem 0.6rem;
		font-size: 0.82rem;
		font-family: inherit;
		outline: none;
		min-height: 2.2rem;
		max-height: 6rem;
	}

	.chat-input:focus {
		border-color: var(--color-border-strong, rgba(255, 136, 102, 0.3));
	}

	.chat-input::placeholder {
		color: var(--color-text-muted, #555);
	}

	.chat-input:disabled {
		opacity: 0.5;
	}

	.send-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2.2rem;
		height: 2.2rem;
		flex-shrink: 0;
		background: rgba(255, 136, 102, 0.2);
		border: 1px solid rgba(255, 136, 102, 0.3);
		border-radius: 0.35rem;
		color: var(--color-brand-500, #ff8866);
		cursor: pointer;
		transition:
			background 0.15s,
			color 0.15s;
	}

	.send-btn:hover:not(:disabled) {
		background: rgba(255, 136, 102, 0.35);
		color: var(--color-brand-400, #ffaa88);
	}

	.send-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
</style>
