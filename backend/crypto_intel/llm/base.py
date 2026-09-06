"""LLMProvider abstraction.

Swapping models is a .env change: LLM_PROVIDER / LLM_MODEL / LLM_API_KEY.
No business code references a specific vendor.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..core.errors import LLMValidationError
from ..logging_setup import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> str:
    """Pull the JSON object out of a response.

    Models wrap JSON in prose or fences more often than not; failing the whole
    call over a markdown fence would be needlessly brittle.
    """
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return fence.group(1)
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


class LLMProvider(ABC):
    """Every model backend implements this."""

    name: str = "base"

    def __init__(self, model: str, api_key: str = "", base_url: str = "",
                 temperature: float = 0.2, max_tokens: int = 4000, timeout: int = 120) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Raw completion. Subclasses implement the transport."""

    async def complete_json(
        self, system: str, user: str, schema: type[T], max_retries: int = 2
    ) -> T:
        """Completion validated against a Pydantic schema.

        On invalid output, the validation error is sent back to the model so it
        can correct itself. After the retries are exhausted we raise rather than
        return something unvalidated - a malformed answer must never propagate.
        """
        last_error = ""
        prompt = user

        for attempt in range(max_retries + 1):
            raw = await self.complete(system, prompt)
            candidate = extract_json(raw)
            try:
                return schema.model_validate_json(candidate)
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = str(exc)[:900]
                log.info("llm_output_invalid", attempt=attempt, error=last_error[:200])
                if attempt < max_retries:
                    prompt = (
                        f"{user}\n\n"
                        f"Your previous reply was rejected because it did not match the required "
                        f"JSON schema.\n\nError:\n{last_error}\n\n"
                        f"Reply with ONLY the corrected JSON object, no prose, no markdown fences."
                    )
        raise LLMValidationError(
            f"Model output failed schema validation after {max_retries + 1} attempts: {last_error}"
        )

    async def health(self) -> tuple[bool, str]:
        try:
            await self.complete("Reply with the single word OK.", "Say OK.")
            return True, "ok"
        except Exception as exc:
            return False, str(exc)[:200]
