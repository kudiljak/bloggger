import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from logging_config import log, setup_logging
from routers import auth, chat

setup_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up")
    yield
    log.info("Shutting down")


app = FastAPI(title="Blogger API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.exception(
            "%s %s -> 500 (%.1f ms)", request.method, request.url.path, elapsed_ms
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info(
        "%s %s -> %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


app.include_router(auth.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
