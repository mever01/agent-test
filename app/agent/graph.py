from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes.classify import classify
from app.agent.nodes.clarify import clarify
from app.agent.nodes.prepare_result import prepare_result
from app.agent.nodes.read_and_retrieve import read_and_retrieve
from app.agent.nodes.save_draft import save_draft
from app.agent.nodes.search import search
from app.agent.state import AgentContext, AgentState, Step


def _next_step(state: AgentState) -> Step:
    return state["next_step"]


# PyCharm does not recognize TypedDict's generated keys in LangGraph's StateLike bound.
# noinspection PyTypeChecker
def build_graph(
    checkpointer: InMemorySaver,
) -> CompiledStateGraph[AgentState, AgentContext, AgentState, AgentState]:  # type: ignore
    graph = StateGraph[AgentState, AgentContext, AgentState, AgentState](  # type: ignore
        AgentState,
        context_schema=AgentContext,
    )
    graph.add_node("classify", classify)
    graph.add_node("search", search)
    graph.add_node("read_and_retrieve", read_and_retrieve)
    graph.add_node("prepare_result", prepare_result)
    graph.add_node("clarify", clarify)
    graph.add_node("save_draft", save_draft)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _next_step, ["search", END])
    graph.add_conditional_edges("search", _next_step, ["read_and_retrieve", "clarify", END])
    graph.add_conditional_edges("read_and_retrieve", _next_step, ["prepare_result", END])
    graph.add_conditional_edges("prepare_result", _next_step, ["save_draft", "clarify", END])
    graph.add_conditional_edges(
        "clarify",
        _next_step,
        ["search", "read_and_retrieve", "prepare_result", "clarify", END],
    )
    graph.add_edge("save_draft", END)
    return graph.compile(checkpointer=checkpointer)
