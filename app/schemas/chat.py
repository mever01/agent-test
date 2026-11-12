from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    user_id: str = Field(default="manager_1", description="ID пользователя/менеджера")
    message: str = Field(..., min_length=1, max_length=4000, description="Запрос менеджера к агенту")

class ChatResponse(BaseModel):
    run_id: str
    response: str
    draft_id: str | None = None
    used_document_ids: list[str] = Field(default_factory=list)
    used_email_ids: list[str] = Field(default_factory=list)
    is_blocked: bool = False
    block_reason: str | None = None

