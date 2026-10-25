"""پیکربندی حالت ذخیره‌سازی در سطح هر سیستم.

حالت ذخیره‌سازی باید *قبل* از باز شدن هر دیتابیسی مشخص باشد، ولی خودِ این
تنظیم را نمی‌توان داخل همان دیتابیسی نگه داشت که مسیرش را تعیین می‌کند.
بنابراین هر سیستم یک فایل کوچک محلی (data/storage_config.json) دارد که
مسیر پوشه اشتراکی شبکه را مشخص می‌کند.
"""
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

from core.config import settings
from utils.logging_setup import get_logger

logger = get_logger(__name__)

CONFIG_PATH: Path = settings.DATA_DIR / "storage_config.json"


def _read_json_config() -> Optional[dict]:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("خواندن %s ممکن نشد", CONFIG_PATH)
    return None


def _peek_shared_from_db() -> Optional[Tuple[str, str]]:
    """برای نصب‌های قدیمی‌تر: حالت ذخیره‌شده در دیتابیس محلی را می‌خواند."""
    db = settings.DB_PATH
    try:
        if not db.exists():
            return None
        con = sqlite3.connect(str(db))
        try:
            rows = dict(
                con.execute(
                    "SELECT key, value FROM app_settings "
                    "WHERE key IN ('storage_mode', 'shared_db_path')"
                ).fetchall()
            )
        finally:
            con.close()
    except Exception:
        # Falling back to local mode because the legacy row couldn't be read is
        # a real configuration change -- log it instead of returning silently.
        logger.exception("Could not read legacy storage settings from %s", db)
        return None

    def _decode(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v

    mode = _decode(rows.get("storage_mode"))
    path = _decode(rows.get("shared_db_path"))
    if isinstance(mode, str) and isinstance(path, str):
        return mode, path
    return None


def load_storage_config() -> None:
    """اعمال پیکربندی ذخیره‌سازی روی settings. باید پیش از باز شدن دیتابیس صدا زده شود."""
    import sys

    data = _read_json_config()
    previous_mode = settings.STORAGE_MODE
    if data:
        mode = data.get("storage_mode")
        if mode in ("local", "shared"):
            settings.STORAGE_MODE = mode
        shared_db = (data.get("shared_db_path") or "").strip()
        if shared_db:
            settings.SHARED_DB_PATH = shared_db
        shared_files = (data.get("shared_files_dir") or "").strip()
        if shared_files:
            settings.SHARED_FILES_DIR = shared_files
    else:
        legacy = _peek_shared_from_db()
        if legacy and legacy[0] == "shared" and legacy[1].strip():
            settings.STORAGE_MODE = "shared"
            settings.SHARED_DB_PATH = legacy[1].strip()
            # تلاش برای خواندن shared_files_dir از دیتابیس
            try:
                db = settings.DB_PATH
                if db.exists():
                    con = sqlite3.connect(str(db))
                    try:
                        row = con.execute(
                            "SELECT value FROM app_settings WHERE key='shared_files_dir'"
                        ).fetchone()
                        if row and row[0]:
                            settings.SHARED_FILES_DIR = row[0]
                    finally:
                        con.close()
            except Exception:
                pass
            logger.info("حالت اشتراکی از تنظیمات ذخیره‌شده در دیتابیس اعمال شد")

    if settings.STORAGE_MODE == "shared" and not (settings.SHARED_DB_PATH or "").strip():
        logger.warning("حالت اشتراکی بدون مسیر شبکه تنظیم شده بود؛ بازگشت به حالت محلی")
        settings.STORAGE_MODE = "local"

    if settings.STORAGE_MODE == "shared":
        # مسیر اشتراکی باید از قبل وجود داشته باشد (طبق راهنما، پوشه روی
        # سرور ساخته و Share می‌شود). ساخت خودکار پوشه‌ی گم‌شده باعث می‌شد
        # داده‌ها بی‌صدا به مسیر اشتباه بروند و همچنین sqlite با
        # «unable to open database file» در اولین کوئری (لاگین) سقوط کند.
        # اگر پوشه سرور در دسترس نیست: بازگشت به حالت محلی + هشدار.
        # منطق تشخیص «پوشه یا فایل» باید با _resolve_shared_db_path یکی باشد.
        raw = settings.SHARED_DB_PATH.strip()
        p = Path(raw)
        target_dir = p if p.suffix.lower() not in (".db", ".sqlite", ".sqlite3") else p.parent
        if not target_dir.exists():
            logger.warning(
                "مسیر اشتراکی %s وجود ندارد؛ بازگشت به حالت محلی. "
                "پوشه را بسازید و مسیر را در تنظیمات → ذخیره‌سازی اصلاح کنید.",
                raw,
            )
            settings.STORAGE_MODE = "local"

    if settings.STORAGE_MODE == "shared":
        logger.info("حالت ذخیره‌سازی: اشتراکی (%s)", settings.SHARED_DB_PATH)
    else:
        logger.info("حالت ذخیره‌سازی: محلی")

    # journal_mode/synchronous are chosen per connection from STORAGE_MODE. If a
    # connection is already open the old pragma sticks, so the same file could
    # end up with mixed journal modes. That only happens if this function runs
    # late (or storage is switched without disposing engines).
    if settings.STORAGE_MODE != previous_mode:
        db_mod = sys.modules.get("core.database")
        if db_mod is not None and getattr(db_mod, "_engines", None):
            logger.warning(
                "Storage mode changed from %s to %s after %d engine(s) were "
                "already open; restart the application to apply journal mode.",
                previous_mode, settings.STORAGE_MODE, len(db_mod._engines),
            )


def save_storage_config(
    storage_mode: str,
    shared_db_path: Optional[str],
    shared_files_dir: Optional[str] = None,
) -> None:
    """ذخیره پیکربندی ذخیره‌سازی همین سیستم (نوشتن اتمیک)."""
    payload = {
        "storage_mode": storage_mode,
        "shared_db_path": (shared_db_path or "").strip() or None,
        "shared_files_dir": (shared_files_dir or "").strip() or None,
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)
    logger.info("پیکربندی ذخیره‌سازی ذخیره شد: %s", payload)
