"""LLM utility â€” wraps Gemini API calls with retry and error handling."""
from __future__ import annotations
import logging
import asyncio
import os
from typing import Optional, Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 2.0  # seconds


class LLMProviderError(RuntimeError):
    """Provider connectivity, quota, or rate-limit failure after bounded retries."""

    def __init__(self, message: str, failure_kind: str = "provider_unavailable"):
        super().__init__(message)
        self.failure_kind = failure_kind


def _provider_failure_kind(error: Exception) -> str:
    detail = str(error).casefold()
    if any(marker in detail for marker in (
        "generaterequestsperday", "free_tier_requests", "quota exceeded for metric",
        "daily request quota",
    )):
        return "quota_exhausted"
    if any(marker in detail for marker in ("api key not valid", "invalid api key", "unauthorized", "401", "403")):
        return "invalid_credentials"
    if any(marker in detail for marker in ("429", "resource_exhausted", "rate limit", "too many requests")):
        return "transient_provider_error"
    return "provider_unavailable"


def _provider_json_schema(response_schema):
    """Convert Pydantic JSON Schema to Gemini's supported JSON Schema subset."""
    root = response_schema.model_json_schema() if hasattr(response_schema, "model_json_schema") else response_schema

    def convert(node):
        if "$ref" in node:
            ref = node["$ref"].split("/")
            target = root
            for part in ref[1:]:
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return convert(target)
        if "anyOf" in node:
            options = [item for item in node["anyOf"] if item.get("type") != "null"]
            if len(options) == 1:
                result = convert(options[0])
                result["nullable"] = len(options) != len(node["anyOf"])
                return result
            raise ValueError("Unsupported union in Gemini structured output schema")
        result = {}
        for key in ("type", "enum", "required", "format", "description"):
            if key in node:
                result[key] = node[key]
        if "properties" in node:
            result["properties"] = {key: convert(value) for key, value in node["properties"].items()}
        if "items" in node:
            result["items"] = convert(node["items"])
        return result

    return convert(root)


async def call_llm(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1000,
    model: Optional[str] = None,
    response_schema=None,
    on_retry: Optional[Callable[[], None]] = None,
) -> str:
    """
    Call the configured LLM (Gemini by default) with retry logic.
    Returns the text response.
    Raises RuntimeError if all retries fail.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Please add it to your .env file."
        )

    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    last_error = None
    failure_kind = "provider_unavailable"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            client = genai.GenerativeModel(model_name)

            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if response_schema is not None:
                # Gemini's generateContent structured output mode constrains
                # response formatting at the provider as well as validating it
                # locally with Pydantic.
                generation_config.update({
                    "response_mime_type": "application/json",
                    "response_schema": _provider_json_schema(response_schema),
                })
            response = await asyncio.to_thread(
                client.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(**generation_config),
                request_options={"timeout": 30},
            )
            return response.text

        except Exception as e:
            last_error = e
            failure_kind = _provider_failure_kind(e)
            logger.warning(
                "LLM provider attempt %s/%s failed (%s)",
                attempt, MAX_RETRIES, failure_kind,
            )
            # A daily quota or credential failure will not recover on an
            # immediate retry. Avoid burning another request and show the
            # actionable cause to the agent/UI.
            if failure_kind in {"quota_exhausted", "invalid_credentials"}:
                break
            if attempt < MAX_RETRIES:
                if on_retry:
                    on_retry()
                await asyncio.sleep(RETRY_DELAY * attempt)

    safe_message = {
        "quota_exhausted": "Gemini daily request quota is exhausted for the configured project/model.",
        "invalid_credentials": "Gemini rejected the configured API credentials.",
        "transient_provider_error": "Gemini rate limited or temporarily rejected the request after bounded retries.",
        "provider_unavailable": "Gemini was unavailable after bounded retries.",
    }[failure_kind]
    raise LLMProviderError(safe_message, failure_kind=failure_kind) from last_error
