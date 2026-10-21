from dataclasses import dataclass
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
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AnthropicNotConfiguredError()
    default_headers = (
        {"anthropic-workspace-id": settings.anthropic_workspace_id}
        if settings.anthropic_workspace_id
        else None
    )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, default_headers=default_headers)


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


@dataclass
class RawCompletion:
    """What Claude actually wrote, before any schema is imposed on it."""

    text: str
    thinking: str
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    used_web_search: bool


def complete_text(
    *,
    model: str,
    system: str,
    user_content: str,
    max_tokens: int = 16000,
    thinking: bool = True,
    tools: list[dict] | None = None,
) -> RawCompletion:
    """A plain completion with NO `output_format`, so the answer is whatever the model chose to
    write rather than something coerced into a pydantic schema.

    Production never calls this: every pass wants a typed result. It exists for the prompt lab
    (../../../promptlab), where a prompt is often being rewritten to produce a shape the schema
    in `schemas.py` does not describe yet. Under `parse_structured` such a prompt looks like it
    did nothing, because the structured-output call quietly refits the answer to the old fields;
    this is how the lab shows what the prompt genuinely produced.
    """
    kwargs: dict = {"tools": tools} if tools else {}
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    # Streamed, not a plain create(): the SDK refuses a non-streaming request whose token budget
    # could run past ten minutes, and a raw answer wants a generous budget precisely because its
    # shape is unknown. The final message is assembled for us, so the caller still gets one
    # response object.
    with _get_client().messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        **kwargs,
    ) as stream:
        response = stream.get_final_message()
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    used_web_search = False
    for block in response.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(block.text)
        elif block_type == "thinking":
            thinking_parts.append(getattr(block, "thinking", "") or "")
        elif block_type == "web_search_tool_result":
            used_web_search = True
    usage = getattr(response, "usage", None)
    return RawCompletion(
        text="\n".join(text_parts).strip(),
        thinking="\n".join(part for part in thinking_parts if part).strip(),
        stop_reason=getattr(response, "stop_reason", None),
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        used_web_search=used_web_search,
    )


def parse_structured(*, model: str, system: str, user_content: str, schema: type[SchemaT], max_tokens: int = 4096, thinking: bool = False) -> SchemaT:
    return _parse(model=model, system=system, user_content=user_content, schema=schema, max_tokens=max_tokens, tools=None, thinking=thinking).parsed_output


def parse_structured_with_web_search(*, model: str, system: str, user_content: str, schema: type[SchemaT], max_tokens: int = 4096) -> tuple[SchemaT, bool]:
    response = _parse(model=model, system=system, user_content=user_content, schema=schema, max_tokens=max_tokens, tools=[WEB_SEARCH_TOOL], thinking=True)
    used_search = any(getattr(block, "type", None) == "web_search_tool_result" for block in response.content)
    return response.parsed_output, used_search
