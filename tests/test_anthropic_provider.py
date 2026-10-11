"""AnthropicProvider against a stub client — no network calls."""

from types import SimpleNamespace

import pytest

from lecture_notes.llm.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from lecture_notes.llm.base import LLMError


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class StubClient:
    def __init__(self, message):
        self.message = message
        self.calls = []
        self.messages = SimpleNamespace(stream=self._stream("plain"))
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream("beta")))

    def _stream(self, kind):
        def stream(**kwargs):
            self.calls.append((kind, kwargs))
            return _Stream(self.message)
        return stream


def _message(text='{"summary": "ok"}', stop_reason="end_turn", iterations=None, model="claude-sonnet-5-5"):
    usage = SimpleNamespace(
        input_tokens=1200, output_tokens=300, cache_read_input_tokens=0,
        cache_creation_input_tokens=0, iterations=iterations,
    )
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason, usage=usage, model=model,
    )


SETTINGS = {"effort": "medium", "max_output_tokens": 1000, "refusal_fallback": True}


def test_request_shape_and_parsing():
    client = StubClient(_message())
    p = AnthropicProvider("claude-sonnet-5-5", SETTINGS, api_key="unused", client=client)
    resp = p.generate_json("system", "user", {"type": "object"})
    assert resp.data == {"summary": "ok"}
    kind, kwargs = client.calls[0]
    assert kind == "beta"
    assert kwargs["betas"] == [FALLBACK_BETA] and kwargs["fallbacks"] == "default"
    assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert kwargs["output_config"]["effort"] == "medium"
    assert kwargs["system"] == "system"
    assert resp.usage[0].model == "claude-sonnet-5-5"
    assert resp.usage[0].input_tokens == 1200


def test_haiku_or_disabled_fallback_uses_plain_endpoint():
    client = StubClient(_message(model="claude-haiku-5-5"))
    AnthropicProvider("claude-haiku-5-5", SETTINGS, api_key="x", client=client).generate_json("s", "u", {})
    client2 = StubClient(_message())
    AnthropicProvider("claude-sonnet-5-5", {**SETTINGS, "refusal_fallback": False}, api_key="x",
                      client=client2).generate_json("s", "u", {})
    assert client.calls[0][0] == "plain" and client2.calls[0][0] == "plain"
    assert "fallbacks" not in client.calls[0][1]


def test_usage_per_model_when_fallback_ran():
    its = [
        SimpleNamespace(type="message", model=None, input_tokens=1, output_tokens=1,
                        cache_read_input_tokens=0, cache_creation_input_tokens=0),
        SimpleNamespace(type="fallback_message", model="claude-opus-5-5", input_tokens=1000,
                        output_tokens=200, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    ]
    client = StubClient(_message(iterations=its))
    resp = AnthropicProvider("claude-sonnet-5-5", SETTINGS, api_key="x", client=client).generate_json("s", "u", {})
    assert [(u.model, u.input_tokens) for u in resp.usage] == [("claude-opus-5-5", 1000)]


@pytest.mark.parametrize("stop_reason, needle", [("refusal", "odmówił"), ("max_tokens", "max_output_tokens")])
def test_bad_stop_reasons(stop_reason, needle):
    client = StubClient(_message(stop_reason=stop_reason))
    with pytest.raises(LLMError, match=needle):
        AnthropicProvider("claude-sonnet-5-5", SETTINGS, api_key="x", client=client).generate_json("s", "u", {})


def test_invalid_json():
    client = StubClient(_message(text="nie json"))
    with pytest.raises(LLMError, match="JSON"):
        AnthropicProvider("claude-sonnet-5-5", SETTINGS, api_key="x", client=client).generate_json("s", "u", {})


def test_create_provider_without_key(monkeypatch):
    import lecture_notes.llm as llm
    monkeypatch.setattr(llm, "get_api_key", lambda provider: None)
    with pytest.raises(LLMError, match="setup"):
        llm.create_provider({"provider": "anthropic", "model": "claude-sonnet-5-5"})
    with pytest.raises(LLMError, match="Nieznany dostawca"):
        llm.create_provider({"provider": "nope", "model": "m"})
