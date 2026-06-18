import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from db import engine, get_session
from deps import get_current_user
from graph import refine_stream, run, run_stream
from llm import Brief
from models import Conversation, Message, User
from schemas import (
    BriefIn,
    ConversationCreate,
    ConversationRead,
    MessageRead,
    RefineIn,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def get_checkpointer(request: Request):
    return request.app.state.checkpointer


def _render_brief(brief: Brief) -> str:
    return (
        f"Topic: {brief.topic}\nBrand: {brief.brand}\nTone: {brief.tone}\n"
        f"Audience: {brief.audience}\nLength: {brief.length}"
    )


def _get_owned_conversation(
    conversation_id: int, user: User, session: Session
) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conversation


def _persist_exchange(conversation_id: int, user_content: str, result: dict) -> dict:
    with Session(engine) as session:
        user_message = Message(
            conversation_id=conversation_id, role="user", content=user_content
        )
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=result["draft"],
            critique=result["critique"],
            iterations=result["iterations"],
        )
        session.add(user_message)
        session.add(assistant_message)
        session.commit()
        session.refresh(user_message)
        session.refresh(assistant_message)
        return {
            "type": "done",
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "iterations": result["iterations"],
        }


@router.post(
    "/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Conversation:
    conversation = Conversation(
        user_id=current_user.id, title=data.title or "New conversation"
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Conversation]:
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.user_id == current_user.id)
            .order_by(Conversation.created_at.desc())
        ).all()
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Message]:
    _get_owned_conversation(conversation_id, current_user, session)
    return list(
        session.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ).all()
    )


@router.post(
    "/conversations/{conversation_id}/messages", response_model=list[MessageRead]
)
async def send_message(
    conversation_id: int,
    brief_in: BriefIn,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    checkpointer=Depends(get_checkpointer),
) -> list[Message]:
    _get_owned_conversation(conversation_id, current_user, session)

    brief = Brief(**brief_in.model_dump())
    final = await run(
        brief,
        thread_id=f"conv-{conversation_id}",
        checkpointer=checkpointer,
    )

    user_message = Message(
        conversation_id=conversation_id, role="user", content=_render_brief(brief)
    )
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=final["draft"],
        critique=final["critique"],
        iterations=final["iterations"],
    )
    session.add(user_message)
    session.add(assistant_message)
    session.commit()
    session.refresh(user_message)
    session.refresh(assistant_message)
    return [user_message, assistant_message]


@router.post("/conversations/{conversation_id}/stream")
async def stream_message(
    conversation_id: int,
    brief_in: BriefIn,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    checkpointer=Depends(get_checkpointer),
) -> StreamingResponse:
    conversation = _get_owned_conversation(conversation_id, current_user, session)
    brief = Brief(**brief_in.model_dump())
    conversation.brief = brief.model_dump()
    session.add(conversation)
    session.commit()

    async def event_generator():
        result = None
        async for event in run_stream(
            brief,
            thread_id=f"conv-{conversation_id}",
            checkpointer=checkpointer,
        ):
            if event["type"] == "result":
                result = event
                continue
            yield f"data: {json.dumps(event)}\n\n"

        done = _persist_exchange(conversation_id, _render_brief(brief), result)
        yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/refine")
async def refine_message(
    conversation_id: int,
    refine_in: RefineIn,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    checkpointer=Depends(get_checkpointer),
) -> StreamingResponse:
    conversation = _get_owned_conversation(conversation_id, current_user, session)

    last_post = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.role == "assistant")
        .order_by(Message.created_at.desc())
    ).first()
    if last_post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Nothing to refine yet"
        )

    instruction = refine_in.instruction
    fallback_brief = conversation.brief
    fallback_post = last_post.content

    async def event_generator():
        result = None
        async for event in refine_stream(
            instruction,
            thread_id=f"conv-{conversation_id}",
            checkpointer=checkpointer,
            fallback_brief=fallback_brief,
            fallback_post=fallback_post,
        ):
            if event["type"] == "result":
                result = event
                continue
            yield f"data: {json.dumps(event)}\n\n"

        done = _persist_exchange(conversation_id, f"Refine: {instruction}", result)
        yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
