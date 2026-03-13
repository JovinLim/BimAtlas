<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import ChatMessage from "./ChatMessage.svelte";
  import ModelConfig from "./ModelConfig.svelte";
  import {
    type ChatMsg,
    type AgentSSEEvent,
    type ToolCallInfo,
    type FileAttachment,
    type AgentConfigDraft,
    type AgentConfig,
    type ChatSession,
    PROVIDER_OPTIONS,
    DEFAULT_MODELS,
    needsApiKey,
    needsBaseUrl,
    generateMessageId,
  } from "./protocol";

  let {
    branchId,
    projectId,
    revision,
    projectName: contextProjectName = null,
    branchName: contextBranchName = null,
    onRequestContext,
  }: {
    branchId: string | null;
    projectId: string | null;
    revision: number | null;
    projectName?: string | null;
    branchName?: string | null;
    onRequestContext?: () => void;
  } = $props();

  const STORAGE_KEY = "bimatlas-agent-config";
  const ACTIVE_CHAT_STORAGE_PREFIX = "bimatlas-agent-active-chat";
  const AGENT_PER_CHAT_STORAGE_KEY = "bimatlas-agent-agent-per-chat";
  const DRAFT_PER_CHAT_STORAGE_KEY = "bimatlas-agent-draft-per-chat";
  const API_BASE = import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";

  let messages = $state<ChatMsg[]>([]);
  let inputText = $state("");
  let pendingFiles = $state<File[]>([]);
  let uploadingFiles = $state(false);
  let sessionId = $state<string | null>(null);
  let fileInputEl: HTMLInputElement | undefined = $state(undefined);
  let loading = $state(false);
  let abortController: AbortController | null = $state(null);
  let liveStreamSource: EventSource | null = $state(null);
  let configModalOpen = $state(false);
  let messagesEl: HTMLDivElement | undefined = $state(undefined);

  let config = $state<AgentConfigDraft>({
    name: "Default Agent",
    provider: "openai",
    model: "gpt-4o",
    apiKey: "",
    baseUrl: undefined,
    prePrompt: "",
  });

  // Saved agent configs (IfcAgent)
  let savedAgents = $state<AgentConfig[]>([]);
  let selectedAgentId = $state<string | null>(null);
  let savingAgent = $state(false);

  // Chat sessions
  let chatSessions = $state<ChatSession[]>([]);
  let activeChatId = $state<string | null>(null);

  // Sidebar: saved agents section collapsed state
  let savedAgentsCollapsed = $state(true);

  // Edit agent overlay
  let editingAgent = $state<AgentConfig | null>(null);
  let editDraft = $state<{
    name: string;
    provider: string;
    model: string;
    apiKey: string;
    baseUrl: string;
    prePrompt: string;
  }>({
    name: "",
    provider: "openai",
    model: "",
    apiKey: "",
    baseUrl: "",
    prePrompt: "",
  });
  let editSaving = $state(false);
  let editShowApiKey = $state(false);

  // Chat context (project + branch names from API fetch; context from parent takes precedence)
  let apiProjectName = $state<string | null>(null);
  let apiBranchName = $state<string | null>(null);
  let contextLoading = $state(false);

  onMount(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        config = { ...config, ...parsed };
        if (config.apiKey) configModalOpen = false;
        else configModalOpen = true;
      } else {
        configModalOpen = true;
      }
    } catch {
      configModalOpen = true;
    }
    loadSavedAgents();
    loadChatSessions();
  });

  onDestroy(() => {
    closeLiveStream();
  });

  $effect(() => {
    if (typeof window === "undefined") return;
    const { name, provider, model, apiKey, baseUrl, prePrompt } = config;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ name, provider, model, apiKey, baseUrl, prePrompt }),
      );
    } catch {}
  });

  $effect(() => {
    if (projectId) loadSavedAgents();
  });

  $effect(() => {
    if (projectId && branchId) loadChatSessions();
  });

  // Debounced persist of input draft for current chat (survives page refresh)
  $effect(() => {
    if (typeof window === "undefined" || !activeChatId) return;
    const chat = activeChatId;
    const text = inputText;
    const t = setTimeout(() => {
      persistDraftForChat(chat, text);
    }, 400);
    return () => clearTimeout(t);
  });

  // Restore per-chat agent selection when switching chats or when savedAgents load
  $effect(() => {
    if (typeof window === "undefined" || !activeChatId || savedAgents.length === 0)
      return;
    const map = readAgentPerChatMap();
    const agentId = map[activeChatId];
    const agent = agentId
      ? savedAgents.find((a) => a.entity_id === agentId)
      : null;
    if (agent) {
      selectedAgentId = agent.entity_id;
      config = {
        name: agent.name || `${agent.provider}/${agent.model}`,
        provider: agent.provider as AgentConfigDraft["provider"],
        model: agent.model,
        apiKey: agent.api_key,
        baseUrl: agent.base_url ?? undefined,
        prePrompt: agent.pre_prompt ?? "",
      };
    } else {
      selectedAgentId = null;
      let fallbackApiKey = "";
      try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved);
          fallbackApiKey = parsed?.apiKey ?? "";
        }
      } catch {}
      config = {
        name: "Default Agent",
        provider: "openai",
        model: "gpt-4o",
        apiKey: fallbackApiKey,
        baseUrl: undefined,
        prePrompt: "",
      };
      persistAgentForChat(activeChatId, null);
    }
  });

  async function loadContext() {
    if (!projectId || !branchId) {
      apiProjectName = null;
      apiBranchName = null;
      return;
    }
    contextLoading = true;
    try {
      const url = `${API_BASE}/agent/context?project_id=${encodeURIComponent(projectId)}&branch_id=${encodeURIComponent(branchId)}`;
      const r = await fetch(url);
      const data = r.ok ? await r.json() : null;
      if (data) {
        apiProjectName = data.project_name ?? null;
        apiBranchName = data.branch_name ?? null;
      } else {
        apiProjectName = null;
        apiBranchName = null;
      }
    } catch {
      apiProjectName = null;
      apiBranchName = null;
    }
    contextLoading = false;
  }

  $effect(() => {
    loadContext();
  });

  async function loadSavedAgents() {
    if (!projectId) return;
    try {
      const res = await fetch(
        `${API_BASE}/agent/configs?project_id=${encodeURIComponent(projectId)}`,
      );
      if (res.ok) savedAgents = await res.json();
    } catch {}
  }

  function getActiveChatStorageKey() {
    if (!projectId || !branchId) return null;
    return `${ACTIVE_CHAT_STORAGE_PREFIX}:${projectId}:${branchId}`;
  }

  function persistActiveChat(chatId: string | null) {
    if (typeof window === "undefined") return;
    const key = getActiveChatStorageKey();
    if (!key) return;
    try {
      if (chatId) localStorage.setItem(key, chatId);
      else localStorage.removeItem(key);
    } catch {}
  }

  function readPersistedActiveChat(): string | null {
    if (typeof window === "undefined") return null;
    const key = getActiveChatStorageKey();
    if (!key) return null;
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function readAgentPerChatMap(): Record<string, string> {
    if (typeof window === "undefined") return {};
    try {
      const raw = localStorage.getItem(AGENT_PER_CHAT_STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return typeof parsed === "object" && parsed !== null ? parsed : {};
    } catch {
      return {};
    }
  }

  function persistAgentForChat(chatId: string | null, agentId: string | null) {
    if (typeof window === "undefined") return;
    try {
      const map = readAgentPerChatMap();
      if (chatId) {
        if (agentId) map[chatId] = agentId;
        else delete map[chatId];
      }
      localStorage.setItem(AGENT_PER_CHAT_STORAGE_KEY, JSON.stringify(map));
    } catch {}
  }

  function readDraftPerChatMap(): Record<string, string> {
    if (typeof window === "undefined") return {};
    try {
      const raw = localStorage.getItem(DRAFT_PER_CHAT_STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return typeof parsed === "object" && parsed !== null ? parsed : {};
    } catch {
      return {};
    }
  }

  function persistDraftForChat(chatId: string | null, text: string) {
    if (typeof window === "undefined") return;
    try {
      const map = readDraftPerChatMap();
      if (chatId) {
        if (text) map[chatId] = text;
        else delete map[chatId];
      }
      localStorage.setItem(DRAFT_PER_CHAT_STORAGE_KEY, JSON.stringify(map));
    } catch {}
  }

  async function loadChatSessions() {
    if (!projectId || !branchId) {
      closeLiveStream();
      chatSessions = [];
      activeChatId = null;
      messages = [];
      inputText = "";
      return;
    }
    try {
      const url = `${API_BASE}/agent/chats?project_id=${encodeURIComponent(projectId)}&branch_id=${encodeURIComponent(branchId)}`;
      const res = await fetch(url);
      if (!res.ok) return;
      const sessions: ChatSession[] = await res.json();
      chatSessions = sessions;

      if (sessions.length === 0) {
        activeChatId = null;
        messages = [];
        inputText = "";
        persistActiveChat(null);
        return;
      }

      const hasActive =
        !!activeChatId && sessions.some((s) => s.chat_id === activeChatId);
      const persistedId = readPersistedActiveChat();
      const persistedExists =
        !!persistedId && sessions.some((s) => s.chat_id === persistedId);

      let chatToOpen: ChatSession | undefined;
      if (hasActive) {
        chatToOpen = sessions.find((s) => s.chat_id === activeChatId);
      } else if (persistedExists) {
        chatToOpen = sessions.find((s) => s.chat_id === persistedId);
      } else {
        chatToOpen = sessions[0];
      }

      if (!chatToOpen) return;
      const shouldReload =
        activeChatId !== chatToOpen.chat_id || messages.length === 0;
      if (shouldReload) await switchChat(chatToOpen, { persist: true });
    } catch {}
  }

  async function selectAgent(agent: AgentConfig) {
    selectedAgentId = agent.entity_id;
    config = {
      name: agent.name || `${agent.provider}/${agent.model}`,
      provider: agent.provider as AgentConfigDraft["provider"],
      model: agent.model,
      apiKey: agent.api_key,
      baseUrl: agent.base_url ?? undefined,
      prePrompt: agent.pre_prompt ?? "",
    };
    configModalOpen = false;
    if (activeChatId) persistAgentForChat(activeChatId, agent.entity_id);
  }

  function clearAgentSelection() {
    selectedAgentId = null;
    config = {
      name: "Default Agent",
      provider: "openai",
      model: "gpt-4o",
      apiKey: config.apiKey,
      baseUrl: undefined,
      prePrompt: "",
    };
    configModalOpen = true; // open modal so user can fill new agent
    if (activeChatId) persistAgentForChat(activeChatId, null);
  }

  async function saveCurrentAgent() {
    if (!projectId || !config.model) return;
    savingAgent = true;
    try {
      const body = {
        name: config.name.trim() || `${config.provider}/${config.model}`,
        provider: config.provider,
        model: config.model,
        apiKey: config.apiKey,
        baseUrl: config.baseUrl || null,
        prePrompt: config.prePrompt || "",
      };
      if (selectedAgentId) {
        const res = await fetch(
          `${API_BASE}/agent/configs/${encodeURIComponent(selectedAgentId)}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
        );
        if (res.ok) {
          await loadSavedAgents();
          configModalOpen = false;
        }
      } else {
        const res = await fetch(`${API_BASE}/agent/configs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, projectId }),
        });
        if (res.ok) {
          const created = await res.json();
          selectedAgentId = created.entity_id;
          await loadSavedAgents();
          configModalOpen = false;
        }
      }
    } catch {}
    savingAgent = false;
  }

  async function deleteSavedAgent(id: string) {
    try {
      await fetch(`${API_BASE}/agent/configs/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (selectedAgentId === id) selectedAgentId = null;
      if (editingAgent?.entity_id === id) editingAgent = null;
      await loadSavedAgents();
    } catch {}
  }

  function openEditAgent(agent: AgentConfig, e: Event) {
    e.stopPropagation();
    editingAgent = agent;
    editDraft = {
      name: agent.name,
      provider: agent.provider,
      model: agent.model,
      apiKey: agent.api_key,
      baseUrl: agent.base_url ?? "",
      prePrompt: agent.pre_prompt ?? "",
    };
    editShowApiKey = false;
  }

  function closeEditAgent() {
    editingAgent = null;
  }

  async function saveEditAgent() {
    if (!editingAgent) return;
    editSaving = true;
    try {
      const res = await fetch(
        `${API_BASE}/agent/configs/${encodeURIComponent(editingAgent.entity_id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: editDraft.name,
            provider: editDraft.provider,
            model: editDraft.model,
            apiKey: editDraft.apiKey,
            baseUrl: editDraft.baseUrl || null,
            prePrompt: editDraft.prePrompt || "",
          }),
        },
      );
      if (res.ok) {
        await loadSavedAgents();
        const updated = await res.json();
        if (selectedAgentId === editingAgent.entity_id) {
          config = {
            name: updated.name ?? "",
            provider: updated.provider as AgentConfigDraft["provider"],
            model: updated.model,
            apiKey: updated.api_key,
            baseUrl: updated.base_url ?? undefined,
            prePrompt: updated.pre_prompt ?? "",
          };
        }
        closeEditAgent();
      }
    } catch {}
    editSaving = false;
  }

  async function createNewChat() {
    if (!projectId || !branchId) return;
    try {
      const res = await fetch(`${API_BASE}/agent/chats`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId, branchId, title: "New chat" }),
      });
      if (res.ok) {
        const chat: ChatSession = await res.json();
        activeChatId = chat.chat_id;
        persistActiveChat(chat.chat_id);
        messages = [];
        inputText = "";
        sessionId = null;
        await loadChatSessions();
      }
    } catch {}
  }

  async function switchChat(
    chat: ChatSession,
    opts: { persist?: boolean } = {},
  ) {
    closeLiveStream();
    if (activeChatId) persistDraftForChat(activeChatId, inputText);
    activeChatId = chat.chat_id;
    sessionId = null;
    inputText = readDraftPerChatMap()[chat.chat_id] ?? "";
    if (opts.persist ?? true) persistActiveChat(chat.chat_id);
    try {
      const res = await fetch(
        `${API_BASE}/agent/chats/${chat.chat_id}/messages`,
      );
      if (res.ok) {
        const msgs = await res.json();
        messages = msgs.map((m: Record<string, unknown>) => ({
          id: m.message_id as string,
          role: m.role as string,
          content: m.content as string,
          toolCalls: (m.tool_calls as ToolCallInfo[] | null) ?? undefined,
          attachments: (m.attachments as FileAttachment[] | null) ?? undefined,
          usage: (m.usage as { prompt_tokens: number; completion_tokens: number; total_tokens: number; cost_usd?: number } | null) ?? undefined,
          timestamp: m.created_at as string,
        }));
      }
    } catch {
      messages = [];
    }
    await restoreLiveStreamState(chat.chat_id);
    await scrollToBottom();
  }

  async function deleteChat(id: string) {
    try {
      await fetch(`${API_BASE}/agent/chats/${id}`, { method: "DELETE" });
      persistAgentForChat(id, null);
      persistDraftForChat(id, "");
      if (activeChatId === id) {
        activeChatId = null;
        persistActiveChat(null);
        messages = [];
        inputText = "";
      }
      await loadChatSessions();
    } catch {}
  }

  async function scrollToBottom() {
    await tick();
    messagesEl?.scrollTo({ top: messagesEl.scrollHeight, behavior: "smooth" });
  }

  function updateMessageById(id: string, updater: (msg: ChatMsg) => ChatMsg) {
    messages = messages.map((m) => (m.id === id ? updater(m) : m));
  }

  function closeLiveStream() {
    if (liveStreamSource) {
      liveStreamSource.close();
      liveStreamSource = null;
    }
  }

  function appendLiveStreamingMessage(
    chatId: string,
    thinkingSteps: string[],
    toolCalls: ToolCallInfo[],
    attachments: FileAttachment[],
    content: string,
  ): string {
    const msgId = `live-${chatId}-${Date.now()}`;
    messages = [
      ...messages,
      {
        id: msgId,
        role: "assistant",
        content,
        thinkingSteps: thinkingSteps.length > 0 ? [...thinkingSteps] : undefined,
        toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
        attachments: attachments.length > 0 ? [...attachments] : undefined,
        isStreaming: true,
        timestamp: new Date().toISOString(),
      },
    ];
    return msgId;
  }

  async function restoreLiveStreamState(chatId: string) {
    try {
      const res = await fetch(`${API_BASE}/agent/chats/${chatId}/live-state`);
      if (!res.ok) return;
      const state = await res.json();
      if (!state?.running) return;

      loading = true;
      const thinkingSteps: string[] = Array.isArray(state.thinking_steps)
        ? [...state.thinking_steps]
        : [];
      const toolCalls: ToolCallInfo[] = Array.isArray(state.tool_calls)
        ? state.tool_calls.map((t: Record<string, unknown>) => ({
            name: (t.name as string) ?? "tool",
            arguments: (t.arguments as Record<string, unknown>) ?? {},
            result: (t.result as string | undefined) ?? undefined,
            status: "complete",
          }))
        : [];
      let assistantContent: string = (state.message as string) ?? "";
      let guidanceRequest: { question: string; context: string } | null = null;
      let usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number; cost_usd?: number } | undefined;
      let hadError = false;
      const streamingMessageId = appendLiveStreamingMessage(
        chatId,
        thinkingSteps,
        toolCalls,
        [],
        assistantContent,
      );

      closeLiveStream();
      const es = new EventSource(`${API_BASE}/agent/chats/${chatId}/live-stream`);
      liveStreamSource = es;

      es.onmessage = (evt) => {
        if (activeChatId !== chatId) return;
        try {
          const event: AgentSSEEvent | { type: "heartbeat" } = JSON.parse(evt.data);
          if (event.type === "heartbeat") return;
          if (event.type === "thinking") {
            thinkingSteps.push(event.content);
            updateMessageById(streamingMessageId, (msg) => ({
              ...msg,
              thinkingSteps: [...thinkingSteps],
            }));
          } else if (event.type === "tool_call") {
            toolCalls.push({
              name: event.name,
              arguments: event.arguments ?? {},
              result: event.result ?? undefined,
              status: "complete",
            });
            updateMessageById(streamingMessageId, (msg) => ({
              ...msg,
              toolCalls: [...toolCalls],
              guidanceRequest: guidanceRequest ?? undefined,
            }));
          } else if (event.type === "guidance_request") {
            guidanceRequest = {
              question: event.question ?? "",
              context: event.context ?? "",
            };
            updateMessageById(streamingMessageId, (msg) => ({
              ...msg,
              guidanceRequest: guidanceRequest ?? undefined,
            }));
          } else if (event.type === "message") {
            assistantContent = event.content;
          } else if (event.type === "error") {
            hadError = true;
            assistantContent = event.content;
          } else if (event.type === "usage") {
            usage = {
              prompt_tokens: event.prompt_tokens ?? 0,
              completion_tokens: event.completion_tokens ?? 0,
              total_tokens: event.total_tokens ?? 0,
              cost_usd: event.cost_usd,
            };
          } else if (event.type === "done") {
            updateMessageById(streamingMessageId, (msg) => ({
              ...msg,
              role: hadError ? "tool" : "assistant",
              content: assistantContent || "(no response)",
              thinkingSteps: thinkingSteps.length > 0 ? [...thinkingSteps] : undefined,
              toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
              guidanceRequest: guidanceRequest ?? undefined,
              usage,
              isStreaming: false,
            }));
            loading = false;
            closeLiveStream();
          }
        } catch {}
      };
      await scrollToBottom();
    } catch {}
  }

  async function sendMessage() {
    closeLiveStream();
    const text = inputText.trim();
    if (!text || loading) return;

    if ((!projectId || !branchId) && onRequestContext) {
      onRequestContext();
      await tick();
    }

    if (savedAgents.length > 0 && selectedAgentId == null) {
      messages = [
        ...messages,
        {
          id: generateMessageId(),
          role: "assistant",
          content: "Please select an agent from the Model dropdown above.",
          timestamp: new Date().toISOString(),
        },
      ];
      await scrollToBottom();
      return;
    }

    if (!branchId) {
      messages = [
        ...messages,
        {
          id: generateMessageId(),
          role: "assistant",
          content: "Please select a project and branch first.",
          timestamp: new Date().toISOString(),
        },
      ];
      await scrollToBottom();
      return;
    }

    if (needsApiKey(config.provider) && !config.apiKey) {
      configModalOpen = true;
      messages = [
        ...messages,
        {
          id: generateMessageId(),
          role: "assistant",
          content: "Please configure your API key in the Model section above.",
          timestamp: new Date().toISOString(),
        },
      ];
      await scrollToBottom();
      return;
    }

    if (!activeChatId && projectId && branchId) {
      try {
        const res = await fetch(`${API_BASE}/agent/chats`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            projectId,
            branchId,
            title: text.length > 40 ? text.slice(0, 40) + "..." : text,
          }),
        });
        if (res.ok) {
          const chat: ChatSession = await res.json();
          activeChatId = chat.chat_id;
          persistActiveChat(chat.chat_id);
          await loadChatSessions();
        }
      } catch {}
    }

    const userAttachments: FileAttachment[] =
      pendingFiles.length > 0
        ? pendingFiles.map((f) => ({
            filename: f.name,
            size_bytes: f.size,
            content_type: f.type || "application/octet-stream",
          }))
        : [];

    if (pendingFiles.length > 0) {
      if (!sessionId) sessionId = crypto.randomUUID();
      uploadingFiles = true;
      try {
        for (const file of pendingFiles) {
          const form = new FormData();
          form.append("file", file);
          form.append("session_id", sessionId);
          const uploadRes = await fetch(`${API_BASE}/agent/upload`, {
            method: "POST",
            body: form,
          });
          if (!uploadRes.ok) {
            const errText = await uploadRes.text();
            throw new Error(errText || `Upload failed: ${uploadRes.status}`);
          }
        }
      } catch (err) {
        uploadingFiles = false;
        messages = [
          ...messages,
          {
            id: generateMessageId(),
            role: "tool",
            content: `File upload failed: ${err instanceof Error ? err.message : err}`,
            timestamp: new Date().toISOString(),
          },
        ];
        await scrollToBottom();
        return;
      } finally {
        uploadingFiles = false;
      }
    }

    const userMsg: ChatMsg = {
      id: generateMessageId(),
      role: "user",
      content: text,
      attachments: userAttachments.length > 0 ? userAttachments : undefined,
      timestamp: new Date().toISOString(),
    };
    messages = [...messages, userMsg];
    inputText = "";
    if (activeChatId) persistDraftForChat(activeChatId, "");
    loading = true;
    const streamingMessageId = generateMessageId();
    messages = [
      ...messages,
      {
        id: streamingMessageId,
        role: "assistant",
        content: "",
        thinkingSteps: [],
        toolCalls: [],
        isStreaming: true,
        timestamp: new Date().toISOString(),
      },
    ];
    await scrollToBottom();

    const body: Record<string, unknown> = {
      message: text,
      provider: config.provider,
      model: config.model,
      apiKey: config.apiKey,
      projectId,
      branchId,
      revision,
      baseUrl: config.baseUrl || null,
      prePrompt: config.prePrompt || "",
      sessionId,
      files: userAttachments.map((f) => f.filename),
    };
    if (activeChatId) body.chatId = activeChatId;
    pendingFiles = [];

    const toolCalls: ToolCallInfo[] = [];
    const thinkingSteps: string[] = [];
    let guidanceRequest: { question: string; context: string } | null = null;
    let usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number; cost_usd?: number } | undefined;
    let assistantContent = "";
    let hadError = false;

    abortController = new AbortController();
    try {
      const res = await fetch(`${API_BASE}/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: abortController.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const chunk of lines) {
          const dataMatch = chunk.match(/^data:\s*(.+)$/s);
          if (!dataMatch) continue;
          try {
            const event: AgentSSEEvent = JSON.parse(dataMatch[1].trim());
            if (event.type === "thinking") {
              thinkingSteps.push(event.content);
              updateMessageById(streamingMessageId, (msg) => ({
                ...msg,
                thinkingSteps: [...thinkingSteps],
              }));
              await scrollToBottom();
            } else if (event.type === "tool_call") {
              toolCalls.push({
                name: event.name,
                arguments: event.arguments ?? {},
                result: event.result ?? undefined,
                status: "complete",
              });
              updateMessageById(streamingMessageId, (msg) => ({
                ...msg,
                toolCalls: [...toolCalls],
                guidanceRequest: guidanceRequest ?? undefined,
              }));
              await scrollToBottom();
            } else if (event.type === "guidance_request") {
              guidanceRequest = {
                question: event.question ?? "",
                context: event.context ?? "",
              };
              updateMessageById(streamingMessageId, (msg) => ({
                ...msg,
                guidanceRequest: guidanceRequest ?? undefined,
              }));
              await scrollToBottom();
            } else if (event.type === "message") {
              assistantContent = event.content;
            } else if (event.type === "usage") {
              usage = {
                prompt_tokens: event.prompt_tokens ?? 0,
                completion_tokens: event.completion_tokens ?? 0,
                total_tokens: event.total_tokens ?? 0,
                cost_usd: event.cost_usd,
              };
            } else if (event.type === "error") {
              hadError = true;
              assistantContent = event.content;
            }
          } catch {}
        }
      }
    } catch (err) {
      hadError = true;
      const isAborted = err instanceof Error && err.name === "AbortError";
      assistantContent = isAborted
        ? "(stopped)"
        : `Failed to reach the agent: ${err instanceof Error ? err.message : err}`;
    } finally {
      abortController = null;
    }

    const assistantMsg: ChatMsg = {
      id: streamingMessageId,
      role: hadError ? "tool" : "assistant",
      content: assistantContent || "(no response)",
      thinkingSteps: thinkingSteps.length > 0 ? thinkingSteps : undefined,
      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
      guidanceRequest: guidanceRequest ?? undefined,
      usage,
      isStreaming: false,
      timestamp: new Date().toISOString(),
    };
    updateMessageById(streamingMessageId, () => assistantMsg);
    loading = false;
    await scrollToBottom();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function stopStream() {
    abortController?.abort();
  }

  function addPendingFiles(files: FileList | File[]) {
    const allowed = new Set([".pdf", ".csv", ".txt", ".json", ".xml", ".xlsx"]);
    const next: File[] = [];
    for (const f of Array.from(files)) {
      const ext = f.name.includes(".")
        ? f.name.slice(f.name.lastIndexOf(".")).toLowerCase()
        : "";
      if (!allowed.has(ext)) continue;
      if (f.size > 20 * 1024 * 1024) continue;
      next.push(f);
    }
    if (next.length === 0) return;
    const existingNames = new Set(pendingFiles.map((f) => f.name));
    pendingFiles = [...pendingFiles, ...next.filter((f) => !existingNames.has(f.name))];
  }

  function handleFileSelect(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    if (!input.files) return;
    addPendingFiles(input.files);
    input.value = "";
  }

  function removePendingFile(index: number) {
    pendingFiles = pendingFiles.filter((_, i) => i !== index);
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "copy";
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    if (loading || uploadingFiles) return;
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
      addPendingFiles(e.dataTransfer.files);
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="chat-panel" ondragover={handleDragOver} ondrop={handleDrop}>
  <!-- Left sidebar -->
  <aside class="chat-sidebar">
    <!-- Toolbar -->
    <div class="sidebar-toolbar">
      <button
        type="button"
        class="toolbar-btn new-chat-btn"
        onclick={createNewChat}
        title="New chat"
      >
        + New chat
      </button>
      <button
        type="button"
        class="toolbar-btn new-agent-btn"
        onclick={clearAgentSelection}
        title="Create new agent"
      >
        + Agent
      </button>
    </div>

    <!-- Collapsible saved agents -->
    <div class="saved-agents-section">
      <button
        type="button"
        class="saved-agents-header"
        onclick={() => (savedAgentsCollapsed = !savedAgentsCollapsed)}
        aria-expanded={!savedAgentsCollapsed}
      >
        <span>Saved Agents</span>
        <span class="chevron" class:open={!savedAgentsCollapsed}>▸</span>
      </button>
      {#if !savedAgentsCollapsed}
        <div class="saved-agents-list">
          {#if savedAgents.length === 0}
            <p class="saved-agents-empty">No saved agents</p>
          {:else}
            {#each savedAgents as agent}
              <div
                class="saved-agent-item"
                class:selected={agent.entity_id === selectedAgentId}
              >
                <button
                  class="saved-agent-name"
                  onclick={() => selectAgent(agent)}
                >
                  {agent.name}
                </button>
                <button
                  class="saved-agent-edit"
                  onclick={(e) => openEditAgent(agent, e)}
                  title="Edit"
                >
                  ✎
                </button>
                <button
                  class="saved-agent-delete"
                  onclick={() => deleteSavedAgent(agent.entity_id)}
                  title="Delete"
                >
                  ×
                </button>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </div>

    <!-- Chat history -->
    <nav class="chat-list" aria-label="Chat history">
      {#each chatSessions as chat}
        <div
          class="chat-list-item"
          class:active={chat.chat_id === activeChatId}
        >
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
    </nav>
  </aside>

  <!-- Right: main content -->
  <div class="chat-main">
    <header class="panel-header">
      <span class="chat-title">
        {#if activeChatId}
          {chatSessions.find((c) => c.chat_id === activeChatId)?.title ??
            "Chat"}
        {:else}
          New chat
        {/if}
      </span>
    </header>

    <section class="chat-details" aria-label="Chat context">
      <span class="chat-details-text">
        {#if contextLoading && !contextProjectName && !contextBranchName}
          Loading…
        {:else if projectId && branchId}
          {@const displayProject = contextProjectName ?? apiProjectName}
          {@const displayBranch = contextBranchName ?? apiBranchName}
          {#if displayProject != null || displayBranch != null}
            {#if displayProject != null}{displayProject}{/if}
            {#if displayProject != null && displayBranch != null}
              <span class="chat-details-sep">/</span>
            {/if}
            {#if displayBranch != null}{displayBranch}{/if}
            {#if revision != null}
              <span class="chat-details-sep">/</span>
              <span class="chat-details-rev">r{revision}</span>
            {/if}
          {:else}
            Project / Branch
            {#if revision != null}
              <span class="chat-details-sep">/</span>
              <span class="chat-details-rev">r{revision}</span>
            {/if}
          {/if}
        {:else}
          No project linked
        {/if}
      </span>
      <button
        type="button"
        class="link-context-btn"
        onclick={() => onRequestContext?.()}
        title="Link to main page's project, branch and revision"
      >
        Link main page
      </button>
    </section>

    <!-- Model config (collapsible) -->
    <ModelConfig
      bind:config
      bind:modalOpen={configModalOpen}
      {savedAgents}
      {selectedAgentId}
      onselectAgent={selectAgent}
      onclearAgent={clearAgentSelection}
      onsaveAgent={saveCurrentAgent}
      {savingAgent}
    />

    <!-- Messages -->
    <div class="messages" bind:this={messagesEl}>
      {#if messages.length === 0}
        <p class="empty-hint">
          Ask me to filter your IFC model. Example: "Show only entities
          inheriting from IfcWindow"
        </p>
      {/if}
      {#each messages as msg (msg.id)}
        <ChatMessage message={msg} />
      {/each}
      {#if loading && !messages.some((m) => m.isStreaming)}
        <div class="loading-indicator">
          <span class="dot"></span><span class="dot"></span><span class="dot"
          ></span>
        </div>
      {/if}
    </div>

    <!-- Input -->
    <div class="input-area">
      <input
        type="file"
        bind:this={fileInputEl}
        accept=".pdf,.csv,.txt,.json,.xml,.xlsx"
        multiple
        onchange={handleFileSelect}
        style="display:none"
      />
      <button
        type="button"
        class="attach-btn"
        title="Attach files"
        onclick={() => fileInputEl?.click()}
        disabled={loading || uploadingFiles}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M21.44 11.05L12.25 20.24a6 6 0 11-8.49-8.49l9.2-9.19a4 4 0 115.65 5.65l-9.2 9.2a2 2 0 11-2.83-2.83l8.48-8.48"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <textarea
        class="chat-input"
        placeholder="Ask the agent (attachments supported)..."
        rows="1"
        bind:value={inputText}
        onkeydown={handleKeydown}
        disabled={loading || uploadingFiles}
      ></textarea>
      <button
        type="button"
        class="send-btn"
        class:stop-btn={loading}
        disabled={!loading && (!inputText.trim() || uploadingFiles || (savedAgents.length > 0 && selectedAgentId == null))}
        title={savedAgents.length > 0 && selectedAgentId == null ? "Select an agent first" : undefined}
        onclick={loading ? stopStream : sendMessage}
        aria-label={loading ? "Stop" : "Send message"}
      >
        {#if loading}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        {:else}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M22 2L11 13M22 2L15 22L11 13M22 2L2 9L11 13"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        {/if}
      </button>
    </div>
    {#if pendingFiles.length > 0}
      <div class="pending-files">
        {#each pendingFiles as file, i}
          <span class="pending-file-chip">
            {file.name} ({formatBytes(file.size)})
            <button
              type="button"
              class="remove-file-btn"
              onclick={() => removePendingFile(i)}
              aria-label={`Remove ${file.name}`}
            >
              ×
            </button>
          </span>
        {/each}
      </div>
    {/if}
  </div>
</div>

<!-- Edit agent overlay -->
<svelte:window
  onkeydown={(e) => editingAgent && e.key === "Escape" && closeEditAgent()}
/>
{#if editingAgent}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="overlay-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="edit-agent-title"
    tabindex="-1"
    onclick={closeEditAgent}
  >
    <div
      class="overlay-content"
      onclick={(e) => e.stopPropagation()}
      role="document"
    >
      <h2 id="edit-agent-title" class="overlay-title">Edit Agent</h2>
      <form
        class="edit-agent-form"
        onsubmit={(e) => {
          e.preventDefault();
          saveEditAgent();
        }}
      >
        <label class="config-field">
          <span class="config-label">Name</span>
          <input
            class="config-input"
            type="text"
            bind:value={editDraft.name}
            placeholder="Agent name"
          />
        </label>
        <label class="config-field">
          <span class="config-label">Provider</span>
          <select class="config-select" bind:value={editDraft.provider}>
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
            list="edit-model-suggestions"
            placeholder="e.g. gpt-4o"
            bind:value={editDraft.model}
          />
          <datalist id="edit-model-suggestions">
            {#each DEFAULT_MODELS[editDraft.provider] ?? [] as m}
              <option value={m}></option>
            {/each}
          </datalist>
        </label>
        {#if needsApiKey(editDraft.provider)}
          <label class="config-field">
            <span class="config-label">API Key</span>
            <div class="key-row">
              <input
                class="config-input key-input"
                type={editShowApiKey ? "text" : "password"}
                placeholder="sk-..."
                bind:value={editDraft.apiKey}
              />
              <button
                type="button"
                class="key-toggle"
                onclick={() => (editShowApiKey = !editShowApiKey)}
                aria-label={editShowApiKey ? "Hide" : "Show"}
              >
                {editShowApiKey ? "🙈" : "👁"}
              </button>
            </div>
          </label>
        {/if}
        {#if needsBaseUrl(editDraft.provider)}
          <label class="config-field">
            <span class="config-label">Base URL</span>
            <input
              class="config-input"
              type="url"
              placeholder="http://localhost:11434"
              bind:value={editDraft.baseUrl}
            />
          </label>
        {/if}
        <label class="config-field">
          <span class="config-label">Pre-Prompt</span>
          <textarea
            class="config-input"
            rows="4"
            placeholder="Optional system instructions applied before each message."
            bind:value={editDraft.prePrompt}
          ></textarea>
        </label>
        <div class="overlay-actions">
          <button
            type="button"
            class="overlay-btn cancel-btn"
            onclick={closeEditAgent}
          >
            Cancel
          </button>
          <button
            type="submit"
            class="overlay-btn save-btn"
            disabled={editSaving || !editDraft.model}
          >
            {editSaving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .chat-panel {
    display: flex;
    flex-direction: row;
    height: 100%;
    background: var(--color-bg-surface);
    overflow: hidden;
  }

  .chat-sidebar {
    width: 15rem;
    min-width: 12.5rem;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--color-border-subtle);
    background: var(--color-bg-canvas);
  }

  .sidebar-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    padding: 0.5rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .toolbar-btn {
    flex: 1;
    min-width: 0;
    padding: 0.35rem 0.5rem;
    font-size: 0.72rem;
    font-family: inherit;
    border-radius: 0.3rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.2rem;
  }

  .new-chat-btn {
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--color-action-primary) 35%, transparent);
    color: var(--color-action-primary);
  }

  .new-chat-btn:hover,
  .new-chat-btn:focus-visible {
    background: var(--color-action-primary);
    border-color: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .new-agent-btn {
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--color-action-primary) 35%, transparent);
    color: var(--color-action-primary);
  }

  .new-agent-btn:hover,
  .new-agent-btn:focus-visible {
    background: var(--color-action-primary);
    border-color: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .saved-agents-section {
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .saved-agents-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 0.5rem;
    background: none;
    border: none;
    color: var(--color-text-muted);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    cursor: pointer;
    font-family: inherit;
    text-align: left;
  }

  .saved-agents-header:hover,
  .saved-agents-header:focus-visible {
    background: color-mix(in srgb, var(--color-text-primary) 3%, transparent);
    color: var(--color-text-secondary);
  }

  .saved-agents-list {
    max-height: 10rem;
    overflow-y: auto;
    padding: 0.2rem 0.5rem 0.5rem;
  }

  .saved-agents-empty {
    color: var(--color-text-muted);
    font-size: 0.72rem;
    margin: 0;
    padding: 0.4rem 0;
  }

  .saved-agent-item {
    display: flex;
    align-items: center;
    padding: 0.2rem 0.35rem;
    border-radius: 0.25rem;
    background: color-mix(in srgb, var(--color-text-primary) 3%, transparent);
    margin-bottom: 0.15rem;
  }

  .saved-agent-item.selected {
    background: color-mix(in srgb, var(--color-brand-500) 12%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--color-brand-500) 25%, transparent);
  }

  .saved-agent-name {
    flex: 1;
    background: none;
    border: none;
    color: var(--color-text-secondary);
    font-size: 0.72rem;
    text-align: left;
    cursor: pointer;
    font-family: inherit;
    padding: 0.15rem 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .saved-agent-name:hover,
  .saved-agent-name:focus-visible {
    color: var(--color-text-primary);
  }

  .saved-agent-edit {
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    font-size: 0.75rem;
    padding: 0 0.2rem;
  }

  .saved-agent-edit:hover,
  .saved-agent-edit:focus-visible {
    color: var(--color-brand-500);
  }

  .saved-agent-delete {
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    font-size: 0.8rem;
    padding: 0 0.15rem;
  }

  .saved-agent-delete:hover,
  .saved-agent-delete:focus-visible {
    color: var(--color-danger);
  }

  .chat-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
  }

  .chat-details {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.6rem;
    font-size: 0.7rem;
    color: var(--color-text-muted);
    background: var(--color-bg-elevated);
    border-bottom: 1px solid var(--color-border-subtle);
    min-width: 0;
  }

  .link-context-btn {
    flex-shrink: 0;
    padding: 0.25rem 0.5rem;
    font-size: 0.7rem;
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--color-action-primary) 35%, transparent);
    border-radius: 0.3rem;
    color: var(--color-action-primary);
    cursor: pointer;
    font-family: inherit;
  }

  .link-context-btn:hover,
  .link-context-btn:focus-visible {
    background: var(--color-action-primary);
    border-color: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .chat-details-text {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chat-details-rev {
    opacity: 0.8;
    font-variant-numeric: tabular-nums;
  }

  .chat-details-sep {
    margin: 0 0.25rem;
    opacity: 0.6;
  }

  .panel-header {
    display: flex;
    align-items: center;
    padding: 0.45rem 0.6rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background: var(--color-bg-canvas);
    min-width: 0;
  }

  .chat-title {
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chat-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.25rem 0;
  }

  .chat-list-item {
    display: flex;
    align-items: center;
    padding: 0.3rem 0.6rem;
  }

  .chat-list-item.active {
    background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
  }

  .chat-list-name {
    flex: 1;
    background: none;
    border: none;
    color: var(--color-text-secondary);
    font-size: 0.75rem;
    text-align: left;
    cursor: pointer;
    font-family: inherit;
    padding: 0.2rem 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chat-list-name:hover,
  .chat-list-name:focus-visible {
    color: var(--color-text-primary);
  }

  .chat-list-delete {
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 0 0.2rem;
  }

  .chat-list-delete:hover,
  .chat-list-delete:focus-visible {
    color: var(--color-danger);
  }

  .chat-list-empty {
    color: var(--color-text-muted);
    font-size: 0.72rem;
    text-align: center;
    padding: 0.6rem;
    margin: 0;
  }

  .messages {
    flex: 1;
    min-width: 0;
    overflow-x: hidden;
    overflow-y: auto;
    padding: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .empty-hint {
    color: var(--color-text-muted);
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
    background: var(--color-text-muted);
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
    border-top: 1px solid var(--color-border-subtle);
    background: var(--color-bg-canvas);
    min-width: 0;
  }

  .attach-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.2rem;
    min-width: 2.2rem;
    border-radius: 0.35rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-elevated);
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .attach-btn:hover:not(:disabled),
  .attach-btn:focus-visible:not(:disabled) {
    border-color: var(--color-border-strong);
    color: var(--color-text-primary);
  }

  .attach-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .chat-input {
    flex: 1;
    min-width: 0;
    resize: none;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    color: var(--color-text-primary);
    padding: 0.45rem 0.6rem;
    font-size: 0.82rem;
    font-family: inherit;
    outline: none;
    min-height: 2.2rem;
    max-height: 6rem;
  }

  .chat-input:focus,
  .chat-input:focus-visible {
    border-color: var(--color-border-strong);
  }

  .chat-input::placeholder {
    color: var(--color-text-muted);
  }

  .chat-input:disabled {
    opacity: 0.5;
  }

  .send-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    align-self: stretch;
    width: 2.5rem;
    min-width: 2.5rem;
    flex-shrink: 0;
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--color-action-primary) 35%, transparent);
    border-radius: 0.35rem;
    color: var(--color-action-primary);
    cursor: pointer;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .send-btn.stop-btn {
    background: color-mix(
      in srgb,
      var(--color-danger, #dc3545) 20%,
      transparent
    );
    border-color: color-mix(
      in srgb,
      var(--color-danger, #dc3545) 30%,
      transparent
    );
    color: var(--color-danger, #dc3545);
  }

  .send-btn.stop-btn:hover:not(:disabled),
  .send-btn.stop-btn:focus-visible:not(:disabled) {
    background: color-mix(
      in srgb,
      var(--color-danger, #dc3545) 35%,
      transparent
    );
    color: var(--color-danger-soft, #ee8888);
  }

  .send-btn:hover:not(:disabled),
  .send-btn:focus-visible:not(:disabled) {
    background: var(--color-action-primary);
    border-color: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .send-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .pending-files {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    padding: 0 0.6rem 0.5rem;
    border-top: 1px solid var(--color-border-subtle);
    background: var(--color-bg-canvas);
  }

  .pending-file-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.45rem;
    border-radius: 0.35rem;
    background: color-mix(in srgb, var(--color-brand-500) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-brand-500) 26%, transparent);
    font-size: 0.72rem;
    color: var(--color-text-primary);
  }

  .remove-file-btn {
    border: none;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.85rem;
    line-height: 1;
    padding: 0;
  }

  /* Edit agent overlay */
  .overlay-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }

  .overlay-content {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    padding: 1.25rem;
    min-width: 20rem;
    max-width: 90vw;
    box-shadow: 0 0.5rem 2rem rgba(0, 0, 0, 0.4);
  }

  .overlay-title {
    margin: 0 0 1rem;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .edit-agent-form .config-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    margin-bottom: 0.75rem;
  }

  .edit-agent-form .config-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--color-text-muted);
  }

  .edit-agent-form .config-input,
  .edit-agent-form .config-select {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.3rem;
    color: var(--color-text-primary);
    padding: 0.4rem 0.5rem;
    font-size: 0.85rem;
    font-family: inherit;
  }

  .edit-agent-form .key-row {
    display: flex;
    gap: 0.3rem;
  }

  .edit-agent-form .key-row .config-input {
    flex: 1;
  }

  .edit-agent-form .key-toggle {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.3rem;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0 0.4rem;
    font-size: 0.75rem;
  }

  .overlay-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  .overlay-btn {
    padding: 0.4rem 0.8rem;
    font-size: 0.82rem;
    font-family: inherit;
    border-radius: 0.35rem;
    cursor: pointer;
  }

  .cancel-btn {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-secondary);
  }

  .cancel-btn:hover,
  .cancel-btn:focus-visible {
    background: color-mix(
      in srgb,
      var(--color-text-primary) 10%,
      var(--color-bg-elevated)
    );
  }

  .save-btn {
    background: color-mix(in srgb, var(--color-action-primary) 15%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--color-action-primary) 35%, transparent);
    color: var(--color-action-primary);
  }

  .save-btn:hover:not(:disabled),
  .save-btn:focus-visible:not(:disabled) {
    background: var(--color-action-primary);
    border-color: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .save-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
