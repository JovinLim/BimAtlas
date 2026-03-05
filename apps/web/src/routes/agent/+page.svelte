<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import ChatPanel from '$lib/agent/ChatPanel.svelte';
	import { AGENT_CHANNEL, type AgentMessage } from '$lib/agent/protocol';
	import { loadSettings } from '$lib/state/persistence';

	let branchId = $state<string | null>(null);
	let projectId = $state<string | null>(null);
	let revision = $state<number | null>(null);

	let channel: BroadcastChannel | null = null;
	let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
	let contextRetryInterval: ReturnType<typeof setInterval> | null = null;

	function applyContextFromUrl() {
		const url = $page.url;
		const b = url.searchParams.get('branchId');
		const p = url.searchParams.get('projectId');
		const r = url.searchParams.get('revision');
		if (b != null && b !== '') branchId = b;
		if (p != null && p !== '') projectId = p;
		if (r != null && r !== '') {
			const parsed = Number(r);
			revision = Number.isNaN(parsed) ? null : parsed;
		}
	}

	function applyContextFallbackFromSettings() {
		const settings = loadSettings();
		if (!settings) return;
		if (branchId == null && settings.activeBranchId != null)
			branchId = settings.activeBranchId;
		if (projectId == null && settings.activeProjectId != null)
			projectId = settings.activeProjectId;
		if (revision == null && settings.activeRevision != null)
			revision = settings.activeRevision;
	}

	function handleIncomingMessage(e: MessageEvent<AgentMessage>) {
		const msg = e.data;
		if (msg.type === 'context') {
			branchId = msg.branchId;
			projectId = msg.projectId;
			revision = msg.revision;

			const params = new URLSearchParams($page.url.searchParams);
			if (branchId != null) params.set('branchId', String(branchId));
			else params.delete('branchId');
			if (projectId != null) params.set('projectId', String(projectId));
			else params.delete('projectId');
			if (revision != null) params.set('revision', String(revision));
			else params.delete('revision');
			window.history.replaceState(null, '', `${$page.url.pathname}?${params.toString()}`);

			if (contextRetryInterval != null) {
				clearInterval(contextRetryInterval);
				contextRetryInterval = null;
			}
		}
	}

	function requestContext() {
		channel?.postMessage({ type: 'request-context' } satisfies AgentMessage);
	}

	onMount(() => {
		applyContextFromUrl();
		applyContextFallbackFromSettings();

		channel = new BroadcastChannel(AGENT_CHANNEL);
		channel.onmessage = handleIncomingMessage;

		requestContext();

		contextRetryTimeout = setTimeout(() => {
			if (branchId == null) requestContext();
			let retries = 0;
			contextRetryInterval = setInterval(() => {
				if (branchId != null || retries >= 8) {
					if (contextRetryInterval != null) clearInterval(contextRetryInterval);
					contextRetryInterval = null;
					return;
				}
				requestContext();
				retries++;
			}, 1000);
		}, 1500);
	});

	onDestroy(() => {
		channel?.close();
		if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
		if (contextRetryInterval != null) clearInterval(contextRetryInterval);
	});
</script>

<svelte:head>
	<title>BimAtlas — Agent</title>
</svelte:head>

<main class="agent-page">
	<ChatPanel {branchId} {projectId} {revision} />
</main>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		background: var(--color-bg-canvas, #12121e);
		color: var(--color-text-primary, #e0e0e0);
		font-family: system-ui, -apple-system, sans-serif;
	}

	.agent-page {
		height: 100vh;
		display: flex;
		flex-direction: column;
	}
</style>
