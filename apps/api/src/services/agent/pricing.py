"""LLM token pricing (USD per 1M tokens) for cost estimation.

Prices are input/output per million tokens. Sources: provider pricing pages.
Fallback to 0 for unknown models (ollama, custom, or unmapped).
"""

# (input_per_1m, output_per_1m) USD
# Order matters: more specific model names first
_OPENAI = [
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.00),
    ("gpt-4-turbo", 10.00, 30.00),
    ("gpt-4.1-mini", 0.80, 3.20),
    ("gpt-4.1", 3.00, 12.00),
    ("gpt-4", 30.00, 60.00),
    ("gpt-3.5-turbo", 0.50, 1.50),
]
_ANTHROPIC = [
    ("claude-sonnet-4", 3.00, 15.00),
    ("claude-3-5-haiku", 0.80, 4.00),
    ("claude-3-5-sonnet", 3.00, 15.00),
    ("claude-3-opus", 15.00, 75.00),
    ("claude-3-sonnet", 3.00, 15.00),
    ("claude-3-haiku", 0.25, 1.25),
]
_GOOGLE = [
    ("gemini-2.0-pro", 1.25, 5.00),
    ("gemini-2.0-flash", 0.10, 0.40),
    ("gemini-1.5-pro", 1.25, 5.00),
    ("gemini-1.5-flash", 0.075, 0.30),
]

_PROVIDER_MAP = {
    "openai": _OPENAI,
    "anthropic": _ANTHROPIC,
    "google": _GOOGLE,
}


def _match_model(provider: str, model: str) -> tuple[float, float]:
    """Return (input_per_1m, output_per_1m) for the given provider and model."""
    models = _PROVIDER_MAP.get((provider or "").lower())
    if models:
        model_lower = (model or "").lower()
        for prefix, inp, out in models:
            if prefix in model_lower or model_lower.startswith(prefix.replace("-", "")):
                return inp, out
    # When provider is custom/ollama/unknown, infer from model name across all providers
    model_lower = (model or "").lower()
    for _provider, provider_models in _PROVIDER_MAP.items():
        for prefix, inp, out in provider_models:
            if prefix in model_lower or model_lower.startswith(prefix.replace("-", "")):
                return inp, out
    return 0.0, 0.0


def compute_cost_usd(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute estimated cost in USD from token counts."""
    inp_per_1m, out_per_1m = _match_model(provider, model)
    cost = (prompt_tokens / 1_000_000) * inp_per_1m + (completion_tokens / 1_000_000) * out_per_1m
    return round(cost, 6)
