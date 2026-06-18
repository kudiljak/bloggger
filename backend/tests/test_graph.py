import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from graph import build_graph, run  # noqa: E402
from llm import Brief, CriterionResult, Critique  # noqa: E402

BRIEF = Brief(
    topic="Cold brew at home",
    brand="BeanThere",
    tone="friendly",
    audience="beginners",
    length="short",
)


def make_critique(approved: bool) -> Critique:
    ok = CriterionResult(passed=True, comment="fine")
    tone = CriterionResult(passed=approved, comment="fine" if approved else "needs work")
    return Critique(
        approved=approved,
        feedback="Looks good!" if approved else "Fix the tone and a typo.",
        spelling=ok,
        grammar=ok,
        accuracy=ok,
        tone_brand_audience=tone,
        length=ok,
    )


class FakeWriter:
    def __init__(self):
        self.calls = 0
        self.feedbacks: list[str | None] = []
        self.prev_drafts: list[str | None] = []

    async def __call__(self, brief, previous_draft, previous_feedback):
        self.calls += 1
        self.feedbacks.append(previous_feedback)
        self.prev_drafts.append(previous_draft)
        return f"draft v{self.calls}"


class FakeCritic:
    def __init__(self, approve_on: int):
        self.approve_on = approve_on
        self.calls = 0

    async def __call__(self, brief, draft):
        self.calls += 1
        return make_critique(approved=self.calls >= self.approve_on)


async def test_approve_first_pass():
    writer, crit = FakeWriter(), FakeCritic(approve_on=1)
    final = await run(BRIEF, advocate_fn=writer, critic_fn=crit)
    assert final["iterations"] == 1
    assert writer.calls == 1
    assert final["critique"]["approved"] is True
    print("PASS approve_first_pass: 1 draft, approved, no revision")


async def test_revise_then_approve():
    writer, crit = FakeWriter(), FakeCritic(approve_on=2)
    final = await run(BRIEF, advocate_fn=writer, critic_fn=crit)
    assert final["iterations"] == 2
    assert writer.calls == 2
    assert final["critique"]["approved"] is True
    assert writer.feedbacks == [None, "Fix the tone and a typo."]
    print("PASS revise_then_approve: 2 drafts, fed feedback on revision, then approved")


async def test_guard_at_three():
    writer, crit = FakeWriter(), FakeCritic(approve_on=999)
    final = await run(BRIEF, advocate_fn=writer, critic_fn=crit, max_revisions=3)
    assert final["iterations"] == 3
    assert writer.calls == 3
    assert final["critique"]["approved"] is False
    print("PASS guard_at_three: stopped after 3 drafts despite no approval")


async def test_checkpointer_persists_state():
    saver = MemorySaver()
    writer, crit = FakeWriter(), FakeCritic(approve_on=1)
    graph = build_graph(advocate_fn=writer, critic_fn=crit, checkpointer=saver)
    config = {"configurable": {"thread_id": "conv-1"}}
    final = await graph.ainvoke(
        {"brief": BRIEF.model_dump(), "draft": "", "critique": None, "iterations": 0},
        config=config,
    )
    # State is retrievable later by thread_id -> proves persistence.
    snapshot = await graph.aget_state(config)
    assert snapshot.values["iterations"] == final["iterations"] == 1
    assert snapshot.values["draft"] == "draft v1"
    print("PASS checkpointer_persists_state: state retrievable by thread_id")


async def test_refine_resumes_from_checkpoint():
    saver = MemorySaver()
    writer, crit = FakeWriter(), FakeCritic(approve_on=1)
    graph = build_graph(advocate_fn=writer, critic_fn=crit, checkpointer=saver)
    config = {"configurable": {"thread_id": "conv-1"}}

    await graph.ainvoke(
        {"brief": BRIEF.model_dump(), "draft": "", "critique": None, "iterations": 0},
        config=config,
    )
    # Refine: resume the same thread with ONLY an instruction (no brief, no draft).
    final = await graph.ainvoke(
        {"critique": {"approved": False, "feedback": "Make it funnier"}, "iterations": 0},
        config=config,
    )

    # The second advocate call must have seen the persisted draft + the instruction,
    # proving brief/draft survived in the checkpoint without being re-sent.
    assert writer.prev_drafts == [None, "draft v1"]
    assert writer.feedbacks == [None, "Make it funnier"]
    assert final["draft"] == "draft v2"
    print("PASS refine_resumes_from_checkpoint: refine sees persisted draft via thread_id")


async def main():
    await test_approve_first_pass()
    await test_revise_then_approve()
    await test_guard_at_three()
    await test_checkpointer_persists_state()
    await test_refine_resumes_from_checkpoint()
    print("\nALL GRAPH TESTS PASSED (async, no API calls)")


if __name__ == "__main__":
    asyncio.run(main())
