"""One-process backend launcher with coordinated optional-client supervision."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field

import uvicorn

from core.config import settings
from study_buddy.logging import configure_logging

logger = logging.getLogger(__name__)


@dataclass
class ProcessSupervisor:
    """Own and cleanly terminate backend companion processes."""

    children: list[tuple[str, subprocess.Popen]] = field(default_factory=list)
    stopping: bool = False

    def start(self, name: str, module: str) -> None:
        environment = os.environ.copy()
        environment["STUDY_BUDDY_MANAGED"] = "1"
        process = subprocess.Popen(
            [sys.executable, "-m", module],
            env=environment,
            start_new_session=False,
        )
        self.children.append((name, process))
        logger.info("component started", extra={"component": name, "pid": process.pid})
        threading.Thread(
            target=self._watch,
            args=(name, process),
            daemon=True,
            name=f"{name}-supervisor",
        ).start()

    def _watch(self, name: str, process: subprocess.Popen) -> None:
        status = process.wait()
        level = logging.INFO if self.stopping or status == 0 else logging.ERROR
        logger.log(
            level,
            "component stopped",
            extra={"component": name, "pid": process.pid, "exit_code": status},
        )

    def stop(self) -> None:
        self.stopping = True
        for name, process in reversed(self.children):
            if process.poll() is None:
                logger.info(
                    "stopping component",
                    extra={"component": name, "pid": process.pid},
                )
                process.terminate()
        for name, process in reversed(self.children):
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "forcing component shutdown",
                    extra={"component": name, "pid": process.pid},
                )
                process.kill()
                process.wait(timeout=5)


def run() -> None:
    """Start every configured backend component from one command."""
    configure_logging()
    supervisor = ProcessSupervisor()

    def terminate(signum: int, _frame: object) -> None:
        """Stop companion processes when the launcher is signalled to exit.

        uvicorn captures SIGTERM/SIGHUP itself, and once its own graceful
        shutdown finishes it restores the previous handler and re-raises the
        signal. Without this handler that re-raise hits Python's default
        disposition, which kills the launcher outright: the ``finally`` below
        never runs and the menubar/telegram children are reparented to init.
        The orphaned bot keeps polling, so the next start dies on Telegram's
        "terminated by other getUpdates" conflict.
        """
        supervisor.stop()
        logger.info("Study Buddy backend stopped")
        logging.shutdown()
        os._exit(128 + signum)

    for received in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(received, terminate)

    logger.info(
        "starting Study Buddy backend",
        extra={
            "environment": settings.environment,
            "host": settings.host,
            "port": settings.port,
            "data_dir": str(settings.data_dir),
        },
    )
    try:
        public_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
        if settings.enable_menubar and sys.platform == "darwin":
            supervisor.start("menubar", "buddy.menubar")
        else:
            logger.info("component disabled", extra={"component": "menubar"})

        if settings.enable_telegram and settings.telegram_bot_token:
            supervisor.start("telegram", "telegram_bot")
        elif not settings.telegram_bot_token:
            logger.info(
                "component disabled",
                extra={"component": "telegram", "reason": "token not configured"},
            )
        else:
            logger.info("component disabled", extra={"component": "telegram"})

        logger.info(
            "API available",
            extra={
                "url": f"http://{public_host}:{settings.port}",
                "docs": f"http://{public_host}:{settings.port}/api/docs",
                "health": f"http://{public_host}:{settings.port}/api/health/ready",
            },
        )
        uvicorn.run(
            "server:app",
            host=settings.host,
            port=settings.port,
            log_config=None,
            access_log=False,
            proxy_headers=True,
            forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        )
    finally:
        supervisor.stop()
        logger.info("Study Buddy backend stopped")
