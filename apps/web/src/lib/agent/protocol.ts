/**
 * Shared types and constants for cross-window Agent popup communication
 * via the BroadcastChannel API and REST endpoints.
 */

export const AGENT_CHANNEL = 'bimatlas-agent';

export interface AgentContextPayload {
	branchId: string | null;
	projectId: string | null;
	revision: number | null;
}

export type AgentMessage =
	| { type: 'request-context' }
	| ({ type: 'context' } & AgentContextPayload);

// --- Chat message types ---

export interface ChatMsg {
	id: string;
	role: 'user' | 'assistant' | 'tool';
	content: string;
	toolCalls?: ToolCallInfo[];
	timestamp: string;
}

export interface ToolCallInfo {
	name: string;
	arguments: Record<string, unknown>;
	result?: string;
	status: 'pending' | 'complete' | 'error';
}

// --- SSE event types from POST /agent/chat ---

export type AgentSSEEvent =
	| { type: 'thinking'; content: string }
	| { type: 'tool_call'; name: string; arguments: Record<string, unknown>; result?: string }
	| { type: 'message'; content: string }
	| { type: 'error'; content: string }
	| { type: 'done' };

// --- Saved agent config (IfcAgent) ---

export interface AgentConfig {
	agent_config_id: string;
	project_id: string;
	name: string;
	provider: string;
	model: string;
	api_key: string;
	base_url: string | null;
}

export interface AgentConfigDraft {
	provider: 'openai' | 'anthropic' | 'google' | 'ollama' | 'custom';
	model: string;
	apiKey: string;
	baseUrl?: string;
}

// --- Chat session ---

export interface ChatSession {
	chat_id: string;
	project_id: string;
	branch_id: string;
	title: string;
	created_at: string;
	updated_at: string;
}

// --- Agent event bus (from GET /stream/agent-events SSE) ---

export type AgentBusEvent =
	| { type: 'filter-applied'; branchId: string; filterSetIds: string[]; matchedCount: number }
	| { type: 'agent-thinking'; step: string }
	| { type: 'agent-error'; message: string }
	| { type: 'heartbeat' }
	| { type: 'connected'; branchId: string };

// --- Constants ---

export const PROVIDER_OPTIONS = [
	{ value: 'openai', label: 'OpenAI' },
	{ value: 'anthropic', label: 'Anthropic' },
	{ value: 'google', label: 'Google' },
	{ value: 'ollama', label: 'Ollama' },
	{ value: 'custom', label: 'Custom' }
] as const;

export const DEFAULT_MODELS: Record<string, string[]> = {
	openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
	anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-haiku-20241022'],
	google: ['gemini-2.0-flash', 'gemini-2.0-pro', 'gemini-1.5-flash'],
	ollama: ['llama3', 'mistral', 'codellama'],
	custom: []
};

export function needsApiKey(provider: string): boolean {
	return provider !== 'ollama';
}

export function needsBaseUrl(provider: string): boolean {
	return provider === 'ollama' || provider === 'custom';
}

let _nextId = 0;
export function generateMessageId(): string {
	return `msg-${Date.now()}-${_nextId++}`;
}
