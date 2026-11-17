from app.dto.db_mail import MailSnippet


def merge_matches(
    lexical: list[MailSnippet], semantic: list[MailSnippet], limit: int,
) -> list[MailSnippet]:
    """Объединяет ранги через RRF и удаляет повторные попадания одного письма."""
    scores: dict[str, float] = {}
    messages: dict[str, MailSnippet] = {}
    for ranking in (lexical, semantic):
        seen: set[str] = set()
        for rank, message in enumerate(ranking, 1):
            if message.email_id in seen:
                continue
            seen.add(message.email_id)
            scores[message.email_id] = (
                scores.get(message.email_id, 0) + 1 / (60 + rank)
            )
            messages.setdefault(message.email_id, message)
    ordered = sorted(messages, key=lambda key: (-scores[key], key))
    return [messages[key] for key in ordered[:limit]]
