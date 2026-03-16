"""Prompt composition tests for agent workflow pre-prompt behavior."""

from src.services.agent.workflow import (
    SYSTEM_PROMPT,
    _build_system_prompt,
    _compose_user_message,
    _normalize_assistant_response,
    _sanitize_thinking_chunk,
)


def test_build_system_prompt_without_pre_prompt_returns_base_prompt():
    assert _build_system_prompt(None) == SYSTEM_PROMPT
    assert _build_system_prompt("   ") == SYSTEM_PROMPT


def test_build_system_prompt_with_pre_prompt_appends_runtime_override():
    pre = "When asked who you are, reply only QWENNN!!!"
    prompt = _build_system_prompt(pre)
    assert "Runtime Instruction Override (HIGHEST PRIORITY)" in prompt
    assert pre in prompt
    assert prompt.startswith(SYSTEM_PROMPT)


def test_compose_user_message_without_pre_prompt_returns_original_message():
    msg = "who are you"
    assert _compose_user_message(msg, None) == msg
    assert _compose_user_message(msg, "   ") == msg


def test_compose_user_message_with_pre_prompt_embeds_instruction_and_user_request():
    pre = "Reply with QWENNN!!!"
    msg = "who are you"
    combined = _compose_user_message(msg, pre)
    assert "Runtime instruction for this chat" in combined
    assert pre in combined
    assert "\nUser request:\nwho are you" in combined


def test_normalize_assistant_response_strips_react_trace_and_keeps_answer():
    raw = (
        "assistant: Thought: need tool\n"
        "Action: search_skills\n"
        "Observation: none\n"
        "Answer: Final user-facing response."
    )
    assert _normalize_assistant_response(raw) == "Final user-facing response."


def test_sanitize_thinking_chunk_filters_internal_reasoning_markers():
    assert _sanitize_thinking_chunk("Thought: The current language of the user is English.") == ""
    assert _sanitize_thinking_chunk("Action: search_skills") == ""
    assert _sanitize_thinking_chunk("Observation: {\"ok\": true}") == ""
    assert _sanitize_thinking_chunk("Runtime Instruction Override (HIGHEST PRIORITY)") == ""
    assert _sanitize_thinking_chunk("Planning query variables...") == "Planning query variables..."
