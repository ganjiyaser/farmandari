"""انتقال دیتابیس بین حالت محلی و پوشه اشتراکی شبکه.

در حالت اشتراکی همه سیستم‌ها مستقیماً روی همان فایل روی شبکه کار می‌کنند.
این ماژول برای مرحله راه‌اندازی و مهاجرت است:
  - ارسال: داده‌های همین سیستم به پوشه اشتراکی کپی می‌شود.
  - دریافت: یک کپی از دیتابیس اشتراکی روی همین سیستم قرار می‌گیرد
    (قبل از جایگزینی، از دیتابیس فعلی پشتیبان گرفته می‌شود).
همه کپی‌ها با API پشتیبان sqlite انجام می‌شود تا تراکنش‌های داخل WAL هم
یکپارچه منتقل شوند.
"""
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from core.config import settings
from core.database import (
    _dispose_engine,
    _resolve_shared_db_path,
    get_current_db_path,
    init_database,
)
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class StorageSyncError(Exception):
    """خطای قابل نمایش به کاربر در انتقال داده."""


def resolve_shared_db_path(raw: str) -> Path:
    return _resolve_shared_db_path((raw or "").strip())


def shared_files_dir_for(raw: str) -> Optional[str]:
    """پوشه فایل‌های پیوست متناظر با دیتابیس اشتراکی."""
    try:
        db = resolve_shared_db_path(raw)
    except Exception:
        return None
    return str(db.parent / "files")


def validate_shared_path(raw: str, create: bool = True) -> Tuple[bool, str, Optional[Path]]:
    """بررسی مسیر پوشه اشتراکی: کامل بودن، وجود/ساخت، و دسترسی نوشتن."""
    raw = (raw or "").strip()
    if not raw:
        return False, "مسیر پوشه مشترک را وارد کنید.", None
    if not (raw.startswith("\\\\") or Path(raw).is_absolute()):
        return False, "مسیر باید کامل باشد؛ مثال: \\\\SERVER\\SharedData یا Z:\\SharedData", None

    db_path = resolve_shared_db_path(raw)
    folder = db_path.parent
    try:
        if not folder.exists():
            if not create:
                return False, "پوشه اشتراکی در این مسیر پیدا نشد.", None
            folder.mkdir(parents=True, exist_ok=True)
        if not folder.is_dir():
            return False, "مسیر وارد‌شده یک پوشه نیست.", None
    except OSError as e:
        return False, f"پوشه در دسترس نیست یا ساخته نشد:\n{e}", None

    probe = folder / f".write_test_{uuid.uuid4().hex[:8]}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return False, f"پوشه قابل نوشتن نیست (دسترسی نوشتن روی اشتراک را بدهید):\n{e}", None

    return True, "", db_path


def _remove_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        p = Path(str(db_path) + suffix)
        try:
            if p.exists():
                p.unlink()
                logger.info("فایل موقت کنار دیتابیس حذف شد: %s", p)
        except OSError:
            logger.warning("حذف فایل موقت %s ممکن نشد", p)


def copy_sqlite_snapshot(src: Path, dst: Path) -> None:
    """کپی یکپارچه از دیتابیس با API پشتیبان sqlite سپس جایگزینی اتمیک."""
    # sqlite3.connect() silently *creates* an empty database when the path
    # doesn't exist, so a missing source would turn into an empty snapshot
    # replacing a good file. Refuse instead.
    if not src.exists():
        raise StorageSyncError(f"دیتابیس مبدأ پیدا نشد:\n{src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + f".tmp_{uuid.uuid4().hex[:6]}")
    try:
        src_con = sqlite3.connect(str(src))
        try:
            dst_con = sqlite3.connect(str(tmp))
            try:
                with dst_con:
                    src_con.backup(dst_con)
            finally:
                dst_con.close()
        finally:
            src_con.close()
        os.replace(tmp, dst)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    # فایل‌های موقت WAL/JOURNAL باقی‌مانده به فایل قبلی تعلق دارند و با
    # فایل تازه‌جایگزین‌شده ناسازگارند؛ باید پاک شوند.
    _remove_sidecars(dst)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(
            os.path.abspath(str(b))
        )
    except Exception:
        return False


def push_to_shared(raw_path: str) -> dict:
    """کپی دیتابیس فعال این سیستم به پوشه اشتراکی."""
    ok, msg, shared_db = validate_shared_path(raw_path)
    if not ok:
        raise StorageSyncError(msg)

    source = get_current_db_path()
    if not source.exists():
        raise StorageSyncError("دیتابیس این سیستم پیدا نشد؛ چیزی برای ارسال وجود ندارد.")
    if _same_file(source, shared_db):
        raise StorageSyncError("همین حالا روی همین فایل اشتراکی کار می‌کنید؛ ارسال لازم نیست.")

    overwrote = shared_db.exists()
    # اگر موتور دیتابیس روی فایل مقصد باز باشد (مثلاً بلافاصله پس از تغییر
    # حالت)، جایگزینی فایل در ویندوز ممکن نیست؛ پیش از کپی آزادش می‌کنیم.
    _dispose_engine(shared_db)
    try:
        copy_sqlite_snapshot(source, shared_db)
    except Exception as e:
        logger.exception("ارسال به اشتراکی ناموفق بود")
        raise StorageSyncError(f"ارسال انجام نشد:\n{e}")

    logger.info("ارسال دیتابیس %s به %s", source, shared_db)
    return {"source": str(source), "target": str(shared_db), "overwrote": overwrote}


def pull_from_shared(raw_path: str) -> dict:
    """جایگزینی دیتابیس این سیستم با کپی دیتابیس اشتراکی."""
    ok, msg, shared_db = validate_shared_path(raw_path, create=False)
    if not ok:
        raise StorageSyncError(msg)
    if not shared_db.exists():
        raise StorageSyncError(f"دیتابیس اشتراکی در این مسیر پیدا نشد:\n{shared_db}")

    target = get_current_db_path()
    if _same_file(shared_db, target):
        raise StorageSyncError("همین حالا روی همین فایل اشتراکی کار می‌کنید؛ دریافت لازم نیست.")

    backup: Optional[Path] = None
    try:
        if target.exists():
            # ریزثانیه لازم است؛ وگرنه دو دریافت در یک ثانیه نام یکسان می‌گیرند
            # و پشتیبان قبلی بی‌سروصدا بازنویسی می‌شود.
            backup = settings.BACKUP_DIR / (
                f"pre_pull_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
            )
            copy_sqlite_snapshot(target, backup)
    except Exception as e:
        logger.exception("پشتیبان‌گیری پیش از دریافت ناموفق بود")
        raise StorageSyncError(f"دریافت انجام نشد:\n{e}")

    # در ویندوز تا وقتی اتصالی به فایل دیتابیس باز است، جایگزینی فایل با
    # WinError 5 رد می‌شود؛ پس موتور را پیش از جایگزینی آزاد می‌کنیم.
    _dispose_engine(target)
    try:
        copy_sqlite_snapshot(shared_db, target)
        init_database(target)
    except Exception as e:
        logger.exception("دریافت از اشتراکی ناموفق بود")
        raise StorageSyncError(f"دریافت انجام نشد:\n{e}")

    logger.info("دریافت دیتابیس %s روی %s", shared_db, target)
    return {
        "source": str(shared_db),
        "target": str(target),
        "backup": str(backup) if backup else None,
    }
