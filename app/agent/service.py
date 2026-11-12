from typing import NotRequired, cast
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, Interrupt

from app.agent.graph import build_graph
from app.agent.schemas import AgentResult
from app.agent.state import AgentContext, AgentState, Step
from app.external_api_clients.llm_client import LLMClient
from app.guardrails.inbound.injection_detector import detect_prompt_injection
from app.guardrails.inbound.pii_masker import mask_pii
from app.rag.retrieval.service import RAGRetrievalService
from app.services.exceptions import SecurityViolationError
from app.services.mail_service import MailService


class AgentInvocation(AgentState):
    __interrupt__: NotRequired[tuple[Interrupt[str], ...]]


class AgentService:
    def __init__(
        self, llm_client: LLMClient, mail_service: MailService, rag_service: RAGRetrievalService
    ) -> None:
        self._llm = llm_client
        self._mail = mail_service
        self._rag = rag_service
        self._checkpointer = InMemorySaver()
        self._graph = build_graph(self._checkpointer)
        self._resuming: set[UUID] = set()

    async def chat(
        self, message: str, user_id: UUID | None = None, continuation_id: UUID | None = None
    ) -> AgentResult:
        run_id = str(continuation_id or uuid4())
        injection_detected, _ = detect_prompt_injection(message)
        if injection_detected:
            return self._blocked(run_id, "PROMPT_INJECTION")
        request = mask_pii(message.strip())
        config: RunnableConfig = {"configurable": {"thread_id": run_id}}
        context = AgentContext(
            llm=self._llm,
            mail=self._mail,
            rag=self._rag,
            canary=f"CANARY_SEC_{uuid4().hex}",
        )

        if continuation_id is None:
            return await self._invoke(
                {"run_id": run_id, "owner_id": user_id, "request": request},
                config, context, run_id, user_id,
            )

        if user_id is None or continuation_id in self._resuming:
            return self._unavailable(run_id)
        self._resuming.add(continuation_id)
        try:
            snapshot = await self._graph.aget_state(config)
            is_owner = snapshot.values.get("owner_id") == user_id
            awaiting_input = any(task.interrupts for task in snapshot.tasks)
            if not is_owner or not awaiting_input:
                return self._unavailable(run_id)
            return await self._invoke(Command(resume=request), config, context, run_id, user_id)
        finally:
            self._resuming.discard(continuation_id)

    async def _invoke(
        self,
        graph_input: AgentState | Command[Step],
        config: RunnableConfig,
        context: AgentContext,
        run_id: str,
        owner_id: UUID | None,
    ) -> AgentResult:
        retain_checkpoint = False
        try:
            output = await self._graph.ainvoke(graph_input, config=config, context=context)
            result = cast(AgentInvocation, output)
            if interrupts := result.get("__interrupt__"):
                retain_checkpoint = owner_id is not None
                return AgentResult(
                    run_id, interrupts[0].value, status="awaiting_input",
                    continuation_id=UUID(run_id) if retain_checkpoint else None,
                )
            return result["result"]
        except SecurityViolationError:
            return self._blocked(run_id, "CANARY_MATCH")
        finally:
            if not retain_checkpoint:
                await self._checkpointer.adelete_thread(run_id)

    @staticmethod
    def _unavailable(run_id: str) -> AgentResult:
        return AgentResult(run_id, "Уточнение недоступно. Начните новый запрос.", status="failed")

    @staticmethod
    def _blocked(run_id: str, reason: str) -> AgentResult:
        return AgentResult(
            run_id, "Обращение заблокировано.", status="blocked",
            is_blocked=True, block_reason=reason,
        )
