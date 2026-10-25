import sys
import os
import warnings
import traceback


def suppress_qfluentwidgets_warnings():
    original_warn = warnings.warn

    def filtered_warn(message, *args, **kwargs):
        msg = str(message)
        if "box-shadow" in msg or "setPointSize" in msg:
            return
        original_warn(message, *args, **kwargs)

    warnings.warn = filtered_warn

    original_stderr = sys.stderr
    if original_stderr is None:
        # pythonw.exe runs the app without any stdio; StderrFilter would then
        # call write() on None and crash the GUI on the first Qt warning.
        return

    class StderrFilter:
        """Drops known-noisy qfluentwidgets warnings without hiding tracebacks.

        The previous version only defined write()/flush(); any library calling
        sys.stderr.fileno(), .encoding, .isatty() or .writelines() raised
        AttributeError. It also dropped *any* output containing the trigger
        substrings, including multi-line traceback text -- now only single-line
        messages (how Qt prints its warnings) are filtered.
        """

        def write(self, text):
            if (
                "\n" not in text
                and ("box-shadow" in text or "setPointSize" in text)
            ):
                return
            original_stderr.write(text)

        def writelines(self, lines):
            for line in lines:
                self.write(line)

        def flush(self):
            original_stderr.flush()

        def fileno(self):
            return original_stderr.fileno()

        def isatty(self):
            return original_stderr.isatty()

        def __getattr__(self, name):
            return getattr(original_stderr, name)

    sys.stderr = StderrFilter()


suppress_qfluentwidgets_warnings()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- لاگ‌ها ---
from utils.logging_setup import setup_logging, install_excepthook, get_logger

setup_logging()
install_excepthook()
logger = get_logger("main")

# حالت ذخیره‌سازی (محلی/اشتراکی) باید پیش از باز شدن هر دیتابیسی مشخص شود،
# پس قبل از ایمپورت ماژول‌هایی که مسیر دیتابیس را قفل می‌کنند اعمال می‌شود.
from core.storage_config import load_storage_config

load_storage_config()

from ui.main_window import main

if __name__ == "__main__":
    try:
        logger.info("Application starting")
        main()
    except Exception as e:
        logger.exception("Fatal error on startup: %s", e)
        raise
