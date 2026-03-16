"""LlamaIndex ReActAgent workflow for agentic IFC filtering.

Uses a ReActAgent with API discovery and direct HTTP execution. The agent
discovers the API contract via discover_api and calls endpoints via execute_request.
No MCP/filter tools — all operations go through the API.
"""

from __future__ import annotations

import logging
import re
from typing import Any, AsyncGenerator
from uuid import uuid4

from llama_index.core.agent import ReActAgent
from llama_index.core.agent.workflow import AgentInput, AgentStream, ToolCall, ToolCallResult
from llama_index.core.callbacks import TokenCountingHandler
from llama_index.core.llms import ChatMessage, MessageRole
from workflows.events import StopEvent

from .llm_factory import create_llm
from .pricing import compute_cost_usd
from .sandbox_tools import get_api_tools

logger = logging.getLogger("bimatlas.agent")

SYSTEM_PROMPT = """\
You are the BimAtlas Technical Agent, an autonomous data analyst and automation
engineer for BIM/IFC projects.

You have these tools:
- `search_skills` — Search IFC skills by intent. Call FIRST for filter requests.
- `discover_api` — API contract + IFC cheat sheet. Read cheat sheet before constructing GraphQL.
- `ask_user_for_guidance` — Request domain guidance when path is unclear. Do NOT guess.
- `save_ifc_skill` — Save learned IFC mapping after user provides guidance.
- `execute_request` — Execute HTTP/GraphQL requests.
- `search_web` — Search the web for up-to-date info, building codes, specs. Use `fetch_webpage` for full content.
- `list_uploaded_files`, `read_uploaded_file` — For attached files.

## Skills + tools execution policy (MANDATORY)
- Skills and tools are complementary, not alternatives.
- First use `search_skills` to retrieve IFC/domain mapping and prior successful patterns.
- Then use `discover_api` to confirm the exact API contract (arguments, input shapes, examples).
- Then execute with `execute_request` using validated payloads.
- If skills and API examples disagree, prefer the API contract and ask user guidance when needed.

## Web search for IFC content
When using `search_web` for IFC-related queries (schema, entities, relationships, documentation),
prefer official buildingSMART sources. Include site-specific terms in your query, e.g.:
- "site:standards.buildingsmart.org IfcWall"
- "site:technical.buildingsmart.org IFC schema"
- "site:buildingsmart.org IFC4"
This yields authoritative IFC definitions over third-party or outdated content.

## Domain-safe filter policy (MANDATORY)
1. Classify: Is this a simple attribute filter or complex relational filter (spatial, material, type)?
2. For complex filters: Call `search_skills(intent)` FIRST.
3. Call `discover_api` and read the `ifc_cheat_sheet` before constructing any GraphQL.
4. If no skill exists and the cheat sheet does not clearly define the path: Call
   `ask_user_for_guidance(question)` immediately. NEVER guess IFC relationships.
5. After user provides guidance: Use it to build the filter, then call `save_ifc_skill`
   to memorize the logic for future sessions.
6. Use `execute_request` for all API calls. Use branchId and revision from context.
7. Do not invent field names. Use only prescribed relationships from cheat sheet or skills.
8. For relational intent, build queries with IFC relation semantics (e.g. `relationTypes`,
   relation-mode filter sets, `IfcRelContainedInSpatialStructure`, `IfcRelAggregates`,
   `IfcRelDefinesByType`). Do not rely on plain attribute matching.
9. `containedIn` is spatial-only convenience. Use it only for spatial containment
   targets; it is not a general relation mechanism.
"""

_REACT_TRACE_LINE = re.compile(
    r"^\s*(Thought|Action|Action Input|Observation)\s*:\s*",
    re.IGNORECASE,
)


def _build_system_prompt(pre_prompt: str | None) -> str:
    if not pre_prompt or not pre_prompt.strip():
        return SYSTEM_PROMPT
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "## Runtime Instruction Override (HIGHEST PRIORITY)\n"
        "Apply the following instruction for this entire chat unless it conflicts with"
        " tool safety or system policy:\n"
        f"{pre_prompt.strip()}\n\n"
        "You must obey the Runtime Instruction Override over default style/voice behavior."
    )


def _normalize_assistant_response(content: str) -> str:
    """Normalize assistant text before emitting to client/chat history.

    Some models prepend role labels like "assistant:" in plain text output.
    Strip that prefix for cleaner UI messages.
    """
    text = (content or "").strip()
    if not text:
        return ""
    if text.lower().startswith("assistant:"):
        text = text[len("assistant:"):].lstrip()

    # ReAct outputs occasionally include internal traces + final "Answer:".
    # Keep only the user-facing answer when present.
    answer_match = re.search(r"(?im)^\s*Answer\s*:\s*", text)
    if answer_match:
        text = text[answer_match.end():].strip()

    # Remove any remaining internal trace lines.
    cleaned_lines = [
        line for line in text.splitlines() if not _REACT_TRACE_LINE.match(line)
    ]
    return "\n".join(cleaned_lines).strip()


def _sanitize_thinking_chunk(content: str | None) -> str:
    """Remove internal reasoning/system-prompt leakage from thinking stream."""
    text = (content or "").strip()
    if not text:
        return ""

    lower = text.lower()

    # Drop explicit ReAct and meta-cognition traces.
    if _REACT_TRACE_LINE.match(text):
        return ""
    if lower.startswith("answer:"):
        return ""
    if "the current language of the user is" in lower:
        return ""
    if "you are the bimatlas technical agent" in lower:
        return ""
    if "runtime instruction override" in lower:
        return ""

    # Hide tool argument dumps that can include noisy internals.
    if lower.startswith("action input:") or lower.startswith("observation:"):
        return ""

    return text


def _compose_user_message(message: str, pre_prompt: str | None) -> str:
    """Compose a user turn that redundantly carries runtime pre-prompt.

    Some OpenAI-compatible custom endpoints may weakly enforce system prompts.
    Duplicating the instruction in the user turn makes behavior more reliable
    while preserving the original user request.
    """
    if not pre_prompt or not pre_prompt.strip():
        return message
    return (
        "Runtime instruction for this chat (must follow unless safety-policy conflict):\n"
        f"{pre_prompt.strip()}\n\n"
        "User request:\n"
        f"{message}"
    )


def _compose_uploaded_files_note(uploaded_files: list[str] | None) -> str:
    if not uploaded_files:
        return ""
    joined = ", ".join(uploaded_files)
    return (
        "Uploaded files available in this chat session: "
        f"{joined}. Use list_uploaded_files/read_uploaded_file only if the user asks "
        "to analyze those attachments."
    )


def _compose_branch_context(branch_id: str, revision: int | None) -> str:
    """Inject branch and revision into system prompt so the agent uses them in API calls."""
    rev_str = str(revision) if revision is not None else "latest"
    return (
        f"Current context: branchId={branch_id!r}, revision={rev_str}. "
        "Use these in all GraphQL variables and REST query params that require them."
    )


def _compose_project_context(project_id: str | None) -> str:
    if not project_id:
        return "Current context: projectId is unavailable for this request."
    return f"Current context: projectId={project_id!r}. Use this when endpoints require projectId."


async def run_agent_streaming(
    message: str,
    branch_id: str,
    provider: str,
    model: str,
    api_key: str,
    revision: int | None = None,
    base_url: str | None = None,
    pre_prompt: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
    session_id: str | None = None,
    uploaded_files: list[str] | None = None,
    api_spec_provider: Any | None = None,
    project_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the agent and yield SSE-compatible event dicts.

    Yields dicts with keys:
      - type: "thinking" | "tool_call" | "message" | "error" | "done"
      - Additional keys vary by type.
    """
    try:
        llm = create_llm(provider, model, api_key, base_url)
    except Exception as exc:
        yield {"type": "error", "content": f"Failed to initialize LLM: {exc}"}
        yield {"type": "done"}
        return

    token_handler = TokenCountingHandler()
    llm.callback_manager.add_handler(token_handler)

    sid = session_id or str(uuid4())
    tools = []
    if callable(api_spec_provider):
        tools.extend(
            get_api_tools(
                sid,
                api_spec_provider,
                include_discover=True,
                branch_id=branch_id,
                revision=revision,
                project_id=project_id,
                api_key=api_key,
            )
        )

    prior_messages: list[ChatMessage] = []
    if chat_history:
        for msg in chat_history:
            role = (
                MessageRole.USER
                if msg.get("role") == "user"
                else MessageRole.ASSISTANT
            )
            prior_messages.append(
                ChatMessage(role=role, content=msg.get("content", ""))
            )

    try:
        files_note = _compose_uploaded_files_note(uploaded_files)
        branch_note = _compose_branch_context(branch_id, revision)
        project_note = _compose_project_context(project_id)
        system_prompt = _build_system_prompt(pre_prompt)
        system_prompt = (
            f"{system_prompt}\n\n## Runtime Context\n{project_note}\n{branch_note}\n"
            "The word 'revision' in user requests refers to the current project branch revision "
            "(model data in the API), not an uploaded file revision.\n"
            "Never send placeholder values like '<use branchId from context>' in API variables. "
            "Always use the exact IDs provided in Runtime Context."
        )
        if files_note:
            system_prompt = f"{system_prompt}\n\n## Uploaded File Context\n{files_note}"
        agent = ReActAgent(
            tools=tools,
            llm=llm,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        yield {"type": "error", "content": f"Failed to create agent: {exc}"}
        yield {"type": "done"}
        return

    yield {"type": "thinking", "content": "Processing your request..."}

    try:
        handler = agent.run(
            user_msg=_compose_user_message(message, pre_prompt),
            chat_history=prior_messages if prior_messages else None,
        )
        latest_streamed_response = ""

        async for event in handler.stream_events():
            if isinstance(event, StopEvent):
                break

            if isinstance(event, AgentInput):
                continue  # Actual reasoning comes from AgentStream.delta

            if isinstance(event, AgentStream):
                if event.delta:
                    chunk = _sanitize_thinking_chunk(event.delta)
                    if chunk:
                        yield {"type": "thinking", "content": chunk}
                if event.thinking_delta:
                    chunk = _sanitize_thinking_chunk(event.thinking_delta)
                    if chunk:
                        yield {"type": "thinking", "content": chunk}
                if event.response:
                    latest_streamed_response = event.response
                continue

            if isinstance(event, ToolCall):
                yield {"type": "thinking", "content": f"\n[Calling tool: {event.tool_name}]\n"}
                continue

            if isinstance(event, ToolCallResult):
                try:
                    result_preview = str(event.tool_output)[:500]
                except Exception:
                    result_preview = "(could not serialize)"
                out = event.tool_output
                if (
                    event.tool_name == "ask_user_for_guidance"
                    and isinstance(out, dict)
                    and out.get("type") == "guidance_request"
                ):
                    yield {
                        "type": "guidance_request",
                        "question": out.get("question", ""),
                        "context": out.get("context", ""),
                    }
                yield {
                    "type": "tool_call",
                    "name": event.tool_name,
                    "arguments": (
                        event.tool_kwargs
                        if isinstance(event.tool_kwargs, dict)
                        else {"input": str(event.tool_kwargs)}
                    ),
                    "result": result_preview,
                }

        response = await handler
        final_response = _normalize_assistant_response(str(getattr(response, "response", "") or latest_streamed_response))
        yield {"type": "message", "content": final_response}

        prompt_tokens = token_handler.prompt_llm_token_count
        completion_tokens = token_handler.completion_llm_token_count
        total_tokens = token_handler.total_llm_token_count
        if total_tokens > 0:
            cost_usd = compute_cost_usd(provider, model, prompt_tokens, completion_tokens)
            yield {
                "type": "usage",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
            }

    except Exception as exc:
        logger.exception("Agent execution failed")
        yield {"type": "error", "content": f"Agent error: {exc}"}

    yield {"type": "done"}
