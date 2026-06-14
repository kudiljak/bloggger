from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from config import get_settings
from llm import Brief
from llm import advocate as default_advocate
from llm import critic as default_critic

settings = get_settings()


class GraphState(TypedDict):
    brief: dict
    draft: str
    critique: dict | None
    iterations: int


def build_graph(
    advocate_fn: Callable = default_advocate,
    critic_fn: Callable = default_critic,
    max_revisions: int | None = None,
    checkpointer=None,
):
    max_revisions = max_revisions or settings.max_revisions

    async def advocate_node(state: GraphState) -> dict:
        previous = state.get("critique")
        draft = await advocate_fn(
            Brief(**state["brief"]),
            state.get("draft") or None,
            previous["feedback"] if previous else None,
        )
        return {"draft": draft, "iterations": state["iterations"] + 1}

    async def critic_node(state: GraphState) -> dict:
        critique = await critic_fn(Brief(**state["brief"]), state["draft"])
        return {"critique": critique.model_dump()}

    def decide(state: GraphState) -> str:
        if state["critique"]["approved"] or state["iterations"] >= max_revisions:
            return "stop"
        return "revise"

    graph = StateGraph(GraphState)
    graph.add_node("advocate", advocate_node)
    graph.add_node("critic", critic_node)
    graph.add_edge(START, "advocate")
    graph.add_edge("advocate", "critic")
    graph.add_conditional_edges("critic", decide, {"revise": "advocate", "stop": END})
    return graph.compile(checkpointer=checkpointer)


async def run(
    brief: Brief, *, thread_id: str | None = None, checkpointer=None, **kwargs
) -> GraphState:
    graph = build_graph(checkpointer=checkpointer, **kwargs)
    config = {"configurable": {"thread_id": thread_id}} if checkpointer else {}
    return await graph.ainvoke(
        {"brief": brief.model_dump(), "draft": "", "critique": None, "iterations": 0},
        config=config,
    )
