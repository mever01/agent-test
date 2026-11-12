import uuid
from datetime import date
from pydantic import BaseModel

class SearchEmailsArgs(BaseModel):
    words: str
    sender: str | None = None
    start_date: date | None = None
    end_date: date | None = None

class ReadThreadArgs(BaseModel):
    thread_id: uuid.UUID

class CreateDraftArgs(BaseModel):
    thread_id: uuid.UUID
    recipient: str
    subject: str
    text: str


TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Поиск писем по ключевым словам/артикулам с фильтрами по отправителю и диапазону дат. Возвращает ID письма и цепочки, тему, отправителя, дату и краткий фрагмент.",
            "parameters": {
                "type": "object",
                "properties": {
                    "words": {
                        "type": "string",
                        "description": "Ключевые слова, фразы, артикулы или названия моделей (например, 'проект X', 'Артикул-98123')",
                    },
                    "sender": {
                        "type": "string",
                        "description": "Email или часть имени отправителя для фильтрации",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Опциональное начало диапазона дат (YYYY-MM-DD). Не указывай, если пользователь не назвал период явно.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Опциональный конец диапазона дат (YYYY-MM-DD). Не указывай, если пользователь не назвал период явно.",
                    },
                },
                "required": ["words"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_thread",
            "description": "Чтение полной цепочки сообщений по thread_id. Возвращает сообщения в хронологическом порядке с текстом, отправителем и получателем.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Идентификатор цепочки переписки (например, 'th_project_alpha_01')",
                    },
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft",
            "description": "Создание черновика ответа на письмо: привязывает к thread_id, указывает получателя, тему и текст. Сохраняет черновик и возвращает draft_id (письмо не отправляется клиенту).",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Идентификатор цепочки переписки",
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Email получателя (клиента)",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Тема черновика письма (например, 'Re: Поставка серверов')",
                    },
                    "text": {
                        "type": "string",
                        "description": "Полный подготовленный текст письма",
                    },
                },
                "required": ["thread_id", "recipient", "subject", "text"],
            },
        },
    },
]

