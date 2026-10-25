# ============================================
# ماژول آپدیت خودکار - برای ادغام در برنامه
# این فایل رو در برنامه import کنید
# ============================================

import os
import sys
import json
import hashlib
import logging
import requests
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from packaging import version as pkg_version

logger = logging.getLogger(__name__)

class AutoUpdater:
    def __init__(self, 
                 current_version: str,
                 update_server_url: str,
                 check_interval_hours: int = 24,
                 on_update_available: Callable = None,
                 on_update_downloaded: Callable = None,
                 on_error: Callable = None,
                 require_https: bool = True,
                 on_before_exit: Callable = None):
        """
        current_version: نسخه فعلی برنامه (مثال: "1.0.0")
        update_server_url: آدرس سرور آپدیت (مثال: "https://server/farmandari/update.json")
        check_interval_hours: فاصله بررسی آپدیت (ساعت)
        on_update_available: تابع callback وقتی آپدیت موجود باشه
        on_update_downloaded: تابع callback وقتی دانلود تمام شد
        on_error: تابع callback در صورت خطا
        require_https: اگر True (پیش‌فرض) فقط HTTPS پذیرفته می‌شود و نصب بدون
            هش sha256 معتبر رد می‌شود (جلوگیری از RCE از طریق MITM).
        on_before_exit: تابع اختیاری که قبل از خروج برای نصب صدا زده می‌شود
            (مثلاً بستن فرم‌ها/ذخیره کارهای در جریان).
        """
        self.current_version = current_version
        self.update_server_url = update_server_url
        self.check_interval = check_interval_hours * 3600
        self.on_update_available = on_update_available
        self.on_update_downloaded = on_update_downloaded
        self.on_error = on_error
        self.require_https = require_https
        self.on_before_exit = on_before_exit
        self._stop_event = threading.Event()
        self._thread = None

    def _validate_url(self, url: str) -> None:
        """اجبار HTTPS در حالت ایمن؛ جلوی دانلود/اجرای کد از مسیر رمزنگاری‌نشده"""
        if not url:
            raise ValueError("آدرس آپدیت خالی است")
        if self.require_https and not url.lower().startswith("https://"):
            raise ValueError(
                f"برای امنیت فقط HTTPS مجاز است (آدرس داده‌شده: {url}). "
                "اگر واقعاً به HTTP نیاز دارید require_https=False بگذارید."
            )

    @staticmethod
    def _sha256_of(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest().lower()

    def start_background_check(self):
        """شروع بررسی دوره‌ای در پس‌زمینه"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
    
    def stop_background_check(self):
        """توقف بررسی دوره‌ای"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
    
    def _check_loop(self):
        while not self._stop_event.is_set():
            try:
                self.check_for_update()
            except Exception as e:
                if self.on_error:
                    self.on_error(str(e))
                else:
                    # رخ دادن بی‌صدا یعنی یک به‌روزرسانی خراب/مهاجم برای ساعت‌ها
                    # دیده نمی‌شود.
                    logger.warning("Update check failed: %s", e)
            # صبر تا interval بعدی
            self._stop_event.wait(self.check_interval)
    
    def check_for_update(self) -> Optional[dict]:
        """بررسی آپدیت در سرور"""
        try:
            self._validate_url(self.update_server_url)
            response = requests.get(self.update_server_url, timeout=10)
            response.raise_for_status()
            # ریدایرکت دنبال می‌شود؛ اعتبارسنجی باید روی URL *نهایی* انجام شود
            # وگرنه یک https:// می‌تواند با 30x به http:// برسد.
            self._validate_url(response.url)
            update_info = response.json()
            
            latest_version = update_info.get("version", "0.0.0")
            download_url = update_info.get("download_url", "")
            changelog = update_info.get("changelog", "")
            mandatory = update_info.get("mandatory", False)
            sha256 = update_info.get("sha256", "")
            size = update_info.get("size")
            min_version = update_info.get("min_version")

            if min_version and pkg_version.parse(self.current_version) < pkg_version.parse(min_version):
                # update.json declares a floor the client hasn't reached; the
                # package may not be applicable. Previously declared but never
                # read by any code.
                logger.warning(
                    "Update %s requires at least version %s (current %s); "
                    "a manual upgrade may be needed.",
                    latest_version, min_version, self.current_version,
                )

            if pkg_version.parse(latest_version) > pkg_version.parse(self.current_version):
                info = {
                    "version": latest_version,
                    "download_url": download_url,
                    "changelog": changelog,
                    "mandatory": mandatory,
                    "sha256": sha256,
                    "size": size,
                }
                if self.on_update_available:
                    self.on_update_available(info)
                return info
            return None
        except Exception as e:
            if self.on_error:
                self.on_error(f"خطا در بررسی آپدیت: {e}")
            else:
                logger.warning("Update check failed: %s", e)
            return None
    
    def download_and_install(self, download_url: str,
                             expected_sha256: str = None,
                             expected_size: Optional[int] = None,
                             progress_callback: Callable = None) -> bool:
        """دانلود، راستی‌آزمایی یکپارچگی و نصب آپدیت"""
        installer_path: Optional[Path] = None
        try:
            self._validate_url(download_url)

            # نام فایل تصادفی: مسیر ثابت/قابل پیش‌بینی در %TEMP% یعنی هر
            # بدافزار هم‌کاربر می‌تواند فایل را قبل از اجرا جایگزین کند (TOCTOU).
            temp_dir = Path(os.environ.get('TEMP', tempfile.gettempdir()))
            fd, tmp_name = tempfile.mkstemp(
                prefix="BakhshdariSetup_", suffix=".exe", dir=str(temp_dir)
            )
            os.close(fd)
            installer_path = Path(tmp_name)
            
            # دانلود با پیشرفت
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()
            self._validate_url(response.url)
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            sha = hashlib.sha256()
            
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._stop_event.is_set():
                        raise ValueError("دانلود توسط کاربر متوقف شد؛ نصب انجام نشد.")
                    if chunk:
                        f.write(chunk)
                        sha.update(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded / total_size * 100)

            # بررسی اندازهٔ اعلام‌شده (دانلود ناقص اجرا نشود)
            if total_size > 0 and downloaded != total_size:
                raise ValueError(
                    f"دانلود ناقص: {downloaded} از {total_size} بایت"
                )
            if expected_size and downloaded != int(expected_size):
                raise ValueError(
                    f"اندازهٔ فایل با مقدار اعلام‌شده در update.json نمی‌خواند "
                    f"({downloaded} != {expected_size})"
                )

            # راستی‌آزمایی هش: در حالت ایمن، نصب بدون sha256 معتبر ممنوع است.
            digest = sha.hexdigest().lower()
            if expected_sha256:
                if digest != str(expected_sha256).strip().lower():
                    raise ValueError(
                        "هش sha256 فایل دانلودشده با مقدار انتظار مطابقت ندارد؛ "
                        "نصب متوقف شد (احتمال دستکاری/MITM)."
                    )
            elif self.require_https:
                raise ValueError(
                    "فیلد sha256 در update.json موجود نیست؛ در حالت ایمن نصب "
                    "بدون هش رد می‌شود."
                )

            if self.on_update_downloaded:
                self.on_update_downloaded(str(installer_path))

            # هش دوباره از روی دیسک، درست قبل از اجرا: بین دانلود و Popen
            # callback ها اجرا می‌شوند و فایل می‌تواند عوض شده باشد (TOCTOU).
            on_disk = self._sha256_of(installer_path)
            if expected_sha256 and on_disk != str(expected_sha256).strip().lower():
                raise ValueError(
                    "هش فایل روی دیسک با مقدار انتظار نمی‌خواند؛ نصب متوقف شد."
                )

            # NOTE (باقی‌مانده): sha256 از همان update.json می‌آید، پس فقط
            # خرابی/MITM را می‌گیرد نه سرورِ آلوده را. پیش از اتصال این ماژول
            # به main.py باید امضای Authenticode نصب‌کننده با کلید پین‌شده
            # راستی‌آزمایی شود.

            # اجرای نصب‌کننده به صورت Silent (NSIS با /S).
            # shell=False: از طریق shell آرگومان /D= که فاصله دارد خراب می‌شد.
            # در NSIS پارامتر /D= باید آخرین آرگومان و بدون quote باشد.
            install_dir = os.path.dirname(sys.executable)
            subprocess.Popen([str(installer_path), "/S", "/D=" + install_dir])
            
            # خروج تمیز: flush، callback و بستن دیتابیس قبل از os._exit
            self._graceful_shutdown()
            os._exit(0)
        except Exception as e:
            if self.on_error:
                self.on_error(f"خطا در دانلود/نصب: {e}")
            else:
                logger.error("Update download/install failed: %s", e)
            if installer_path is not None:
                try:
                    installer_path.unlink()
                except OSError:
                    pass
            return False

    def _graceful_shutdown(self) -> None:
        """flush و بستن منابع قبل از خروج سخت‌افزاری (os._exit)"""
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        if self.on_before_exit:
            try:
                self.on_before_exit()
            except Exception:
                pass
        # آزادسازی قفل دیتابیس تا نصب‌کننده بتواند فایل‌ها را جایگزین کند
        try:
            from core.database import get_current_db_path, _dispose_engine
            _dispose_engine(get_current_db_path())
        except Exception:
            pass


# ============================================
# فایل تنظیمات سرور آپدیت (update.json)
# این فایل رو روی سرور وب یا شبکه قرار بدید
# ============================================
UPDATE_JSON_EXAMPLE = {
    "version": "1.0.1",
    "download_url": "https://server/farmandari/BakhshdariSetup_1.0.1.exe",
    "changelog": "- رفع باگ تقویم\n- بهبود عملکرد گروه‌ها\n- اصلاح دیتابیس",
    "mandatory": False,
    "min_version": "1.0.0",
    # هش sha256 فایل نصب (در حالت ایمن اجباری است):
    #   certutil -hashfile BakhshdariSetup_1.0.1.exe SHA256
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    # اندازهٔ دقیق فایل بر حسب بایت (اختیاری، برای رد دانلود ناقص):
    "size": 0
}

# ============================================
# نمونه استفاده در main.py:
# ============================================
"""
from utils.auto_updater import AutoUpdater

# در تابع main():
updater = AutoUpdater(
    current_version="1.0.0",
    update_server_url="https://YOUR_SERVER/farmandari/update.json",
    check_interval_hours=24,
    on_update_available=lambda info: show_update_dialog(info),
    on_update_downloaded=lambda path: print(f"Downloaded: {path}"),
    on_error=lambda err: print(f"Update error: {err}")
)

# شروع بررسی در پس‌زمینه
updater.start_background_check()

# یا بررسی دستی در منوی کمک:
def check_update_manual():
    info = updater.check_for_update()
    if info:
        # نمایش دیالوگ آپدیت
        pass
    else:
        QMessageBox.information(None, "آپدیت", "شما آخرین نسخه را دارید.")
"""