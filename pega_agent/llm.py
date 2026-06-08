"""LLM provider router. Picks the first configured provider in this order:

  1. ANTHROPIC_API_KEY   → Claude Sonnet (best at structured output + ES tone)
  2. OPENAI_API_KEY      → GPT-4o-mini (cheap default for extraction)

The router returns a LangChain `BaseChatModel` ready for `.with_structured_output()`.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from pega_agent.config import settings


class NoLLMConfiguredError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def get_chat_model(
    *,
    temperature: float = 0.1,
    prefer: str | None = None,
) -> BaseChatModel:
    """Return a chat model. `prefer` may be 'anthropic' | 'openai'."""
    order: list[str]
    if prefer == "anthropic":
        order = ["anthropic", "openai"]
    elif prefer == "openai":
        order = ["openai", "anthropic"]
    else:
        order = ["anthropic", "openai"]

    for p in order:
        if p == "anthropic" and settings.anthropic_api_key:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model="claude-sonnet-4-5",
                temperature=temperature,
                api_key=settings.anthropic_api_key,
            )
        if p == "openai" and settings.openai_api_key:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                api_key=settings.openai_api_key,
            )

    raise NoLLMConfiguredError(
        "No LLM provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env."
    )


def has_llm() -> bool:
    return bool(settings.anthropic_api_key or settings.openai_api_key)
