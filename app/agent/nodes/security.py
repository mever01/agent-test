import asyncio
import logging

import httpx
from pydantic import BaseModel

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentContext
from app.external_api_clients.schemas import (
    ChatMessage,
    LLMResponse,
    StructuredResponseFormat,
    ToolDefinition,
)
from app.guardrails.outbound.canary_detector import find_canary_in_response
from app.guardrails.security_logger import log_canary_leak
from app.services.exceptions import LLMTimeoutError, SecurityViolationError, ServiceError

logger = logging.getLogger(__name__)


async def checked_chat(
    context: AgentContext,
    run_id: str,
    messages: list[ChatMessage],
    *,
    tools: list[ToolDefinition] | None = None,
    stage: str,
    output_schema: type[BaseModel] | None = None,
) -> LLMResponse:
    def inspect_response(payload: object) -> None:
        location = find_canary_in_response(payload, context.canary)
        if location:
            raise SecurityViolationError(location)

    response_format: StructuredResponseFormat | None = None
    if output_schema is not None:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": output_schema.__name__,
                "schema": output_schema.model_json_schema(),
            },
        }
    system_prompt = SYSTEM_PROMPT.format(canary=context.canary)
    try:
        response = await context.llm.chat(
            messages=[{"role": "system", "content": system_prompt}, *messages],
            tools=tools,
            response_format=response_format,
            inspect_response=inspect_response,
        )
        inspect_response(response.model_dump())
        if response.finish_reason == "length":
            limit_error = f"Ответ модели превысил лимит генерации. Этап: {stage}."
            if output_schema is None or response.tool_calls:
                raise ServiceError(limit_error)
            try:
                output_schema.model_validate_json(response.content or "")
            except ValueError:
                raise ServiceError(limit_error) from None
        return response
    except SecurityViolationError as exc:
        location = (
            "tool_call_arguments" if exc.args == ("tool_call_arguments",) else "model_response"
        )
        try:
            await asyncio.to_thread(log_canary_leak, run_id, location)
        except OSError:
            logger.error("Could not write Canary audit: run_id=%s", run_id)
        raise SecurityViolationError("CANARY_MATCH") from None
    except httpx.TimeoutException:
        raise LLMTimeoutError("Модель не ответила вовремя.") from None
    except (httpx.HTTPError, ValueError, LookupError, TypeError, AttributeError) as exc:
        logger.error("LLM response failed: run_id=%s, stage=%s, type=%s", run_id, stage,
                     type(exc).__name__)
        raise ServiceError(f"Не удалось получить ответ модели. Этап: {stage}.") from None
