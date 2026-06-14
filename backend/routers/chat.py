from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.checkpoint.memory import MemorySaver
from sqlmodel import Session, select

from db import get_session
from deps import get_current_user
from graph import run
from llm import Brief
from models import Conversation, Message, User
from schemas import BriefIn, ConversationCreate, ConversationRead, MessageRead

router = APIRouter(prefix="/chat", tags=["chat"])
checkpointer = MemorySaver()


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
