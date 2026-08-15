"""Backend logging configuration shared by the API and managed processes."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from core.config import settings

_STANDARD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        "color_message",
    }
)


class JsonFormatter(logging.Formatter):
    """Render one machine-readable JSON object per log event."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _STANDARD_FIELDS and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Readable local logs that retain useful structured context."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_FIELDS and not key.startswith("_")
        }
        if not context:
            return rendered
        details = " ".join(f"{key}={value}" for key, value in sorted(context.items()))
        return f"{rendered} | {details}"


def configure_logging() -> None:
    """Configure application and Uvicorn logs once for the current process."""
    level = getattr(logging, settings.log_level, None)
    if not isinstance(level, int):
        raise ValueError(f"Unknown LOG_LEVEL: {settings.log_level}")

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            ConsoleFormatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        configured = logging.getLogger(name)
        configured.handlers.clear()
        configured.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
