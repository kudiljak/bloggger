from collections.abc import Generator

from sqlmodel import Session, create_engine

from config import get_settings

settings = get_settings()

# SQLite forbids sharing a connection across threads by default; FastAPI uses many.
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url, echo=settings.sql_echo, connect_args=connect_args
)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
