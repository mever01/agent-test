from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.dto.db_mail import MailSearchCriteria
from app.external_api_clients.schemas import LLMResponse, ToolDefinition


class SearchEmailsArgs(MailSearchCriteria):
    model_config = ConfigDict(extra="forbid")

    words: str | None = Field(
        default=None,
        description="Тема, которую обсуждали в письмах, название проекта или артикул. "
                    "Для «где обсуждали перенос сроков» укажи «перенос сроков».",
    )
    sender: str | None = Field(default=None, description="Адрес или имя отправителя письма.")
    participant: str | None = Field(
        default=None,
        description="Адрес участника переписки в обе стороны.",
    )
    start_date: date | None = Field(default=None, description="Первый день периода включительно.")
    end_date: date | None = Field(default=None, description="Последний день периода включительно.")
    thread_selection: Literal["latest"] | None = Field(
        default=None,
        description="latest только по явной просьбе выбрать последнюю переписку из совпадений.",
    )
    @field_validator("words")
    @classmethod
    def discard_generic_terms(cls, value: str | None) -> str | None:
        if value and value.strip().casefold() in {"письмо", "письма", "переписка", "переписку"}:
            return None
        return value


class ReadThreadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: UUID


class CreateDraftArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: UUID
    recipient: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    ]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _tool(name: str, description: str, schema: type[BaseModel]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema.model_json_schema(),
        },
    }


SEARCH_EMAILS = _tool(
    "search_emails",
    "Поиск исходных писем по словам, отправителю, участнику и датам ISO."
    "Нужен хотя бы один критерий.",
    SearchEmailsArgs,
)
READ_THREAD = _tool(
    "read_thread",
    "Чтение полной цепочки по UUID.",
    ReadThreadArgs
)
CREATE_DRAFT = _tool(
    "create_draft",
    "Сохранение черновика ответа без отправки.",
    CreateDraftArgs
)
TOOLS_DEFINITIONS = [SEARCH_EMAILS, READ_THREAD, CREATE_DRAFT]


def tool_arguments[T: BaseModel](response: LLMResponse, name: str, schema: type[T]) -> T:
    if len(response.tool_calls) != 1 or response.tool_calls[0]["name"] != name:
        raise ValueError("Unexpected tool call")
    return schema.model_validate(response.tool_calls[0]["args"])
