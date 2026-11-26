import json

import httpx
import pytest

from app.llm import Generation, ModelUnavailable, OpenAIProvider, configured_provider


def test_openai_payload_and_token_reporting():
    def respond(request):
        assert request.url.path == "/v1/responses"
        data = json.loads(request.content)
        assert data["max_output_tokens"] == 32
        assert data["store"] is False
        assert data["input"] == "Untrusted task data"
        assert data["instructions"] == "Summarize the task"
        return httpx.Response(200, json={
            "status":"completed",
            "output":[{"type":"message", "content":[{"type":"output_text","text":"Summary"}]}],
            "usage":{"input_tokens":20,"output_tokens":5},
        })

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = OpenAIProvider(client, "mock-key", "mock-model").generate("Summarize the task", "Untrusted task data", 32)
        assert response == Generation("Summary", 20, 5)


def test_configured_key_alone_does_not_enable_generation(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setenv("OPENAI_MODEL", "mock-model")
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    with httpx.Client() as client, pytest.raises(ModelUnavailable, match="model_provider_disabled"):
        configured_provider(client)
