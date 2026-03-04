"""LlamaIndex ReActAgent workflow for agentic IFC filtering.

Uses a ReActAgent with a strong system prompt that guides the agent through
Discovery -> Validation -> Creation -> Application steps.  The agent
autonomously selects tools based on the system prompt instructions.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from llama_index.core.agent import ReActAgent
from llama_index.core.llms import ChatMessage, MessageRole

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

### Relation mode
Use the relation name (e.g. 'IfcRelVoidsElement') as the filter value.

## Rules
- NEVER create filters without calling `get_project_schema` first.
- NEVER guess IFC class names — only use classes from the schema response.
- When the user says "inherits from" or "subtypes of", use `inherits_from`.
- When creating multi-condition filters within a single set, use `logic="AND"` \
to require all conditions to match, or `logic="OR"` for any.
- After applying filters, report how many entities matched.
- Be concise.  Do not explain IFC concepts unless the user asks.
- If the user's request is ambiguous, ask a clarifying question.
"""


async def run_agent_streaming(
    message: str,
    branch_id: str,
    provider: str,
    model: str,
    api_key: str,
    revision: int | None = None,
    base_url: str | None = None,
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

    tools = get_agent_tools()

    prior_messages: list[ChatMessage] = []
    if chat_history:
        for msg in chat_history:
            role = MessageRole.USER if msg.get("role") == "user" else MessageRole.ASSISTANT
            prior_messages.append(ChatMessage(role=role, content=msg.get("content", "")))

    try:
        agent = ReActAgent.from_tools(
            tools=tools,
            llm=llm,
            verbose=False,
            system_prompt=SYSTEM_PROMPT,
            chat_history=prior_messages,
        )
    except Exception as exc:
        yield {"type": "error", "content": f"Failed to create agent: {exc}"}
        yield {"type": "done"}
        return

    yield {"type": "thinking", "content": "Processing your request..."}

    try:
        response = await agent.achat(message)

        for source in response.sources:
            tool_name = source.tool_name if hasattr(source, "tool_name") else "unknown"
            raw_input = source.raw_input if hasattr(source, "raw_input") else {}
            raw_output = source.raw_output if hasattr(source, "raw_output") else ""
            try:
                result_preview = str(raw_output)[:500]
            except Exception:
                result_preview = "(could not serialize)"

            yield {
                "type": "tool_call",
                "name": tool_name,
                "arguments": (
                    raw_input if isinstance(raw_input, dict) else {"input": str(raw_input)}
                ),
                "result": result_preview,
            }

        yield {"type": "message", "content": str(response)}

    except Exception as exc:
        logger.exception("Agent execution failed")
        yield {"type": "error", "content": f"Agent error: {exc}"}

    yield {"type": "done"}
