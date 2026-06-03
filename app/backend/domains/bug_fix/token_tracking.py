"""Token usage tracking and cost estimation utilities.

Provides functions to estimate LLM API costs based on token counts
and model pricing. Supports common models from Anthropic, OpenAI, etc.
"""
from __future__ import annotations

from typing import Any


# Pricing per 1M tokens (USD) as of 2025-01
# Sources: https://docs.anthropic.com/en/docs/about-claude/pricing
#          https://openai.com/api/pricing/
_MODEL_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20240620": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 0.8, "output": 4.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    # Google
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
    # DeepSeek
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-coder": {"input": 0.14, "output": 0.28},
}

# Default pricing for unknown models (median of common models)
_DEFAULT_PRICING = {"input": 3.0, "output": 10.0}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    """Estimate the cost of an LLM call based on token usage.

    Args:
        model: Model name/identifier
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens

    Returns:
        Dict with cost breakdown:
        - input_cost_usd: Cost for input tokens
        - output_cost_usd: Cost for output tokens
        - total_cost_usd: Total estimated cost
        - pricing: The pricing rates used (per 1M tokens)
    """
    # Find pricing for this model (try exact match, then prefix match)
    pricing = _MODEL_PRICING.get(model)
    if not pricing:
        # Try prefix match (e.g., "claude-sonnet-4-6" matches "claude-sonnet-4")
        for key, p in _MODEL_PRICING.items():
            if model.startswith(key.split("-20")[0]):
                pricing = p
                break
    if not pricing:
        pricing = _DEFAULT_PRICING

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    return {
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
        "pricing": pricing,
    }


def aggregate_token_usage(usage_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate token usage across multiple LLM calls.

    Args:
        usage_list: List of token usage dicts, each with:
            - input_tokens: int
            - output_tokens: int
            - total_tokens: int (optional)
            - model: str
            - provider: str (optional)

    Returns:
        Aggregated usage summary:
        - total_input_tokens: Sum of all input tokens
        - total_output_tokens: Sum of all output tokens
        - total_tokens: Sum of all tokens
        - total_cost_usd: Sum of all estimated costs
        - by_model: Breakdown by model
        - call_count: Number of calls aggregated
    """
    total_input = 0
    total_output = 0
    total_cost = 0.0
    by_model: dict[str, dict[str, Any]] = {}

    for usage in usage_list:
        if not usage:
            continue

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        model = usage.get("model", "unknown")

        total_input += input_tokens
        total_output += output_tokens

        # Estimate cost for this call
        cost_info = estimate_cost(model, input_tokens, output_tokens)
        total_cost += cost_info["total_cost_usd"]

        # Aggregate by model
        if model not in by_model:
            by_model[model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost_usd": 0.0,
                "call_count": 0,
            }
        by_model[model]["input_tokens"] += input_tokens
        by_model[model]["output_tokens"] += output_tokens
        by_model[model]["total_cost_usd"] += cost_info["total_cost_usd"]
        by_model[model]["call_count"] += 1

    # Round costs in by_model
    for model_data in by_model.values():
        model_data["total_cost_usd"] = round(model_data["total_cost_usd"], 6)

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "total_cost_usd": round(total_cost, 6),
        "by_model": by_model,
        "call_count": len(usage_list),
    }
