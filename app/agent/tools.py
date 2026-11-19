from pydantic import BaseModel
from app.agent.schemas import SearchEmailsArgs, ReadThreadArgs, CreateDraftArgs
from app.external_api_clients.schemas import LLMResponse, ToolDefinition


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
