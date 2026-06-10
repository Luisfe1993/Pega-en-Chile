"""LLM provider router. Picks the first configured provider in this order:

  1. ANTHROPIC_API_KEY   → Claude Sonnet (best at structured output + ES tone)
  2. OPENAI_API_KEY      → GPT-4o-mini (cheap default for extraction)
  3. GITHUB_TOKEN        → GitHub Models (free tier, OpenAI-compatible)

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
    """Return a chat model. `prefer` may be 'anthropic' | 'openai' | 'github'."""
    default_order = ["anthropic", "openai", "github"]
    if prefer in default_order:
        order = [prefer, *[p for p in default_order if p != prefer]]
    else:
        order = default_order

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
        if p == "github" and settings.github_token:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=settings.github_models_model,
                temperature=temperature,
                api_key=settings.github_token,
                base_url=settings.github_models_base_url,
            )

    raise NoLLMConfiguredError(
        "No LLM provider configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
        "or GITHUB_TOKEN in .env."
    )


def has_llm() -> bool:
    return bool(
        settings.anthropic_api_key
        or settings.openai_api_key
        or settings.github_token
    )
