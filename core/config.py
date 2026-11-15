import json
import os
import sys
import warnings
from pathlib import Path
from typing import Optional

# Project root: <repo>/core/config.py -> <repo>. Anchoring to this instead of
# the process CWD keeps .env loadable when the app is started from a shortcut,
# via `python C:\path\to\main.py`, or by the frozen exe with a different
# working directory (previously all SMS_*/SYNC_* values silently became "").
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> dict:
    """Minimal .env reader (KEY=VALUE, optional export/quotes, # comments).

    pydantic-settings pulled pydantic-core, whose compiled wheels require a
    newer Windows than 7. The app only needs flat KEY=VALUE settings, so this
    keeps the same .env semantics without a Rust dependency.
    """
    values = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            values[key] = value
    return values


def _get(env: dict, key: str):
    return env.get(key)


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_int(value, default: int, key: str) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError("{} must be an integer, got {!r}".format(key, value)) from exc


def _as_path(value, default: Path) -> Path:
    return Path(str(value)).expanduser() if value not in (None, "") else default


def _as_optional_str(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _as_tuple(value, default: tuple) -> tuple:
    if value is None:
        return default
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            return tuple(str(item).strip() for item in parsed)
        except (ValueError, TypeError):
            pass
    return tuple(item.strip() for item in text.split(",") if item.strip())


class Settings:
    APP_NAME = "سیستم مدیریت امور دفتری فرمانداری"
    APP_VERSION = "1.2.0"
    ORGANIZATION = "فرمانداری"
    APP_DEBUG = False

    # Multi-user settings
    DEFAULT_USER_DB_NAME = "user.db"

    # Storage mode: "local" or "shared"
    STORAGE_MODE = "local"
    SHARED_DB_PATH = None  # Network path for shared mode
    SHARED_FILES_DIR = None

    # Auto backup
    AUTO_BACKUP_ENABLED = True
    AUTO_BACKUP_INTERVAL_HOURS = 6
    MAX_BACKUP_COUNT = 10

    SMS_PROVIDER = "custom"
    SMS_API_URL = ""
    SMS_API_KEY = ""
    SMS_SENDER_NUMBER = ""
    SMS_USERNAME = ""
    SMS_PASSWORD = ""
    SMS_TEMPLATE_ID = ""

    # روتر D-Link (ارسال/دریافت پیامک از طریق پنل وب روتر روی Wi-Fi).
    # رمز روتر عمداً default خالی است و فقط از متغیر محیطی خوانده می‌شود؛
    # به هیچ فایلی (حتی .env) نوشته نمی‌شود — UI در زمان اتصال از کاربر می‌پرسد
    # و فقط در حافظه نگه می‌دارد.
    DLINK_ROUTER_USER = "admin"
    DLINK_ROUTER_PASSWORD = ""

    SYNC_ENABLED = False
    SYNC_SERVER_URL = ""
    SYNC_API_KEY = ""
    SYNC_INTERVAL_MINUTES = 30

    PAGE_SIZE = 50
    MAX_FILE_SIZE_MB = 50
    ALLOWED_FILE_EXTENSIONS = (
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".txt", ".rtf", ".zip", ".rar"
    )

    def __init__(self):
        env = _load_dotenv(PROJECT_ROOT / ".env")
        # Real environment variables win over .env, as with pydantic-settings.
        env.update(os.environ)

        self.BASE_DIR = (
            Path(sys.executable).parent if getattr(sys, "frozen", False)
            else PROJECT_ROOT
        )
        # در نسخه‌ی نصب‌شده (exe) داده‌ها در %LOCALAPPDATA%\Farmandari\data ذخیره می‌شوند،
        # چون پوشه‌ی Program Files قابل نوشتن نیست. در حالت توسعه مثل قبل پوشه‌ی data پروژه است.
        default_data_dir = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Farmandari" / "data"
            if getattr(sys, "frozen", False)
            else self.BASE_DIR / "data"
        )

        self.DATA_DIR = _as_path(_get(env, "DATA_DIR"), default_data_dir)
        self.DB_PATH = _as_path(_get(env, "DB_PATH"), self.DATA_DIR / "app.db")
        self.FILES_DIR = _as_path(_get(env, "FILES_DIR"), self.DATA_DIR / "files")
        self.BACKUP_DIR = _as_path(_get(env, "BACKUP_DIR"), self.DATA_DIR / "backups")
        self.LOGS_DIR = _as_path(_get(env, "LOGS_DIR"), self.DATA_DIR / "logs")
        self.EXPORT_DIR = _as_path(_get(env, "EXPORT_DIR"), self.DATA_DIR / "exports")
        self.USERS_DIR = _as_path(_get(env, "USERS_DIR"), self.DATA_DIR / "users")

        self.APP_NAME = env.get("APP_NAME", self.APP_NAME)
        self.APP_VERSION = env.get("APP_VERSION", self.APP_VERSION)
        self.ORGANIZATION = env.get("ORGANIZATION", self.ORGANIZATION)
        self.APP_DEBUG = _as_bool(_get(env, "APP_DEBUG"), self.APP_DEBUG)

        self.DEFAULT_USER_DB_NAME = env.get("DEFAULT_USER_DB_NAME", self.DEFAULT_USER_DB_NAME)

        mode = str(env.get("STORAGE_MODE", self.STORAGE_MODE)).strip().lower()
        if mode not in ("local", "shared"):
            warnings.warn("STORAGE_MODE must be 'local' or 'shared'; using 'local'")
            mode = "local"
        self.STORAGE_MODE = mode
        self.SHARED_DB_PATH = _as_optional_str(_get(env, "SHARED_DB_PATH"))
        self.SHARED_FILES_DIR = _as_optional_str(_get(env, "SHARED_FILES_DIR"))

        self.AUTO_BACKUP_ENABLED = _as_bool(_get(env, "AUTO_BACKUP_ENABLED"), self.AUTO_BACKUP_ENABLED)
        self.AUTO_BACKUP_INTERVAL_HOURS = _as_int(
            _get(env, "AUTO_BACKUP_INTERVAL_HOURS"), self.AUTO_BACKUP_INTERVAL_HOURS,
            "AUTO_BACKUP_INTERVAL_HOURS",
        )
        self.MAX_BACKUP_COUNT = _as_int(_get(env, "MAX_BACKUP_COUNT"), self.MAX_BACKUP_COUNT, "MAX_BACKUP_COUNT")

        self.SMS_PROVIDER = env.get("SMS_PROVIDER", self.SMS_PROVIDER)
        self.SMS_API_URL = env.get("SMS_API_URL", self.SMS_API_URL)
        self.SMS_API_KEY = env.get("SMS_API_KEY", self.SMS_API_KEY)
        self.SMS_SENDER_NUMBER = env.get("SMS_SENDER_NUMBER", self.SMS_SENDER_NUMBER)
        self.SMS_USERNAME = env.get("SMS_USERNAME", self.SMS_USERNAME)
        self.SMS_PASSWORD = env.get("SMS_PASSWORD", self.SMS_PASSWORD)
        self.SMS_TEMPLATE_ID = env.get("SMS_TEMPLATE_ID", self.SMS_TEMPLATE_ID)

        self.DLINK_ROUTER_USER = env.get("DLINK_ROUTER_USER", self.DLINK_ROUTER_USER)
        self.DLINK_ROUTER_PASSWORD = env.get("DLINK_ROUTER_PASSWORD", self.DLINK_ROUTER_PASSWORD)

        self.SYNC_ENABLED = _as_bool(_get(env, "SYNC_ENABLED"), self.SYNC_ENABLED)
        self.SYNC_SERVER_URL = env.get("SYNC_SERVER_URL", self.SYNC_SERVER_URL)
        self.SYNC_API_KEY = env.get("SYNC_API_KEY", self.SYNC_API_KEY)
        self.SYNC_INTERVAL_MINUTES = _as_int(
            _get(env, "SYNC_INTERVAL_MINUTES"), self.SYNC_INTERVAL_MINUTES, "SYNC_INTERVAL_MINUTES"
        )

        self.PAGE_SIZE = _as_int(_get(env, "PAGE_SIZE"), self.PAGE_SIZE, "PAGE_SIZE")
        self.MAX_FILE_SIZE_MB = _as_int(_get(env, "MAX_FILE_SIZE_MB"), self.MAX_FILE_SIZE_MB, "MAX_FILE_SIZE_MB")
        self.ALLOWED_FILE_EXTENSIONS = _as_tuple(
            _get(env, "ALLOWED_FILE_EXTENSIONS"), self.ALLOWED_FILE_EXTENSIONS
        )


settings = Settings()

for dir_path in [
    settings.DATA_DIR,
    settings.FILES_DIR,
    settings.BACKUP_DIR,
    settings.LOGS_DIR,
    settings.EXPORT_DIR,
    settings.USERS_DIR
]:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Fail with an actionable message instead of an opaque traceback from
        # deep inside the first INSERT/LOG call.
        raise RuntimeError(
            f"Cannot create data directory '{dir_path}': {e}\n"
            "Check permissions on the install/data folder."
        ) from e
