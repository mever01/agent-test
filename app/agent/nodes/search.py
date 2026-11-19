import logging
import httpx
from uuid import UUID

from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.agent.nodes.security import checked_chat
from app.agent.prompts import RETRY, SEARCH
from app.agent.schemas import AgentResult, Clarification, SearchNeedsCriteria
from app.agent.state import AgentContext, AgentState, AgentUpdate
from app.agent.tools import SEARCH_EMAILS, SearchEmailsArgs, tool_arguments
from app.dto.db_mail import MailSearchCriteria, MailSnippet

SEARCH_LIMIT = 10
logger = logging.getLogger(__name__)


async def search(
    state: AgentState,
    *,
    runtime: Runtime[AgentContext],
) -> AgentUpdate:
    run_id = state["run_id"]
    request = state["request"]
    if answer := state.get("clarification_answer"):
        request = f"{request}\nУточнение менеджера: {answer}"
    criteria: SearchEmailsArgs | None = None
    for instruction in (SEARCH, f"{SEARCH}\n{RETRY}"):
        response = await checked_chat(
            runtime.context, run_id,
            [
                {"role": "system", "content": instruction}, {"role": "user", "content": request}
            ],
            tools=[SEARCH_EMAILS],
            stage="подготовка поиска",
        )
        try:
            if not response.tool_calls:
                SearchNeedsCriteria.model_validate_json(response.content or "")
                break
            criteria = tool_arguments(response, "search_emails", SearchEmailsArgs)
            break
        except ValueError:
            continue
    if criteria is None:
        question = Clarification(
            "Уточните проект, отправителя, артикул или период поиска.",
            "criteria",
        )
        return {"clarification": question, "next_step": "clarify"}

    try:
        matches = await _search_mail(runtime.context, criteria)
    except (SQLAlchemyError, OSError, httpx.HTTPError, ValueError):
        return {"result": AgentResult(
            run_id, "Не удалось выполнить поиск писем.", status="failed"
        ), "next_step": "__end__"}
    if not matches:
        logger.info(
            "Mail search empty: run_id=%s word_count=%d sender=%s participant=%s period=%s",
            run_id,
            len((criteria.words or "").split()),
            criteria.sender is not None,
            criteria.participant is not None,
            criteria.start_date is not None or criteria.end_date is not None,
        )
        return {"result": AgentResult(
            run_id, "Подходящие письма не найдены. Попробуйте уточнить тему, участника или период."
        ), "next_step": "__end__"}
    if state["intent"] == "search":
        return {"result": AgentResult(run_id, _format_matches(matches)), "next_step": "__end__"}
    return _select_thread(matches, criteria.thread_selection == "latest")


async def _search_mail(
    context: AgentContext, criteria: SearchEmailsArgs,
) -> list[MailSnippet]:
    filters = MailSearchCriteria(
        words=criteria.words,
        sender=criteria.sender,
        participant=criteria.participant,
        start_date=criteria.start_date,
        end_date=criteria.end_date,
    )
    matches = await context.email_search.search(
        filters, owner_id=context.owner_id,
        limit=100 if criteria.thread_selection == "latest" else SEARCH_LIMIT + 1,
    )
    if criteria.thread_selection == "latest":
        return await context.threads.thread_activity(
            matches, owner_id=context.owner_id
        )
    return matches


def _select_thread(matches: list[MailSnippet], latest: bool) -> AgentUpdate:
    by_thread: dict[str, MailSnippet] = {}
    for match in sorted(
        matches,
        key=lambda mail: mail.thread_last_date or mail.date,
        reverse=True,
    ):
        by_thread.setdefault(match.thread_id, match)
    candidates = tuple(by_thread.values())
    unambiguous_latest = latest and len(candidates) > 1 and (
        (candidates[0].thread_last_date or candidates[0].date)
        > (candidates[1].thread_last_date or candidates[1].date)
    )
    if len(candidates) == 1 or unambiguous_latest:
        return {"thread_id": UUID(candidates[0].thread_id), "next_step": "read_and_retrieve"}
    options = candidates[:SEARCH_LIMIT]
    listing = "\n".join(
        f"{index}. {mail.subject} ({mail.sender}, {mail.date.date()})\n   {_snippet(mail)}"
        for index, mail in enumerate(options, 1)
    )
    return {
        "clarification": Clarification(f"Выберите номер цепочки:\n{listing}", "candidate", options),
        "next_step": "clarify",
    }


def _snippet(mail: MailSnippet) -> str:
    text = " ".join(mail.snippet.replace("<b>", "").replace("</b>", "").split())
    return text[:160]


def _format_matches(matches: list[MailSnippet]) -> str:
    rows = [
        f"- {mail.date.date()} · {mail.subject} · {mail.sender}\n"
        f"  Письмо: {mail.email_id}, цепочка: {mail.thread_id}\n  {mail.snippet}"
        for mail in matches[:SEARCH_LIMIT]
    ]
    if len(matches) > SEARCH_LIMIT:
        rows.append("Показаны первые 10 совпадений. Уточните поиск, чтобы сузить выдачу.")
    return "\n".join(rows)
