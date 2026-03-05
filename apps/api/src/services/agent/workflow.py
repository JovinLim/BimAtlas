"""LlamaIndex ReActAgent workflow for agentic IFC filtering.

Uses a ReActAgent with a strong system prompt that guides the agent through
Discovery -> Validation -> Creation -> Application steps.  The agent
autonomously selects tools based on the system prompt instructions.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from llama_index.core.agent import ReActAgent
from llama_index.core.agent.workflow import AgentInput, AgentStream, ToolCall, ToolCallResult
from llama_index.core.llms import ChatMessage, MessageRole
from workflows.events import StopEvent

from .llm_factory import create_llm
from .mcp_tools import get_agent_tools

logger = logging.getLogger("bimatlas.agent")

SYSTEM_PROMPT = """\
You are the BimAtlas Filtering Agent.  Your sole purpose is to help users \
create and apply IFC data filters on BimAtlas projects.  You translate \
natural language filter requests into structured filter set operations.

## Workflow — follow these steps IN ORDER for every request:

1. **Discovery**: ALWAYS call `get_project_schema` first to learn which IFC \
classes, attributes, operators, and relationships exist in the current \
project context.  Never guess — only use classes and attributes that are \
confirmed by the schema.

2. **Validation**: Before creating any filters, verify that:
   - The IFC class(es) mentioned by the user exist in the schema.
   - The attribute key(s) exist in common_attributes.
   - The operator is valid for the chosen mode.
   If something doesn't match, inform the user and suggest alternatives from \
the schema.

3. **Creation**: Create a filter set with `create_filter_set`, then add \
conditions one by one with `add_filter_condition`.

4. **Application**: Apply the filter set with `apply_filter_set_to_context`.  \
The combination_logic between multiple filter sets is always "OR".

## Operator Reference

### Class mode operators
- `is` — exact class match
- `is_not` — exclude exact class
- `inherits_from` — class + all descendants in the IFC hierarchy \
(e.g. `inherits_from IfcWindow` matches IfcWindow AND IfcWindowStandardCase)

### Attribute mode — string operators
is, is_not, contains, not_contains, starts_with, ends_with, is_empty, is_not_empty

### Attribute mode — numeric operators (set value_type="numeric")
equals, not_equals, gt, lt, gte, lte

### Attribute value_type selection (IMPORTANT)
- `string`: match string values under the attribute key.
- `numeric`: match numeric values (required for equals/not_equals/gt/lt/gte/lte).
- `object`: match nested object key names under the attribute key.
- For property-set name filtering (e.g. `PropertySets` contains `Pset_WallCommon`),
  ALWAYS use `value_type="object"`, not string.

### Relation mode
Use the relation name (e.g. 'IfcRelVoidsElement') as the filter value.

## Rules
- NEVER create filters without calling `get_project_schema` first.
- NEVER guess IFC class names — only use classes from the schema response.
- ALWAYS choose an explicit attribute `value_type` that matches user intent.
- When the user says "inherits from" or "subtypes of", use `inherits_from`.
- When creating multi-condition filters within a single set, use `logic="AND"` \
to require all conditions to match, or `logic="OR"` for any.
- After applying filters, report how many entities matched.
- Be concise.  Do not explain IFC concepts unless the user asks.
- If the user's request is ambiguous, ask a clarifying question.
"""


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
    if text.lower().startswith("assistant:"):
        return text[len("assistant:"):].lstrip()
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

    tools = get_agent_tools(branch_id, revision)

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
        agent = ReActAgent(
            tools=tools,
            llm=llm,
            system_prompt=_build_system_prompt(pre_prompt),
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
                    yield {"type": "thinking", "content": event.delta}
                if event.thinking_delta:
                    yield {"type": "thinking", "content": event.thinking_delta}
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

    except Exception as exc:
        logger.exception("Agent execution failed")
        yield {"type": "error", "content": f"Agent error: {exc}"}

    yield {"type": "done"}
