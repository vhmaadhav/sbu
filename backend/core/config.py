"""Validated, centralized backend configuration.

Environment variables are read once at process startup.  The module-level
constants remain as a compatibility layer for the existing domain modules.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _integer(name: str, default: int, *, minimum: int = 1, maximum: int = 65535) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _path(name: str, default: str) -> Path:
    configured = Path(os.getenv(name, default)).expanduser()
    return configured.resolve() if configured.is_absolute() else (ROOT / configured).resolve()


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


def _id_set(name: str) -> frozenset[int]:
    values = _csv(name)
    invalid = [value for value in values if not value.lstrip("-").isdigit()]
    if invalid:
        raise ValueError(f"{name} contains a non-numeric identifier")
    return frozenset(int(value) for value in values)


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str
    environment: str
    host: str
    port: int
    log_level: str
    log_format: str
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    max_upload_mb: int
    enable_menubar: bool
    enable_telegram: bool
    lmstudio_base_url: str
    lmstudio_api_key: str
    lmstudio_model: str
    vision_model: str
    reranker_enabled: bool
    reranker_model: str
    reranker_candidate_k: int
    reranker_max_chars: int
    stt_model: str
    embed_model: str
    kokoro_voice: str
    telegram_bot_token: str
    telegram_allowed_user_ids: frozenset[int]
    telegram_allowed_chat_ids: frozenset[int]
    telegram_allow_all: bool
    telegram_max_upload_mb: int
    google_calendar_client_id: str
    google_calendar_client_secret: str
    google_calendar_redirect_uri: str
    google_calendar_timezone: str
    web_base_url: str
    pet_poll_seconds: int
    pet_notice_seconds: int
    pet_concerned_seconds: int
    pet_nag_seconds: int
    pet_plead_seconds: int
    pet_recovery_seconds: int
    pet_bubble_cooldown: int
    pet_plead_repeat_seconds: int
    pet_backend_url: str
    pet_study_apps: tuple[str, ...]
    pet_distract_hosts: tuple[str, ...]
    data_dir: Path
    inbox_dir: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        environment = os.getenv("APP_ENV", "development").strip().lower()
        if environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        log_format = os.getenv(
            "LOG_FORMAT", "json" if environment == "production" else "console"
        ).strip().lower()
        if log_format not in {"console", "json"}:
            raise ValueError("LOG_FORMAT must be console or json")
        model = os.getenv("LMSTUDIO_MODEL", "qwen/qwen3-4b").strip()
        cors_origins = _csv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        )
        trusted_hosts = _csv("TRUSTED_HOSTS", "*")
        if environment == "production" and "*" in trusted_hosts:
            raise ValueError(
                "TRUSTED_HOSTS must list explicit hostnames when APP_ENV=production"
            )
        return cls(
            service_name="study-buddy-api",
            environment=environment,
            host=os.getenv("BACKEND_HOST", "0.0.0.0").strip(),
            port=_integer("BACKEND_PORT", 8010),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_format=log_format,
            cors_origins=cors_origins,
            trusted_hosts=trusted_hosts,
            max_upload_mb=_integer("MAX_UPLOAD_MB", 1000, maximum=10_000),
            enable_menubar=_boolean("STUDY_BUDDY_MENUBAR", True),
            enable_telegram=_boolean("STUDY_BUDDY_TELEGRAM", True),
            lmstudio_base_url=os.getenv(
                "LMSTUDIO_BASE_URL", "http://localhost:1234/v1"
            ).rstrip("/"),
            lmstudio_api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio"),
            lmstudio_model=model,
            vision_model=os.getenv("VISION_MODEL", "qwen/qwen3-vl-4b").strip(),
            reranker_enabled=_boolean("RERANKER_ENABLED", True),
            reranker_model=os.getenv(
                "RERANKER_MODEL",
                "mlx-community/Qwen3-Reranker-0.6B-mxfp8",
            ).strip(),
            reranker_candidate_k=_integer(
                "RERANKER_CANDIDATE_K", 24, maximum=100
            ),
            reranker_max_chars=_integer(
                "RERANKER_MAX_CHARS", 6000, minimum=256, maximum=100_000
            ),
            stt_model=os.getenv("STT_MODEL", "moonshine/base").strip(),
            embed_model=os.getenv(
                "EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ).strip(),
            kokoro_voice=os.getenv("KOKORO_VOICE", "af_heart").strip(),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_user_ids=_id_set("TELEGRAM_ALLOWED_USER_IDS"),
            telegram_allowed_chat_ids=_id_set("TELEGRAM_ALLOWED_CHAT_IDS"),
            telegram_allow_all=_boolean("TELEGRAM_ALLOW_ALL", False),
            telegram_max_upload_mb=_integer("TELEGRAM_MAX_UPLOAD_MB", 20, maximum=2000),
            google_calendar_client_id=os.getenv("GOOGLE_CALENDAR_CLIENT_ID", ""),
            google_calendar_client_secret=os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", ""),
            google_calendar_redirect_uri=os.getenv(
                "GOOGLE_CALENDAR_REDIRECT_URI",
                "http://localhost:8010/api/calendar/google/callback",
            ),
            google_calendar_timezone=os.getenv(
                "GOOGLE_CALENDAR_TIMEZONE", "Asia/Kolkata"
            ),
            web_base_url=os.getenv("WEB_BASE_URL", "http://localhost:3000").rstrip("/"),
            pet_poll_seconds=_integer("PET_POLL_SECONDS", 5, maximum=600),
            pet_notice_seconds=_integer("PET_NOTICE_SECONDS", 90, maximum=86_400),
            pet_concerned_seconds=_integer("PET_CONCERNED_SECONDS", 180, maximum=86_400),
            pet_nag_seconds=_integer("PET_NAG_SECONDS", 360, maximum=86_400),
            pet_plead_seconds=_integer("PET_PLEAD_SECONDS", 600, maximum=86_400),
            pet_recovery_seconds=_integer("PET_RECOVERY_SECONDS", 60, maximum=86_400),
            pet_bubble_cooldown=_integer("PET_BUBBLE_COOLDOWN", 90, maximum=86_400),
            pet_plead_repeat_seconds=_integer(
                "PET_PLEAD_REPEAT_SECONDS", 240, maximum=86_400
            ),
            pet_backend_url=os.getenv("PET_BACKEND_URL", "http://127.0.0.1:8010").rstrip("/"),
            pet_study_apps=_csv("PET_STUDY_APPS"),
            pet_distract_hosts=_csv("PET_DISTRACT_HOSTS"),
            data_dir=_path("DATA_DIR", "data"),
            inbox_dir=_path("INBOX_DIR", "inbox"),
        )

    def prepare_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.inbox_dir,
            self.files_dir,
            self.lancedb_dir,
            self.audiobooks_dir,
            self.handwriting_dir,
            self.hw_pages_dir,
            self.hw_crops_dir,
            self.video_dir,
            self.video_frames_dir,
            self.video_crops_dir,
            self.figures_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def lancedb_dir(self) -> Path:
        return self.data_dir / "lancedb"

    @property
    def audiobooks_dir(self) -> Path:
        return self.data_dir / "audiobooks"

    @property
    def handwriting_dir(self) -> Path:
        return self.data_dir / "handwriting"

    @property
    def hw_pages_dir(self) -> Path:
        return self.handwriting_dir / "pages"

    @property
    def hw_crops_dir(self) -> Path:
        return self.handwriting_dir / "crops"

    @property
    def video_dir(self) -> Path:
        return self.data_dir / "video"

    @property
    def video_frames_dir(self) -> Path:
        return self.video_dir / "frames"

    @property
    def video_crops_dir(self) -> Path:
        return self.video_dir / "crops"

    @property
    def figures_dir(self) -> Path:
        return self.data_dir / "figures"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


settings = Settings.from_environment()
settings.prepare_directories()

# Compatibility names used by the domain layer.
LMSTUDIO_BASE_URL = settings.lmstudio_base_url
LMSTUDIO_API_KEY = settings.lmstudio_api_key
LMSTUDIO_MODEL = settings.lmstudio_model
VISION_MODEL = settings.vision_model
RERANKER_ENABLED = settings.reranker_enabled
RERANKER_MODEL = settings.reranker_model
RERANKER_CANDIDATE_K = settings.reranker_candidate_k
RERANKER_MAX_CHARS = settings.reranker_max_chars
STT_MODEL = settings.stt_model
EMBED_MODEL = settings.embed_model
KOKORO_VOICE = settings.kokoro_voice
TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
TELEGRAM_ALLOWED_USER_IDS = set(settings.telegram_allowed_user_ids)
TELEGRAM_ALLOWED_CHAT_IDS = set(settings.telegram_allowed_chat_ids)
TELEGRAM_ALLOW_ALL = settings.telegram_allow_all
TELEGRAM_MAX_UPLOAD_MB = settings.telegram_max_upload_mb
GOOGLE_CALENDAR_CLIENT_ID = settings.google_calendar_client_id
GOOGLE_CALENDAR_CLIENT_SECRET = settings.google_calendar_client_secret
GOOGLE_CALENDAR_REDIRECT_URI = settings.google_calendar_redirect_uri
GOOGLE_CALENDAR_TIMEZONE = settings.google_calendar_timezone
DATA_DIR = settings.data_dir
INBOX_DIR = settings.inbox_dir
FILES_DIR = settings.files_dir
LANCEDB_DIR = settings.lancedb_dir
AUDIOBOOKS_DIR = settings.audiobooks_dir
HANDWRITING_DIR = settings.handwriting_dir
HW_PAGES_DIR = settings.hw_pages_dir
HW_CROPS_DIR = settings.hw_crops_dir
VIDEO_DIR = settings.video_dir
VIDEO_FRAMES_DIR = settings.video_frames_dir
VIDEO_CROPS_DIR = settings.video_crops_dir
FIGURES_DIR = settings.figures_dir
DB_PATH = settings.db_path
PET_POLL_SECONDS = settings.pet_poll_seconds
PET_NOTICE_SECONDS = settings.pet_notice_seconds
PET_CONCERNED_SECONDS = settings.pet_concerned_seconds
PET_NAG_SECONDS = settings.pet_nag_seconds
PET_PLEAD_SECONDS = settings.pet_plead_seconds
PET_RECOVERY_SECONDS = settings.pet_recovery_seconds
PET_BUBBLE_COOLDOWN = settings.pet_bubble_cooldown
PET_PLEAD_REPEAT_SECONDS = settings.pet_plead_repeat_seconds
PET_BACKEND_URL = settings.pet_backend_url
PET_STUDY_APPS = settings.pet_study_apps
PET_DISTRACT_HOSTS = settings.pet_distract_hosts

AUDIO_EXTS = frozenset({".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"})
VIDEO_EXTS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi"})
IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".heic", ".webp", ".tiff", ".bmp"})
PDF_EXTS = frozenset({".pdf"})
TEXT_EXTS = frozenset({".txt", ".md"})


def kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in TEXT_EXTS:
        return "text"
    return None
