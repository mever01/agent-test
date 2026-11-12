from typing import Literal

from pydantic import BaseModel, Field, JsonValue
from typing_extensions import NotRequired, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class ToolFunction(TypedDict):
    name: str
    description: str
    parameters: dict[str, object]


class ToolDefinition(TypedDict):
    type: Literal["function"]
    function: ToolFunction


class ToolName(TypedDict):
    name: str


class NamedToolChoice(TypedDict):
    type: Literal["function"]
    function: ToolName


class JsonSchema(TypedDict):
    name: str
    schema: dict[str, object]


class StructuredResponseFormat(TypedDict):
    type: Literal["json_schema"]
    json_schema: JsonSchema


class JsonObjectResponseFormat(TypedDict):
    type: Literal["json_object"]


type ResponseFormat = StructuredResponseFormat | JsonObjectResponseFormat
type ToolChoice = str | NamedToolChoice


class ChatCompletionRequest(TypedDict):
    model: str
    messages: list[ChatMessage]
    temperature: float
    tools: NotRequired[list[ToolDefinition]]
    tool_choice: NotRequired[ToolChoice]
    max_tokens: NotRequired[int]
    response_format: NotRequired[ResponseFormat]


class ProviderToolFunction(TypedDict, total=False):
    name: str
    arguments: JsonValue


class ProviderToolCall(TypedDict, total=False):
    id: str | None
    type: str
    function: ProviderToolFunction | None
    name: str
    args: JsonValue


class ProviderMessage(TypedDict, total=False):
    content: str | None
    tool_calls: list[ProviderToolCall] | None


class ProviderChoice(TypedDict):
    message: ProviderMessage
    finish_reason: NotRequired[str | None]


class ProviderChatCompletion(TypedDict):
    choices: list[ProviderChoice]


class ToolCall(TypedDict):
    name: str
    args: JsonValue
    id: NotRequired[str | None]
    type: NotRequired[str]
    function: NotRequired[ProviderToolFunction]


class LLMResponse(BaseModel):
    content: str | None = None
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
