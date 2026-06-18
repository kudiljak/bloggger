from functools import lru_cache
from typing import Callable

import anthropic
from pydantic import BaseModel

from config import get_settings

settings = get_settings()


@lru_cache
def get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)


class Brief(BaseModel):
    topic: str
    brand: str
    tone: str
    audience: str
    length: str


class CriterionResult(BaseModel):
    passed: bool
    comment: str


class Critique(BaseModel):
    approved: bool
    feedback: str  # the "Blogger" comment shown to the user (transparent QC)
    spelling: CriterionResult
    grammar: CriterionResult
    accuracy: CriterionResult
    tone_brand_audience: CriterionResult
    length: CriterionResult


WRITER_SYSTEM = (
    "You are Blogger, an expert blog-post writer. Write a complete blog post in "
    "English for the user's brand. Match the requested tone, audience, topic, and "
    "length. Output only the blog post itself - no preamble, no meta commentary."
)

CRITIC_SYSTEM = (
    "You are a strict quality-control editor for blog posts. Judge the draft on "
    "five criteria: spelling, grammar, factual accuracy, whether the tone fits "
    "the requested brand and audience, and whether the post's length matches the "
    "requested length. Approve only if all five are satisfied. If not, set "
    "approved=false and explain concretely what to fix. The 'feedback' field is a "
    "short comment shown to the user explaining your verdict."
)


def _brief_block(brief: Brief) -> str:
    return (
        f"Brand: {brief.brand}\n"
        f"Topic: {brief.topic}\n"
        f"Tone: {brief.tone}\n"
        f"Audience: {brief.audience}\n"
        f"Length: {brief.length}"
    )


def _advocate_user_content(
    brief: Brief,
    previous_draft: str | None,
    previous_feedback: str | None,
) -> str:
    if previous_draft and previous_feedback:
        return (
            f"{_brief_block(brief)}\n\n"
            f"Your previous draft was:\n{previous_draft}\n\n"
            f"The editor asked for these changes:\n{previous_feedback}\n\n"
            "Rewrite the blog post addressing every point."
        )
    return f"{_brief_block(brief)}\n\nWrite the blog post."


async def advocate(
    brief: Brief,
    previous_draft: str | None = None,
    previous_feedback: str | None = None,
) -> str:
    """Write a new draft, or revise the previous one given the critic's feedback."""
    user_content = _advocate_user_content(brief, previous_draft, previous_feedback)
    response = await get_client().messages.create(
        model=settings.llm_model,
        max_tokens=4000,
        system=WRITER_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


async def advocate_stream(
    brief: Brief,
    previous_draft: str | None,
    previous_feedback: str | None,
    emit: Callable[[str], None],
) -> str:
    """Stream a draft token by token, calling emit() for each chunk; return the full text."""
    user_content = _advocate_user_content(brief, previous_draft, previous_feedback)
    parts: list[str] = []
    async with get_client().messages.stream(
        model=settings.llm_model,
        max_tokens=4000,
        system=WRITER_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        async for text in stream.text_stream:
            emit(text)
            parts.append(text)
    return "".join(parts)


async def critic(brief: Brief, draft: str) -> Critique:
    """Score a draft against the four criteria, returning a structured verdict."""
    user_content = (
        f"{_brief_block(brief)}\n\n"
        f"Draft to review:\n{draft}\n\n"
        "Return your structured verdict."
    )
    response = await get_client().messages.parse(
        model=settings.llm_model,
        max_tokens=1500,
        system=CRITIC_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        output_format=Critique,
    )
    return response.parsed_output
