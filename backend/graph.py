from typing import AsyncIterator, Callable, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from config import get_settings
from llm import Brief
from llm import advocate as default_advocate
from llm import advocate_stream
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


def build_streaming_graph(checkpointer=None, max_revisions: int | None = None):
    max_revisions = max_revisions or settings.max_revisions

    async def advocate_node(state: GraphState) -> dict:
        writer = get_stream_writer()
        iteration = state["iterations"] + 1
        writer({"type": "writer_start", "iteration": iteration})
        previous = state.get("critique")
        draft = await advocate_stream(
            Brief(**state["brief"]),
            state.get("draft") or None,
            previous["feedback"] if previous else None,
            lambda token: writer({"type": "token", "text": token}),
        )
        return {"draft": draft, "iterations": iteration}

    async def critic_node(state: GraphState) -> dict:
        writer = get_stream_writer()
        writer({"type": "critic_start"})
        critique = await default_critic(Brief(**state["brief"]), state["draft"])
        writer(
            {
                "type": "critique",
                "approved": critique.approved,
                "feedback": critique.feedback,
            }
        )
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


def _make_config(thread_id: str | None, checkpointer) -> dict:
    return {"configurable": {"thread_id": thread_id}} if checkpointer else {}


async def _stream_graph(graph, config: dict, initial: dict) -> AsyncIterator[dict]:
    final_state: GraphState | None = None
    async for mode, chunk in graph.astream(
        initial,
        config=config,
        stream_mode=["custom", "values"],
    ):
        if mode == "custom":
            yield chunk
        else:
            final_state = chunk
    yield {
        "type": "result",
        "draft": final_state["draft"],
        "critique": final_state["critique"],
        "iterations": final_state["iterations"],
    }


async def run_stream(
    brief: Brief, *, thread_id: str | None = None, checkpointer=None
) -> AsyncIterator[dict]:
    graph = build_streaming_graph(checkpointer=checkpointer)
    config = _make_config(thread_id, checkpointer)
    initial: GraphState = {
        "brief": brief.model_dump(),
        "draft": "",
        "critique": None,
        "iterations": 0,
    }
    async for event in _stream_graph(graph, config, initial):
        yield event


async def refine_stream(
    instruction: str,
    *,
    thread_id: str | None = None,
    checkpointer=None,
    fallback_brief: dict | None = None,
    fallback_post: str | None = None,
) -> AsyncIterator[dict]:
    graph = build_streaming_graph(checkpointer=checkpointer)
    config = _make_config(thread_id, checkpointer)

    warm = False
    if checkpointer:
        snapshot = await graph.aget_state(config)
        warm = bool(snapshot.values.get("draft"))

    if warm:
        initial: dict = {
            "critique": {"approved": False, "feedback": instruction},
            "iterations": 0,
        }
    else:
        initial = {
            "brief": fallback_brief,
            "draft": fallback_post,
            "critique": {"approved": False, "feedback": instruction},
            "iterations": 0,
        }

    async for event in _stream_graph(graph, config, initial):
        yield event
