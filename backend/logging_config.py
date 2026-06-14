import logging
from logging.config import dictConfig

from config import get_settings

settings = get_settings()


def setup_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "default",
                }
            },
            "root": {"level": settings.log_level, "handlers": ["console"]},
            "loggers": {
                "uvicorn": {"level": settings.log_level, "handlers": ["console"], "propagate": False},
                "uvicorn.error": {"level": settings.log_level, "handlers": ["console"], "propagate": False},
                # We log requests ourselves in middleware, so silence uvicorn's access log.
                "uvicorn.access": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            },
        }
    )


log = logging.getLogger("blogger")
