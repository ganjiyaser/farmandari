from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    Enum, Boolean, JSON, Index, UniqueConstraint, CheckConstraint, Table,
    select
)
from sqlalchemy.orm import relationship, declarative_base, object_session
from sqlalchemy.sql import func
import hashlib
import hmac
import logging
import secrets
import uuid as uuid_lib

Base = declarative_base()

logger = logging.getLogger(__name__)

# OWASP 2023+ floor for PBKDF2-HMAC-SHA256 is 600k iterations (210k minimum).
# Hashes are stored with a version prefix so this can be raised again later
# without invalidating existing passwords.
PBKDF2_ITERATIONS = 600_000
# Iterations used by builds that stored a bare hex digest (no prefix).
LEGACY_PBKDF2_ITERATIONS = 100_000


def _pbkdf2_hex(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()


def _verify_hash(password: str, salt: str, stored: str) -> bool:
    """Compare ``password`` against a versioned or legacy (bare hex) hash."""
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        parts = stored.split("$")
        if len(parts) != 3:
            return False
        _, iterations, digest = parts
        try:
            iterations = int(iterations)
        except ValueError:
            return False
        return hmac.compare_digest(_pbkdf2_hex(password, salt, iterations), digest)
    # Legacy format: bare hex digest computed at 100k iterations.
    return hmac.compare_digest(
        _pbkdf2_hex(password, salt, LEGACY_PBKDF2_ITERATIONS), stored
    )



# Association table for User-Role many-to-many
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)


# Association table for Role-Permission many-to-many
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)


# Association table for User-Permission (direct permissions override)
user_permissions = Table(
    'user_permissions',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Column('granted', Boolean, default=True, nullable=False)  # True=grant, False=deny
)


class ContactStatus(PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class UserRole(PyEnum):
    ADMIN = "admin"
    DISTRICT_GOVERNOR = "district_governor"  # بخشدار
    OFFICE_MANAGER = "office_manager"  # مسئول دفتر
    REGULAR_USER = "regular_user"  # کاربر عادی


class PermissionName(PyEnum):
    # Pages
    DASHBOARD = "dashboard"
    CONTACTS = "contacts"
    OFFICIALS = "officials"
    ORG_CHART = "org_chart"
    CALENDAR = "calendar"
    DECISIONS = "decisions"
    LETTERS = "letters"
    TASKS = "tasks"
    GROUPS = "groups"
    SMS = "sms"
    FILES = "files"
    REPORTS = "reports"
    SETTINGS = "settings"
    USER_MANAGEMENT = "user_management"
    
    # Actions
    CONTACT_CREATE = "contact_create"
    CONTACT_EDIT = "contact_edit"
    CONTACT_DELETE = "contact_delete"
    CONTACT_EXPORT = "contact_export"
    CONTACT_IMPORT = "contact_import"
    
    EVENT_CREATE = "event_create"
    EVENT_EDIT = "event_edit"
    EVENT_DELETE = "event_delete"
    
    TASK_CREATE = "task_create"
    TASK_EDIT = "task_edit"
    TASK_DELETE = "task_delete"
    
    NOTE_CREATE = "note_create"
    NOTE_EDIT = "note_edit"
    NOTE_DELETE = "note_delete"
    
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"
    
    SMS_SEND = "sms_send"
    SMS_VIEW = "sms_view"
    
    GROUP_CREATE = "group_create"
    GROUP_EDIT = "group_edit"
    GROUP_DELETE = "group_delete"
    
    USER_CREATE = "user_create"
    USER_EDIT = "user_edit"
    USER_DELETE = "user_delete"
    USER_CHANGE_PASSWORD = "user_change_password"
    USER_ASSIGN_ROLE = "user_assign_role"
    
    BACKUP_CREATE = "backup_create"
    BACKUP_RESTORE = "backup_restore"
    SYNC_PUSH = "sync_push"
    SYNC_PULL = "sync_pull"
    
    SETTINGS_VIEW = "settings_view"
    SETTINGS_EDIT = "settings_edit"


class Gender(PyEnum):
    MALE = "male"
    FEMALE = "female"


class MessageType(PyEnum):
    SMS = "sms"
    FILE = "file"
    IMAGE = "image"
    DOCUMENT = "document"
    LETTER = "letter"


class MessageDirection(PyEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class MessageStatus(PyEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RECEIVED = "received"


class EventType(PyEnum):
    MEETING = "meeting"
    CONFERENCE = "conference"
    VISIT = "visit"  # بازدید / دیدار
    FOLLOWUP = "followup"
    REMINDER = "reminder"
    OTHER = "other"


class OfficialPosition(PyEnum):
    GOVERNOR = "governor"  # فرماندار
    DEPUTY_GOVERNOR = "deputy_governor"  # معاون فرماندار
    DISTRICT_GOVERNOR = "district_governor"  # بخشدار


OFFICIAL_POSITION_LABELS = {
    OfficialPosition.GOVERNOR: "فرماندار",
    OfficialPosition.DEPUTY_GOVERNOR: "معاون فرماندار",
    OfficialPosition.DISTRICT_GOVERNOR: "بخشدار",
}


class ParticipantStatus(PyEnum):
    INVITED = "invited"  # دعوت‌شده (بی‌پاسخ)
    ACCEPTED = "accepted"  # تایید کرد
    DECLINED = "declined"  # اعلام عدم حضور
    ATTENDED = "attended"  # حاضر
    ABSENT = "absent"  # غایب


class DecisionStatus(PyEnum):
    OPEN = "open"  # در جریان
    IN_PROGRESS = "in_progress"  # در حال اجرا
    DONE = "done"  # انجام شد
    CANCELLED = "cancelled"  # لغو شد


class LetterDirection(PyEnum):
    INCOMING = "incoming"  # وارده
    OUTGOING = "outgoing"  # صادره


class LetterStatus(PyEnum):
    REGISTERED = "registered"  # ثبت‌شده
    IN_PROGRESS = "in_progress"  # در حال پیگیری
    ANSWERED = "answered"  # پاسخ داده شد
    ARCHIVED = "archived"  # بایگانی


class EventPriority(PyEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventStatus(PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Permission(Base):
    """دسترسی‌ها"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Enum(PermissionName), unique=True, nullable=False, index=True)
    label = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # page, action, etc.
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class Role(Base):
    """نقش‌ها"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Enum(UserRole), unique=True, nullable=False, index=True)
    label = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)  # system roles can't be deleted
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    permissions = relationship("Permission", secondary=role_permissions, backref="roles")


class User(Base):
    """کاربران سیستم"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))
    
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(128), nullable=False)
    salt = Column(String(32), nullable=False)
    
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    national_code = Column(String(10), unique=True, nullable=True, index=True)
    
    mobile = Column(String(20), nullable=True)
    phone = Column(String(20), nullable=True)
    
    avatar_path = Column(String(500), nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    
    # User-specific settings (JSON)
    settings = Column(JSON, nullable=True, default=dict)
    
    # Default role (for quick reference)
    default_role = Column(Enum(UserRole), default=UserRole.REGULAR_USER, nullable=False)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    roles = relationship("Role", secondary=user_roles, backref="users")
    direct_permissions = relationship("Permission", secondary=user_permissions, backref="direct_users")
    # Self-referential one-to-many: the *-to-one side must carry remote_side,
    # otherwise `created_users` resolves as MANYTOONE and `creator` as a
    # collection -- the exact opposite of their names.
    creator = relationship("User", backref="created_users", remote_side=[id])
    
    # User-specific data
    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="user", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_users_active_name', 'is_active', 'username'),
    )
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
    
    def set_password(self, password: str) -> None:
        """Hash and set password"""
        self.salt = secrets.token_hex(16)
        self.password_hash = self._hash_password(password, self.salt)

    def check_password(self, password: str) -> bool:
        """Verify password (constant-time compare, legacy hashes accepted)."""
        if not self.password_hash or not self.salt:
            return False
        return _verify_hash(password, self.salt, str(self.password_hash))

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """PBKDF2-HMAC-SHA256 with a versioned prefix.

        Format: ``pbkdf2_sha256$<iterations>$<hex digest>``.
        Rows written by older builds store a bare hex digest computed with
        100_000 iterations; those are still accepted by check_password() so
        existing accounts keep working, and are re-hashed on the next
        set_password() call.
        """
        return (
            f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
            + _pbkdf2_hex(password, salt, PBKDF2_ITERATIONS)
        )

    def has_permission(self, perm_name: PermissionName) -> bool:
        """Check if user has permission (direct override, then roles).

        A direct row in ``user_permissions`` is authoritative: ``granted=False``
        denies the permission even when a role grants it. Previously any row was
        treated as a grant and every lazy-load failure silently granted access to
        admins (fail-open); failures are now logged and deny by default.
        """
        if self.is_superuser:
            return True

        direct = self._direct_permission_state(perm_name)
        if direct is not None:
            return direct

        try:
            for role in self.roles:
                for perm in role.permissions:
                    if perm.name == perm_name:
                        return True
        except Exception:
            logger.exception(
                "Could not evaluate role permissions for user %r (denying %s)",
                getattr(self, "username", self.id), perm_name,
            )
        return False

    def _direct_permission_state(self, perm_name: PermissionName) -> Optional[bool]:
        """Explicit direct-permission decision: True/False, or None if no row."""
        cached = self.__dict__.get("_direct_grants")
        if cached is not None:
            return cached.get(perm_name)

        session = object_session(self)
        if session is not None:
            row = session.execute(
                select(user_permissions.c.granted)
                .join(Permission, Permission.id == user_permissions.c.permission_id)
                .where(
                    user_permissions.c.user_id == self.id,
                    Permission.name == perm_name,
                )
            ).scalar_one_or_none()
            return None if row is None else bool(row)

        # Detached instance without a prefilled cache: fall back to the eagerly
        # loaded relationship (row exists => grant, matching the DB default).
        try:
            return any(p.name == perm_name for p in self.direct_permissions)
        except Exception:
            return None

    def cache_direct_grants(self, grants) -> None:
        """Prefill ``has_permission`` for a detached instance.

        Called by UserRepository right after eager-loading, so permission checks
        keep working after the session is closed (expunge_all) without touching
        the DB or raising DetachedInstanceError.
        """
        self.__dict__["_direct_grants"] = dict(grants)

    def get_accessible_pages(self) -> List[str]:
        """Get list of accessible page names"""
        pages = [
            PermissionName.DASHBOARD, PermissionName.CONTACTS,
            PermissionName.OFFICIALS, PermissionName.ORG_CHART,
            PermissionName.CALENDAR, PermissionName.TASKS, PermissionName.GROUPS,
            PermissionName.DECISIONS, PermissionName.LETTERS,
            PermissionName.SMS, PermissionName.FILES, PermissionName.REPORTS,
            PermissionName.SETTINGS, PermissionName.USER_MANAGEMENT
        ]
        return [p.value for p in pages if self.has_permission(p)]


class Contact(Base):
    """مخاطبین عمومی"""
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))
    
    first_name = Column(String(100), nullable=False, index=True)
    last_name = Column(String(100), nullable=False, index=True)
    # موبایل اختیاری است؛ ادارات و دفاتر ممکن است فقط تلفن ثابت/فکس داشته باشند
    mobile = Column(String(20), nullable=True, unique=True, index=True)
    phone = Column(String(20), nullable=True, index=True)
    extension = Column(String(20), nullable=True)  # تلفن داخلی
    fax = Column(String(20), nullable=True)  # تلفن نمابر
    national_code = Column(String(10), nullable=True, unique=True, index=True)
    
    gender = Column(Enum(Gender), nullable=True)
    birth_date = Column(DateTime, nullable=True)
    father_name = Column(String(100), nullable=True)
    
    education = Column(String(100), nullable=True)
    field_of_study = Column(String(100), nullable=True)
    
    province = Column(String(100), nullable=True)
    county = Column(String(100), nullable=True, index=True)
    district = Column(String(100), nullable=True, index=True)
    rural_district = Column(String(100), nullable=True, index=True)
    village = Column(String(100), nullable=True, index=True)
    address = Column(Text, nullable=True)
    postal_code = Column(String(10), nullable=True)
    
    position = Column(String(100), nullable=True, index=True)
    organization = Column(String(200), nullable=True)

    custom_fields = Column(JSON, nullable=True, default=dict)
    status = Column(Enum(ContactStatus), default=ContactStatus.ACTIVE, nullable=False)
    notes = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True, default=list)
    
    photo_path = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    last_contact_at = Column(DateTime, nullable=True)
    
    group_memberships = relationship("ContactGroup", back_populates="contact", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="contact", cascade="all, delete-orphan")
    files = relationship("ContactFile", back_populates="contact", cascade="all, delete-orphan")
    profile = relationship("ContactProfile", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_contacts_name', 'first_name', 'last_name'),
        Index('ix_contacts_location', 'county', 'district', 'rural_district', 'village'),
    )
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def display_name(self) -> str:
        parts = [self.full_name]
        if self.position:
            parts.append(f"({self.position})")
        return " ".join(parts)


class ContactProfile(Base):
    """پروفایل تکمیلی مخاطب"""
    __tablename__ = "contact_profiles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), unique=True, nullable=False)

    # فیلدهای پرکاربرد پروفایل (هم‌راستا با profile_dialog)
    birth_date = Column(DateTime, nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    education = Column(String(100), nullable=True)
    appointment_date = Column(DateTime, nullable=True)
    
    marital_status = Column(String(20), nullable=True)
    children_count = Column(Integer, default=0)
    
    employment_type = Column(String(50), nullable=True)
    salary_grade = Column(String(20), nullable=True)
    insurance_number = Column(String(20), nullable=True)
    
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    emergency_contact_relation = Column(String(50), nullable=True)
    
    admin_notes = Column(Text, nullable=True)
    performance_notes = Column(Text, nullable=True)
    custom_data = Column(JSON, nullable=True, default=dict)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    contact = relationship("Contact", back_populates="profile")


class Group(Base):
    """گروه‌بندی"""
    __tablename__ = "groups"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    color = Column(String(7), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # remote_side belongs on the many-to-one side; declaring it on `children`
    # made that attribute a single object and `parent` a collection.
    parent = relationship(
        "Group", backref="children", remote_side=[id], foreign_keys=[parent_id]
    )
    members = relationship("ContactGroup", back_populates="group", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('name', 'parent_id', name='uq_group_name_parent'),
    )


class ContactGroup(Base):
    __tablename__ = "contact_groups"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=func.now(), nullable=False)
    assigned_by = Column(String(100), nullable=True)
    
    contact = relationship("Contact", back_populates="group_memberships")
    group = relationship("Group", back_populates="members")
    
    __table_args__ = (
        UniqueConstraint('contact_id', 'group_id', name='uq_contact_group'),
    )


class ContactFile(Base):
    """فایل‌ها و نامه‌ها"""
    __tablename__ = "contact_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    file_name = Column(String(500), nullable=False)
    original_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_extension = Column(String(20), nullable=True)
    
    file_category = Column(String(50), nullable=True, index=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True, default=list)
    
    letter_number = Column(String(100), nullable=True, index=True)
    letter_date = Column(DateTime, nullable=True, index=True)
    letter_subject = Column(String(500), nullable=True)
    letter_type = Column(String(50), nullable=True)
    sender = Column(String(200), nullable=True)
    receiver = Column(String(200), nullable=True)
    
    uploaded_by = Column(String(100), nullable=True)
    is_confidential = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    contact = relationship("Contact", back_populates="files")


class Message(Base):
    """پیامک‌ها"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)

    message_type = Column(Enum(MessageType), default=MessageType.SMS, nullable=False)
    direction = Column(Enum(MessageDirection), default=MessageDirection.OUTGOING, nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.PENDING, nullable=False)
    
    content = Column(Text, nullable=True)
    subject = Column(String(500), nullable=True)
    
    sender_number = Column(String(20), nullable=True)
    recipient_number = Column(String(20), nullable=True)
    provider_message_id = Column(String(100), nullable=True, index=True)
    provider_response = Column(JSON, nullable=True)
    
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # وضعیت گزارش تحویل: NULL = منتظر تاییدیه، "delivered" = تحویل شد،
    # "undelivered" = تحویل نشد (علت در error_message)
    delivery_status = Column(String(20), nullable=True)
    delivery_code = Column(Integer, nullable=True)

    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    contact = relationship("Contact", back_populates="messages")

    __table_args__ = (
        # Hot paths: MessageRepository.get_statistics / get_pending_messages /
        # delivery reports filter on these; only uuid/contact were indexed before.
        Index("ix_messages_status_created", "status", "created_at"),
        Index("ix_messages_recipient", "recipient_number"),
        Index("ix_messages_created_at", "created_at"),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class Event(Base):
    """رویداد / جلسه"""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))
    
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    event_date = Column(String(10), nullable=False, index=True)
    event_time = Column(String(5), nullable=True)
    end_time = Column(String(5), nullable=True)
    
    location = Column(String(200), nullable=True)
    
    event_type = Column(Enum(EventType), default=EventType.MEETING, nullable=False)
    priority = Column(Enum(EventPriority), default=EventPriority.MEDIUM, nullable=False)
    status = Column(Enum(EventStatus), default=EventStatus.PENDING, nullable=False)
    
    reminder_minutes = Column(Integer, default=30)
    reminder_enabled = Column(Boolean, default=True, nullable=False)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    official_id = Column(Integer, ForeignKey("officials.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    host = Column(String(200), nullable=True)  # میزبان / مقام ملاقات (بازدید)

    custom_fields = Column(JSON, nullable=True, default=dict)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    contact = relationship("Contact", foreign_keys=[contact_id])
    official = relationship("Official", foreign_keys=[official_id])
    user = relationship("User", back_populates="events")
    participants = relationship("EventParticipant", back_populates="event", cascade="all, delete-orphan")
    minute = relationship("MeetingMinute", back_populates="event", uselist=False, cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="event", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_events_date_time', 'event_date', 'event_time'),
        Index('ix_events_user_date', 'user_id', 'event_date'),
    )


class Note(Base):
    """یادداشت شخصی"""
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, index=True)
    content = Column(Text, nullable=True)
    color = Column(String(7), default="#0969da")
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    user = relationship("User", back_populates="notes")
    
    __table_args__ = (
        Index('ix_notes_user_pinned', 'user_id', 'is_pinned'),
    )


class Task(Base):
    """کار روزانه"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_done = Column(Boolean, default=False, nullable=False)
    priority = Column(String(10), default="medium")
    due_date = Column(String(10), nullable=True)
    due_time = Column(String(5), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    user = relationship("User", back_populates="tasks")
    
    __table_args__ = (
        Index('ix_tasks_user_date', 'user_id', 'due_date'),
        Index('ix_tasks_user_done', 'user_id', 'is_done'),
    )

class Official(Base):
    """مسئولین فرمانداری (فرماندار، معاونین، بخشداران)"""
    __tablename__ = "officials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))

    first_name = Column(String(100), nullable=False, index=True)
    last_name = Column(String(100), nullable=False, index=True)

    position = Column(Enum(OfficialPosition), nullable=False, index=True)
    organization = Column(String(200), nullable=True)  # مثلاً «بخشداری مرکزی»

    mobile = Column(String(20), nullable=True, index=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)

    color = Column(String(7), nullable=True)  # رنگ برنامه در تقویم
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)

    notes = Column(Text, nullable=True)
    custom_fields = Column(JSON, nullable=True, default=dict)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    events = relationship("Event", back_populates="official", foreign_keys="Event.official_id")
    participations = relationship("EventParticipant", back_populates="official")

    __table_args__ = (
        Index('ix_officials_position_active', 'position', 'is_active'),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str:
        parts = [self.full_name]
        if self.organization:
            parts.append(f"({self.organization})")
        return " ".join(parts)


class EventParticipant(Base):
    """دعوت‌شدگان جلسه (مسئولین و مخاطبین)"""
    __tablename__ = "event_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)

    # یکی از دو مقدار زیر پر می‌شود
    official_id = Column(Integer, ForeignKey("officials.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)

    status = Column(Enum(ParticipantStatus), default=ParticipantStatus.INVITED, nullable=False)
    responded_at = Column(DateTime, nullable=True)
    note = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)

    event = relationship("Event", back_populates="participants")
    official = relationship("Official", back_populates="participations")
    contact = relationship("Contact")

    __table_args__ = (
        UniqueConstraint('event_id', 'official_id', name='uq_event_official'),
        UniqueConstraint('event_id', 'contact_id', name='uq_event_contact'),
        Index('ix_participants_event_status', 'event_id', 'status'),
    )

    @property
    def name(self) -> str:
        if self.official is not None:
            return self.official.display_name
        if self.contact is not None:
            return self.contact.display_name
        return "-"

    @property
    def mobile(self) -> Optional[str]:
        if self.official is not None:
            return self.official.mobile
        if self.contact is not None:
            return self.contact.mobile
        return None


class MeetingMinute(Base):
    """صورت‌جلسه"""
    __tablename__ = "meeting_minutes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    content = Column(Text, nullable=True)  # متن صورت‌جلسه
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    event = relationship("Event", back_populates="minute")


class Decision(Base):
    """مصوبهٔ جلسه و پیگیری آن"""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)

    content = Column(Text, nullable=False)

    # مسئول اجرا: یکی از مسئولین/مخاطبین سیستم یا متن آزاد
    assignee_official_id = Column(Integer, ForeignKey("officials.id", ondelete="SET NULL"), nullable=True, index=True)
    assignee_contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    assignee_text = Column(String(200), nullable=True)  # مثلاً «واحد مالی»

    due_date = Column(String(10), nullable=True, index=True)  # مهلت (شمسی YYYY/MM/DD)
    status = Column(Enum(DecisionStatus), default=DecisionStatus.OPEN, nullable=False, index=True)
    followup_note = Column(Text, nullable=True)
    result = Column(Text, nullable=True)  # نتیجهٔ حاصل‌شده
    completed_at = Column(DateTime, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    event = relationship("Event", back_populates="decisions")
    assignee_official = relationship("Official")
    assignee_contact = relationship("Contact")
    actions = relationship(
        "DecisionAction", back_populates="decision",
        cascade="all, delete-orphan", order_by="DecisionAction.id",
    )

    @property
    def assignee_name(self) -> str:
        if self.assignee_official is not None:
            return self.assignee_official.display_name
        if self.assignee_contact is not None:
            return self.assignee_contact.display_name
        return self.assignee_text or "-"


class Letter(Base):
    """دفتر اندیکاتور — نامه‌های ورودی و صادره"""
    __tablename__ = "letters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))

    direction = Column(Enum(LetterDirection), default=LetterDirection.INCOMING, nullable=False, index=True)

    # شمارهٔ اندیکاتور: خودکار، جداگانه برای هر جهت و هر سال شمسی
    indicator_number = Column(Integer, nullable=False, default=0)
    indicator_year = Column(Integer, nullable=False, index=True)

    letter_number = Column(String(50), nullable=True)  # شمارهٔ روی نامه
    letter_date = Column(String(10), nullable=True)  # تاریخ نامه (شمسی)
    subject = Column(String(500), nullable=False)

    sender = Column(String(200), nullable=True)  # فرستنده (وارده)
    receiver = Column(String(200), nullable=True)  # گیرنده (صادره)

    summary = Column(Text, nullable=True)
    referral_to = Column(String(200), nullable=True)  # ارجاع به واحد/شخص
    referral_note = Column(Text, nullable=True)

    status = Column(Enum(LetterStatus), default=LetterStatus.REGISTERED, nullable=False, index=True)
    file_path = Column(String(1000), nullable=True)  # اسکن/فایل نامه

    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    contact = relationship("Contact")
    event = relationship("Event")
    referrals = relationship(
        "LetterReferral", back_populates="letter",
        cascade="all, delete-orphan", order_by="LetterReferral.id",
    )
    actions = relationship(
        "LetterAction", back_populates="letter",
        cascade="all, delete-orphan", order_by="LetterAction.id",
    )

    __table_args__ = (
        UniqueConstraint('direction', 'indicator_year', 'indicator_number',
                         name='uq_letter_indicator'),
        Index('ix_letters_date', 'letter_date'),
    )


class LetterReferral(Base):
    """سابقهٔ ارجاع نامه به شخص یا واحد."""
    __tablename__ = "letter_referrals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    letter_id = Column(Integer, ForeignKey("letters.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    referred_to = Column(String(200), nullable=False)
    note = Column(Text, nullable=True)
    referral_date = Column(String(10), nullable=True, index=True)  # شمسی
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    letter = relationship("Letter", back_populates="referrals")


class LetterAction(Base):
    """اقدام انجام‌شده روی نامه و نتیجهٔ آن."""
    __tablename__ = "letter_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    letter_id = Column(Integer, ForeignKey("letters.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    action_date = Column(String(10), nullable=True, index=True)  # شمسی
    action_text = Column(Text, nullable=False)
    result = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    letter = relationship("Letter", back_populates="actions")


class DecisionAction(Base):
    """اقدام انجام‌شده برای اجرای مصوبه و نتیجهٔ آن."""
    __tablename__ = "decision_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(Integer, ForeignKey("decisions.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    action_date = Column(String(10), nullable=True, index=True)  # شمسی
    action_text = Column(Text, nullable=False)
    result = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    decision = relationship("Decision", back_populates="actions")


class Holiday(Base):
    """تعطیلات رسمی"""
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    holiday_date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY/MM/DD شمسی
    title = Column(String(200), nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)


class OrgPost(Base):
    """پست سازمانی در چارت سازمانی (مستقل از محل خدمت فعلی پرسنل)."""
    __tablename__ = "org_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True,
                  default=lambda: str(uuid_lib.uuid4()))

    title = Column(String(300), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("org_posts.id", ondelete="CASCADE"),
                       nullable=True, index=True)
    code = Column(String(50), nullable=True)  # کد پست سازمانی
    chart_key = Column(String(60), nullable=True, index=True)  # کلید ورود از فایل چارت
    category = Column(String(150), nullable=True)  # معاونت / بخشداری / ستاد ...
    approved_count = Column(Integer, default=1, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    parent = relationship("OrgPost", remote_side=[id], back_populates="children")
    children = relationship(
        "OrgPost", back_populates="parent", cascade="all, delete-orphan",
        order_by="OrgPost.sort_order, OrgPost.id",
    )
    employees = relationship("Employee", back_populates="post")

    __table_args__ = (
        Index('ix_org_posts_parent_order', 'parent_id', 'sort_order'),
    )


class Employee(Base):
    """پرسنل فرمانداری؛ پست سازمانی و محل خدمت فعلی جداگانه ثبت می‌شوند."""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True,
                  default=lambda: str(uuid_lib.uuid4()))

    personnel_code = Column(String(30), unique=True, nullable=True, index=True)
    national_code = Column(String(10), unique=True, nullable=True, index=True)
    first_name = Column(String(100), nullable=False, index=True)
    last_name = Column(String(100), nullable=False, index=True)
    father_name = Column(String(100), nullable=True)

    gender = Column(String(10), nullable=True)
    birth_date = Column(String(10), nullable=True)  # شمسی
    birth_place = Column(String(100), nullable=True)
    marital_status = Column(String(20), nullable=True)

    education_level = Column(String(100), nullable=True)
    field_of_study = Column(String(150), nullable=True)
    hire_date = Column(String(10), nullable=True)  # شمسی
    employment_type = Column(String(50), nullable=True)
    employment_status = Column(String(30), default="شاغل", nullable=True)

    post_id = Column(Integer, ForeignKey("org_posts.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    workplace = Column(String(300), nullable=True)  # محل خدمت فعلی (ممکن است با پست متفاوت باشد)

    mobile = Column(String(20), nullable=True, index=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(String(400), nullable=True)

    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    post = relationship("OrgPost", back_populates="employees")

    __table_args__ = (
        Index('ix_employees_post_active', 'post_id', 'is_active'),
        Index('ix_employees_name', 'last_name', 'first_name'),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self) -> str:
        parts = [self.full_name]
        if self.personnel_code:
            parts.append(f"({self.personnel_code})")
        return " ".join(parts)
