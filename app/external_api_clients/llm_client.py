import httpx
import logging
from typing import Any
from app.configs import settings

logger = logging.getLogger(__name__)

class LLMResponse:
    def __init__(self, content: str | None = None, tool_calls: list[dict] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []

class LLMClient:
    def __init__(
        self,
        url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ):
        self.url = url or settings.llm.url
        self.model_name = model_name or settings.llm.model_name
        self.api_key = api_key or settings.llm.api_key
        self.temperature = temperature if temperature is not None else settings.llm.temperature
        self.timeout = timeout or settings.llm.timeout

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = "auto",
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """
        Вызов OpenAI-совместимого эндпоинта генерации чата.
        Поддерживает function calling (tools) и структурированный вывод (JSON).
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        if response_format:
            payload["response_format"] = response_format

        timeout_config = httpx.Timeout(self.timeout, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            try:
                response = await client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                choice = data["choices"][0]["message"]
                content = choice.get("content")
                raw_tool_calls = choice.get("tool_calls", [])

                formatted_tool_calls = []
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name") or tc.get("name", "")
                    fn_args = fn.get("arguments") or tc.get("args", "{}")

                    if isinstance(fn_args, str):
                        try:
                            parsed_args = json.loads(fn_args)
                        except Exception:
                            parsed_args = fn_args
                    elif isinstance(fn_args, dict):
                        parsed_args = fn_args
                    else:
                        parsed_args = {}

                    raw_args_str = fn_args if isinstance(fn_args, str) else json.dumps(fn_args, ensure_ascii=False)

                    # Стандартный формат OpenAI tool_calls + поля удобства name и args
                    formatted_tool_calls.append({
                        "id": tc.get("id", "call_default"),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": fn_name,
                            "arguments": raw_args_str,
                        },
                        "name": fn_name,
                        "args": parsed_args,
                    })

                return LLMResponse(content=content, tool_calls=formatted_tool_calls)
            except httpx.ReadTimeout as e:
                logger.error(
                    f"Превышен таймаут ответа LLM ({self.timeout}с) по адресу {self.url}. "
                    "Рекомендуется увеличить LLM_TIMEOUT или использовать меньшую/быструю модель."
                )
                raise e
            except httpx.HTTPStatusError as e:
                logger.error(f"Ошибка вызова LLM по адресу {self.url}: {e}. Ответ сервера: {e.response.text}")
                raise e
            except Exception as e:
                logger.error(f"Ошибка вызова LLM по адресу {self.url}: {e}")
                raise e

