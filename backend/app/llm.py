import os
from dataclasses import dataclass
from typing import Protocol

import httpx


class ModelUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Generation:
    text: str
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    def generate(self, instruction: str, input_text: str, max_output_tokens: int) -> Generation: ...


class OpenAIProvider:
    def __init__(self, client: httpx.Client, api_key: str, model: str):
        self.client = client
        self.api_key = api_key
        self.model = model

    def generate(self, instruction, input_text, max_output_tokens):
        if len(instruction) > 4000 or len(input_text) > 16000 or not 16 <= max_output_tokens <= 2048:
            raise ValueError("Model input or output limit exceeded")
        try:
            response = self.client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "instructions": instruction, "input": input_text,
                      "max_output_tokens": max_output_tokens, "store": False},
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()
            if payload["status"] != "completed":
                raise ModelUnavailable("model_response_incomplete")
            text = "\n".join(
                part["text"] for item in payload["output"] if item["type"] == "message"
                for part in item["content"] if part["type"] == "output_text"
            )
            metrics = payload["usage"]
            return Generation(text, metrics["input_tokens"], metrics["output_tokens"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ModelUnavailable("model_provider_unavailable") from None


def configured_provider(client: httpx.Client) -> LLMProvider:
    key, model = os.getenv("OPENAI_API_KEY"), os.getenv("OPENAI_MODEL")
    if os.getenv("LLM_ENABLED") != "true" or not key or not model:
        raise ModelUnavailable("model_provider_disabled")
    return OpenAIProvider(client, key, model)
