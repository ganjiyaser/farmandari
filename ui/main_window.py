import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QFrame, QLabel, QScrollArea, QShortcut,
)
from PyQt5.QtCore import Qt, QLockFile, QSize, QStandardPaths
from PyQt5.QtGui import QKeySequence, QIcon

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, setTheme, Theme, setThemeColor,
    InfoBar, InfoBarPosition, MessageBox, NavigationAvatarWidget,
    ScrollBarHandleDisplayMode,
)

from ui.styles import get_font
from ui.theme import theme_manager, ThemeMode
from ui.fluent_icons import fluent_icon
from ui.dashboard_page import DashboardPage
from ui.contacts_page import ContactsPage
from ui.officials_page import OfficialsPage
from ui.org_chart_page import OrgChartPage
from ui.decisions_page import DecisionsPage
from ui.letters_page import LettersPage
from ui.groups_page import GroupsPage
from ui.sms_page import SMSPage
from ui.files_page import FilesPage
from ui.reports_page import ReportsPage
from ui.settings_page import SettingsPage
from ui.calendar_page import CalendarPage
from ui.notes_page import NotesPage
from ui.tasks_page import TasksPage
from ui.users_page import UsersPage
from ui.login_page import LoginPage, APP_TITLE
from core.config import settings
from core.database import (
    init_user_database, set_current_user_context, init_database,
    clear_current_user_context,
)
from services.repositories import setting_repo, user_repo
from utils.window_utils import (
    ScreenFitFilter, available_geometry, center_on_screen,
    fit_window_to_screen, watch_window_screen,
)
from services.reminder_service import reminder_service


NAV_SPEC = [
    ("dashboard", DashboardPage, "dashboard", "داشبورد", "HOME", True),
    ("contacts", ContactsPage, "contacts", "دفترچه تلفن", "PEOPLE", True),
    ("officials", OfficialsPage, "officials", "مسئولین", "PEOPLE", True),
    ("org_chart", OrgChartPage, "org_chart", "چارت سازمانی", "UNIT", True),
    ("calendar", CalendarPage, "calendar", "تقویم و جلسات", "CALENDAR", True),
    ("decisions", DecisionsPage, "decisions", "صورت‌جلسه و مصوبات", "EDIT", True),
    ("letters", LettersPage, "letters", "دفتر اندیکاتور", "DOCUMENT", True),
    ("groups", GroupsPage, "groups", "گروه‌ها", "PEOPLE", True),
    ("sms", SMSPage, "sms", "پیامک", "CHAT", True),
    ("files", FilesPage, "files", "فایل‌ها و نامه‌ها", "FOLDER", True),
    ("notes", NotesPage, "notes", "یادداشت‌ها", "EDIT", True),
    ("tasks", TasksPage, "tasks", "کارهای روزانه", "CHECKBOX", True),
    ("reports", ReportsPage, "reports", "گزارش‌ها", "DOCUMENT", True),
    ("settings", SettingsPage, "settings", "تنظیمات", "SETTING", True),
    ("users", UsersPage, "user_management", "مدیریت کاربران", "PEOPLE", True),
]


class MainWindow(FluentWindow):
    def __init__(self, user=None):
        super().__init__()
        self.current_user = user
        self.all_pages = {}
        self.setMicaEffectEnabled(False)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._setup_content_scroll()

        self._load_theme()
        self._create_pages()
        self._setup_navigation()
        self._init_window()

        theme_manager.theme_changed.connect(self._on_theme_changed)
        self._start_reminder_service()

        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(lambda: self._global_search(""))

    def _setup_content_scroll(self):
        """محتوای صفحه‌ها در یک ناحیهٔ اسکرول‌شونده قرار می‌گیرد.

        روی نمایشگرهای کوچک‌تر از اندازهٔ طراحی، به‌جای جمع‌کردن رابط
        کاربری، اندازهٔ طبیعی حفظ می‌شود و اسکرول افقی/عمودی ظاهر می‌شود.
        """
        self._content_scroll = QScrollArea(self)
        self._content_scroll.setObjectName("contentScroll")
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content_scroll.setStyleSheet(
            "QScrollArea#contentScroll { border: none; background: transparent; }"
            "QScrollArea#contentScroll > QWidget > QWidget { background: transparent; }"
        )
        self._content_scroll.viewport().setAutoFillBackground(False)
        self.widgetLayout.removeWidget(self.stackedWidget)
        self.stackedWidget.setMinimumSize(1000, 600)
        self._content_scroll.setWidget(self.stackedWidget)
        self.widgetLayout.addWidget(self._content_scroll)

    def _fit_scroll_content(self):
        """ارتفاع محتوا بر اساس صفحهٔ جاری تعیین می‌شود.

        اگر ارتفاع محتوا کمتر از نیاز طبیعی صفحه باشد، چیدمان فشرده
        می‌شود (مثلاً دکمه‌ها روی هم می‌افتند). پس حداقل ارتفاع همان
        اندازهٔ طبیعی صفحهٔ جاری است و در صورت کمبود فضا، اسکرول می‌آید.
        """
        page = self.stackedWidget.currentWidget()
        min_h = 600
        if page is not None:
            try:
                min_h = max(min_h, page.minimumSizeHint().height())
            except Exception:
                pass
        self.stackedWidget.setMinimumHeight(min_h)

    def _load_theme(self):
        try:
            saved = setting_repo.get_setting("theme", "light")
            if saved:
                theme_manager.set_mode(ThemeMode(saved) if isinstance(saved, str) else saved)
            if theme_manager.mode == ThemeMode.DARK:
                setTheme(Theme.DARK)
            else:
                setTheme(Theme.LIGHT)
            setThemeColor(theme_manager.current.primary)
        except Exception:
            setTheme(Theme.LIGHT)
            setThemeColor("#0969da")

    def _create_pages(self):
        for attr, cls, perm, title, icon_name, _is_top in NAV_SPEC:
            try:
                page = cls(self)
            except TypeError:
                page = cls()
            except Exception:
                logging.exception("Failed to create page %s", attr)
                page = QLabel(f"خطا در بارگذاری صفحه «{title}»")
                page.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page.setObjectName(attr)
            setattr(self, attr, page)
            self.all_pages[attr] = (page, perm, icon_name, title)

    def _setup_navigation(self):
        try:
            accessible = self.current_user.get_accessible_pages() if self.current_user else []
        except Exception:
            accessible = []
        is_super = bool(self.current_user and self.current_user.is_superuser)
        if not is_super and not accessible:
            # fail-open ممنوع: کاربر بدون هیچ دسترسی فقط داشبورد را می‌بیند
            accessible = ["dashboard"]

        first_page = None
        for attr, _cls, perm, title, icon_name, is_top in NAV_SPEC:
            if attr not in self.all_pages:
                continue
            if not is_super and perm not in accessible:
                continue
            page = self.all_pages[attr][0]
            # آیتم‌های اصلی در ناحیهٔ اسکرول‌شوندهٔ منو قرار می‌گیرند تا در
            # صفحه‌های کوتاه، منو با چرخ ماوس/اسکرول در دسترس بماند.
            pos = NavigationItemPosition.SCROLL if is_top else NavigationItemPosition.BOTTOM
            self.addSubInterface(page, fluent_icon(icon_name), title, pos)
            if first_page is None:
                first_page = page

        # User avatar at bottom (Fluent pattern)
        if self.current_user:
            try:
                name = getattr(self.current_user, "full_name", None) or self.current_user.username
                self.navigationInterface.addWidget(
                    routeKey="avatar",
                    widget=NavigationAvatarWidget(name, None),
                    onClick=lambda: InfoBar.info(
                        title="کاربر",
                        content=name,
                        parent=self,
                        position=InfoBarPosition.TOP,
                        duration=2500,
                    ),
                    position=NavigationItemPosition.BOTTOM,
                )
            except Exception:
                pass

        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        self.navigationInterface.addItem(
            routeKey="logout",
            icon=fluent_icon("RETURN", "CLOSE"),
            text="خروج از حساب",
            onClick=self.logout,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        if first_page:
            self.navigationInterface.setCurrentItem(first_page.objectName())
            if hasattr(first_page, "refresh"):
                try:
                    first_page.refresh()
                except Exception:
                    pass
            self._ensure_nav_visible(first_page)

        # دستهٔ اسکرول منو همیشه دیده شود تا کاربر بتواند منو را جابه‌جا کند
        try:
            self.navigationInterface.panel.scrollArea.scrollDelagate.vScrollBar.setHandleDisplayMode(
                ScrollBarHandleDisplayMode.ALWAYS
            )
        except Exception:
            pass

        self.stackedWidget.currentChanged.connect(self._on_stack_changed)

    def _ensure_nav_visible(self, page=None):
        """آیتم فعال منو داخل ناحیهٔ اسکرول‌شونده دیده شود."""
        if page is None:
            page = self.stackedWidget.currentWidget()
        if page is None:
            return
        try:
            item = self.navigationInterface.widget(page.objectName())
            if item is not None:
                self.navigationInterface.panel.scrollArea.ensureWidgetVisible(item, 0, 12)
        except Exception:
            pass

    def _on_stack_changed(self, _index):
        # صفحهٔ تازه از بالای ناحیهٔ اسکرول دیده شود
        self._fit_scroll_content()
        self._content_scroll.verticalScrollBar().setValue(0)
        self._content_scroll.horizontalScrollBar().setValue(0)
        page = self.stackedWidget.currentWidget()
        if page and hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception:
                pass
        self._ensure_nav_visible(page)

    def _init_window(self):
        # حداقلِ پنجره فقط برای خود قاب است؛ محتوا داخل ناحیهٔ اسکرول‌شونده
        # اندازهٔ طبیعی خود را حفظ می‌کند.
        self.setMinimumSize(900, 560)
        self._prefer_maximized = False
        preferred = QSize(1400, 900)
        avail = available_geometry(self)
        if avail is not None and not avail.isEmpty():
            if avail.width() < preferred.width() or avail.height() < preferred.height():
                # نمایشگر کوچک‌تر از اندازهٔ طراحی: تمام‌صفحه، با اسکرول
                self._prefer_maximized = True
            # اندازهٔ حالت عادی (پس از Restore Down) هم از صفحه بزرگ‌تر نشود
            self.resize(
                min(preferred.width(), max(700, avail.width() - 40)),
                min(preferred.height(), max(480, avail.height() - 80)),
            )
        else:
            self.resize(preferred)
        self._fit_scroll_content()
        self.setWindowTitle(settings.APP_NAME)
        try:
            self.setWindowIcon(QIcon(":/qfluentwidgets/images/logo.png"))
        except Exception:
            pass

    def _start_reminder_service(self):
        reminder_service.reminder_triggered.connect(self._on_reminder)
        reminder_service.program_digest_done.connect(self._on_program_digest)
        reminder_service.start()

    def _on_program_digest(self, result):
        if result.get("error"):
            InfoBar.warning(
                title="برنامهٔ فردا",
                content=result["error"],
                orient=Qt.Orientation.Vertical,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                parent=self,
            )
            return
        if not result.get("total"):
            return
        InfoBar.success(
            title="برنامهٔ فردا",
            content=(
                f"پیامک برنامهٔ {result.get('target_date')}\n"
                f"{result.get('success', 0)} از {result.get('total', 0)} برنامه ارسال شد"
            ),
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=6000,
            parent=self,
        )

    def _on_reminder(self, event_id, title, date_time):
        InfoBar.success(
            title="یادآوری",
            content=f"{title}\n{date_time}",
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self,
        )

    def _on_theme_changed(self, _theme_name):
        try:
            if theme_manager.mode == ThemeMode.DARK:
                setTheme(Theme.DARK)
            else:
                setTheme(Theme.LIGHT)
            setThemeColor(theme_manager.current.primary)
        except Exception:
            pass
        for page, *_rest in self.all_pages.values():
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:
                    pass

    def navigate_to(self, key):
        if key not in self.all_pages:
            return
        # چک دسترسی: shortcutهای درون‌صفحه‌ای هم نباید از فیلتر ناوبری عبور کنند
        is_super = bool(self.current_user and self.current_user.is_superuser)
        if not is_super:
            try:
                accessible = self.current_user.get_accessible_pages() or []
            except Exception:
                accessible = []
            _page, perm, _icon, _title = self.all_pages[key]
            if perm not in accessible:
                InfoBar.warning(
                    title="دسترسی",
                    content="شما به این بخش دسترسی ندارید",
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )
                return
        self.switchTo(self.all_pages[key][0])

    def _global_search(self, text):
        from ui.search_dialog import SearchDialog
        dlg = SearchDialog(self, text)
        dlg.exec()

    def logout(self):
        box = MessageBox("خروج", "از حساب خارج می‌شوید؟", self)
        box.yesButton.setText("خروج")
        box.cancelButton.setText("انصراف")
        if not box.exec():
            return
        self.current_user = None
        try:
            setting_repo.set_setting("current_user_id", None)
            setting_repo.set_setting("current_username", None)
            setting_repo.set_setting("remember_login", False)
        except Exception:
            logging.exception("Could not clear session settings on logout")
        # کانتکست دیتابیس کاربر قبلی باید پاک شود وگرنه لاگین بعدی در
        # دیتابیس همان کاربر جست‌وجو می‌شود و ورود غیرممکن می‌شود.
        try:
            clear_current_user_context()
        except Exception:
            pass
        try:
            reminder_service.stop()
            reminder_service.reminder_triggered.disconnect(self._on_reminder)
        except Exception:
            pass
        try:
            theme_manager.theme_changed.disconnect(self._on_theme_changed)
        except Exception:
            pass
        self.hide()
        login = LoginPage()
        login.setWindowTitle(APP_TITLE)
        fit_window_to_screen(login, preferred=QSize(1100, 700), center=False)
        login.login_successful.connect(lambda user, w=login: _open_main_from_login(user, w))
        app = QApplication.instance()
        # ارجاع به پنجرهٔ بسته‌شده پاک شود؛ وگرنه تایمر/کارگرهای پس‌زمینهٔ آن
        # زنده می‌مانند و بعد از ورود دوباره دو مجموعه موازی اجرا می‌شوند
        app._main_window = None
        app._login_window = login
        login.show()
        center_on_screen(login)
        self.close()


def _open_main_from_login(user, login_window):
    app = QApplication.instance()
    win = MainWindow(user)
    app._main_window = win
    if getattr(win, "_prefer_maximized", False):
        win.showMaximized()
    else:
        win.show()
        center_on_screen(win)
    watch_window_screen(win)
    login_window.close()


def _warn_already_running():
    """اعلان «برنامه از قبل باز است» بدون نیاز به QApplication (پیش از ساخت Qt)"""
    msg_fa = "برنامه هم‌اکنون در حال اجراست.\nنمونهٔ دوم باز نمی‌شود."
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg_fa, APP_TITLE, 0x00000040)  # MB_ICONINFORMATION
    except Exception:
        logging.warning("Second instance blocked: %s", msg_fa)


def _enable_high_dpi():
    """Scale the UI correctly on Win7/10 displays with DPI scaling enabled.

    Qt 6 turns this on automatically, but Qt 5 requires the attributes before
    QApplication is constructed (and Qt 5.14+ supports fractional scaling).
    """
    for attr_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(Qt, attr_name, None)
        if attr is not None:
            QApplication.setAttribute(attr, True)

    rounding_enum = getattr(Qt, "HighDpiScaleFactorRoundingPolicy", None)
    if rounding_enum is not None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(rounding_enum.PassThrough)


def main():
    _enable_high_dpi()
    # جلوگیری از اجرای دوبارهٔ برنامه: دو نمونه همزمان روی همان دیتابیس
    # SQLite و همان پورت سریال مودم تداخل ایجاد می‌کنند
    lock = QLockFile(
        os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation),
                     "farmandari-app.lock")
    )
    if not lock.tryLock(100):
        _warn_already_running()
        sys.exit(0)

    init_database()
    try:
        from services.repositories import permission_repo, role_repo, user_repo as _user_repo
        permission_repo.initialize_default_permissions()
        role_repo.initialize_default_roles()
        # فقط در صورت نبودِ ادمین ساخته می‌شود؛ رمز تغییر یافته هرگز ریست نمی‌شود
        # (ریست رمز در هر اجرا = دور زدن تغییر رمز و قفل حساب)
        _user_repo.initialize_admin_user()
    except Exception as e:
        logging.warning("Could not initialize default data: %s", e)

    saved_user = None
    try:
        user_id = setting_repo.get_setting("current_user_id")
        # Restoring the previous session is opt-in. Without this check anyone
        # launching the app inherited the last user's permissions with no
        # password prompt ("به‌خاطرسپاری ورود" was created but never read).
        remember = setting_repo.get_setting("remember_login")
        if user_id and remember in (True, "True", "true", 1, "1"):
            user = user_repo.get_by_id(user_id)
            if user and user.is_active:
                init_user_database(user.username)
                set_current_user_context(user.username)
                saved_user = user
    except Exception:
        logging.exception("Could not restore previous session; showing login")

    app = QApplication(sys.argv)
    # هر دیالوگ تازه در اولین نمایش داخل فضای مانیتور جا داده می‌شود
    app._screen_fit_filter = ScreenFitFilter(app)
    app.installEventFilter(app._screen_fit_filter)
    app.setApplicationName(settings.APP_NAME)
    app.setOrganizationName(settings.APP_NAME)
    app.setApplicationVersion(settings.APP_VERSION)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setFont(get_font(10))
    setTheme(Theme.LIGHT)
    setThemeColor("#0969da")

    if saved_user:
        window = MainWindow(saved_user)
        app._main_window = window
        if getattr(window, "_prefer_maximized", False):
            window.showMaximized()
        else:
            window.show()
            center_on_screen(window)
        watch_window_screen(window)
    else:
        login = LoginPage()
        login.setWindowTitle(APP_TITLE)
        fit_window_to_screen(login, preferred=QSize(1100, 700), center=False)
        login.login_successful.connect(lambda user, w=login: _open_main_from_login(user, w))
        app._login_window = login
        login.show()
        center_on_screen(login)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
