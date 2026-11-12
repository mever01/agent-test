import json
from app.agent.tools.schemas import SearchEmailsArgs, ReadThreadArgs, CreateDraftArgs
from app.db.repositories.email_repository import EmailRepository

async def execute_tool_call(
    name: str,
    args: dict | str,
    email_repo: EmailRepository,
) -> str:
    """Исполнение вызова инструмента и возврат строкового результата для LLM."""
    if isinstance(args, str):
        try:
            parsed_args = json.loads(args)
        except Exception:
            parsed_args = {}
    else:
        parsed_args = args or {}

    if name == "search_emails":
        try:
            validated = SearchEmailsArgs.model_validate(parsed_args)
            words = validated.words
            sender = validated.sender
            start_date = validated.start_date
            end_date = validated.end_date
        except Exception:
            words = str(parsed_args.get("words", ""))
            sender = parsed_args.get("sender")
            start_date = None
            end_date = None

        snippets = await email_repo.search_emails(
            words=words, sender=sender, start_date=start_date, end_date=end_date
        )
        if not snippets:
            return "Писем по заданным критериям не найдено."
        results = [
            f"- Email ID: {s.email_id}, Thread ID: {s.thread_id}, От: {s.sender}, Дата: {s.date.strftime('%Y-%m-%d')}, Тема: '{s.subject}', Фрагмент: {s.snippet}"
            for s in snippets
        ]
        return "Найденные письма:\n" + "\n".join(results)

    elif name == "read_thread":
        try:
            val_args = ReadThreadArgs.model_validate(parsed_args)
        except Exception:
            return "Ошибка вызова read_thread: укажите корректный UUID thread_id из результатов поиска."

        thread = await email_repo.get_thread(val_args.thread_id)
        if not thread:
            return f"Цепочка с ID '{val_args.thread_id}' не найдена."
        if not thread.messages:
            return f"Цепочка '{val_args.thread_id}' найдена, но в ней нет сообщений."

        formatted_msgs = []
        for msg in thread.messages:
            formatted_msgs.append(
                f"[ID письма: {msg.id}] {msg.date.strftime('%Y-%m-%d %H:%M')} | От: {msg.sender} -> Кому: {msg.recipient}\n"
                f"Тема: {msg.subject}\n"
                f"Текст:\n{msg.body}"
            )
        return (
            f"История переписки по треду '{thread.thread_id}' (Тема: {thread.subject}, Клиент: {thread.client_email}, Статус: {thread.status}):\n\n"
            + "\n\n---\n\n".join(formatted_msgs)
        )

    elif name == "create_draft":
        try:
            draft_args = CreateDraftArgs.model_validate(parsed_args)
        except Exception:
            return "Ошибка вызова create_draft: проверьте правильность UUID thread_id и обязательные поля."

        draft_id = await email_repo.save_draft(
            thread_id=draft_args.thread_id,
            recipient=draft_args.recipient,
            subject=draft_args.subject,
            text_content=draft_args.text,
        )
        return json.dumps({"status": "saved", "draft_id": str(draft_id)}, ensure_ascii=False)

    return f"Неизвестный инструмент: {name}"

