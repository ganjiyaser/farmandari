"""
مرکز مدیریت لاگ‌های برنامه
- فایل چرخشی در data/logs
- ثبت خطاهای مدیریت‌نشده
- سطح قابل تنظیم
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from typing import Optional

_CONFIGURED = False
_LOGGER_NAME = "farmandari"


def get_logs_dir() -> Path:
    try:
        from core.config import settings
        d = Path(settings.LOGS_DIR)
    except Exception:
        if getattr(sys, "frozen", False):
            # نسخه‌ی نصب‌شده: Program Files قابل نوشتن نیست
            d = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Farmandari" / "data" / "logs"
        else:
            d = Path(__file__).resolve().parent.parent / "data" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(
    level: int = logging.INFO,
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
    also_console: bool = True,
) -> logging.Logger:
    """یک‌بار در شروع برنامه فراخوانی شود."""
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    # clear() only empties the list -- the previous RotatingFileHandler objects
    # keep their file handles open. Close them properly.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    logger.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = get_logs_dir() / "app.log"
    error_file = get_logs_dir() / "errors.log"

    fh = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    eh = RotatingFileHandler(
        error_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    logger.addHandler(eh)

    if also_console and sys.stdout is not None:
        # None under pythonw.exe -- StreamHandler(None) would fall back to
        # sys.stderr (also None) and blow up on the first WARNING.
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    # ریشه را هم کمی هم‌تراز کن تا sqlalchemy و ... زیاد شلوغ نکنند
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    _CONFIGURED = True
    logger.info("Logging started → %s", log_file)
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    if not _CONFIGURED:
        setup_logging()
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


def log_exception(exc: BaseException, context: str = "") -> None:
    logger = get_logger("exception")
    msg = f"{context + ': ' if context else ''}{type(exc).__name__}: {exc}"
    logger.error(msg)
    logger.error("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


def install_excepthook() -> None:
    """خطاهای مدیریت‌نشده را در فایل ثبت و در صورت امکان به کاربر نشان بده."""
    def _hook(exc_type, exc_value, exc_tb):
        try:
            logger = get_logger("unhandled")
            logger.error("Unhandled exception")
            logger.error("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance():
                QMessageBox.critical(
                    None,
                    "خطای برنامه",
                    f"{exc_value}\n\nجزئیات در پوشه لاگ ذخیره شد:\n{get_logs_dir() / 'errors.log'}",
                )
                return
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook

    # Worker-thread exceptions go through threading.excepthook, NOT
    # sys.excepthook -- without this, every QThread/threading failure only
    # reached the (filtered) stderr and never errors.log.
    def _thread_hook(args, /):
        try:
            logger = get_logger("unhandled")
            logger.error(
                "Unhandled exception in thread %r",
                getattr(args, "thread", None),
            )
            logger.error(
                "".join(
                    traceback.format_exception(
                        args.exc_type, args.exc_value, args.exc_traceback
                    )
                )
            )
        except Exception:
            pass

    threading.excepthook = _thread_hook


def list_log_files() -> list[Path]:
    d = get_logs_dir()
    return sorted(d.glob("*.log*"), key=lambda p: p.stat().st_mtime, reverse=True)


def clear_old_logs(keep_days: int = 30) -> int:
    """حذف فایل‌های لاگ قدیمی‌تر از keep_days روز. تعداد حذف‌شده را برمی‌گرداند."""
    import time
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for p in get_logs_dir().glob("*.log*"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def tail_errors(lines: int = 50) -> str:
    path = get_logs_dir() / "errors.log"
    if not path.exists():
        return "(فایل errors.log خالی یا موجود نیست)"
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError as e:
        return f"خطا در خواندن لاگ: {e}"
