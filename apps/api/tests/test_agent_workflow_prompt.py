"""Prompt composition tests for agent workflow pre-prompt behavior."""

from src.services.agent.workflow import (
    SYSTEM_PROMPT,
    _build_system_prompt,
    _compose_user_message,
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
