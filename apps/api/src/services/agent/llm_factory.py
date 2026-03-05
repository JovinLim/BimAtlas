"""Provider-agnostic LLM factory for the agentic filtering framework.

Instantiates the appropriate LlamaIndex LLM based on provider string.
API keys are per-request from the frontend and never persisted.
"""

from __future__ import annotations

from llama_index.core.llms import LLM


def create_llm(
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
) -> LLM:
    """Return a LlamaIndex LLM instance for the given provider.

    Parameters
    ----------
    provider : 'openai', 'anthropic', 'google', 'ollama', or 'custom'.
    model : Model identifier (e.g. 'gpt-4o', 'claude-sonnet-4-20250514').
    api_key : API key (passed per-request, not stored).
    base_url : Custom endpoint URL (used by ollama / custom providers).
    """
    provider = provider.lower().strip()

    if provider == "openai":
        from llama_index.llms.openai import OpenAI
        kwargs: dict = {"model": model, "api_key": api_key}
        if base_url:
            kwargs["api_base"] = base_url
        return OpenAI(**kwargs)

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic
        return Anthropic(model=model, api_key=api_key)

    if provider == "google":
        from llama_index.llms.gemini import Gemini
        return Gemini(model=model, api_key=api_key)

    if provider == "ollama":
        from llama_index.llms.ollama import Ollama
        url = base_url or "http://localhost:11434"
        return Ollama(model=model, base_url=url, request_timeout=120.0)

    if provider == "custom":
        from llama_index.llms.openai_like import OpenAILike
        if not base_url:
            raise ValueError("base_url is required for 'custom' provider")
        return OpenAILike(
            model=model,
            api_base=base_url.rstrip("/"),
            api_key=api_key or "not-needed",
            context_window=128000,
            is_chat_model=True,
            is_function_calling_model=True,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
