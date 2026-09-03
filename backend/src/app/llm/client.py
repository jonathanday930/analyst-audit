from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.config import get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AnthropicNotConfiguredError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("ANTHROPIC_API_KEY is not set (see backend/.env.example).")


@lru_cache
def _get_client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise AnthropicNotConfiguredError()
    return anthropic.Anthropic(api_key=key)


WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 3,
    "allowed_callers": ["direct"],
}


def _parse(*, model: str, system: str, user_content: str, schema: type[SchemaT], max_tokens: int, tools: list[dict] | None, thinking: bool):
    kwargs: dict = {"tools": tools} if tools else {}
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    response = _get_client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_format=schema,
        **kwargs,
    )
    if response.parsed_output is None:
        raise RuntimeError(f"Claude did not return output matching {schema.__name__} (stop_reason={response.stop_reason}).")
    return response


def parse_structured(*, model: str, system: str, user_content: str, schema: type[SchemaT], max_tokens: int = 4096, thinking: bool = False) -> SchemaT:
    return _parse(model=model, system=system, user_content=user_content, schema=schema, max_tokens=max_tokens, tools=None, thinking=thinking).parsed_output


def parse_structured_with_web_search(*, model: str, system: str, user_content: str, schema: type[SchemaT], max_tokens: int = 4096) -> tuple[SchemaT, bool]:
    response = _parse(model=model, system=system, user_content=user_content, schema=schema, max_tokens=max_tokens, tools=[WEB_SEARCH_TOOL], thinking=True)
    used_search = any(getattr(block, "type", None) == "web_search_tool_result" for block in response.content)
    return response.parsed_output, used_search
