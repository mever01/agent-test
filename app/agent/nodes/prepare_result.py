import json
from dataclasses import asdict

from langgraph.runtime import Runtime

from app.agent.nodes.security import checked_chat
from app.agent.prompts import DRAFT, RETRY, SUMMARY
from app.agent.schemas import AgentResult, Clarification, SourcedAnswer
from app.agent.state import AgentContext, AgentState, AgentUpdate
from app.agent.tools import CREATE_DRAFT, CreateDraftArgs, tool_arguments
from app.db.schemas import MailThreadDetails
from app.external_api_clients.schemas import ChatMessage
from app.guardrails.inbound.pii_masker import mask_pii


async def prepare_result(
    state: AgentState,
    *,
    runtime: Runtime[AgentContext],
) -> AgentUpdate:
    run_id = state["run_id"]
    thread = state["thread"]
    assert thread is not None
    is_draft = state["intent"] == "draft"
    recipient = _recipient(
        thread, state.get("clarification_answer")
    ) if is_draft else None
    if is_draft and recipient is None:
        return _ask("Уточните адрес получателя из переписки.")

    payload = _model_context(state, thread, recipient)
    prompt = DRAFT if is_draft else SUMMARY
    answer: SourcedAnswer | None = None
    draft: CreateDraftArgs | None = None
    for instruction in (prompt, f"{prompt}\n{RETRY}"):
        messages: list[ChatMessage] = [
            {"role": "system", "content": instruction},
            {"role": "user", "content": payload}
        ]
        response = await checked_chat(
            runtime.context, run_id, messages,
            tools=[CREATE_DRAFT] if is_draft else None,
            stage="подготовка черновика" if is_draft else "подготовка сводки",
            output_schema=None if is_draft else SourcedAnswer,
        )
        try:
            candidate_draft = None
            if is_draft and response.tool_calls:
                candidate_draft = tool_arguments(
                    response, "create_draft", CreateDraftArgs
                )
                if (
                    candidate_draft.thread_id != state["thread_id"]
                    or candidate_draft.recipient.casefold() != recipient
                ):
                    return _ask("Уточните адрес получателя из переписки.")
            elif response.tool_calls:
                raise ValueError("Unexpected tool call")

            if candidate_draft is not None and not response.content:
                summary = await checked_chat(
                    runtime.context, run_id,
                    [
                        {"role": "system", "content": SUMMARY},
                        {"role": "user", "content": payload}
                    ],
                    stage="подготовка сводки к черновику",
                    output_schema=SourcedAnswer,
                )
                if summary.tool_calls:
                    raise ValueError("Unexpected tool call")
                response = summary

            candidate_answer = SourcedAnswer.model_validate_json(response.content or "")
            if candidate_answer.question:
                return _ask(candidate_answer.question)
            if is_draft and candidate_draft is None:
                raise ValueError("Missing draft")
            answer = candidate_answer
            draft = candidate_draft
            break
        except ValueError:
            continue
    if answer is None:
        return {
            "result": AgentResult(
                run_id,
                "Не удалось подготовить результат.",
                status="failed"
            ),
            "next_step": "__end__",
        }

    allowed_emails = {mail.id for mail in thread.messages[-20:]}
    allowed_documents = {
        chunk.source_id
        for chunk in state["rag_chunks"]
        if chunk.source_type == "company_doc"
    }
    result = AgentResult(
        run_id, answer.response,
        used_email_ids=list(
            dict.fromkeys(
                item for item in answer.email_ids if item in allowed_emails
            )
        ),
        used_document_ids=list(
            dict.fromkeys(
                item for item in answer.document_ids if item in allowed_documents
            )
        ),
    )
    if draft is not None:
        return {"result": result, "draft": draft, "next_step": "save_draft"}
    return {"result": result, "next_step": "__end__"}


def _recipient(thread: MailThreadDetails, clarification: str | None) -> str | None:
    client = (thread.client_email or "").strip().casefold()
    confirmed = {mail.sender.strip().casefold() for mail in thread.messages}
    if client and client in confirmed:
        return client
    if clarification:
        proposed = clarification.strip().casefold()
        participants = {
                       mail.recipient.strip().casefold()
                       for mail in thread.messages
                       } | confirmed
        if "@" in proposed and proposed in participants:
            return proposed
    return None


def _ask(question: str) -> AgentUpdate:
    return {"clarification": Clarification(question, "fact"), "next_step": "clarify"}


def _model_context(
    state: AgentState,
    thread: MailThreadDetails,
    recipient: str | None
) -> str:
    emails = [
        {**asdict(mail), "body": mask_pii(mail.body[:4000])}
        for mail in thread.messages[-20:]
    ]
    sources = [
        {"kind": chunk.source_type, "source_id": chunk.source_id,
         "thread_id": chunk.thread_id, "date": chunk.date,
         "content": mask_pii(chunk.content[:2500])}
        for chunk in state["rag_chunks"]
    ]
    return json.dumps({
        "request": state["request"],
        "clarification": state.get("clarification_answer"),
        "thread_id": thread.thread_id,
        "recipient": recipient,
        "untrusted_emails": emails,
        "rag_sources": sources,
    }, ensure_ascii=False, default=str)
