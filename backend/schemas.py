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
