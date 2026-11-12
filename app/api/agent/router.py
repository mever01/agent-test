from fastapi import APIRouter, Depends, HTTPException, status

from app.api.agent.schemas import ChatRequest, ChatResponse
from app.api.dependencies import get_agent_service, require_role
from app.db.models.user import User
from app.agent.service import AgentService
from app.services.exceptions import LLMTimeoutError, ServiceError

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat_with_agent(
    payload: ChatRequest,
    user: User = Depends(require_role(["manager", "admin"])),
    agent_service: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    """Основной эндпоинт взаимодействия с AI-агентом."""
    try:
        result = await agent_service.chat(
            message=payload.message,
            user_id=user.id,
            continuation_id=payload.continuation_id,
        )
        return ChatResponse.model_validate(result, from_attributes=True)
    except LLMTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(e),
        )
    except ServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
