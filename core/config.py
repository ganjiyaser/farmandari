import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Literal

# Project root: <repo>/core/config.py -> <repo>. Anchoring to this instead of
# the process CWD keeps .env loadable when the app is started from a shortcut,
# via `python C:\path\to\main.py`, or by the frozen exe with a different
# working directory (previously all SMS_*/SYNC_* values silently became "").
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "سیستم مدیریت امور دفتری فرمانداری"
    APP_VERSION: str = "1.2.0"
    ORGANIZATION: str = "فرمانداری"
    APP_DEBUG: bool = False
    
    BASE_DIR: Path = (
        Path(sys.executable).parent if getattr(sys, "frozen", False)
        else PROJECT_ROOT
    )
    # در نسخه‌ی نصب‌شده (exe) داده‌ها در %LOCALAPPDATA%\Farmandari\data ذخیره می‌شوند،
    # چون پوشه‌ی Program Files قابل نوشتن نیست. در حالت توسعه مثل قبل پوشه‌ی data پروژه است.
    DATA_DIR: Path = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Farmandari" / "data"
        if getattr(sys, "frozen", False)
        else BASE_DIR / "data"
    )
    DB_PATH: Path = DATA_DIR / "app.db"
    FILES_DIR: Path = DATA_DIR / "files"
    BACKUP_DIR: Path = DATA_DIR / "backups"
    LOGS_DIR: Path = DATA_DIR / "logs"
    EXPORT_DIR: Path = DATA_DIR / "exports"
    
    # Multi-user settings
    USERS_DIR: Path = DATA_DIR / "users"
    DEFAULT_USER_DB_NAME: str = "user.db"
    
    # Storage mode: "local" or "shared"
    STORAGE_MODE: Literal["local", "shared"] = "local"
    SHARED_DB_PATH: Optional[str] = None  # Network path for shared mode
    SHARED_FILES_DIR: Optional[str] = None
    
    # Auto backup
    AUTO_BACKUP_ENABLED: bool = True
    AUTO_BACKUP_INTERVAL_HOURS: int = 6
    MAX_BACKUP_COUNT: int = 10
    
    SMS_PROVIDER: str = "custom"
    SMS_API_URL: str = ""
    SMS_API_KEY: str = ""
    SMS_SENDER_NUMBER: str = ""
    SMS_USERNAME: str = ""
    SMS_PASSWORD: str = ""
    SMS_TEMPLATE_ID: str = ""

    # روتر D-Link (ارسال/دریافت پیامک از طریق پنل وب روتر روی Wi-Fi).
    # رمز روتر عمداً default خالی است و فقط از متغیر محیطی خوانده می‌شود؛
    # به هیچ فایلی (حتی .env) نوشته نمی‌شود — UI در زمان اتصال از کاربر می‌پرسد
    # و فقط در حافظه نگه می‌دارد.
    DLINK_ROUTER_USER: str = "admin"
    DLINK_ROUTER_PASSWORD: str = ""
    
    SYNC_ENABLED: bool = False
    SYNC_SERVER_URL: str = ""
    SYNC_API_KEY: str = ""
    SYNC_INTERVAL_MINUTES: int = 30
    
    PAGE_SIZE: int = 50
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_FILE_EXTENSIONS: tuple = (
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".txt", ".rtf", ".zip", ".rar"
    )
    
    # pydantic v2 / pydantic-settings v2 form. The old inner `class Config`
    # still worked but is deprecated and warns on pydantic >= 2.13.
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
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
