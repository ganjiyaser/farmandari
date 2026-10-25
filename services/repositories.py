from typing import Optional, List, Dict, Any, TypeVar, Generic, Type
from abc import ABC
from datetime import datetime, timedelta
import uuid
from sqlalchemy import func, or_, desc, select, text, case, cast, String
from sqlalchemy.orm import Session, joinedload, selectinload
import logging

from models.models import (
    Contact, Group, ContactGroup, ContactProfile, ContactFile,
    Message, AppSetting, Event, Note, Task,
    User, Role, Permission, user_permissions, role_permissions, user_roles,
    ContactStatus, MessageType, MessageDirection, MessageStatus, Gender,
    EventType, EventPriority, EventStatus, UserRole, PermissionName,
    Official, OfficialPosition, EventParticipant, ParticipantStatus,
    MeetingMinute, Decision, DecisionStatus, Letter, LetterDirection,
    LetterStatus, Holiday, LetterReferral, LetterAction, DecisionAction,
    OrgPost, Employee
)
from core.database import get_db, get_users_db_path

import jdatetime

logger = logging.getLogger(__name__)

T = TypeVar('T')


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards so user input can't widen a search."""
    return (
        str(term)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def like_pattern(term: str) -> str:
    return f"%{escape_like(term)}%"


class BaseRepository(Generic[T], ABC):
    # None -> resolve via current user context; subclasses may pin a fixed DB
    # (e.g. the global users DB) by setting this in __init__.
    db_path = None

    def __init__(self, model: Type[T]):
        self.model = model

    def _get_db(self) -> Session:
        return get_db(self.db_path)

    def get_by_id(self, id: int) -> Optional[T]:
        session = self._get_db()
        try:
            return session.query(self.model).filter(self.model.id == id).first()
        finally:
            session.close()
    
    def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        session = self._get_db()
        try:
            return session.query(self.model).offset(offset).limit(limit).all()
        finally:
            session.close()
    
    def count(self) -> int:
        session = self._get_db()
        try:
            return session.query(func.count(self.model.id)).scalar()
        finally:
            session.close()
    
    def create(self, **kwargs) -> T:
        # Auto-fill user_id for models that require it (Note, Task, Event)
        if getattr(self.model, "__name__", "") in ("Note", "Task", "Event") and "user_id" not in kwargs:
            # setting_repo is defined later in this module; resolve at call time
            uid = setting_repo.get_setting("current_user_id")
            if uid is None:
                # These columns are NOT NULL -- failing here used to be silent
                # (bare `except: pass`) and surfaced later as a bare
                # IntegrityError with no context.
                raise ValueError(
                    f"Cannot create {self.model.__name__}: no current user is set "
                    "(log in again, or pass user_id explicitly)."
                )
            kwargs["user_id"] = int(uid)
        session = self._get_db()
        try:
            obj = self.model(**kwargs)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return obj
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def update(self, id: int, **kwargs) -> Optional[T]:
        session = self._get_db()
        try:
            obj = session.query(self.model).filter(self.model.id == id).first()
            if obj:
                for key, value in kwargs.items():
                    setattr(obj, key, value)
                session.commit()
                session.refresh(obj)
            return obj
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def delete(self, id: int) -> bool:
        session = self._get_db()
        try:
            obj = session.query(self.model).filter(self.model.id == id).first()
            if obj:
                session.delete(obj)
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class ContactRepository(BaseRepository[Contact]):
    def __init__(self):
        super().__init__(Contact)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Contact]:
        session = self._get_db()
        try:
            return session.query(Contact).order_by(
                Contact.last_name, Contact.first_name
            ).offset(offset).limit(limit).all()
        except Exception:
            # خطای DB را نباید با «مخاطبی یافت نشد» اشتباه گرفت
            logger.exception("ContactRepository.get_all failed")
            return []
        finally:
            session.close()
    
    def bulk_create(self, contacts_data: List[Dict[str, Any]]) -> int:
        session = self._get_db()
        try:
            count = 0
            for data in contacts_data:
                obj = Contact(**data)
                session.add(obj)
                count += 1
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def search(self, query: str, limit: int = 50) -> List[Contact]:
        """جستجو در تمام فیلدهای مخاطب

        هر فیلدی که در فرم و جدول نمایش داده می‌شود پوشش داده می‌شود: نام، نام
        پدر، عنوان، سازمان، همهٔ شماره‌ها، کد ملی/پستی، موقعیت جغرافیایی، آدرس،
        تحصیلات، یادداشت، فیلدهای سفارشی، برچسب‌ها، تاریخ تولد، وضعیت و نام
        دسته‌بندی‌ها.
        """
        session = self._get_db()
        try:
            term = like_pattern(query)
            escape = "\\"
            status_label = case(
                (Contact.status == ContactStatus.ACTIVE, "فعال"),
                (Contact.status == ContactStatus.INACTIVE, "غیرفعال"),
                else_="مسدود",
            )
            fields = [
                Contact.first_name, Contact.last_name, Contact.father_name,
                Contact.position, Contact.organization,
                Contact.mobile, Contact.phone, Contact.fax, Contact.extension,
                Contact.national_code, Contact.postal_code,
                Contact.province, Contact.county, Contact.district,
                Contact.rural_district, Contact.village, Contact.address,
                Contact.education, Contact.field_of_study, Contact.notes,
                status_label,
                cast(Contact.birth_date, String),
            ]
            conditions = [f.ilike(term, escape=escape) for f in fields]

            # JSON: ستون‌ها با ensure_ascii ذخیره می‌شوند (فارسی → \uXXXX)، پس
            # LIKE روی خود ستون هیچ نتیجه‌ای نمی‌دهد. json_each کلید/مقدار را
            # به‌صورت متن واقعی برمی‌گرداند؛ روی NULL هم ردیف نمی‌سازد.
            conditions.append(self._json_contains(Contact.custom_fields, term, escape))
            conditions.append(self._json_contains(Contact.tags, term, escape))

            # نام دسته‌ها هم جستجو شود (ستون «دسته‌بندی» در جدول دیده می‌شود)
            group_matches = (
                select(Group.id)
                .join(ContactGroup, ContactGroup.group_id == Group.id)
                .where(
                    ContactGroup.contact_id == Contact.id,
                    Group.name.ilike(term, escape=escape),
                )
            )
            conditions.append(group_matches.exists())

            return session.query(Contact).filter(or_(*conditions)).limit(limit).all()
        finally:
            session.close()

    @staticmethod
    def _json_contains(column, term: str, escape: str):
        """شاخهٔ EXISTS روی json_each ستون JSON

        کلید و مقدار هر ورودی (و هر عضو آرایه مثل tags) را به‌صورت متن واقعی
        جستجو می‌کند؛ به‌جای مقایسهٔ مستقیم متنِ JSON که کاراکترهای غیراسکی
        را \\uXXXX می‌بیند. اگر ستون NULL یا JSON نامعتبر باشد ردیفی برنمی‌گردد
        (SQLite روی NULL خالی است).
        """
        values = func.json_each(column).table_valued("key", "value").alias(
            "je_" + column.key
        )
        return (
            select(values.c.value)
            .where(
                or_(
                    values.c.key.ilike(term, escape=escape),
                    values.c.value.ilike(term, escape=escape),
                )
            )
            .exists()
        )
    
    def get_by_mobile(self, mobile: str) -> Optional[Contact]:
        session = self._get_db()
        try:
            return session.query(Contact).filter(Contact.mobile == mobile).first()
        finally:
            session.close()
    
    def get_by_national_code(self, national_code: str) -> Optional[Contact]:
        session = self._get_db()
        try:
            return session.query(Contact).filter(Contact.national_code == national_code).first()
        finally:
            session.close()
    
    def get_by_group(self, group_id: int, limit: int = 5000) -> List[Contact]:
        session = self._get_db()
        try:
            return session.query(Contact).join(ContactGroup).filter(
                ContactGroup.group_id == group_id
            ).limit(limit).all()
        finally:
            session.close()

    def get_without_group(self, limit: int = 5000) -> List[Contact]:
        """مخاطبینی که در هیچ دسته‌ای قرار نگرفته‌اند"""
        session = self._get_db()
        try:
            members = session.query(ContactGroup.contact_id)
            return session.query(Contact).filter(
                ~Contact.id.in_(members)
            ).order_by(Contact.last_name, Contact.first_name).limit(limit).all()
        except Exception:
            logger.exception("ContactRepository.get_without_group failed")
            return []
        finally:
            session.close()

    def get_active(self, limit: int = 100, offset: int = 0) -> List[Contact]:
        session = self._get_db()
        try:
            return session.query(Contact).filter(
                Contact.status == ContactStatus.ACTIVE
            ).order_by(Contact.last_name, Contact.first_name).offset(offset).limit(limit).all()
        except Exception:
            # Falling back to an *unfiltered* query silently hands inactive /
            # blocked contacts to exports, reports and pickers. Keep the
            # fallback (an empty list would look like "no contacts at all") but
            # make the degradation visible in the log.
            logger.exception(
                "ContactRepository.get_active failed while filtering by status; "
                "returning unfiltered results"
            )
            try:
                return session.query(Contact).order_by(
                    Contact.last_name, Contact.first_name
                ).offset(offset).limit(limit).all()
            except Exception:
                logger.exception("ContactRepository.get_active fallback failed")
                return []
        finally:
            session.close()
    
    def get_with_profile(self, contact_id: int) -> Optional[Contact]:
        """Load the contact with its profile eagerly loaded — the returned
        instance is detached after the session closes, so lazy access to
        contact.profile would raise DetachedInstanceError."""
        session = self._get_db()
        try:
            return (
                session.query(Contact)
                .options(joinedload(Contact.profile))
                .filter(Contact.id == contact_id)
                .first()
            )
        finally:
            session.close()
    
    def get_statistics(self) -> Dict[str, int]:
        session = self._get_db()
        try:
            total = session.query(func.count(Contact.id)).scalar()
            active = session.query(func.count(Contact.id)).filter(Contact.status == ContactStatus.ACTIVE).scalar()
            inactive = session.query(func.count(Contact.id)).filter(Contact.status == ContactStatus.INACTIVE).scalar()
            by_position = dict(session.query(Contact.position, func.count(Contact.id)).group_by(Contact.position).all())
            by_district = dict(session.query(Contact.district, func.count(Contact.id)).filter(Contact.district != None).group_by(Contact.district).all())
            return {'total': total, 'active': active, 'inactive': inactive, 'by_position': by_position, 'by_district': by_district}
        finally:
            session.close()


class GroupRepository(BaseRepository[Group]):
    # دسته‌بندی‌های پیش‌فرض دفترچه تلفن (ادارات)
    DEFAULT_CATEGORIES = [
        "ادارات بخش",
        "ادارات شهرستان",
        "استانداری",
        "اداره کل‌های دستگاه‌های اجرایی",
    ]

    def __init__(self):
        super().__init__(Group)

    def ensure_default_categories(self) -> int:
        """دسته‌بندی‌های پیش‌فرض سازمانی را در صورت نبودِ هرکدام ایجاد می‌کند"""
        created = 0
        session = self._get_db()
        try:
            for order, name in enumerate(self.DEFAULT_CATEGORIES):
                exists = session.query(Group).filter(
                    Group.name == name, Group.parent_id == None
                ).first()
                if exists:
                    continue
                session.add(Group(
                    uuid=str(uuid.uuid4()),
                    name=name,
                    description="دسته‌بندی پیش‌فرض دفترچه تلفن",
                    is_system=True,
                    sort_order=order,
                ))
                created += 1
            if created:
                session.commit()
            return created
        except Exception:
            session.rollback()
            logger.exception("ensure_default_categories failed")
            return 0
        finally:
            session.close()

    def get_tree(self) -> List[Group]:
        session = self._get_db()
        try:
            return session.query(Group).filter(Group.parent_id == None).order_by(Group.sort_order, Group.name).all()
        finally:
            session.close()
    
    def get_children(self, parent_id: int) -> List[Group]:
        session = self._get_db()
        try:
            return session.query(Group).filter(Group.parent_id == parent_id).all()
        finally:
            session.close()
    
    def get_contact_count(self, group_id: int) -> int:
        session = self._get_db()
        try:
            return session.query(func.count(ContactGroup.contact_id)).filter(ContactGroup.group_id == group_id).scalar()
        finally:
            session.close()
    
    def get_with_counts(self) -> List[Dict[str, Any]]:
        session = self._get_db()
        try:
            groups = session.query(Group).order_by(Group.sort_order, Group.name).all()
            # One GROUP BY instead of one COUNT per group (N+1; called on load
            # of contacts, groups, reports and the SMS page).
            rows = (
                session.query(
                    ContactGroup.group_id, func.count(ContactGroup.contact_id)
                )
                .group_by(ContactGroup.group_id)
                .all()
            )
            counts = {gid: cnt for gid, cnt in rows}
            return [
                {'group': g, 'contact_count': counts.get(g.id, 0)}
                for g in groups
            ]
        finally:
            session.close()

    def search(self, query: str, limit: int = 50) -> List[Group]:
        session = self._get_db()
        try:
            term = like_pattern(query)
            return session.query(Group).filter(
                or_(Group.name.ilike(term, escape="\\"), Group.description.ilike(term, escape="\\"))
            ).order_by(Group.name).limit(limit).all()
        finally:
            session.close()


class ContactGroupRepository(BaseRepository[ContactGroup]):
    def __init__(self):
        super().__init__(ContactGroup)
    
    def add_contact_to_group(self, contact_id: int, group_id: int, assigned_by: str = None) -> ContactGroup:
        contact_id = int(contact_id)
        group_id = int(group_id)
        session = self._get_db()
        try:
            # Validate foreign keys exist
            if not session.query(Contact.id).filter(Contact.id == contact_id).first():
                raise ValueError(f"مخاطب با شناسه {contact_id} یافت نشد")
            if not session.query(Group.id).filter(Group.id == group_id).first():
                raise ValueError(f"گروه با شناسه {group_id} یافت نشد")

            existing = session.query(ContactGroup).filter(
                ContactGroup.contact_id == contact_id, ContactGroup.group_id == group_id
            ).first()
            if existing:
                return existing
            cg = ContactGroup(contact_id=contact_id, group_id=group_id, assigned_by=assigned_by)
            session.add(cg)
            session.commit()
            session.refresh(cg)
            return cg
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def remove_contact_from_group(self, contact_id: int, group_id: int) -> bool:
        session = self._get_db()
        try:
            cg = session.query(ContactGroup).filter(
                ContactGroup.contact_id == contact_id, ContactGroup.group_id == group_id
            ).first()
            if cg:
                session.delete(cg)
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_contact_groups(self, contact_id: int) -> List[Group]:
        session = self._get_db()
        try:
            return session.query(Group).join(ContactGroup).filter(ContactGroup.contact_id == contact_id).all()
        finally:
            session.close()

    def get_group_map(self, contact_ids: List[int]) -> Dict[int, List[tuple]]:
        """نقشهٔ contact_id -> [(group_id, group_name), ...] با یک کوئری"""
        result: Dict[int, List[tuple]] = {}
        if not contact_ids:
            return result
        session = self._get_db()
        try:
            rows = session.query(
                ContactGroup.contact_id, Group.id, Group.name
            ).join(Group, ContactGroup.group_id == Group.id).filter(
                ContactGroup.contact_id.in_(contact_ids)
            ).all()
            for contact_id, group_id, group_name in rows:
                result.setdefault(contact_id, []).append((group_id, group_name))
            return result
        except Exception:
            logger.exception("ContactGroupRepository.get_group_map failed")
            return result
        finally:
            session.close()


class ContactProfileRepository(BaseRepository[ContactProfile]):
    def __init__(self):
        super().__init__(ContactProfile)
    
    def get_by_contact(self, contact_id: int) -> Optional[ContactProfile]:
        session = self._get_db()
        try:
            return session.query(ContactProfile).filter(ContactProfile.contact_id == contact_id).first()
        finally:
            session.close()
    
    def create_or_update(self, contact_id: int, **kwargs) -> ContactProfile:
        session = self._get_db()
        try:
            profile = session.query(ContactProfile).filter(ContactProfile.contact_id == contact_id).first()
            if profile:
                for key, value in kwargs.items():
                    setattr(profile, key, value)
            else:
                profile = ContactProfile(contact_id=contact_id, **kwargs)
                session.add(profile)
            session.commit()
            session.refresh(profile)
            return profile
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class ContactFileRepository(BaseRepository[ContactFile]):
    def __init__(self):
        super().__init__(ContactFile)
    
    def get_by_contact(self, contact_id: int, category: str = None) -> List[ContactFile]:
        session = self._get_db()
        try:
            q = session.query(ContactFile).filter(ContactFile.contact_id == contact_id)
            if category:
                q = q.filter(ContactFile.file_category == category)
            return q.order_by(desc(ContactFile.created_at)).all()
        finally:
            session.close()
    
    def search_files(self, query: str, contact_id: int = None) -> List[ContactFile]:
        session = self._get_db()
        try:
            term = like_pattern(query)
            q = session.query(ContactFile).filter(
                or_(ContactFile.original_name.ilike(term, escape="\\"), ContactFile.description.ilike(term, escape="\\"),
                    ContactFile.letter_number.ilike(term, escape="\\"), ContactFile.letter_subject.ilike(term, escape="\\"))
            )
            if contact_id:
                q = q.filter(ContactFile.contact_id == contact_id)
            return q.order_by(desc(ContactFile.created_at)).limit(100).all()
        finally:
            session.close()
    
    def get_letters(self, contact_id: int = None, letter_type: str = None) -> List[ContactFile]:
        session = self._get_db()
        try:
            q = session.query(ContactFile).filter(ContactFile.file_category == 'letter')
            if contact_id:
                q = q.filter(ContactFile.contact_id == contact_id)
            if letter_type:
                q = q.filter(ContactFile.letter_type == letter_type)
            return q.order_by(desc(ContactFile.letter_date)).all()
        finally:
            session.close()


class MessageRepository(BaseRepository[Message]):
    def __init__(self):
        super().__init__(Message)
    
    def get_pending_messages(self, limit: int = 100) -> List[Message]:
        session = self._get_db()
        try:
            return session.query(Message).filter(
                Message.status == MessageStatus.PENDING, Message.direction == MessageDirection.OUTGOING
            ).order_by(Message.created_at).limit(limit).all()
        finally:
            session.close()
    
    def get_by_contact(self, contact_id: int, limit: int = 50) -> List[Message]:
        session = self._get_db()
        try:
            return session.query(Message).filter(Message.contact_id == contact_id).order_by(desc(Message.created_at)).limit(limit).all()
        finally:
            session.close()

    def count_by_contacts(self, contact_ids: List[int]) -> int:
        """شمارش پیامک‌های مجموعه‌ای از مخاطب‌ها (برای هشدار پیش از حذف)."""
        if not contact_ids:
            return 0
        session = self._get_db()
        try:
            return session.query(func.count(Message.id)).filter(
                Message.contact_id.in_(contact_ids)
            ).scalar() or 0
        finally:
            session.close()
    
    def get_all(self, limit: int = 100) -> List[Message]:
        session = self._get_db()
        try:
            return session.query(Message).order_by(desc(Message.created_at)).limit(limit).all()
        finally:
            session.close()

    def get_incoming(self, limit: int = 200, days: Optional[int] = None) -> List[Message]:
        """پیامک‌های دریافتی، جدیدترین اول (برای تب «پیام‌های دریافتی»)

        فیلتر تاریخ پیش‌فرض ندارد: ساعت مودم قابل اعتماد نیست و نباید
        پیامی به‌خاطر تاریخ اشتباه از فهرست پنهان شود.
        """
        session = self._get_db()
        try:
            stamp = func.coalesce(Message.received_at, Message.created_at)
            q = session.query(Message).filter(Message.direction == MessageDirection.INCOMING)
            if days:
                # created_at از func.now() (UTC) است؛ received_at محلی — utcnow
                # پنجره را کمی بازتر نگه می‌دارد و پیامی پنهان نمی‌شود.
                q = q.filter(stamp >= datetime.utcnow() - timedelta(days=days))
            return q.order_by(desc(stamp)).limit(limit).all()
        finally:
            session.close()

    def find_incoming_by_key(self, provider_message_id: str) -> Optional[Message]:
        """پیام دریافتی با شناسهٔ تکرار (برای جلوگیری از ثبت دوباره)"""
        session = self._get_db()
        try:
            return (
                session.query(Message)
                .filter(Message.provider_message_id == str(provider_message_id))
                .filter(Message.direction == MessageDirection.INCOMING)
                .first()
            )
        finally:
            session.close()
    
    def get_statistics(self) -> Dict[str, int]:
        session = self._get_db()
        try:
            # NOTE: `.count()` wraps the query in `SELECT count(*) FROM (...)`,
            # so an aggregate without GROUP BY always returns exactly one row
            # and `.count()` on it reported 1 for every status. Use `.scalar()`.
            def _count(status: MessageStatus) -> int:
                return (
                    session.query(func.count(Message.id))
                    .filter(Message.status == status)
                    .scalar()
                    or 0
                )

            total = session.query(func.count(Message.id)).scalar() or 0
            return {
                'total': total,
                'sent': _count(MessageStatus.SENT),
                'failed': _count(MessageStatus.FAILED),
                'pending': _count(MessageStatus.PENDING),
            }
        finally:
            session.close()

    # ---------- گزارش تحویل ----------

    def get_by_provider_id(self, provider_message_id: str, within_hours: int = 72) -> Optional[Message]:
        """جدیدترین پیامک ارسالی با شناسهٔ مرکز پیام (برای تطبیق +CDS)"""
        session = self._get_db()
        try:
            q = session.query(Message).filter(
                Message.provider_message_id == str(provider_message_id),
                Message.direction == MessageDirection.OUTGOING,
            )
            if within_hours:
                since = datetime.utcnow() - timedelta(hours=within_hours)
                q = q.filter(Message.created_at >= since)
            return q.order_by(desc(Message.created_at)).first()
        finally:
            session.close()

    def set_delivery(self, message_id: int, delivered: bool, code: int = None,
                     reason: str = "") -> Optional[Message]:
        """ثبت نتیجهٔ گزارش تحویل روی یک پیامک"""
        session = self._get_db()
        try:
            msg = session.query(Message).filter(Message.id == message_id).first()
            if msg is None:
                return None
            msg.delivery_status = "delivered" if delivered else "undelivered"
            msg.delivery_code = code
            if delivered:
                msg.status = MessageStatus.DELIVERED
                msg.delivered_at = datetime.now()
                msg.error_message = None
            else:
                msg.status = MessageStatus.FAILED
                msg.error_message = reason or "تحویل نشد"
            session.commit()
            session.refresh(msg)
            return msg
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_delivery_summary(self, days: int = 7) -> Dict[str, int]:
        """شمارش پیامک‌های ارسالی بر اساس وضعیت تحویل"""
        session = self._get_db()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            base = session.query(Message).filter(
                Message.direction == MessageDirection.OUTGOING,
                Message.created_at >= since,
            )
            delivered = base.filter(Message.delivery_status == "delivered").count()
            undelivered = base.filter(Message.delivery_status == "undelivered").count()
            waiting = base.filter(
                Message.delivery_status == None,  # noqa: E711
                Message.status.in_([MessageStatus.SENT, MessageStatus.PENDING]),
            ).count()
            return {'delivered': delivered, 'undelivered': undelivered,
                    'waiting': waiting, 'total': delivered + undelivered + waiting}
        finally:
            session.close()

    def get_by_delivery(self, delivery_status: str, days: int = 7, limit: int = 500) -> List[Message]:
        """پیامک‌های ارسالی با وضعیت تحویل مشخص ('delivered' یا 'undelivered')"""
        session = self._get_db()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            return session.query(Message).filter(
                Message.direction == MessageDirection.OUTGOING,
                Message.delivery_status == delivery_status,
                Message.created_at >= since,
            ).order_by(desc(Message.created_at)).limit(limit).all()
        finally:
            session.close()


class AppSettingRepository(BaseRepository[AppSetting]):
    # تنظیمات برنامه (و current_user_id) باید در DB سراسری ذخیره شوند، نه DB
    # کاربر جاری — وگرنه بعد از خروج/تعویض کاربر خوانده نمی‌شوند.
    def __init__(self):
        super().__init__(AppSetting)
        self.db_path = get_users_db_path()
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        session = self._get_db()
        try:
            setting = session.query(AppSetting).filter(AppSetting.key == key).first()
            return setting.value if setting else default
        finally:
            session.close()
    
    def set_setting(self, key: str, value: Any, description: str = None) -> AppSetting:
        session = self._get_db()
        try:
            setting = session.query(AppSetting).filter(AppSetting.key == key).first()
            if setting:
                setting.value = value
            else:
                setting = AppSetting(key=key, value=value, description=description)
                session.add(setting)
            session.commit()
            session.refresh(setting)
            return setting
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class CalendarRepository(BaseRepository[Event]):
    def __init__(self):
        super().__init__(Event)
    
    def get_by_date(self, date_str: str) -> List[Event]:
        session = self._get_db()
        try:
            return session.query(Event).filter(Event.event_date == date_str).order_by(Event.event_time).all()
        finally:
            session.close()
    
    def get_by_month(self, year: int, month: int) -> List[Event]:
        session = self._get_db()
        try:
            prefix = f"{year:04d}/{month:02d}"
            return session.query(Event).filter(Event.event_date.like(f"{prefix}%")).order_by(Event.event_date, Event.event_time).all()
        finally:
            session.close()
    
    def get_range(self, start_date: str, end_date: str) -> List[Event]:
        """جلسات یک بازهٔ تاریخ (رشته‌های شمسی با مقایسهٔ متنی مرتب‌سازی می‌شوند)."""
        session = self._get_db()
        try:
            return (
                session.query(Event)
                .filter(
                    Event.event_date >= start_date,
                    Event.event_date <= end_date,
                    Event.status != EventStatus.CANCELLED,
                )
                .order_by(Event.event_date, Event.event_time)
                .all()
            )
        finally:
            session.close()

    def get_by_year(self, year: int) -> List[Event]:
        session = self._get_db()
        try:
            return (
                session.query(Event)
                .filter(Event.event_date.like(f"{year:04d}/%"))
                .order_by(Event.event_date, Event.event_time)
                .all()
            )
        finally:
            session.close()

    def get_upcoming(self, days: int = 7) -> List[Event]:
        session = self._get_db()
        try:
            import jdatetime
            today = jdatetime.date.today()
            # Single IN() query instead of one query per day (7-30 round trips
            # on every reminder tick and page load).
            date_strs = [
                (today + jdatetime.timedelta(days=i)).strftime("%Y/%m/%d")
                for i in range(max(int(days), 1))
            ]
            return (
                session.query(Event)
                .filter(
                    Event.event_date.in_(date_strs),
                    Event.status != EventStatus.CANCELLED,
                )
                .order_by(Event.event_date, Event.event_time)
                .all()
            )
        finally:
            session.close()
    
    def get_pending_reminders(self) -> List[Event]:
        session = self._get_db()
        try:
            import jdatetime
            now = jdatetime.datetime.now()
            today_str = now.strftime("%Y/%m/%d")
            current_time = now.strftime("%H:%M")
            return session.query(Event).filter(
                Event.reminder_enabled == True,
                Event.reminder_sent == False,
                Event.status.in_([EventStatus.PENDING, EventStatus.CONFIRMED]),
                Event.event_date >= today_str
            ).all()
        finally:
            session.close()
    
    def should_remind(self, event: Event) -> bool:
        if not event.reminder_enabled or event.reminder_sent:
            return False
        # حالت ارسال پیامک یادآوری توسط کاربر در زمان ثبت جلسه انتخاب می‌شود
        custom = event.custom_fields or {}
        mode = custom.get("reminder_mode") or "before"
        if mode in ("off", "manual"):
            return False
        try:
            import jdatetime
            now = jdatetime.datetime.now()
            today_str = now.strftime("%Y/%m/%d")

            if mode == "fixed":
                # ساعت ثابت در روز جلسه؛ پنجرهٔ ۵ دقیقه‌ای تا ارسال تا اگر
                # برنامه در آن لحظه باز نبود، پس از باز شدن هم ارسال انجام شود
                if event.event_date != today_str:
                    return False
                fixed = str(custom.get("reminder_fixed_time") or "08:00")
                try:
                    fixed_dt = jdatetime.datetime.strptime(
                        f"{today_str} {fixed}", "%Y/%m/%d %H:%M"
                    )
                except ValueError:
                    logger.warning(
                        "Skipping reminder for event %s: unparsable fixed time %r",
                        event.id, fixed,
                    )
                    return False
                return 0 <= (now - fixed_dt).total_seconds() <= 300

            event_datetime = jdatetime.datetime.strptime(
                f"{event.event_date} {event.event_time or '00:00'}", "%Y/%m/%d %H:%M"
            )
            diff = event_datetime - now
            diff_minutes = diff.total_seconds() / 60
            return 0 <= diff_minutes <= (event.reminder_minutes or 30)
        except Exception:
            # Previously returned False silently, so a malformed/legacy
            # event_time (e.g. "HH:MM:SS") meant the reminder *never* fired and
            # nothing ever hinted why.
            logger.warning(
                "Skipping reminder for event %s: unparsable date/time %r/%r",
                event.id, event.event_date, event.event_time,
            )
            return False

    def mark_reminder_sent(self, event_id: int) -> bool:
        session = self._get_db()
        try:
            event = session.query(Event).filter(Event.id == event_id).first()
            if event:
                event.reminder_sent = True
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            logger.exception("Could not mark reminder sent for event %s", event_id)
            return False
        finally:
            # Every other method in this file closes its session; this one ran
            # on every reminder tick and leaked a connection each time.
            session.close()

    def search(self, query: str) -> List[Event]:
        session = self._get_db()
        try:
            term = like_pattern(query)
            return session.query(Event).filter(
                or_(Event.title.ilike(term, escape="\\"), Event.description.ilike(term, escape="\\"))
            ).order_by(Event.event_date.desc()).limit(20).all()
        finally:
            session.close()
    
    def get_statistics(self) -> Dict[str, int]:
        session = self._get_db()
        try:
            import jdatetime
            today = jdatetime.date.today().strftime("%Y/%m/%d")
            total = session.query(func.count(Event.id)).scalar()
            pending = session.query(func.count(Event.id)).filter(Event.status == EventStatus.PENDING).scalar()
            confirmed = session.query(func.count(Event.id)).filter(Event.status == EventStatus.CONFIRMED).scalar()
            completed = session.query(func.count(Event.id)).filter(Event.status == EventStatus.COMPLETED).scalar()
            today_count = session.query(func.count(Event.id)).filter(Event.event_date == today).scalar()
            return {'total': total, 'pending': pending, 'confirmed': confirmed,
                    'completed': completed, 'today': today_count}
        finally:
            session.close()


class NoteRepository(BaseRepository[Note]):
    def __init__(self):
        super().__init__(Note)

    def get_all(self, limit: int = 100, include_archived: bool = False) -> List[Note]:
        session = self._get_db()
        try:
            q = session.query(Note)
            if not include_archived:
                q = q.filter(Note.is_archived == False)
            return q.order_by(Note.is_pinned.desc(), Note.updated_at.desc()).limit(limit).all()
        finally:
            session.close()

    def search(self, query: str) -> List[Note]:
        session = self._get_db()
        try:
            term = like_pattern(query)
            return session.query(Note).filter(
                Note.is_archived == False,
                or_(Note.title.ilike(term, escape="\\"), Note.content.ilike(term, escape="\\"))
            ).order_by(Note.is_pinned.desc(), Note.updated_at.desc()).all()
        finally:
            session.close()

    def toggle_pin(self, note_id: int):
        session = self._get_db()
        try:
            note = session.get(Note, note_id)
            if note:
                note.is_pinned = not note.is_pinned
                session.commit()
        finally:
            session.close()

    def archive(self, note_id: int):
        session = self._get_db()
        try:
            note = session.get(Note, note_id)
            if note:
                note.is_archived = True
                session.commit()
        finally:
            session.close()


class TaskRepository(BaseRepository[Task]):
    def __init__(self):
        super().__init__(Task)

    def get_all(self, limit: int = 200) -> List[Task]:
        session = self._get_db()
        try:
            return session.query(Task).order_by(
                Task.is_done.asc(),
                Task.created_at.desc()
            ).limit(limit).all()
        finally:
            session.close()

    def get_today(self) -> List[Task]:
        import jdatetime
        session = self._get_db()
        try:
            today = jdatetime.date.today().strftime("%Y/%m/%d")
            return session.query(Task).filter(
                Task.due_date == today
            ).order_by(Task.is_done.asc(), Task.created_at.desc()).all()
        finally:
            session.close()

    def get_pending(self) -> List[Task]:
        session = self._get_db()
        try:
            return session.query(Task).filter(
                Task.is_done == False
            ).order_by(Task.created_at.desc()).all()
        finally:
            session.close()

    def toggle_done(self, task_id: int):
        session = self._get_db()
        try:
            task = session.get(Task, task_id)
            if task:
                task.is_done = not task.is_done
                session.commit()
        finally:
            session.close()

    def get_statistics(self) -> dict:
        session = self._get_db()
        try:
            total = session.query(Task).count()
            done = session.query(Task).filter(Task.is_done == True).count()
            pending = total - done
            return {"total": total, "done": done, "pending": pending}
        finally:
            session.close()


class PermissionRepository(BaseRepository[Permission]):
    def __init__(self):
        super().__init__(Permission)
        self.db_path = get_users_db_path()

    def get_by_name(self, name: PermissionName) -> Optional[Permission]:
        session = self._get_db()
        try:
            return session.query(Permission).filter(Permission.name == name).first()
        finally:
            session.close()

    def get_all(self) -> List[Permission]:
        session = self._get_db()
        try:
            ids = self._readable_ids(session)
            if not ids:
                return []
            return (
                session.query(Permission)
                .filter(Permission.id.in_(ids))
                .order_by(Permission.category, Permission.label)
                .all()
            )
        finally:
            session.close()

    @staticmethod
    def _readable_ids(session) -> List[int]:
        """ids of permission rows the Enum column can actually decode.

        The `permissions.name` column is an Enum of PermissionName, which
        SQLAlchemy persists as the member *name* (`FILE_UPLOAD`). Older builds
        wrote the member *value* (`file_upload`); reading such a row raises
        LookupError and takes down every screen that lists permissions. Raw
        SQL here avoids touching the typed column at all.
        """
        valid = {m.name for m in PermissionName}
        rows = session.execute(text("SELECT id, name FROM permissions")).all()
        return [rid for rid, name in rows if name in valid]

    def get_by_category(self, category: str) -> List[Permission]:
        session = self._get_db()
        try:
            ids = self._readable_ids(session)
            if not ids:
                return []
            return (
                session.query(Permission)
                .filter(Permission.category == category)
                .filter(Permission.id.in_(ids))
                .all()
            )
        finally:
            session.close()

    @staticmethod
    def _normalize_legacy_permission_names(session) -> int:
        """Fold `permissionname.value` rows back into `permissionname.name`.

        Runs at startup with raw SQL so the broken rows are never handed to
        the ORM. Rows are either renamed in place, merged into their canonical
        counterpart (grant references repointed) or dropped when no enum member
        can represent them. Returns the number of rows touched.
        """
        by_value = {m.value: m.name for m in PermissionName}
        rows = session.execute(text("SELECT id, name FROM permissions")).all()
        if not rows:
            return 0

        valid = {m.name for m in PermissionName}
        canonical = {name: rid for rid, name in rows if name in valid}

        touched = 0
        for rid, name in rows:
            if name in valid:
                continue
            target = by_value.get(name)
            if target is None:
                # Not representable -- the ORM could never read it anyway.
                session.execute(
                    text("DELETE FROM permissions WHERE id = :id"), {"id": rid}
                )
                touched += 1
                continue
            keep = canonical.get(target)
            if keep is None:
                session.execute(
                    text("UPDATE permissions SET name = :name WHERE id = :id"),
                    {"name": target, "id": rid},
                )
                canonical[target] = rid
            else:
                for fk_table in ("role_permissions", "user_permissions"):
                    session.execute(
                        text(
                            f"UPDATE {fk_table} SET permission_id = :keep "
                            "WHERE permission_id = :rid"
                        ),
                        {"keep": keep, "rid": rid},
                    )
                session.execute(
                    text("DELETE FROM permissions WHERE id = :id"), {"id": rid}
                )
            touched += 1
        if touched:
            logger.info("Normalized %d legacy permission rows", touched)
        return touched

    def initialize_default_permissions(self):
        """Create all default permissions if they don't exist"""
        session = None
        try:
            session = self._get_db()
            self._normalize_legacy_permission_names(session)
            defaults = [
                # Pages
                (PermissionName.DASHBOARD, "داشبورد", "دسترسی به داشبورد", "page"),
                (PermissionName.CONTACTS, "مخاطبین", "دسترسی به مدیریت مخاطبین", "page"),
                (PermissionName.OFFICIALS, "مسئولین", "دسترسی به فهرست فرماندار، معاونین و بخشداران", "page"),
                (PermissionName.ORG_CHART, "چارت سازمانی", "دسترسی به چارت سازمانی و اطلاعات پرسنل", "page"),
                (PermissionName.CALENDAR, "تقویم و جلسات", "دسترسی به تقویم و جلسات", "page"),
                (PermissionName.DECISIONS, "صورت‌جلسات و مصوبات", "دسترسی به صورت‌جلسات و پیگیری مصوبات", "page"),
                (PermissionName.LETTERS, "دفتر اندیکاتور", "دسترسی به نامه‌های ورودی و صادره", "page"),
                (PermissionName.TASKS, "کارهای روزانه", "دسترسی به کارهای روزانه", "page"),
                (PermissionName.GROUPS, "گروه‌ها", "دسترسی به مدیریت گروه‌ها", "page"),
                (PermissionName.SMS, "پیامک", "دسترسی به ارسال و مشاهده پیامک", "page"),
                (PermissionName.FILES, "فایل‌ها و نامه‌ها", "دسترسی به فایل‌ها و نامه‌ها", "page"),
                (PermissionName.REPORTS, "گزارش‌ها", "دسترسی به گزارش‌ها", "page"),
                (PermissionName.SETTINGS, "تنظیمات", "دسترسی به تنظیمات", "page"),
                (PermissionName.USER_MANAGEMENT, "مدیریت کاربران", "دسترسی به مدیریت کاربران", "page"),
                # Contact actions
                (PermissionName.CONTACT_CREATE, "ایجاد مخاطب", "امکان ایجاد مخاطب جدید", "action"),
                (PermissionName.CONTACT_EDIT, "ویرایش مخاطب", "امکان ویرایش مخاطب", "action"),
                (PermissionName.CONTACT_DELETE, "حذف مخاطب", "امکان حذف مخاطب", "action"),
                (PermissionName.CONTACT_EXPORT, "خروجی مخاطبین", "امکان خروجی گرفتن از مخاطبین", "action"),
                (PermissionName.CONTACT_IMPORT, "ورودی مخاطبین", "امکان وارد کردن مخاطبین از اکسل", "action"),
                # Event actions
                (PermissionName.EVENT_CREATE, "ایجاد جلسه", "امکان ایجاد جلسه جدید", "action"),
                (PermissionName.EVENT_EDIT, "ویرایش جلسه", "امکان ویرایش جلسه", "action"),
                (PermissionName.EVENT_DELETE, "حذف جلسه", "امکان حذف جلسه", "action"),
                # Task actions
                (PermissionName.TASK_CREATE, "ایجاد کار", "امکان ایجاد کار روزانه", "action"),
                (PermissionName.TASK_EDIT, "ویرایش کار", "امکان ویرایش کار روزانه", "action"),
                (PermissionName.TASK_DELETE, "حذف کار", "امکان حذف کار روزانه", "action"),
                # Note actions
                (PermissionName.NOTE_CREATE, "ایجاد یادداشت", "امکان ایجاد یادداشت", "action"),
                (PermissionName.NOTE_EDIT, "ویرایش یادداشت", "امکان ویرایش یادداشت", "action"),
                (PermissionName.NOTE_DELETE, "حذف یادداشت", "امکان حذف یادداشت", "action"),
                # File actions
                (PermissionName.FILE_UPLOAD, "آپلود فایل", "امکان آپلود فایل", "action"),
                (PermissionName.FILE_DOWNLOAD, "دانلود فایل", "امکان دانلود فایل", "action"),
                (PermissionName.FILE_DELETE, "حذف فایل", "امکان حذف فایل", "action"),
                # SMS actions
                (PermissionName.SMS_SEND, "ارسال پیامک", "امکان ارسال پیامک", "action"),
                (PermissionName.SMS_VIEW, "مشاهده پیامک", "امکان مشاهده پیامک‌ها", "action"),
                # Group actions
                (PermissionName.GROUP_CREATE, "ایجاد گروه", "امکان ایجاد گروه", "action"),
                (PermissionName.GROUP_EDIT, "ویرایش گروه", "امکان ویرایش گروه", "action"),
                (PermissionName.GROUP_DELETE, "حذف گروه", "امکان حذف گروه", "action"),
                # User actions
                (PermissionName.USER_CREATE, "ایجاد کاربر", "امکان ایجاد کاربر جدید", "action"),
                (PermissionName.USER_EDIT, "ویرایش کاربر", "امکان ویرایش کاربر", "action"),
                (PermissionName.USER_DELETE, "حذف کاربر", "امکان حذف کاربر", "action"),
                (PermissionName.USER_CHANGE_PASSWORD, "تغییر رمز کاربر", "امکان تغییر رمز عبور کاربر", "action"),
                (PermissionName.USER_ASSIGN_ROLE, "اختصاص نقش", "امکان اختصاص نقش به کاربر", "action"),
                # Backup/Sync actions
                (PermissionName.BACKUP_CREATE, "پشتیبان‌گیری", "امکان ایجاد پشتیبان", "action"),
                (PermissionName.BACKUP_RESTORE, "بازیابی پشتیبان", "امکان بازیابی از پشتیبان", "action"),
                (PermissionName.SYNC_PUSH, "ارسال داده", "امکان ارسال داده به اشتراکی", "action"),
                (PermissionName.SYNC_PULL, "دریافت داده", "امکان دریافت داده از اشتراکی", "action"),
                # Settings actions
                (PermissionName.SETTINGS_VIEW, "مشاهده تنظیمات", "امکان مشاهده تنظیمات", "action"),
                (PermissionName.SETTINGS_EDIT, "ویرایش تنظیمات", "امکان ویرایش تنظیمات", "action"),
            ]
            
            for name, label, desc, category in defaults:
                existing = session.query(Permission).filter(Permission.name == name).first()
                if not existing:
                    perm = Permission(name=name, label=label, description=desc, category=category)
                    session.add(perm)
            
            session.commit()
        except Exception as e:
            logger.error("Could not initialize default permissions", exc_info=True)
        finally:
            if session is not None:
                session.close()


class RoleRepository(BaseRepository[Role]):
    def __init__(self):
        super().__init__(Role)
        self.db_path = get_users_db_path()

    def get_by_name(self, name: UserRole) -> Optional[Role]:
        session = self._get_db()
        try:
            return session.query(Role).filter(Role.name == name).first()
        finally:
            session.close()

    def get_all(self) -> List[Role]:
        session = self._get_db()
        try:
            return session.query(Role).order_by(Role.sort_order).all()
        finally:
            session.close()

    def initialize_default_roles(self):
        """Create default roles with permissions"""
        session = self._get_db()
        try:
            # Admin role - all permissions
            admin_role = session.query(Role).filter(Role.name == UserRole.ADMIN).first()
            if not admin_role:
                admin_role = Role(
                    name=UserRole.ADMIN,
                    label="مدیر",
                    description="دسترسی کامل به تمام بخش‌ها",
                    is_system=True,
                    sort_order=0
                )
                session.add(admin_role)
                session.flush()
                # Assign all permissions
                all_perms = session.query(Permission).all()
                admin_role.permissions = all_perms
            
            # District Governor role
            dg_role = session.query(Role).filter(Role.name == UserRole.DISTRICT_GOVERNOR).first()
            if not dg_role:
                dg_role = Role(
                    name=UserRole.DISTRICT_GOVERNOR,
                    label="بخشدار",
                    description="دسترسی به بخش‌های مدیریتی و نظارتی",
                    is_system=True,
                    sort_order=1
                )
                session.add(dg_role)
                session.flush()
                # Assign most permissions except user management
                perms = session.query(Permission).filter(
                    Permission.name.not_in([
                        PermissionName.USER_CREATE, PermissionName.USER_EDIT,
                        PermissionName.USER_DELETE, PermissionName.USER_ASSIGN_ROLE,
                        PermissionName.SETTINGS_EDIT, PermissionName.SYNC_PUSH,
                        PermissionName.SYNC_PULL, PermissionName.BACKUP_RESTORE
                    ])
                ).all()
                dg_role.permissions = perms
            
            # Office Manager role
            om_role = session.query(Role).filter(Role.name == UserRole.OFFICE_MANAGER).first()
            if not om_role:
                om_role = Role(
                    name=UserRole.OFFICE_MANAGER,
                    label="مسئول دفتر",
                    description="دسترسی به بخش‌های اداری و پشتیبانی",
                    is_system=True,
                    sort_order=2
                )
                session.add(om_role)
                session.flush()
                # Assign operational permissions
                perms = session.query(Permission).filter(
                    Permission.category.in_(["page", "action"]),
                    Permission.name.not_in([
                        PermissionName.USER_CREATE, PermissionName.USER_EDIT,
                        PermissionName.USER_DELETE, PermissionName.USER_ASSIGN_ROLE,
                        PermissionName.SETTINGS_EDIT, PermissionName.SYNC_PUSH,
                        PermissionName.SYNC_PULL, PermissionName.BACKUP_RESTORE,
                        PermissionName.BACKUP_CREATE
                    ])
                ).all()
                om_role.permissions = perms
            
            # Regular User role
            user_role = session.query(Role).filter(Role.name == UserRole.REGULAR_USER).first()
            if not user_role:
                user_role = Role(
                    name=UserRole.REGULAR_USER,
                    label="کاربر عادی",
                    description="دسترسی پایه به بخش‌های اصلی",
                    is_system=True,
                    sort_order=3
                )
                session.add(user_role)
                session.flush()
                # Assign basic permissions
                perms = session.query(Permission).filter(
                    Permission.name.in_([
                        PermissionName.DASHBOARD, PermissionName.CONTACTS,
                        PermissionName.ORG_CHART,
                        PermissionName.CALENDAR, PermissionName.TASKS,
                        PermissionName.GROUPS, PermissionName.SMS,
                        PermissionName.FILES, PermissionName.REPORTS,
                        PermissionName.SETTINGS,
                        PermissionName.CONTACT_CREATE, PermissionName.CONTACT_EDIT,
                        PermissionName.EVENT_CREATE, PermissionName.EVENT_EDIT,
                        PermissionName.TASK_CREATE, PermissionName.TASK_EDIT,
                        PermissionName.TASK_DELETE, PermissionName.NOTE_CREATE,
                        PermissionName.NOTE_EDIT, PermissionName.NOTE_DELETE,
                        PermissionName.FILE_UPLOAD, PermissionName.FILE_DOWNLOAD,
                        PermissionName.SMS_SEND, PermissionName.SMS_VIEW,
                        PermissionName.GROUP_CREATE, PermissionName.GROUP_EDIT
                    ])
                ).all()
                user_role.permissions = perms
            
            session.commit()
        except Exception as e:
            logger.error("Could not initialize default roles", exc_info=True)
        finally:
            session.close()


class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)
        # جدول users باید سراسری باشد؛ login قبل از شناختن کاربر نمی‌داند
        # در کدام DB کاربرِ-محصور بگردد.
        self.db_path = get_users_db_path()

    @staticmethod
    def _attach_direct_grants(session: Session, user: Optional[User]) -> None:
        """Prefill User.has_permission for a detached instance.

        get_by_username/get_by_id call expunge_all() before returning, so the
        association table can no longer be queried. Without this cache a
        permission check either raised DetachedInstanceError or (worse) was
        silently treated as "granted".
        """
        if user is None or user.id is None:
            return
        rows = session.execute(
            select(user_permissions.c.granted, Permission.name)
            .join(Permission, Permission.id == user_permissions.c.permission_id)
            .where(user_permissions.c.user_id == user.id)
        ).all()
        user.cache_direct_grants({name: bool(granted) for granted, name in rows})

    def get_by_username(self, username: str) -> Optional[User]:
        session = self._get_db()
        try:
            user = (
                session.query(User)
                .options(
                    joinedload(User.roles).joinedload(Role.permissions),
                    joinedload(User.direct_permissions),
                )
                .filter(User.username == username)
                .first()
            )
            if user:
                self._attach_direct_grants(session, user)
                session.expunge_all()
            return user
        finally:
            session.close()

    def get_by_id(self, id: int) -> Optional[User]:
        session = self._get_db()
        try:
            user = (
                session.query(User)
                .options(
                    joinedload(User.roles).joinedload(Role.permissions),
                    joinedload(User.direct_permissions),
                )
                .filter(User.id == id)
                .first()
            )
            if user:
                self._attach_direct_grants(session, user)
                session.expunge_all()
            return user
        finally:
            session.close()

    def get_by_email(self, email: str) -> Optional[User]:
        session = self._get_db()
        try:
            return session.query(User).filter(User.email == email).first()
        finally:
            session.close()

    def get_active_users(self) -> List[User]:
        session = self._get_db()
        try:
            return session.query(User).filter(User.is_active == True).order_by(User.username).all()
        finally:
            session.close()

    def get_all_users(self) -> List[User]:
        """Every account, active or not.

        The users page previously sourced its table and its status filter from
        get_active_users(), so "غیرفعال" could never match a row and
        deactivated accounts were invisible to admins.
        """
        session = self._get_db()
        try:
            return session.query(User).order_by(User.username).all()
        finally:
            session.close()

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password.
        Returns None on failure. Raises ValueError with Persian message for lock/inactive.
        """
        username = (username or "").strip()
        user = self.get_by_username(username)
        if not user:
            return None

        session = self._get_db()
        try:
            db_user = session.query(User).filter(User.id == user.id).first()
            if not db_user:
                return None

            # Unlock if lock expired
            if db_user.locked_until and db_user.locked_until > datetime.now():
                raise ValueError(
                    f"حساب موقتاً قفل است. تا {db_user.locked_until.strftime('%H:%M')} صبر کنید "
                    "یا با مدیر تماس بگیرید."
                )
            if db_user.locked_until and db_user.locked_until <= datetime.now():
                db_user.locked_until = None
                db_user.failed_login_attempts = 0

            if not db_user.is_active:
                raise ValueError("این حساب غیرفعال است")

            if db_user.check_password(password):
                # Transparently upgrade hashes written by older builds
                # (bare hex @ 100k iterations) to the current versioned format.
                if not str(db_user.password_hash or "").startswith("pbkdf2_sha256$"):
                    db_user.set_password(password)
                db_user.failed_login_attempts = 0
                db_user.locked_until = None
                db_user.last_login_at = datetime.now()
                session.commit()
                uid = db_user.id
                # خروج باید آبجکتِ eager-loaded باشد؛ وگرنه has_permission روی
                # آبجکت detached به DetachedInstanceError می‌خورد
                session.close()
                return self.get_by_id(uid)

            db_user.failed_login_attempts = (db_user.failed_login_attempts or 0) + 1
            if db_user.failed_login_attempts >= 5:
                from datetime import timedelta
                db_user.locked_until = datetime.now() + timedelta(minutes=15)
                session.commit()
                raise ValueError("به‌خاطر تلاش‌های ناموفق، حساب ۱۵ دقیقه قفل شد")
            session.commit()
            return None
        except ValueError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_user(self, username: str, password: str, first_name: str, last_name: str,
                   email: str = None, mobile: str = None, role: UserRole = UserRole.REGULAR_USER,
                   created_by: int = None, is_superuser: bool = False,
                   is_active: bool = True) -> User:
        """Create a new user with password"""
        session = self._get_db()
        try:
            user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                mobile=mobile,
                default_role=role,
                created_by=created_by,
                is_superuser=bool(is_superuser),
                is_active=bool(is_active),
            )
            user.set_password(password)
            session.add(user)
            session.flush()

            # Assign default role
            role_obj = session.query(Role).filter(Role.name == role).first()
            if role_obj:
                user.roles.append(role_obj)

            session.commit()
            uid = user.id
            session.close()
            return self.get_by_id(uid)
        finally:
            session.close()

    def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        session = self._get_db()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                # password attribute مدل نیست؛ بدون این، تغییر رمز بی‌صدا no-op می‌شد
                password = kwargs.pop("password", None)
                if password:
                    user.set_password(password)
                for key, value in kwargs.items():
                    if hasattr(user, key) and key not in ['id', 'uuid', 'password_hash', 'salt', 'created_at']:
                        setattr(user, key, value)
                session.commit()
                uid = user.id
                session.close()
                return self.get_by_id(uid)
            return None
        finally:
            session.close()

    def change_password(self, user_id: int, new_password: str) -> bool:
        session = self._get_db()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.set_password(new_password)
                session.commit()
                return True
            return False
        finally:
            session.close()

    def assign_role(self, user_id: int, role: UserRole) -> bool:
        session = self._get_db()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            role_obj = session.query(Role).filter(Role.name == role).first()
            if user and role_obj:
                # Remove existing roles
                user.roles = [role_obj]
                user.default_role = role
                session.commit()
                return True
            return False
        finally:
            session.close()

    def add_permission(self, user_id: int, perm_name: PermissionName, granted: bool = True) -> bool:
        session = self._get_db()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            perm = session.query(Permission).filter(Permission.name == perm_name).first()
            if user and perm:
                # Check if already exists
                existing = session.query(user_permissions).filter(
                    user_permissions.c.user_id == user_id,
                    user_permissions.c.permission_id == perm.id
                ).first()
                if existing:
                    # Update granted status
                    session.execute(
                        user_permissions.update().where(
                            user_permissions.c.user_id == user_id,
                            user_permissions.c.permission_id == perm.id
                        ).values(granted=granted)
                    )
                else:
                    session.execute(
                        user_permissions.insert().values(
                            user_id=user_id,
                            permission_id=perm.id,
                            granted=granted
                        )
                    )
                session.commit()
                return True
            return False
        finally:
            session.close()

    def remove_permission(self, user_id: int, perm_name: PermissionName) -> bool:
        session = self._get_db()
        try:
            perm = session.query(Permission).filter(Permission.name == perm_name).first()
            if perm:
                session.execute(
                    user_permissions.delete().where(
                        user_permissions.c.user_id == user_id,
                        user_permissions.c.permission_id == perm.id
                    )
                )
                session.commit()
                return True
            return False
        finally:
            session.close()

    def get_user_permissions(self, user_id: int) -> List[PermissionName]:
        """Get all effective permissions for a user (from roles and direct)"""
        session = self._get_db()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return []

            # Two flat queries instead of one `user_permissions.select()` per
            # direct permission plus lazy loads through roles (N+1; called for
            # every row of the users table on each keystroke).
            direct_rows = session.execute(
                select(Permission.name, user_permissions.c.granted)
                .join(Permission, Permission.id == user_permissions.c.permission_id)
                .where(user_permissions.c.user_id == user_id)
            ).all()
            role_rows = session.execute(
                select(Permission.name)
                .join(role_permissions, role_permissions.c.permission_id == Permission.id)
                .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
                .where(user_roles.c.user_id == user_id)
            ).all()

            perms = {name for (name,) in role_rows}
            for name, granted in direct_rows:
                if granted:
                    perms.add(name)
                else:
                    # A direct deny overrides the role grant.
                    perms.discard(name)
            return list(perms)
        finally:
            session.close()

    def initialize_admin_user(self, reset_password: bool = False):
        """Create default admin if missing. Optionally reset password to admin123."""
        try:
            session = self._get_db()
            try:
                admin = session.query(User).filter(User.username == "admin").first()
                if not admin:
                    admin = User(
                        username="admin",
                        first_name="مدیر",
                        last_name="سیستم",
                        email="admin@local",
                        is_superuser=True,
                        is_active=True,
                        default_role=UserRole.ADMIN,
                        settings={},
                    )
                    admin.set_password("admin123")
                    session.add(admin)
                    session.flush()
                    try:
                        admin_role = session.query(Role).filter(
                            Role.name == UserRole.ADMIN
                        ).first()
                        if admin_role:
                            admin.roles.append(admin_role)
                    except Exception as e:
                        logger.warning("Could not assign admin role: %s", e)
                    session.commit()
                    logger.info("Default admin account created")
                else:
                    # Reset the password ONLY when explicitly asked or when the
                    # account has no usable credentials. The old code also
                    # cleared failed_login_attempts / locked_until on *every*
                    # launch, which silently defeated the 15-minute lockout
                    # enforced in authenticate() -- restarting the app was
                    # enough to brute-force again.
                    changed = False
                    if reset_password or not admin.password_hash or not admin.salt:
                        admin.set_password("admin123")
                        changed = True
                        logger.warning(
                            "Admin password was reset to the built-in default; "
                            "change it immediately."
                        )
                    if changed:
                        session.commit()
            finally:
                session.close()
        except Exception as e:
            logger.error("Could not initialize admin user", exc_info=True)

    def reset_admin_password(self, new_password: str = "admin123") -> bool:
        """Force-reset admin password and unlock account. Returns True on success."""
        session = self._get_db()
        try:
            admin = session.query(User).filter(User.username == "admin").first()
            if not admin:
                self.initialize_admin_user(reset_password=True)
                return True
            admin.set_password(new_password)
            admin.is_active = True
            admin.is_superuser = True
            admin.failed_login_attempts = 0
            admin.locked_until = None
            session.commit()
            logger.info("Admin password was force-reset")
            return True
        except Exception as e:
            session.rollback()
            logger.warning("reset_admin_password failed: %s", e)
            return False
        finally:
            session.close()


contact_repo = ContactRepository()
group_repo = GroupRepository()
contact_group_repo = ContactGroupRepository()
profile_repo = ContactProfileRepository()
file_repo = ContactFileRepository()
message_repo = MessageRepository()
setting_repo = AppSettingRepository()
calendar_repo = CalendarRepository()
note_repo = NoteRepository()
task_repo = TaskRepository()
user_repo = UserRepository()
role_repo = RoleRepository()
permission_repo = PermissionRepository()

# Initialize default data - commented out to prevent import-time initialization
# These should be called explicitly after database is ready
# permission_repo.initialize_default_permissions()
# role_repo.initialize_default_roles()
# user_repo.initialize_admin_user()

class OfficialRepository(BaseRepository[Official]):
    def __init__(self):
        super().__init__(Official)
        self.db_path = get_users_db_path()

    def get_all(self, limit: int = 500, offset: int = 0) -> List[Official]:
        session = self._get_db()
        try:
            return (
                session.query(Official)
                .order_by(Official.sort_order, Official.position, Official.last_name)
                .offset(offset).limit(limit).all()
            )
        finally:
            session.close()

    def get_active(self, limit: int = 200) -> List[Official]:
        session = self._get_db()
        try:
            return (
                session.query(Official)
                .filter(Official.is_active == True)  # noqa: E712
                .order_by(Official.sort_order, Official.position, Official.last_name)
                .limit(limit).all()
            )
        finally:
            session.close()

    def get_by_position(self, position, active_only: bool = True) -> List[Official]:
        session = self._get_db()
        try:
            q = session.query(Official).filter(Official.position == position)
            if active_only:
                q = q.filter(Official.is_active == True)  # noqa: E712
            return q.order_by(Official.sort_order, Official.last_name).all()
        finally:
            session.close()

    def search(self, query: str, limit: int = 50) -> List[Official]:
        session = self._get_db()
        try:
            term = like_pattern(query)
            return (
                session.query(Official)
                .filter(or_(
                    Official.first_name.ilike(term, escape="\\"),
                    Official.last_name.ilike(term, escape="\\"),
                    Official.organization.ilike(term, escape="\\")))
                .limit(limit).all()
            )
        finally:
            session.close()


class EventParticipantRepository(BaseRepository[EventParticipant]):
    def __init__(self):
        super().__init__(EventParticipant)

    def get_by_event(self, event_id: int) -> List[EventParticipant]:
        session = self._get_db()
        try:
            return (
                session.query(EventParticipant)
                .filter(EventParticipant.event_id == event_id)
                .all()
            )
        finally:
            session.close()

    def replace_participants(self, event_id: int,
                             official_ids: List[int],
                             contact_ids: List[int]) -> bool:
        """دعوت‌شدگان جلسه را بازنویسی می‌کند؛ وضعیت قبلی دعوت‌شدگانِ ثابت حفظ می‌شود."""
        session = self._get_db()
        try:
            existing = (
                session.query(EventParticipant)
                .filter(EventParticipant.event_id == event_id)
                .all()
            )
            by_official = {p.official_id: p for p in existing if p.official_id}
            by_contact = {p.contact_id: p for p in existing if p.contact_id}

            keep_ids = []
            for oid in official_ids or []:
                row = by_official.get(oid)
                if row:
                    keep_ids.append(row.id)
                else:
                    row = EventParticipant(event_id=event_id, official_id=oid)
                    session.add(row)
                    session.flush()
                    keep_ids.append(row.id)
            for cid in contact_ids or []:
                row = by_contact.get(cid)
                if row:
                    keep_ids.append(row.id)
                else:
                    row = EventParticipant(event_id=event_id, contact_id=cid)
                    session.add(row)
                    session.flush()
                    keep_ids.append(row.id)

            for row in existing:
                if row.id not in keep_ids:
                    session.delete(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            logger.exception("replace_participants failed for event %s", event_id)
            return False
        finally:
            session.close()

    def set_status(self, participant_id: int, status) -> bool:
        session = self._get_db()
        try:
            row = session.query(EventParticipant).filter(
                EventParticipant.id == participant_id).first()
            if not row:
                return False
            row.status = status
            row.responded_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            logger.exception("set_status failed for participant %s", participant_id)
            return False
        finally:
            session.close()

    def count_by_official(self, year: int = None) -> dict:
        """آمار دعوت/حضور هر مسئول؛ خروجی: {official_id: {invited, attended}}"""
        session = self._get_db()
        try:
            q = (
                session.query(
                    EventParticipant.official_id,
                    EventParticipant.status,
                    func.count(EventParticipant.id),
                )
                .join(Event, EventParticipant.event_id == Event.id)
                .filter(EventParticipant.official_id != None)  # noqa: E711
            )
            if year is not None:
                q = q.filter(Event.event_date.like(f"{year:04d}/%"))
            result = {}
            for official_id, status, count in q.group_by(
                    EventParticipant.official_id, EventParticipant.status).all():
                entry = result.setdefault(official_id, {"invited": 0, "attended": 0})
                entry["invited"] += count
                if status == ParticipantStatus.ATTENDED:
                    entry["attended"] += count
            return result
        finally:
            session.close()


class MeetingMinuteRepository(BaseRepository[MeetingMinute]):
    def __init__(self):
        super().__init__(MeetingMinute)

    def get_by_event(self, event_id: int) -> Optional[MeetingMinute]:
        session = self._get_db()
        try:
            return (
                session.query(MeetingMinute)
                .filter(MeetingMinute.event_id == event_id)
                .first()
            )
        finally:
            session.close()

    def upsert(self, event_id: int, content: str, created_by: int = None) -> Optional[MeetingMinute]:
        session = self._get_db()
        try:
            row = (
                session.query(MeetingMinute)
                .filter(MeetingMinute.event_id == event_id)
                .first()
            )
            if row is None:
                row = MeetingMinute(event_id=event_id, created_by=created_by)
                session.add(row)
            row.content = content
            session.commit()
            session.refresh(row)
            return row
        except Exception:
            session.rollback()
            logger.exception("upsert minute failed for event %s", event_id)
            return None
        finally:
            session.close()


class DecisionRepository(BaseRepository[Decision]):
    def __init__(self):
        super().__init__(Decision)

    def get_detail(self, decision_id: int) -> Optional[Decision]:
        """مصوبه با روابط لازم برای پنجرهٔ پیگیری و گزارش چاپی."""
        session = self._get_db()
        try:
            return (
                session.query(Decision)
                .options(
                    joinedload(Decision.event),
                    joinedload(Decision.assignee_official),
                    joinedload(Decision.assignee_contact),
                    selectinload(Decision.actions),
                )
                .filter(Decision.id == decision_id)
                .first()
            )
        finally:
            session.close()

    def get_by_event(self, event_id: int) -> List[Decision]:
        session = self._get_db()
        try:
            return (
                session.query(Decision)
                .options(
                    joinedload(Decision.assignee_official),
                    joinedload(Decision.assignee_contact),
                    selectinload(Decision.actions),
                )
                .filter(Decision.event_id == event_id)
                .order_by(Decision.id)
                .all()
            )
        finally:
            session.close()

    def get_filtered(self, status=None, due_from: str = None, due_to: str = None,
                     limit: int = 500) -> List[Decision]:
        session = self._get_db()
        try:
            q = session.query(Decision).options(
                joinedload(Decision.event),
                joinedload(Decision.assignee_official),
                joinedload(Decision.assignee_contact),
                selectinload(Decision.actions),
            )
            if status is not None:
                q = q.filter(Decision.status == status)
            if due_from:
                q = q.filter(Decision.due_date >= due_from)
            if due_to:
                q = q.filter(Decision.due_date <= due_to)
            return q.order_by(Decision.due_date, Decision.id).limit(limit).all()
        finally:
            session.close()

    def get_open_with_event(self, limit: int = 500) -> List[Decision]:
        """مصوبات باز همراه با جلسهٔ مربوطه (برای صفحهٔ پیگیری)."""
        session = self._get_db()
        try:
            return (
                session.query(Decision)
                .options(
                    joinedload(Decision.event),
                    joinedload(Decision.assignee_official),
                    joinedload(Decision.assignee_contact),
                    selectinload(Decision.actions),
                )
                .filter(Decision.status.in_([DecisionStatus.OPEN, DecisionStatus.IN_PROGRESS]))
                .order_by(Decision.due_date, Decision.id)
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def get_statistics(self) -> dict:
        session = self._get_db()
        try:
            base = session.query(func.count(Decision.id))
            today = jdatetime.date.today().strftime("%Y/%m/%d")
            return {
                "total": base.scalar() or 0,
                "open": session.query(func.count(Decision.id))
                    .filter(Decision.status == DecisionStatus.OPEN).scalar() or 0,
                "in_progress": session.query(func.count(Decision.id))
                    .filter(Decision.status == DecisionStatus.IN_PROGRESS).scalar() or 0,
                "done": session.query(func.count(Decision.id))
                    .filter(Decision.status == DecisionStatus.DONE).scalar() or 0,
                "overdue": session.query(func.count(Decision.id))
                    .filter(Decision.status.in_([DecisionStatus.OPEN, DecisionStatus.IN_PROGRESS]),
                            Decision.due_date != None,  # noqa: E711
                            Decision.due_date < today).scalar() or 0,
            }
        except Exception:
            logger.exception("DecisionRepository.get_statistics failed")
            return {"total": 0, "open": 0, "in_progress": 0, "done": 0, "overdue": 0}
        finally:
            session.close()


class LetterRepository(BaseRepository[Letter]):
    def __init__(self):
        super().__init__(Letter)

    def get_filtered(self, direction=None, year: int = None, status=None,
                     query: str = None, limit: int = 300) -> List[Letter]:
        session = self._get_db()
        try:
            q = session.query(Letter).options(
                selectinload(Letter.referrals),
                selectinload(Letter.actions),
            )
            if direction is not None:
                q = q.filter(Letter.direction == direction)
            if year is not None:
                q = q.filter(Letter.indicator_year == year)
            if status is not None:
                q = q.filter(Letter.status == status)
            if query:
                term = like_pattern(query)
                q = q.filter(or_(
                    Letter.subject.ilike(term, escape="\\"),
                    Letter.sender.ilike(term, escape="\\"),
                    Letter.receiver.ilike(term, escape="\\"),
                    Letter.letter_number.ilike(term, escape="\\"),
                    Letter.referral_to.ilike(term, escape="\\")))
            return (
                q.order_by(desc(Letter.indicator_year), desc(Letter.indicator_number))
                .limit(limit).all()
            )
        finally:
            session.close()

    def next_indicator_number(self, direction, year: int) -> int:
        session = self._get_db()
        try:
            last = (
                session.query(func.max(Letter.indicator_number))
                .filter(Letter.direction == direction, Letter.indicator_year == year)
                .scalar()
            )
            return (last or 0) + 1
        finally:
            session.close()

    def create_numbered(self, **data) -> Letter:
        """ثبت نامه با شمارهٔ اندیکاتور خودکار؛ در برابر ثبت هم‌زمان مقاوم است."""
        direction = data.get("direction", LetterDirection.INCOMING)
        year = data.get("indicator_year") or jdatetime.date.today().year
        data["indicator_year"] = year
        for attempt in range(5):
            data["indicator_number"] = self.next_indicator_number(direction, year)
            session = self._get_db()
            try:
                row = Letter(**data)
                session.add(row)
                session.commit()
                session.refresh(row)
                return row
            except Exception as e:
                session.rollback()
                if "uq_letter_indicator" in str(e) and attempt < 4:
                    continue  # کاربر هم‌زمان دیگری شماره گرفت؛ دوباره
                logger.exception("create_numbered failed")
                raise
            finally:
                session.close()
        raise RuntimeError("could not allocate indicator number")


class LetterReferralRepository(BaseRepository[LetterReferral]):
    def __init__(self):
        super().__init__(LetterReferral)

    def get_by_letter(self, letter_id: int) -> List[LetterReferral]:
        session = self._get_db()
        try:
            return (
                session.query(LetterReferral)
                .filter(LetterReferral.letter_id == letter_id)
                .order_by(LetterReferral.referral_date, LetterReferral.id)
                .all()
            )
        finally:
            session.close()

    def add(self, letter_id: int, referred_to: str, note: str = None,
            referral_date: str = None, created_by: int = None) -> LetterReferral:
        return self.create(
            letter_id=letter_id, referred_to=referred_to, note=note,
            referral_date=referral_date, created_by=created_by,
        )


class LetterActionRepository(BaseRepository[LetterAction]):
    def __init__(self):
        super().__init__(LetterAction)

    def get_by_letter(self, letter_id: int) -> List[LetterAction]:
        session = self._get_db()
        try:
            return (
                session.query(LetterAction)
                .filter(LetterAction.letter_id == letter_id)
                .order_by(LetterAction.action_date, LetterAction.id)
                .all()
            )
        finally:
            session.close()

    def add(self, letter_id: int, action_text: str, result: str = None,
            action_date: str = None, created_by: int = None) -> LetterAction:
        return self.create(
            letter_id=letter_id, action_text=action_text, result=result,
            action_date=action_date, created_by=created_by,
        )


class DecisionActionRepository(BaseRepository[DecisionAction]):
    def __init__(self):
        super().__init__(DecisionAction)

    def get_by_decision(self, decision_id: int) -> List[DecisionAction]:
        session = self._get_db()
        try:
            return (
                session.query(DecisionAction)
                .filter(DecisionAction.decision_id == decision_id)
                .order_by(DecisionAction.action_date, DecisionAction.id)
                .all()
            )
        finally:
            session.close()

    def add(self, decision_id: int, action_text: str, result: str = None,
            action_date: str = None, created_by: int = None) -> DecisionAction:
        return self.create(
            decision_id=decision_id, action_text=action_text, result=result,
            action_date=action_date, created_by=created_by,
        )


class HolidayRepository(BaseRepository[Holiday]):
    def __init__(self):
        super().__init__(Holiday)
        self.db_path = get_users_db_path()

    def get_by_year(self, year: int) -> List[Holiday]:
        session = self._get_db()
        try:
            return (
                session.query(Holiday)
                .filter(Holiday.holiday_date.like(f"{year}/%"))
                .order_by(Holiday.holiday_date)
                .all()
            )
        finally:
            session.close()

    def get_by_date(self, date_str: str) -> Optional[Holiday]:
        session = self._get_db()
        try:
            return session.query(Holiday).filter(
                Holiday.holiday_date == date_str).first()
        finally:
            session.close()

    def is_holiday(self, date_str: str) -> bool:
        return self.get_by_date(date_str) is not None

    def upsert(self, date_str: str, title: str) -> bool:
        session = self._get_db()
        try:
            row = session.query(Holiday).filter(
                Holiday.holiday_date == date_str).first()
            if row:
                row.title = title
            else:
                session.add(Holiday(holiday_date=date_str, title=title))
            session.commit()
            return True
        except Exception:
            session.rollback()
            logger.exception("holiday upsert failed for %s", date_str)
            return False
        finally:
            session.close()


class OrgPostRepository(BaseRepository[OrgPost]):
    def __init__(self):
        super().__init__(OrgPost)

    def get_ordered(self) -> List[OrgPost]:
        session = self._get_db()
        try:
            return (
                session.query(OrgPost)
                .order_by(OrgPost.sort_order, OrgPost.id)
                .all()
            )
        finally:
            session.close()

    def find_by_title_parent(self, title: str, parent_id: Optional[int]) -> Optional[OrgPost]:
        session = self._get_db()
        try:
            q = session.query(OrgPost).filter(OrgPost.title == title)
            if parent_id is None:
                q = q.filter(OrgPost.parent_id == None)  # noqa: E711
            else:
                q = q.filter(OrgPost.parent_id == parent_id)
            return q.first()
        finally:
            session.close()


class EmployeeRepository(BaseRepository[Employee]):
    def __init__(self):
        super().__init__(Employee)

    def get_all_with_post(self, limit: int = 5000) -> List[Employee]:
        session = self._get_db()
        try:
            return (
                session.query(Employee)
                .options(joinedload(Employee.post))
                .order_by(Employee.last_name, Employee.first_name)
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def get_by_post(self, post_id: int) -> List[Employee]:
        session = self._get_db()
        try:
            return (
                session.query(Employee)
                .options(joinedload(Employee.post))
                .filter(Employee.post_id == post_id)
                .order_by(Employee.last_name, Employee.first_name)
                .all()
            )
        finally:
            session.close()

    def search(self, term: str, limit: int = 2000) -> List[Employee]:
        session = self._get_db()
        try:
            q = session.query(Employee).options(joinedload(Employee.post))
            term = (term or "").strip()
            if term:
                pattern = like_pattern(term)
                q = q.outerjoin(OrgPost, Employee.post_id == OrgPost.id).filter(or_(
                    Employee.first_name.ilike(pattern, escape="\\"),
                    Employee.last_name.ilike(pattern, escape="\\"),
                    Employee.personnel_code.ilike(pattern, escape="\\"),
                    Employee.national_code.ilike(pattern, escape="\\"),
                    Employee.workplace.ilike(pattern, escape="\\"),
                    OrgPost.title.ilike(pattern, escape="\\"),
                ))
            return q.order_by(Employee.last_name, Employee.first_name).limit(limit).all()
        finally:
            session.close()


official_repo = OfficialRepository()
participant_repo = EventParticipantRepository()
minute_repo = MeetingMinuteRepository()
decision_repo = DecisionRepository()
decision_action_repo = DecisionActionRepository()
letter_repo = LetterRepository()
letter_referral_repo = LetterReferralRepository()
letter_action_repo = LetterActionRepository()
holiday_repo = HolidayRepository()
org_post_repo = OrgPostRepository()
employee_repo = EmployeeRepository()
