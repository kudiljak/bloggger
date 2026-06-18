from datetime import datetime

from sqlmodel import SQLModel


class UserCreate(SQLModel):
    email: str
    password: str


class UserRead(SQLModel):
    id: int
    email: str
    created_at: datetime


class MessageResponse(SQLModel):
    message: str


class ConversationCreate(SQLModel):
    title: str | None = None


class ConversationRead(SQLModel):
    id: int
    title: str
    brief: dict | None
    created_at: datetime


class BriefIn(SQLModel):
    topic: str
    brand: str
    tone: str
    audience: str
    length: str


class RefineIn(SQLModel):
    instruction: str


class MessageRead(SQLModel):
    id: int
    role: str
    content: str
    critique: dict | None
    iterations: int | None
    created_at: datetime
