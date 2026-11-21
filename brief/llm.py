"""The models that write the brief, tried in order: Claude, then Gemini, then OpenAI.

A provider counts as failed when it has no key, the call errors or times out, it declines,
its answer is cut off, or the answer doesn't pass `check`. The next one then gets the same
request. Each provider uses its own official SDK.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import Config

log = logging.getLogger(__name__)

TIMEOUT = 600.0  # seconds; a long night can mean a few hundred items to read


class ProviderError(Exception):
    pass


class Provider(Protocol):
    label: str  # "Claude", "Gemini", "OpenAI"
    model: str

    def configured(self) -> bool: ...

    def complete(self, system: str, user: str, schema: dict) -> tuple[dict, str]:
        """The parsed JSON answer and the model that actually wrote it."""
        ...


def _parse(text: str, who: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{who} answered with invalid JSON: {exc}") from exc


@dataclass
class Claude:
    key: str
    model: str
    effort: str
    label: str = "Claude"

    def configured(self) -> bool:
        return bool(self.key)

    def complete(self, system: str, user: str, schema: dict) -> tuple[dict, str]:
        import anthropic

        client = anthropic.Anthropic(api_key=self.key, timeout=TIMEOUT, max_retries=2)
        # Streaming keeps a long answer clear of HTTP timeouts. Thinking is adaptive (the
        # model's default); `fallbacks` lets the API rerun a declined request on another
        # Claude model inside the same call.
        with client.beta.messages.stream(
            model=self.model,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            raise ProviderError("Claude declined the request")
        if message.stop_reason == "max_tokens":
            raise ProviderError("Claude's answer was cut off at max_tokens")
        text = "".join(b.text for b in message.content if b.type == "text")
        return _parse(text, "Claude"), message.model


@dataclass
class Gemini:
    key: str
    model: str
    label: str = "Gemini"

    def configured(self) -> bool:
        return bool(self.key)

    def complete(self, system: str, user: str, schema: dict) -> tuple[dict, str]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.key, http_options=types.HttpOptions(timeout=int(TIMEOUT * 1000)))
        response = client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        reason = response.candidates[0].finish_reason if response.candidates else None
        if reason is not None and getattr(reason, "name", str(reason)) not in {"STOP", "FINISH_REASON_UNSPECIFIED"}:
            raise ProviderError(f"Gemini stopped early: {getattr(reason, 'name', reason)}")
        if not response.text:
            raise ProviderError("Gemini returned no text")
        return _parse(response.text, "Gemini"), self.model


@dataclass
class OpenAI:
    key: str
    model: str
    label: str = "OpenAI"

    def configured(self) -> bool:
        return bool(self.key)

    def complete(self, system: str, user: str, schema: dict) -> tuple[dict, str]:
        import openai

        client = openai.OpenAI(api_key=self.key, timeout=TIMEOUT, max_retries=2)
        response = client.responses.create(
            model=self.model,
            instructions=system,
            input=user,
            max_output_tokens=64000,
            text={"format": {"type": "json_schema", "name": "morning_brief", "schema": schema, "strict": True}},
        )
        if response.status != "completed":
            raise ProviderError(f"OpenAI's answer is {response.status}")
        return _parse(response.output_text, "OpenAI"), response.model or self.model


def providers(cfg: Config) -> list[Provider]:
    return [
        Claude(cfg.anthropic_key, cfg.anthropic_model, cfg.anthropic_effort),
        Gemini(cfg.gemini_key, cfg.gemini_model),
        OpenAI(cfg.openai_key, cfg.openai_model),
    ]


@dataclass
class Outcome:
    value: object = None  # what `check` returned for the answer that passed
    writer: str = ""  # "claude-opus-5-5 (Claude)"
    failures: list[str] = field(default_factory=list)


def write(chain: list[Provider], system: str, user: str, schema: dict, check: Callable[[dict], object]) -> Outcome:
    """Asks each provider in turn until one gives an answer that `check` accepts."""
    out = Outcome()
    for p in chain:
        if not p.configured():
            out.failures.append(f"{p.label}: no API key set")
            continue
        try:
            data, model = p.complete(system, user, schema)
            out.value = check(data)
        except Exception as exc:  # any failure, of any SDK or of the answer, moves on to the next
            log.warning("%s (%s) failed: %s: %s", p.label, p.model, type(exc).__name__, exc)
            out.failures.append(f"{p.label}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        out.writer = f"{model} ({p.label})"
        log.info("brief written by %s", out.writer)
        return out
    return out
