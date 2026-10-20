"""Provider retry classification and quota fail-fast tests."""
import asyncio
import sys
from types import SimpleNamespace
import pytest

from app.utils.llm import LLMProviderError, call_llm


async def no_sleep(_):
    return None


def fake_genai(generate_content):
    model = SimpleNamespace(generate_content=generate_content)
    return SimpleNamespace(
        configure=lambda **kwargs: None,
        GenerativeModel=lambda model_name: model,
        types=SimpleNamespace(GenerationConfig=lambda **kwargs: kwargs),
    )


@pytest.mark.asyncio
async def test_daily_quota_exhaustion_fails_fast_without_spending_retry(monkeypatch):
    calls = 0

    def generate_content(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError(
            "429 quota exceeded for metric generativelanguage.generateRequestsPerDay"
        )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai(generate_content))
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    with pytest.raises(LLMProviderError) as error:
        await call_llm("test", max_tokens=20)

    assert error.value.failure_kind == "quota_exhausted"
    assert calls == 1
    assert "daily request quota" in str(error.value)


@pytest.mark.asyncio
async def test_transient_rate_limit_uses_bounded_provider_retry(monkeypatch):
    calls = 0

    def generate_content(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 rate limit; retry later")
        return SimpleNamespace(text="ok")

    retry_count = []
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai(generate_content))
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await call_llm("test", max_tokens=20, on_retry=lambda: retry_count.append(1))

    assert result == "ok"
    assert calls == 2
    assert retry_count == [1]
