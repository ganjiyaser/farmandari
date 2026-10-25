from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import requests
import logging
import json
import re
import hashlib
import uuid as uuid_lib
from datetime import datetime
from core.config import settings
from core.database import get_db
from models.models import MessageStatus, MessageType, MessageDirection
from services.dlink_sms import router_pool
from services.repositories import message_repo, contact_repo, setting_repo
from services.sim_sms import ModemInfo, delivery_reason

logger = logging.getLogger(__name__)

# ارقام فارسی/عربی → انگلیسی
_DIGIT_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_mobile(raw: str) -> str:
    """شماره وارد‌شده را به قالب 09xxxxxxxxx تبدیل می‌کند"""
    if not raw:
        return ""
    text = str(raw).translate(_DIGIT_MAP)
    text = re.sub(r"[^\d+]", "", text)
    if text.startswith("+98"):
        text = "0" + text[3:]
    elif text.startswith("0098"):
        text = "0" + text[4:]
    elif text.startswith("98") and len(text) == 12:
        text = "0" + text[2:]
    elif text.startswith("9") and len(text) == 10:
        text = "0" + text
    return text


def is_valid_mobile(raw: str) -> bool:
    return bool(re.fullmatch(r"09\d{9}", normalize_mobile(raw)))


class SMSProviderType(Enum):
    KAVENEGAR = "kavenegar"
    MELIPAYAMAK = "melipayamak"
    CUSTOM = "custom"
    SIM_CARD = "sim_card"
    DLINK_ROUTER = "dlink_router"


@dataclass
class SMSResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    cost: Optional[float] = None
    parts: int = 1


class BaseSMSProvider(ABC):
    def __init__(self, api_key: str = "", sender_number: str = "", **kwargs):
        self.api_key = api_key
        self.sender_number = sender_number
        self.config = kwargs
    
    @abstractmethod
    def send_single(self, receptor: str, message: str, sender: str = None) -> SMSResult:
        pass
    
    @abstractmethod
    def send_bulk(self, receptors: List[str], message: str, sender: str = None) -> List[SMSResult]:
        pass
    
    @abstractmethod
    def get_balance(self) -> float:
        pass
    
    def _get_sender(self, sender: str = None) -> str:
        return sender or self.sender_number


class KavenegarProvider(BaseSMSProvider):
    BASE_URL = "https://api.kavenegar.com/v1"
    
    def send_single(self, receptor: str, message: str, sender: str = None) -> SMSResult:
        url = f"{self.BASE_URL}/{self.api_key}/sms/send.json"
        data = {"receptor": receptor, "message": message, "sender": self._get_sender(sender)}
        return self._request(url, data)
    
    def send_bulk(self, receptors: List[str], message: str, sender: str = None) -> List[SMSResult]:
        url = f"{self.BASE_URL}/{self.api_key}/sms/send.json"
        data = {"receptor": ",".join(receptors), "message": message, "sender": self._get_sender(sender)}
        result = self._request(url, data)
        # حتی در خطا هم به تعداد گیرندگان خروجی بده؛ فراخواننده‌ها نتایج را با
        # فهرست گیرندگان zip می‌کنند و کوتاه‌ماندن فهرست، ثبت شکست‌ها را می‌بُرد
        return [result] * len(receptors)
    
    def get_balance(self) -> float:
        url = f"{self.BASE_URL}/{self.api_key}/account/info.json"
        result = self._request(url, {})
        if result.success and result.raw_response:
            try:
                return float(result.raw_response.get('entries', {}).get('credit', 0))
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def _request(self, url: str, data: Dict) -> SMSResult:
        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get('return', {}).get('status') == 200:
                entries = result.get('entries', [])
                # account/info.json دیکشنری برمی‌گرداند و sms/send.json فهرست
                if isinstance(entries, dict):
                    return SMSResult(success=True, raw_response=result)
                if entries:
                    entry = entries[0]
                    return SMSResult(success=True, message_id=str(entry.get('messageid', '')),
                                     raw_response=result, cost=entry.get('cost', 0))
                return SMSResult(success=True, raw_response=result)
            return SMSResult(success=False, error=result.get('return', {}).get('message', 'Unknown error'))
        except Exception as e:
            return SMSResult(success=False, error=str(e))


class MelipayamakProvider(BaseSMSProvider):
    BASE_URL = "https://api.payamak-panel.com/post/Send.asmx"
    
    def send_single(self, receptor: str, message: str, sender: str = None) -> SMSResult:
        data = {"username": self.config.get('username', ''), "password": self.config.get('password', ''),
                "to": receptor, "from": self._get_sender(sender), "text": message, "isflash": "false"}
        return self._request("SendSimpleSMS", data)
    
    def send_bulk(self, receptors: List[str], message: str, sender: str = None) -> List[SMSResult]:
        data = {"username": self.config.get('username', ''), "password": self.config.get('password', ''),
                "to": ",".join(receptors), "from": self._get_sender(sender), "text": message, "isflash": "false"}
        result = self._request("SendSimpleSMS", data)
        # حتی در خطا هم به تعداد گیرندگان خروجی بده؛ فراخواننده‌ها zip می‌کنند
        return [result] * len(receptors)

    def get_balance(self) -> float:
        data = {"username": self.config.get('username', ''), "password": self.config.get('password', '')}
        result = self._request("GetCredit", data)
        if result.success and result.raw_response:
            try:
                return float(result.raw_response.get('response', 0) or 0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    # کدهای خطای REST ملipayamak: روی خطا، بدنهٔ پاسخ فقط یک کد عددی کوتاه است
    _ERRORS = {
        "1": "اتصال به بانک اطلاعاتی سرویس‌دهنده با مشکل مواجه شد",
        "2": "اعتبار کافی نیست",
        "3": "کاربر موردنظر فعال نیست",
        "4": "کاربر موردنظر مخفی است",
        "5": "نام کاربری یا رمز عبور اشتباه است",
        "6": "شماره گیرنده معتبر نیست",
        "7": "حداقل یک گیرنده لازم است",
        "8": "متن پیامک خالی است یا طول آن بیش از حد مجاز است",
        "9": "متن پیامک حاوی کلمات غیرمجاز است",
        "10": "خطای ناشناخته",
        "11": "ارسال از خط اشتراکی به این شماره مجاز نیست",
    }

    def _request(self, method: str, data: Dict) -> SMSResult:
        try:
            response = requests.post(f"{self.BASE_URL}/{method}", data=data, timeout=30)
            response.raise_for_status()
            body = (response.text or "").strip().strip('"')
            # پاسخ موفق، شناسهٔ بلند پیامک یا اعتبار است؛ کد خطا عدد ۱-۲ رقمی است
            if re.fullmatch(r"\d{1,2}", body) and body in self._ERRORS:
                return SMSResult(success=False, error=self._ERRORS[body],
                                 raw_response={'response': body})
            return SMSResult(success=True, message_id=body or None,
                             raw_response={'response': body})
        except Exception as e:
            return SMSResult(success=False, error=str(e))


class CustomSMSProvider(BaseSMSProvider):
    def __init__(self, api_key: str = "", sender_number: str = "", **kwargs):
        super().__init__(api_key, sender_number, **kwargs)
        self.api_url = kwargs.get('api_url', settings.SMS_API_URL)
        self.headers = kwargs.get('headers', {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'})
        self.payload_template = kwargs.get('payload_template', {'mobile': '{receptor}', 'message': '{message}', 'sender': '{sender}'})
    
    def send_single(self, receptor: str, message: str, sender: str = None) -> SMSResult:
        payload = {}
        for key, template in self.payload_template.items():
            payload[key] = template.format(receptor=receptor, message=message, sender=self._get_sender(sender))
        return self._send_request(payload)
    
    def send_bulk(self, receptors: List[str], message: str, sender: str = None) -> List[SMSResult]:
        results = []
        for receptor in receptors:
            results.append(self.send_single(receptor, message, sender))
        return results
    
    def get_balance(self) -> float:
        try:
            response = requests.get(f"{self.api_url}/balance", headers=self.headers, timeout=30)
            return float(response.json().get('balance', 0))
        except:
            return 0.0
    
    def _send_request(self, payload: Dict) -> SMSResult:
        try:
            response = requests.post(self.api_url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            success = data.get('success', data.get('status', False))
            return SMSResult(success=bool(success), raw_response=data,
                             error=data.get('message', None) if not success else None)
        except Exception as e:
            return SMSResult(success=False, error=str(e))


class SIMCardProvider(BaseSMSProvider):
    """ارسال از طریق سیمکارت"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._modem = None
    
    @property
    def modem(self):
        if self._modem is None:
            from services.sim_sms import sim_modem
            self._modem = sim_modem
        return self._modem
    
    def send_single(self, receptor: str, message: str, sender: str = None) -> SMSResult:
        result = self.modem.send_sms(receptor, message)
        return SMSResult(
            success=result.success,
            message_id=result.message_id,
            error=result.error,
            raw_response={'raw': result.raw_response}
        )
    
    def send_bulk(self, receptors: List[str], message: str, sender: str = None) -> List[SMSResult]:
        results = self.modem.send_bulk_sms(receptors, message)
        return [SMSResult(success=r.success, message_id=r.message_id, error=r.error) for r in results]
    
    def get_balance(self) -> float:
        return self.modem.get_balance()


class DLinkRouterProvider(BaseSMSProvider):
    """ارسال از طریق روتر D-Link روی شبکه محلی (Wi-Fi/LAN)"""

    @property
    def pool(self):
        return router_pool

    def send_single(self, receptor: str, message: str, sender: str = None) -> SMSResult:
        result = self.pool.send_sms(receptor, message)
        return SMSResult(
            success=result.success,
            message_id=result.message_id or None,
            error=result.error,
            raw_response={'raw': result.raw_response}
        )

    def send_bulk(self, receptors: List[str], message: str, sender: str = None) -> List[SMSResult]:
        results = self.pool.send_bulk_sms(receptors, message)
        return [SMSResult(success=r.success, message_id=r.message_id or None, error=r.error)
                for r in results]

    def get_balance(self) -> float:
        return self.pool.get_balance()


class SMSService:
    # کلید ذخیرهٔ مودم انتخابی در AppSetting: "router:IP" یا "usb:PORT"
    MODEM_SETTING_KEY = "sms_selected_modem"

    def __init__(self):
        self.api_provider: Optional[BaseSMSProvider] = None
        self.sim_provider: Optional[SIMCardProvider] = None
        self.router_provider: Optional[DLinkRouterProvider] = None
        self.active_mode: str = "sim_card"
        self._selected_modem: Optional[str] = None
        # سازمان‌ها/صفحات می‌توانند برای اطلاع از تاییدیهٔ تحویل به این متصل شوند
        self.on_delivery_update = None
        # برای اطلاع از پیامک دریافتی از مودم (از نخ سریال/پایش روتر صدا زده
        # می‌شود؛ listener سیگنال Qt ارسال می‌کند نه اتصال مستقیم به ویجت)
        self.on_incoming_update = None
        self._init_providers()
    
    def _init_providers(self):
        provider_type = settings.SMS_PROVIDER.lower()
        
        if provider_type == "kavenegar":
            self.api_provider = KavenegarProvider(api_key=settings.SMS_API_KEY, sender_number=settings.SMS_SENDER_NUMBER)
        elif provider_type == "melipayamak":
            self.api_provider = MelipayamakProvider(api_key=settings.SMS_API_KEY, sender_number=settings.SMS_SENDER_NUMBER,
                username=settings.SMS_USERNAME, password=settings.SMS_PASSWORD)
        else:
            self.api_provider = CustomSMSProvider(api_key=settings.SMS_API_KEY, sender_number=settings.SMS_SENDER_NUMBER,
                api_url=settings.SMS_API_URL)
        
        self.sim_provider = SIMCardProvider()
        self.router_provider = DLinkRouterProvider()
        self.active_mode = "sim_card"
        # مودم هر گزارش تحویل (+CDS) را به این تابع می‌دهد تا در سابقه ثبت شود
        self.sim_provider.modem.on_delivery_report = self._handle_delivery_report
        # مودم هر پیام دریافتی (+CMT/+CMTI) را اینجا تحویل می‌گیرد
        self.sim_provider.modem.on_incoming_sms = self._handle_incoming_sms
        # نخ پایش صندوق روتر هم هر پیام تازه را همین‌جا تحویل می‌دهد
        router_pool.on_incoming_sms = self._handle_incoming_sms

    # ---------- انتخاب و اتصال مودم ----------

    def get_selected_modem(self) -> str:
        """شناسهٔ مودم انتخابی: 'router:IP' یا 'usb:PORT' ('' = پیش‌فرض USB)"""
        if self._selected_modem is None:
            try:
                self._selected_modem = str(
                    setting_repo.get_setting(self.MODEM_SETTING_KEY, "") or ""
                )
            except Exception:
                self._selected_modem = ""
        return self._selected_modem

    def select_modem(self, modem_id: str):
        """ثبت انتخاب کاربر بدون اتصال (انتخاب هنگام اتصال موفق هم خودکار ثبت می‌شود)"""
        self._selected_modem = modem_id or ""
        try:
            setting_repo.set_setting(self.MODEM_SETTING_KEY, self._selected_modem)
        except Exception:
            logger.exception("Could not persist selected modem")

    def scan_modems(self, progress_cb=None) -> List[Dict[str, Any]]:
        """کشف همهٔ درگاه‌های پیامک: روتر D-Link روی شبکه + مودم USB سریال"""
        modems: List[Dict[str, Any]] = []
        try:
            for r in router_pool.discover(progress_cb):
                modems.append({
                    "id": f"router:{r.ip}",
                    "kind": "router",
                    "ip": r.ip,
                    "label": f"روتر D-Link ({r.ip})",
                    "detail": r.mac or "",
                })
        except Exception:
            logger.exception("Router discovery failed")
        try:
            for d in self.sim_provider.modem.detect_modems():
                if d.is_modem:
                    modems.append({
                        "id": f"usb:{d.port}",
                        "kind": "usb",
                        "port": d.port,
                        "label": f"مودم USB ({d.port})",
                        "detail": d.description or "",
                        "baud": d.baud or 115200,
                        "in_use": d.in_use,
                    })
        except Exception:
            logger.exception("USB modem detection failed")
        return modems

    def router_needs_password(self, host: str) -> bool:
        return not router_pool.has_credentials(host)

    def set_router_credentials(self, host: str, username: str, password: str):
        """رمز فقط در حافظه نگه داشته می‌شود و هرگز در فایل ذخیره نمی‌شود"""
        router_pool.set_credentials(host, username, password)

    def connect_modem(self, modem_id: str, baud: int = 115200,
                      password: Optional[str] = None) -> bool:
        """اتصال به مودم انتخابی: 'router:IP' یا 'usb:PORT'"""
        if not modem_id:
            return False
        if modem_id.startswith("router:"):
            host = modem_id.split(":", 1)[1]
            ok = router_pool.connect(host, username=settings.DLINK_ROUTER_USER or "admin",
                                     password=password)
        else:
            port = modem_id.split(":", 1)[1] if ":" in modem_id else modem_id
            ok = self.connect_sim(port, baud)
        if ok:
            self.select_modem(modem_id)
        return ok

    def disconnect_modem(self):
        modem = self.get_selected_modem()
        if modem.startswith("router:"):
            router_pool.disconnect()
        else:
            self.disconnect_sim()

    def get_modem_status(self) -> ModemInfo:
        modem = self.get_selected_modem()
        if modem.startswith("router:"):
            return router_pool.get_modem_info()
        return self.get_sim_status()

    def is_modem_connected(self) -> bool:
        modem = self.get_selected_modem()
        if modem.startswith("router:"):
            return router_pool.is_connected()
        try:
            return bool(self.sim_provider.modem.is_connected())
        except Exception:
            return False
    
    def set_mode(self, mode: str):
        """تغییر حالت ارسال: 'sim_card' یا 'api'"""
        self.active_mode = mode
    
    def get_active_provider(self) -> BaseSMSProvider:
        if self.active_mode == "api":
            return self.api_provider
        if self.get_selected_modem().startswith("router:"):
            return self.router_provider
        return self.sim_provider
    
    def connect_sim(self, port: str, baud_rate: int = 115200, pin: str = None) -> bool:
        """اتصال به مودم سیمکارت

        Args:
            port: پورت سریال (مثال: COM3)
            baud_rate: نرخ باند (پیش‌فرض 115200)
            pin: کد PIN سیمکارت (اختیاری)
        """
        try:
            return self.sim_provider.modem.connect(port, baud_rate, pin)
        except Exception as e:
            logger.error(f"SIM connect error: {e}")
            return False
    
    def disconnect_sim(self):
        """قطع اتصال سیمکارت"""
        try:
            self.sim_provider.modem.disconnect()
        except Exception:
            pass
    
    def get_sim_status(self):
        """وضعیت سیمکارت"""
        try:
            return self.sim_provider.modem.get_modem_info()
        except Exception:
            return ModemInfo()
    
    def get_available_ports(self):
        """لیست پورت‌های COM"""
        try:
            return self.sim_provider.modem.scan_ports()
        except Exception:
            return []
    
    def get_smsc(self) -> Optional[str]:
        """خواندن آدرس مرکز پیامک (SMSC) فعلی"""
        try:
            return self.sim_provider.modem.get_smsc()
        except Exception:
            return None

    def set_smsc(self, smsc_number: str) -> bool:
        """تنظیم آدرس مرکز پیامک (SMSC)"""
        try:
            return self.sim_provider.modem.set_smsc(smsc_number)
        except Exception:
            return False
    
    def send_sms(self, contact_id: int, message: str, message_id: int = None,
                 mobile: str = None) -> SMSResult:
        """ارسال به یک مخاطب

        mobile: شماره جایگزین (وقتی کاربر در صفحهٔ ارسال شماره را تغییر داده).
        در این حالت خودِ مخاطب تغییر نمی‌کند ولی شمارهٔ ارسالی در سابقه ثبت می‌شود.
        """
        contact = contact_repo.get_by_id(contact_id)
        if not contact:
            return SMSResult(success=False, error="Contact not found")
        number = normalize_mobile(mobile) if mobile else (contact.mobile or "")
        if not number:
            return SMSResult(success=False, error="No mobile number")

        provider = self.get_active_provider()
        result = provider.send_single(number, message)

        if message_id:
            self._update_message_status(message_id, result)
        else:
            message_repo.create(
                uuid=str(uuid_lib.uuid4()),
                contact_id=contact.id,
                message_type=MessageType.SMS,
                direction=MessageDirection.OUTGOING,
                content=message,
                recipient_number=number,
                status=MessageStatus.SENT if result.success else MessageStatus.FAILED,
                provider_message_id=result.message_id,
                provider_response=result.raw_response,
                error_message=result.error,
                sent_at=datetime.now() if result.success else None,
            )

        return result
    
    def send_bulk_sms(self, contact_ids: List[int], message: str, group_id: int = None) -> Dict[str, Any]:
        contacts = []
        for cid in contact_ids:
            contact = contact_repo.get_by_id(cid)
            if contact and contact.mobile:
                contacts.append(contact)
        
        if not contacts:
            return {'success': 0, 'failed': 0, 'results': [], 'error': 'No valid contacts'}
        
        provider = self.get_active_provider()
        receptors = [c.mobile for c in contacts]
        results = provider.send_bulk(receptors, message)
        
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        
        message_records = []
        for contact, result in zip(contacts, results):
            msg = message_repo.create(
                uuid=str(uuid_lib.uuid4()),
                contact_id=contact.id,
                message_type=MessageType.SMS,
                direction=MessageDirection.OUTGOING,
                content=message,
                recipient_number=contact.mobile,
                status=MessageStatus.SENT if result.success else MessageStatus.FAILED,
                provider_message_id=result.message_id,
                provider_response=result.raw_response,
                error_message=result.error,
                sent_at=datetime.now() if result.success else None,
            )
            message_records.append(msg)
        
        return {'success': success_count, 'failed': failed_count, 'total': len(contacts),
                'results': [{'contact_id': c.id, 'mobile': c.mobile, 'success': r.success, 'error': r.error}
                           for c, r in zip(contacts, results)]}
    
    def send_to_recipients(self, recipients: List[Dict[str, Any]], message: str) -> Dict[str, Any]:
        """ارسال پیامک به فهرست گیرندگان دلخواه

        هر گیرنده: {'contact_id': int|None, 'mobile': str, 'name': str}
        گیرنده بدون contact_id (مثل بخشدار) ارسال می‌شود ولی در سابقه پیامک ثبت نمی‌شود.
        """
        valid = [r for r in recipients if (r.get('mobile') or '').strip()]
        if not valid:
            return {'success': 0, 'failed': 0, 'total': 0, 'results': []}

        provider = self.get_active_provider()
        results = provider.send_bulk([r['mobile'] for r in valid], message)

        success_count = 0
        for recipient, result in zip(valid, results):
            if result.success:
                success_count += 1
            contact_id = recipient.get('contact_id')
            if not contact_id:
                continue
            try:
                message_repo.create(
                    uuid=str(uuid_lib.uuid4()),
                    contact_id=contact_id,
                    message_type=MessageType.SMS,
                    direction=MessageDirection.OUTGOING,
                    content=message,
                    recipient_number=recipient['mobile'],
                    status=MessageStatus.SENT if result.success else MessageStatus.FAILED,
                    provider_message_id=result.message_id,
                    provider_response=result.raw_response,
                    error_message=result.error,
                    sent_at=datetime.now() if result.success else None,
                )
            except Exception as e:
                logger.error(f"Message log error: {e}")

        return {
            'success': success_count,
            'failed': len(valid) - success_count,
            'total': len(valid),
            'results': [
                {'name': r.get('name'), 'mobile': r['mobile'], 'success': res.success, 'error': res.error}
                for r, res in zip(valid, results)
            ],
        }

    def send_number(self, mobile: str, message: str) -> SMSResult:
        """ارسال به شماره‌ای که در فهرست مخاطبین نیست

        چون جدول پیامک به مخاطب گره خورده، این ارسال در سابقه ثبت نمی‌شود؛
        برای ثبت در سابقه کاربر باید شماره را به مخاطبین اضافه کند.
        """
        mobile = normalize_mobile(mobile)
        if not mobile:
            return SMSResult(success=False, error="شماره موبایل نامعتبر است")
        provider = self.get_active_provider()
        return provider.send_single(mobile, message)

    def ensure_contact(self, mobile: str):
        """مخاطب موجود با این شماره را برمی‌گرداند و اگر نبود می‌سازد"""
        mobile = normalize_mobile(mobile)
        if not mobile:
            return None
        existing = contact_repo.get_by_mobile(mobile)
        if existing:
            return existing
        try:
            return contact_repo.create(
                uuid=str(uuid_lib.uuid4()),
                first_name="مخاطب",
                last_name=mobile,
                mobile=mobile,
            )
        except Exception:
            logger.exception("Could not create contact for %s", mobile)
            return contact_repo.get_by_mobile(mobile)

    def get_balance(self) -> Dict[str, float]:
        balances = {}
        if self.sim_provider and self.sim_provider.modem.is_connected():
            balances['sim_card'] = self.sim_provider.get_balance()
        if self.api_provider:
            balances['api'] = self.api_provider.get_balance()
        return balances

    # ---------- پیامک دریافتی ----------

    def _handle_incoming_sms(self, number: str, text: str, received_at=None):
        """ذخیرهٔ پیامکی که مودم خودجوش دریافت کرده است

        از نخ سریال صدا زده می‌شود؛ خطای داخلی نباید نخ گوش‌دهنده را بکشد.
        """
        raw_number = number or ""
        try:
            number = normalize_mobile(raw_number) or raw_number.strip()
            if not number:
                logger.warning("Incoming SMS without a usable sender number")
                return
            contact = self.ensure_contact(number)
            if contact is None:
                logger.warning("Incoming SMS ignored, no contact for %s", number)
                return

            stamp = received_at if isinstance(received_at, datetime) else datetime.now()
            # شناسهٔ یکتا برای حذف تکرار: برخی مودم‌ها هم +CMT و هم +CMTI می‌فرستند
            dedupe_key = "sim-in-" + hashlib.sha1(
                ("%s|%s|%s" % (number, stamp.isoformat(sep=" ", timespec="seconds"), text or "")).encode("utf-8", "replace")
            ).hexdigest()[:24]
            if message_repo.find_incoming_by_key(dedupe_key):
                logger.info("Duplicate incoming SMS ignored (%s)", number)
                return

            own_number = ""
            if not self.get_selected_modem().startswith("router:") and self.sim_provider:
                own_number = getattr(self.sim_provider.modem.info, "sim_number", "") or ""
            message = message_repo.create(
                uuid=str(uuid_lib.uuid4()),
                contact_id=contact.id,
                message_type=MessageType.SMS,
                direction=MessageDirection.INCOMING,
                status=MessageStatus.RECEIVED,
                content=text or "",
                sender_number=number[:20],
                recipient_number=(own_number[:20] or None),
                provider_message_id=dedupe_key,
                received_at=stamp,
            )
            logger.info("Incoming SMS stored: id=%s from=%s", getattr(message, "id", "?"), number)
            if self.on_incoming_update:
                try:
                    self.on_incoming_update(message.id)
                except Exception:
                    logger.exception("Incoming SMS update callback failed")
        except Exception:
            logger.exception("Failed to store incoming SMS from %s", raw_number)

    def get_incoming(self, limit: int = 200, days: Optional[int] = None):
        """پیامک‌های دریافتی برای نمایش در UI"""
        try:
            return message_repo.get_incoming(limit=limit, days=days)
        except Exception:
            logger.exception("Incoming SMS list failed")
            return []

    # ---------- گزارش تحویل ----------

    def _handle_delivery_report(self, mr: int, st: int):
        """ذخیرهٔ تاییدیهٔ تحویل که مودم خودجوش فرستاده است

        mr = شمارهٔ پیام در مرکز پیام (همان +CMGS)، st = کد وضعیت تحویل.
        """
        try:
            msg = message_repo.get_by_provider_id(mr)
            if msg is None:
                logger.info("Delivery report for unknown message reference %s", mr)
                return
            reason = delivery_reason(st)
            message_repo.set_delivery(msg.id, delivered=(st == 0), code=st, reason=reason)
            logger.info("Delivery report stored: id=%s mr=%s st=%s", msg.id, mr, st)
            if self.on_delivery_update:
                try:
                    self.on_delivery_update(msg.id, st)
                except Exception:
                    logger.exception("Delivery update callback failed")
        except Exception:
            logger.exception("Failed to store delivery report (mr=%s, st=%s)", mr, st)

    def get_delivery_summary(self, days: int = 7) -> Dict[str, int]:
        """خلاصهٔ تحویل پیامک‌های اخیر برای نمایش در UI"""
        try:
            return message_repo.get_delivery_summary(days)
        except Exception:
            logger.exception("Delivery summary failed")
            return {'delivered': 0, 'undelivered': 0, 'waiting': 0, 'total': 0}

    def get_delivery_report(self, days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """فهرست «چه کسی تحویل گرفت» و «چه کسی نگرفت»"""
        out = {'delivered': [], 'undelivered': [], 'waiting': []}
        contacts = {}

        def row(msg):
            contact = contacts.get(msg.contact_id)
            if msg.contact_id not in contacts:
                contact = contact_repo.get_by_id(msg.contact_id)
                contacts[msg.contact_id] = contact
            name = f"{contact.first_name} {contact.last_name}".strip() if contact else "—"
            return {
                'name': name or "—",
                'mobile': msg.recipient_number or (contact.mobile if contact else "") or "",
                'date': msg.created_at.isoformat(sep=' ', timespec='minutes') if msg.created_at else "",
                'delivered_at': msg.delivered_at.isoformat(sep=' ', timespec='minutes') if msg.delivered_at else "",
                'reason': msg.error_message or "",
            }

        try:
            for status in ('delivered', 'undelivered'):
                out[status] = [row(m) for m in message_repo.get_by_delivery(status, days)]
            waiting = [
                m for m in message_repo.get_all(limit=500)
                if m.direction == MessageDirection.OUTGOING and m.delivery_status is None
                and m.status in (MessageStatus.SENT, MessageStatus.PENDING)
            ]
            out['waiting'] = [row(m) for m in waiting]
        except Exception:
            logger.exception("Delivery report failed")
        return out

    def _update_message_status(self, message_id: int, result: SMSResult):
        session = get_db()
        try:
            msg = session.query(message_repo.model).filter(message_repo.model.id == message_id).first()
            if msg:
                msg.status = MessageStatus.SENT if result.success else MessageStatus.FAILED
                msg.provider_message_id = result.message_id
                msg.provider_response = result.raw_response
                msg.error_message = result.error
                msg.sent_at = datetime.now() if result.success else None
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


sms_service = SMSService()