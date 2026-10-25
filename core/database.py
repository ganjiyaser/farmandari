from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from pathlib import Path
import logging
import threading

from core.config import settings
from models.models import Base, User

logger = logging.getLogger(__name__)

# Global current user context
_current_user_db_path = None
_current_user_files_dir = None
_context_lock = threading.Lock()

# Process-wide engine cache (keyed by db path string)
_engines = {}
_engines_lock = threading.Lock()

# Process-wide session factory cache. A session *factory* is thread-safe to
# share (it only builds a new Session per call), and keeping it process-wide
# means _dispose_engine() can drop factories owned by *other* threads too --
# otherwise a disposed/replaced engine stays reachable from worker threads
# (reminder timer, send workers) and keeps the file locked on Windows.
_session_factories = {}
_session_factories_lock = threading.Lock()


def _db_key(db_path: Path) -> str:
    """Stable cache key for a database path.

    The old code used ``str(p.resolve() if p.exists() else p)`` which produced
    *different* keys before and after the file was created: the first call
    (before create_all) stored an unresolved key, every later call resolved it,
    so a second engine was built for the same file and _dispose_engine popped
    the wrong entry.
    """
    p = Path(db_path)
    try:
        return str(p.expanduser().absolute())
    except (OSError, ValueError):
        return str(p)


def set_current_user_context(username: str):
    """Set the current user context for database operations"""
    global _current_user_db_path, _current_user_files_dir
    db_path = get_user_db_path(username)
    files_dir = get_user_files_dir(username)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)
    # Assign both together under a lock so a concurrent reader never sees a
    # new DB path paired with the previous user's files dir.
    with _context_lock:
        _current_user_db_path = db_path
        _current_user_files_dir = files_dir


def clear_current_user_context():
    """Clear the current user context"""
    global _current_user_db_path, _current_user_files_dir
    with _context_lock:
        _current_user_db_path = None
        _current_user_files_dir = None


def get_current_db_path() -> Path:
    """Get the current user's database path, or default"""
    with _context_lock:
        if _current_user_db_path:
            return _current_user_db_path
    return settings.DB_PATH


def get_current_files_dir() -> Path:
    """Get the current user's files directory, or default"""
    with _context_lock:
        if _current_user_files_dir:
            return _current_user_files_dir
    return settings.FILES_DIR


def _resolve_shared_db_path(raw: str) -> Path:
    """
    Resolve SHARED_DB_PATH.
    If the path points to an existing directory (or ends with a separator /
    looks like a folder), append DEFAULT_USER_DB_NAME.
    Otherwise treat it as a full file path.
    """
    p = Path(raw)
    # Network/UNC paths may not exist locally yet; still detect "folder-like"
    looks_like_dir = (
        raw.endswith(("/", "\\"))
        or p.suffix.lower() not in (".db", ".sqlite", ".sqlite3")
    )
    try:
        if p.exists() and p.is_dir():
            return p / settings.DEFAULT_USER_DB_NAME
    except OSError:
        pass
    if looks_like_dir and p.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
        return p / settings.DEFAULT_USER_DB_NAME
    return p


def get_engine(db_path: Path = None, echo: bool = False):
    """Get or create a cached engine for the given database path"""
    if db_path is None:
        db_path = get_current_db_path()

    db_key = _db_key(db_path)

    with _engines_lock:
        if db_key in _engines:
            return _engines[db_key]

        db_url = f"sqlite:///{db_path}"
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            # QueuePool gives every thread its own DBAPI connection. The old
            # StaticPool shared ONE connection across all threads, so a
            # commit()/rollback() in one thread could publish or discard another
            # thread's half-finished transaction.
            poolclass=QueuePool,
            pool_size=8,
            max_overflow=8,
            pool_recycle=1800,
            echo=echo,
        )

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # Wait instead of failing instantly with "database is locked" when
            # another connection (other thread / other PC on the share) writes.
            cursor.execute("PRAGMA busy_timeout=30000")
            if settings.STORAGE_MODE == "shared":
                # WAL relies on shared-memory locking that network shares (SMB)
                # don't support reliably -> use the classic rollback journal
                # with full fsync to avoid corruption over the network.
                cursor.execute("PRAGMA journal_mode=DELETE")
                cursor.execute("PRAGMA synchronous=FULL")
            else:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()

        _engines[db_key] = engine
        return engine



def rebuild_contacts_for_phonebook(engine) -> bool:
    """ستون contacts.mobile را در دیتابیس‌های قدیمی اختیاری می‌کند.

    دفترچه تلفن به رکوردهایی نیاز دارد که فقط تلفن ثابت/فکس دارند (ادارات)،
    ولی جدول قدیمی mobile را NOT NULL ساخته است و SQLite هم
    ALTER ... DROP NOT NULL ندارد. پس جدول با تعریف جدید مدل بازسازی می‌شود؛
    قبل از آن یک نسخه پشتیبان کنار فایل دیتابیس نوشته می‌شود.
    """
    import shutil
    import sqlite3
    from sqlalchemy import inspect as sa_inspect, MetaData
    from sqlalchemy.schema import CreateTable, CreateIndex
    from models.models import Contact

    try:
        insp = sa_inspect(engine)
        if "contacts" not in insp.get_table_names():
            return False
        old_cols = insp.get_columns("contacts")
    except Exception:
        return False

    mobile_col = next((c for c in old_cols if c["name"] == "mobile"), None)
    if mobile_col is None or mobile_col.get("nullable", True):
        return False

    db_path = engine.url.database
    if not db_path or not Path(db_path).exists():
        return False

    engine.dispose()
    raw = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        try:
            raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass

        backup = Path(str(db_path) + ".pre-phonebook.bak")
        try:
            if not backup.exists():
                shutil.copy2(db_path, backup)
                logger.info("Contacts backup written to %s", backup)
        except Exception as e:
            # بدون نسخه پشتیبان ریسک بازسازی جدول را نمی‌پذیریم
            logger.error("Contacts rebuild skipped (backup failed): %s", e)
            return False

        tmp_name = "contacts__phonebook_rebuild"
        md = MetaData()
        new_table = Contact.__table__.to_metadata(md, name=tmp_name)
        # جدول‌های مرجع (villages و...) هم باید در همین MetaData باشند، وگرنه
        # کامپایل DDL روی کلید خارجی با NoReferencedTableError شکست می‌خورد
        for fk in Contact.__table__.foreign_keys:
            target = fk.target_fullname.split(".")[0]
            if target in md.tables:
                continue
            ref = Base.metadata.tables.get(target)
            if ref is not None:
                ref.to_metadata(md, name=target)
        create_sql = str(CreateTable(new_table).compile(engine))
        old_names = [c["name"] for c in old_cols]
        keep = [col.name for col in Contact.__table__.columns if col.name in old_names]
        col_list = ", ".join(f'"{name}"' for name in keep)

        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("BEGIN IMMEDIATE")
        raw.execute(f'DROP TABLE IF EXISTS "{tmp_name}"')
        raw.execute(create_sql)
        raw.execute(f'INSERT INTO "{tmp_name}" ({col_list}) SELECT {col_list} FROM contacts')
        raw.execute("DROP TABLE contacts")
        raw.execute(f'ALTER TABLE "{tmp_name}" RENAME TO contacts')
        for index in Contact.__table__.indexes:
            raw.execute(str(CreateIndex(index).compile(engine)))
        raw.execute("COMMIT")
        raw.execute("PRAGMA foreign_keys=ON")

        broken = raw.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            logger.warning("Contacts rebuild left FK issues: %s", broken[:5])
        else:
            logger.info("Contacts rebuilt (mobile optional). Backup: %s", backup)
        return True
    except Exception:
        try:
            raw.execute("ROLLBACK")
        except Exception:
            pass
        logger.exception("Contacts rebuild failed; original table left untouched")
        return False
    finally:
        raw.close()


def ensure_sqlite_columns(engine) -> None:
    """Add missing columns on existing SQLite DBs (create_all does not ALTER)."""
    from sqlalchemy import text, inspect

    rebuild_contacts_for_phonebook(engine)

    try:
        insp = inspect(engine)
    except Exception:
        return

    def existing_cols(table: str):
        try:
            return {c["name"] for c in insp.get_columns(table)}
        except Exception:
            return set()

    alters = []
    # contacts: تلفن داخلی و فکس (دفترچه تلفن)
    if "contacts" in insp.get_table_names():
        cols = existing_cols("contacts")
        mapping = {
            "extension": "VARCHAR(20)",
            "fax": "VARCHAR(20)",
        }
        for col, typ in mapping.items():
            if col not in cols:
                alters.append(f"ALTER TABLE contacts ADD COLUMN {col} {typ}")

    # contact_profiles extra fields
    if "contact_profiles" in insp.get_table_names():
        cols = existing_cols("contact_profiles")
        mapping = {
            "birth_date": "DATETIME",
            "gender": "VARCHAR(20)",
            "education": "VARCHAR(100)",
            "appointment_date": "DATETIME",
        }
        for col, typ in mapping.items():
            if col not in cols:
                alters.append(f"ALTER TABLE contact_profiles ADD COLUMN {col} {typ}")

    # messages: گزارش تحویل پیامک
    if "messages" in insp.get_table_names():
        cols = existing_cols("messages")
        mapping = {
            "delivery_status": "VARCHAR(20)",
            "delivery_code": "INTEGER",
        }
        for col, typ in mapping.items():
            if col not in cols:
                alters.append(f"ALTER TABLE messages ADD COLUMN {col} {typ}")

    # events: مالک برنامه و میزبان (دیتابیس‌های واردشده از نسخهٔ بخشداری)
    if "events" in insp.get_table_names():
        cols = existing_cols("events")
        mapping = {
            "official_id": "INTEGER",
            "host": "VARCHAR(200)",
        }
        for col, typ in mapping.items():
            if col not in cols:
                alters.append(f"ALTER TABLE events ADD COLUMN {col} {typ}")

    # decisions: نتیجهٔ حاصل‌شده از اجرای مصوبه
    if "decisions" in insp.get_table_names():
        cols = existing_cols("decisions")
        if "result" not in cols:
            alters.append("ALTER TABLE decisions ADD COLUMN result TEXT")

    if not alters:
        return

    with engine.begin() as conn:
        for stmt in alters:
            try:
                conn.execute(text(stmt))
                logger.info("Applied schema patch: %s", stmt)
            except Exception as e:
                logger.warning("Schema patch skipped (%s): %s", stmt, e)


def init_database(db_path: Path = None) -> sessionmaker:
    """Initialize database at the given path (or default/current user)"""
    if db_path is None:
        db_path = get_current_db_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(db_path, echo=settings.APP_DEBUG)
    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
    )

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns(engine)
    logger.info("Database initialized at %s", db_path)
    return SessionLocal


def get_db(db_path: Path = None) -> Session:
    """Get a database session for the given path (or current user context)"""
    if db_path is None:
        db_path = get_current_db_path()

    db_key = _db_key(db_path)
    with _session_factories_lock:
        factory = _session_factories.get(db_key)
        if factory is None:
            engine = get_engine(db_path, echo=settings.APP_DEBUG)
            factory = sessionmaker(
                autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
            )
            _session_factories[db_key] = factory
    return factory()


@contextmanager
def db_session(db_path: Path = None) -> Session:
    """Context manager for database session"""
    session = get_db(db_path)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_user_db_path(username: str) -> Path:
    """مسیر دیتابیس برای «همهٔ» کاربران — یک دیتابیس مشترک واحد.

    در فرمانداری جلسات فرماندار/معاونین/بخشداران باید در یک جای مشترک باشند
    تا (۱) منشی و مسئولین همان داده را ببینند و (۲) بررسی تداخل بین
    برنامهٔ مسئولین مختلف ممکن باشد. حالت shared شبکه‌ای هم به همین
    مسیر ختم می‌شود تا چند PC روی یک دیتابیس کار کنند.
    """
    return get_users_db_path()


def get_users_db_path() -> Path:
    """Path of the single shared database (users/roles/permissions + all data)."""
    if settings.STORAGE_MODE == "shared" and settings.SHARED_DB_PATH:
        return _resolve_shared_db_path(settings.SHARED_DB_PATH)
    return settings.DB_PATH


def get_user_files_dir(username: str) -> Path:
    """پوشهٔ فایل‌ها هم مشترک است؛ فایل هر جلسه/نامه متعلق به دفتر است نه شخص."""
    return settings.FILES_DIR


def _dispose_engine(db_path: Path) -> None:
    """Dispose cached engine and session factory for a path"""
    db_key = _db_key(db_path)

    with _session_factories_lock:
        _session_factories.pop(db_key, None)

    with _engines_lock:
        engine = _engines.pop(db_key, None)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                logger.exception("Failed to dispose engine for %s", db_key)


def reset_database(db_path: Path = None) -> None:
    """Reset database at the given path (or default)"""
    if db_path is None:
        db_path = get_current_db_path()

    _dispose_engine(db_path)

    # WAL/SHM sidecars must go too, otherwise the "fresh" database gets the
    # old write-ahead log replayed into it on the next open.
    for suffix in ("", "-wal", "-shm", "-journal"):
        target = Path(str(db_path) + suffix) if suffix else Path(db_path)
        if target.exists():
            try:
                target.unlink()
            except OSError as e:
                logger.warning("Could not delete database file %s: %s", target, e)

    init_database(db_path)
    logger.info("Database reset completed at %s", db_path)


def _mirror_owner_into_user_db(db_path: Path, username: str) -> None:
    """تضمین می‌کند دیتابیس اختصاصی کاربر، ردیف خودش را در جدول users دارد.

    دیتابیس اختصاصی فقط با schema ساخته می‌شد و جدول users آن خالی می‌ماند؛
    در نتیجه هر FK به users.id (یادداشت/تسک/رویداد و...) با خطای
    FOREIGN KEY constraint failed رد می‌شد و هیچ‌کدام ذخیره نمی‌شدند.

    در حالت shared، دیتابیس کاربر همان دیتابیس global است؛ در آن حالت کاری
    لازم نیست و نباید به ردیف اصلی دست زد. همچنین هش/نمک رمز عبور عمداً
    کپی نمی‌شود: احراز هویت فقط روی دیتابیس global انجام می‌شود و هر کپیِ
    از این مواد، یک هدف exfiltration تازه است (به‌خصوص روی share شبکه).
    """
    if _db_key(db_path) == _db_key(get_users_db_path()):
        return

    src = get_db(get_users_db_path())
    try:
        owner = src.query(User).filter(User.username == username).first()
        if owner is None:
            return
        snapshot = {
            "id": owner.id,
            "uuid": owner.uuid,
            "username": owner.username,
            "email": owner.email,
            "password_hash": "",
            "salt": "",
            "first_name": owner.first_name,
            "last_name": owner.last_name,
            "national_code": owner.national_code,
            "mobile": owner.mobile,
            "phone": owner.phone,
            "is_active": owner.is_active,
            "is_superuser": owner.is_superuser,
            "default_role": owner.default_role,
            "settings": owner.settings,
            "created_by": None,
        }
    finally:
        src.close()

    dst = get_db(db_path)
    try:
        existing = dst.query(User).filter(User.id == snapshot["id"]).first()
        if existing is None:
            existing = dst.query(User).filter(User.username == snapshot["username"]).first()
        if existing is None:
            dst.add(User(**snapshot))
        elif existing.password_hash or existing.salt:
            # Scrub credentials copied by older versions of this function.
            existing.password_hash = ""
            existing.salt = ""
        dst.commit()
    except Exception:
        dst.rollback()
        logger.exception("Failed to mirror owner row into %s", db_path)
    finally:
        dst.close()


def init_user_database(username: str):
    """Initialize database for a specific user and set user context"""
    db_path = get_user_db_path(username)
    files_dir = get_user_files_dir(username)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    set_current_user_context(username)
    session_factory = init_database(db_path)
    _mirror_owner_into_user_db(db_path, username)
    return session_factory


# Initialize default database on import (non-fatal)
try:
    init_database()
except Exception as e:
    logger.warning("Default database initialization deferred: %s", e)
