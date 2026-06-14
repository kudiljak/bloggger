from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from config import get_settings
from db import engine
from routers import auth

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Temporary for step 1: create tables directly. Replaced by Alembic in step 2.
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="Blogger API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
