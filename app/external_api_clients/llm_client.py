import json
from collections.abc import Callable
from typing import cast

import httpx
from pydantic import JsonValue

from app.configs import settings
from app.external_api_clients.schemas import (
    ChatCompletionRequest,
    ChatMessage,
    LLMResponse,
    ProviderChatCompletion,
    ProviderToolCall,
    ProviderToolFunction,
    ResponseFormat,
    ToolCall,
    ToolChoice,
    ToolDefinition,
)
from core.utils.mixins.logger import LoggerMixin


class LLMClient(LoggerMixin):
    def __init__(
        self,
        url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> None:
        self.url = settings.llm.url if url is None else url
        self.model_name = (
            settings.llm.model_name
            if model_name is None
            else model_name
        )
        self.api_key = (
            settings.llm.api_key
            if api_key is None
            else api_key
        )
        self.temperature = (
            settings.llm.temperature
            if temperature is None
            else temperature
        )
        self.timeout = (
            settings.llm.timeout
            if timeout is None
            else timeout
        )

        headers = {"Content-Type": "application/json"}

        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(
                self.timeout,
                connect=15.0,
            ),
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        tool_choice: ToolChoice | None = "auto",
        response_format: ResponseFormat | None = None,
        max_tokens: int | None = None,
        inspect_response: Callable[[object], None] | None = None,
    ) -> LLMResponse:
        """Выполняет запрос к OpenAI-совместимому Chat API."""

        payload: ChatCompletionRequest = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }

        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if response_format is not None:
            payload["response_format"] = response_format

        try:
            response = await self._client.post(self.url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.logger.error("LLM HTTP error: status=%s", exc.response.status_code)
            raise
        except httpx.HTTPError as exc:
            self.logger.error("LLM request failed: type=%s", type(exc).__name__)
            raise

        try:
            data = response.json()
        except ValueError:
            if inspect_response is not None:
                inspect_response(response.text)
            raise
        if inspect_response is not None:
            inspect_response(data)
            inspect_response(response.text)

        completion = cast(ProviderChatCompletion, data)
        choice = completion["choices"][0]
        message = choice["message"]
        return LLMResponse(
            content=message.get("content"),
            finish_reason=choice.get("finish_reason"),
            tool_calls=self._parse_tool_calls(message.get("tool_calls") or []),
        )

    @staticmethod
    def _parse_tool_calls(
        raw_tool_calls: list[ProviderToolCall],
    ) -> list[ToolCall]:
        """Нормализует tool calls для использования в агенте."""

        result: list[ToolCall] = []

        for tool_call in raw_tool_calls:
            function: ProviderToolFunction = tool_call.get("function") or {}

            name = (
                function.get("name")
                or tool_call.get("name", "")
            )

            raw_args = function.get("arguments")
            if raw_args is None:
                raw_args = tool_call.get("args", "{}")

            parsed_args: JsonValue
            if isinstance(raw_args, str):
                arguments_str = raw_args
                try:
                    parsed_args = cast(JsonValue, json.loads(raw_args))
                except json.JSONDecodeError:
                    parsed_args = raw_args
            else:
                parsed_args = raw_args
                arguments_str = json.dumps(
                    raw_args,
                    ensure_ascii=False,
                )

            result.append(
                {
                    "id": tool_call.get("id"),
                    "type": tool_call.get("type", "function"),
                    "function": {
                        "name": name,
                        "arguments": arguments_str,
                    },
                    "name": name,
                    "args": parsed_args,
                }
            )

        return result

    async def close(self) -> None:
        """Закрывает пул HTTP-соединений."""
        await self._client.aclose()
