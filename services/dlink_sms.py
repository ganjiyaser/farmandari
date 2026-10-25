# -*- coding: utf-8 -*-
"""دروازه پیامک از طریق روتر D-Link DWR-M921 روی شبکه محلی (Wi-Fi/LAN).

برخلاف services/sim_sms.py که با پورت سریال و دستور AT کار می‌کند، اینجا
ارسال/دریافت از API وب روتر انجام می‌شود: ورود Digest روی /login.cgi و دستورات
XML روی /xml_action.cgi (همان چیزی که پنل وب روتر خودش استفاده می‌کند).

نکتهٔ امنیتی: رمز عبور روتر فقط در حافظه نگه داشته می‌شود و هرگز در فایل یا
پایگاه‌داده ذخیره نمی‌شود؛ یا از کاربر پرسیده می‌شود یا از متغیر محیط
DLINK_ROUTER_PASSWORD خوانده می‌شود.
"""
import hashlib
import ipaddress
import logging
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Callable, Dict, List, Optional

import requests

from core.config import settings
from services.sim_sms import ModemInfo, ModemStatus, SIMSMSResult

logger = logging.getLogger(__name__)

# URI ثابت در پاسخ Digest — حتی برای مسیر واقعی /xml_action.cgi هم همین است
# (رفتار خاص فریم‌ور Marvell روتر؛ طبق JS پنل وب استخراج شده).
XML_URI = "/cgi/xml_action.cgi"
PROBE_REALM = "highwmg"  # realm ثابت چالش Digest روترهای D-Link این سری


class RouterAuthError(Exception):
    """نام کاربری/رمز روتر اشتباه است یا نشست منقضی شده و ورود مجدد ناموفق بود"""


class RouterConnectionError(Exception):
    """روتر روی شبکه پیدا نشد یا پاسخ نمی‌دهد"""


@dataclass
class RouterMessage:
    """یک پیامک خوانده‌شده از حافظهٔ روتر"""
    id: str = ""
    address: str = ""
    date: str = ""
    msg_type: str = ""
    read: bool = False
    status: str = ""
    text: str = ""
    received_at: Optional[datetime] = None


@dataclass
class DiscoveredRouter:
    """روتر D-Link پیدا‌شده روی شبکه محلی"""
    ip: str = ""
    mac: str = ""
    model: str = "D-Link DWR-M921"


def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


class DLinkRouterClient:
    """کلاینت HTTP API یک روتر؛ نخ‌امن به‌خاطر شمارندهٔ nc در Digest"""

    def __init__(self, host: str, username: str, password: str):
        self.host = self._normalize_host(host)
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.realm: Optional[str] = None
        self.nonce: Optional[str] = None
        self.qop: str = "auth"
        self.nc = 1
        self.logged_in = False
        # RLock: post_xml قفل را نگه می‌دارد و login() دوباره همان قفل را می‌گیرد
        self._lock = threading.RLock()

    @staticmethod
    def _normalize_host(host: str) -> str:
        host = (host or "").strip().rstrip("/")
        if not host:
            return host
        if not host.startswith("http://") and not host.startswith("https://"):
            host = "http://" + host
        return host

    def set_credentials(self, username: str, password: str):
        with self._lock:
            self.username = username
            self.password = password
            self.logged_in = False
            self.nc = 1

    # ---------- Digest auth (رفتار خاص فریم‌ور روتر، از پنل وب استخراج شده) ----------

    def _parse_challenge(self, header: str):
        m = re.search(r"Digest\s+(.*)", header or "", re.IGNORECASE)
        if not m:
            raise RouterConnectionError(f"WWW-Authenticate نامعتبر: {header!r}")
        params = dict(re.findall(r'(\w+)="?([^",]+)"?', m.group(1)))
        self.realm = params.get("realm")
        self.nonce = params.get("nonce")
        self.qop = (params.get("qop") or "auth").split(",")[0]

    def _digest(self, method: str):
        """ساخت یک پاسخ Digest و بردن شمارندهٔ nc"""
        ha1 = _md5_hex(f"{self.username}:{self.realm}:{self.password}")
        ha2 = _md5_hex(f"{method}:{XML_URI}")
        cnonce = _md5_hex(f"{time.time()}-{self.nc}")[:16]
        nc = f"{self.nc:08x}"
        resp = _md5_hex(f"{ha1}:{self.nonce}:{nc}:{cnonce}:{self.qop}:{ha2}")
        self.nc += 1
        return resp, cnonce, nc

    def _auth_header(self, method: str) -> str:
        resp, cnonce, nc = self._digest(method)
        return (
            f'Digest username="{self.username}", realm="{self.realm}", '
            f'nonce="{self.nonce}", uri="{XML_URI}", response="{resp}", '
            f"qop={self.qop}, nc={nc}, cnonce=\"{cnonce}\""
        )

    def login(self) -> bool:
        """ورود به پنل؛ False یعنی رمز اشتباه است"""
        with self._lock:
            try:
                r = self.session.get(f"{self.host}/login.cgi", timeout=10)
            except requests.RequestException as e:
                raise RouterConnectionError(f"روتر پاسخ نمی‌دهد: {e}") from e
            self._parse_challenge(r.headers.get("WWW-Authenticate", ""))
            resp, cnonce, nc = self._digest("GET")
            # پنل وب روتر برای همین درخواست، هدر Authorization را هم با cnonce
            # تازه ولی همان nc=00000001 می‌فرستد؛ بدون هدر، روتر همیشه 500 می‌دهد
            header = self._auth_header("GET")
            q = urllib.parse.urlencode({
                "Action": "Digest", "username": self.username, "realm": self.realm,
                "nonce": self.nonce, "response": resp,
                "qop": self.qop, "cnonce": cnonce, "nc": nc, "temp": "marvell",
            })
            try:
                r = self.session.get(
                    f"{self.host}/login.cgi?{q}", timeout=10,
                    headers={"Authorization": header,
                             "Cache-Control": "no-store, no-cache, must-revalidate"},
                )
            except requests.RequestException as e:
                raise RouterConnectionError(f"روتر پاسخ نمی‌دهد: {e}") from e
            # بدنهٔ «HTTP/1.1 500 OK» به‌معنای «ورود ناموفق» است (حتی با کد 200)
            body = r.text.strip()
            if r.status_code in (401, 403) or body.startswith("HTTP/1.1 500"):
                self.logged_in = False
                return False
            self.logged_in = True
            logger.info("Router login OK: %s", self.host)
            return True

    # ---------- دستورات XML ----------

    def _post_once(self, obj_path: str, obj_method: str, fields: dict) -> ET.Element:
        body = self._build_xml(obj_path, obj_method, fields)
        try:
            r = self.session.post(
                f"{self.host}/xml_action.cgi?method=set",
                data=body.encode("utf-8"),
                headers={
                    "Authorization": self._auth_header("POST"),
                    "Content-Type": "text/xml",
                    "Cache-Control": "no-store, no-cache, must-revalidate",
                    "Pragma": "no-cache",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise RouterConnectionError(f"خطای ارتباط با روتر: {e}") from e
        if r.status_code in (401, 403) or r.text.strip().startswith("HTTP/1.1 500"):
            self.logged_in = False
            raise RouterAuthError("نشست روتر نامعتبر است")
        if r.status_code != 200:
            raise RouterConnectionError(f"HTTP {r.status_code} از روتر")
        try:
            return ET.fromstring(r.content)
        except ET.ParseError as e:
            raise RouterConnectionError(f"پاسخ نامعتبر روتر: {e}") from e

    def post_xml(self, obj_path: str, obj_method: str, fields: dict) -> ET.Element:
        """ارسال دستور؛ با یک بار ورود مجدد خودکار در صورت منقضی‌شدن نشست"""
        with self._lock:
            if not self.logged_in:
                if not self.login():
                    raise RouterAuthError("نام کاربری یا رمز عبور روتر اشتباه است")
            try:
                return self._post_once(obj_path, obj_method, fields)
            except RouterAuthError:
                if not self.login():
                    raise RouterAuthError("نام کاربری یا رمز عبور روتر اشتباه است")
                return self._post_once(obj_path, obj_method, fields)

    @staticmethod
    def _build_xml(obj_path: str, obj_method: str, fields: dict) -> str:
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<RGW>", "  <param>",
                 "    <method>call</method>", "    <session>000</session>",
                 f"    <obj_path>{obj_path}</obj_path>",
                 f"    <obj_method>{obj_method}</obj_method>", "  </param>"]
        if fields:
            lines.append("  <sms_info>")
            lines.append("    <sms>")
            for k, v in fields.items():
                lines.append(f"      <{k}>{v}</{k}>")
            lines.append("    </sms>")
            lines.append("  </sms_info>")
        lines.append("</RGW>")
        return "\n".join(lines)

    # ---------- پیامک ----------

    @staticmethod
    def _uni_encode(text: str) -> str:
        """متن → هگز UCS2 (UTF-16BE) طبق قرارداد API روتر"""
        # utf-16-be جای ord(ch) را می‌گیرد تا کاراکترهای خارج از BMP
        # (سوروگیت‌ها) هم ۴ رقم هگز درست تولید کنند
        return text.encode("utf-16-be").hex()

    @staticmethod
    def _uni_decode(hex_text: str) -> str:
        clean = re.sub(r"[^0-9A-Fa-f]", "", hex_text or "")
        if len(clean) < 4 or len(clean) % 4 != 0:
            return hex_text or ""
        try:
            return bytes.fromhex(clean).decode("utf-16-be")
        except Exception:
            return hex_text or ""

    @staticmethod
    def _sms_time() -> str:
        now = datetime.now(timezone(timedelta(hours=3, minutes=30)))
        return f"{now:%y},{now.month},{now.day},{now.hour},{now.minute},{now.second},%2B3:30"

    @staticmethod
    def _parse_router_date(raw: str) -> Optional[datetime]:
        """قالب روتر: yy,m,d,h,m,s,%2B3:30 → datetime محلی"""
        if not raw:
            return None
        try:
            parts = [p for p in raw.split(",")[:6]]
            nums = [int(re.sub(r"\D", "", p)) for p in parts]
            if len(nums) < 6:
                return None
            yy, mo, dd, hh, mm, ss = nums
            return datetime(2000 + yy, mo, dd, hh, mm, min(ss, 59))
        except Exception:
            return None

    def send_sms(self, number: str, text: str) -> tuple:
        """ارسال پیامک؛ خروجی: (موفق؟, شناسهٔ smsRef)"""
        root = self.post_xml("sms", "sms.send", {
            "id": "-1",
            "gsm7": "1" if all(ord(c) < 128 for c in text) else "0",
            "address": number,
            "body": self._uni_encode(text),
            "date": self._sms_time(),
            "protocol": "0",
        })
        resp = root.findtext(".//resp")
        if resp != "0":
            return False, ""
        ref = ""
        for el in root.iter():
            if el.tag.lower() in ("smsref", "ref", "sms_ref") and el.text:
                ref = el.text.strip()
                break
        return True, ref

    def list_sms(self, list_type: int = 0, page: int = 1) -> List[RouterMessage]:
        """خواندن یک صفحه از صندوق پیامک (0=دریافتی، 1=ارسالی)"""
        root = self.post_xml("sms", "sms.list_by_type", {
            "page_index": str(page),
            "list_type": str(list_type),
        })
        messages: List[RouterMessage] = []
        node_list = root.find(".//node_list")
        if node_list is None:
            return messages
        for node in node_list:
            msg = RouterMessage(
                id=(node.findtext("id") or "").strip(),
                address=(node.findtext("address") or "").strip(),
                date=(node.findtext("date") or "").strip(),
                msg_type=(node.findtext("type") or "").strip(),
                read=(node.findtext("read") or "0").strip() not in ("0", ""),
                status=(node.findtext("status") or "").strip(),
                text=self._uni_decode(node.findtext("body") or ""),
            )
            msg.received_at = self._parse_router_date(msg.date)
            messages.append(msg)
        return messages


# ---------- کشف روتر روی شبکه محلی ----------

_IPV4_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")


def _hidden_subprocess_kwargs() -> dict:
    """آرگومان‌های subprocess برای اجرای بدون پنجرهٔ کنسول در ویندوز.

    بدون این، هر دستور (ping/ipconfig/...) در نسخهٔ exe بدون کنسول یک
    پنجرهٔ Windows Terminal جدید می‌سازد و صفحه پر از پنجره می‌شود.
    """
    if sys.platform != "win32":
        return {}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    except Exception:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


_HIDDEN_SUBPROCESS = _hidden_subprocess_kwargs()


def _run(cmd: List[str], timeout: int = 15) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, encoding="utf-8", errors="ignore",
                             **_HIDDEN_SUBPROCESS)
        return out.stdout or ""
    except Exception:
        return ""


def _local_subnets() -> List[ipaddress.IPv4Network]:
    """ساب‌نت‌های آدرس‌های IPv4 محلی (از خروجی ipconfig)

    برچسب‌های ipconfig در ویندوز غیرانگلیسی (مثل فارسی) ترجمه می‌شوند؛ پس
    به‌جای جستجوی «IPv4 Address/Subnet Mask» از ترتیب ثابت سطرهای هر بلوک
    آداپتور استفاده می‌کنیم: اولین نشانی = IP، دومین = ماسک.
    """
    text = _run(["ipconfig"])
    subnets: List[ipaddress.IPv4Network] = []
    quads: List[str] = []
    for line in text.splitlines():
        if not line.strip():
            quads = []  # جداکنندهٔ آداپتور
            continue
        quads.extend(m.group(0) for m in _IPV4_RE.finditer(line))
        if len(quads) >= 2:
            try:
                net = ipaddress.IPv4Network(f"{quads[0]}/{quads[1]}", strict=False)
                if net.is_private and not net.is_link_local and net.prefixlen <= 24:
                    subnets.append(net)
            except ValueError:
                pass
            quads = []  # هر بلوک فقط یک ساب‌نت
    # حذف تکراری‌ها حفظ ترتیب
    seen, result = set(), []
    for net in subnets:
        if net not in seen:
            seen.add(net)
            result.append(net)
    return result


def _default_gateways() -> List[str]:
    """درگاه‌های پیش‌فرض از جدول مسیریابی (مستقل از زبان ویندوز)

    سطر مسیر پیش‌فرض در «route print -4» همیشه چنین است:
    ``0.0.0.0  0.0.0.0  <gateway>  <interface>  <metric>``
    """
    gateways: List[str] = []
    for line in _run(["route", "print", "-4"]).splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            gw = parts[2]
            # درگاه on-link (متن ترجمه‌شده) و خودِ 0.0.0.0 قابل استفاده نیستند
            if _IPV4_RE.fullmatch(gw) and gw != "0.0.0.0" and gw not in gateways:
                gateways.append(gw)
    return gateways


def _arp_table() -> Dict[str, str]:
    table: Dict[str, str] = {}
    for line in _run(["arp", "-a"]).splitlines():
        m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9A-Fa-f-]{17})", line)
        if m:
            table[m.group(1)] = m.group(2).upper()
    return table


def _ping_hosts(ips: List[str], workers: int = 64) -> List[str]:
    alive: List[str] = []

    def ping_one(ip: str):
        try:
            out = subprocess.run(["ping", "-n", "1", "-w", "300", ip],
                                 capture_output=True, timeout=5,
                                 **_HIDDEN_SUBPROCESS)
            if out.returncode == 0:
                alive.append(ip)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(ping_one, ips))
    return alive


def probe_router(ip: str, timeout: float = 2.0) -> Optional[DiscoveredRouter]:
    """آیا این IP یک روتر D-Link سری Marvell است؟ (چالش Digest با realm=Highwmg)"""
    try:
        r = requests.get(f"http://{ip}/login.cgi", timeout=timeout)
    except requests.RequestException:
        return None
    challenge = r.headers.get("WWW-Authenticate", "")
    if PROBE_REALM not in challenge.lower():
        return None
    return DiscoveredRouter(ip=ip)


def discover_routers(progress_cb: Optional[Callable[[str], None]] = None) -> List[DiscoveredRouter]:
    """جستجوی روترهای D-Link روی همهٔ ساب‌نت‌های محلی"""
    routers: Dict[str, DiscoveredRouter] = {}
    arp = _arp_table()

    def note(ip: str, router: DiscoveredRouter):
        router.mac = arp.get(ip, "")
        routers[ip] = router
        if progress_cb:
            try:
                progress_cb(ip)
            except Exception:
                pass

    # درگاه پیش‌فرض اول — بیشترین احتمال دارد روتر باشد
    for gw in _default_gateways():
        if progress_cb:
            progress_cb(gw)
        found = probe_router(gw)
        if found:
            note(gw, found)

    for net in _local_subnets():
        if progress_cb:
            progress_cb(str(net))
        hosts = [str(ip) for ip in net.hosts() if str(ip) not in routers]
        if not hosts:
            continue
        alive = set(_ping_hosts(hosts))
        # برخی دستگاه‌ها ping را بلاک می‌کنند ولی در جدول ARP هستند
        alive.update(ip for ip in hosts if ip in arp)
        with ThreadPoolExecutor(max_workers=16) as pool:
            # alive مجموع است (بدون ترتیب) — zip باید روی همان نسخهٔ
            # مرتب‌شده‌ای بچرخد که به pool.map داده شده وگرنه IPها جابه‌جا
            # ثبت می‌شوند
            targets = sorted(alive)
            for ip, found in zip(targets, pool.map(probe_router, targets)):
                if found:
                    note(ip, found)
    return sorted(routers.values(), key=lambda r: [int(p) for p in r.ip.split(".")])


# ---------- مخزن روترها (singleton) — سطح مشابه SIMCardModem ----------

class RouterModemPool:
    """مدیریت روترهای D-Link؛ اتصال فعال یک روتر و پایش خودکار صندوق دریافت"""

    POLL_INTERVAL = 15  # ثانیه بین هر خواندن صندوق دریافت
    MAX_SEEN = 2000     # سقف شناسه‌های نگه‌داشته‌شده برای حذف تکرار

    def __init__(self):
        self.routers: List[DiscoveredRouter] = []
        self.clients: Dict[str, DLinkRouterClient] = {}
        self._creds: Dict[str, tuple] = {}  # host -> (user, pass) فقط در حافظه
        self.selected_host: str = ""
        self.info = ModemInfo()
        # سازگاری با سطح sim_modem؛ روتر گزارش تحویل لحظه‌ای ندارد
        self.delivery_reports_enabled = False
        self.on_incoming_sms: Optional[Callable] = None
        self._poll_thread: Optional[Thread] = None
        self._poll_stop = Event()
        # dict به‌جای set تا بتوان قدیمی‌ترها را حذف کرد (ترتیب درج حفظ می‌شود)
        self._seen_ids: Dict[str, None] = {}
        self._first_poll = True

    # ---------- کشف ----------
    def discover(self, progress_cb: Optional[Callable[[str], None]] = None) -> List[DiscoveredRouter]:
        self.routers = discover_routers(progress_cb)
        logger.info("Discovered %d D-Link router(s): %s",
                    len(self.routers), ", ".join(r.ip for r in self.routers) or "-")
        return self.routers

    # ---------- اعتبارنامه (فقط حافظه) ----------
    def set_credentials(self, host: str, username: str, password: str):
        self._creds[host] = (username, password)
        client = self.clients.get(host)
        if client:
            client.set_credentials(username, password)

    def has_credentials(self, host: str) -> bool:
        if host in self._creds:
            return True
        # متغیر محیط فقط خوانده می‌شود و هرگز نوشته نمی‌شود
        return bool(settings.DLINK_ROUTER_PASSWORD)

    def _credentials_for(self, host: str):
        if host in self._creds:
            return self._creds[host]
        if settings.DLINK_ROUTER_PASSWORD:
            return (settings.DLINK_ROUTER_USER or "admin"), settings.DLINK_ROUTER_PASSWORD
        return None

    # ---------- اتصال ----------
    def _client_for(self, host: str) -> DLinkRouterClient:
        client = self.clients.get(host)
        if client is None:
            creds = self._credentials_for(host)
            if creds is None:
                raise RouterAuthError("برای اتصال به روتر، رمز عبور لازم است")
            client = DLinkRouterClient(host, creds[0], creds[1])
            self.clients[host] = client
        return client

    def connect(self, host: str, username: Optional[str] = None,
                password: Optional[str] = None) -> bool:
        host = (host or "").strip()
        if not host:
            return False
        if username is not None and password is not None:
            self.set_credentials(host, username, password)
        client = self._client_for(host)
        if not client.login():
            raise RouterAuthError("نام کاربری یا رمز عبور روتر اشتباه است")
        self.selected_host = host
        self.info = ModemInfo(
            port=host,
            manufacturer="D-Link",
            model="DWR-M921",
            status=ModemStatus.READY,
            sim_ready=True,
        )
        self._start_polling()
        return True

    def disconnect(self):
        self._stop_polling()
        self.selected_host = ""
        self.info.status = ModemStatus.DISCONNECTED
        self._first_poll = True

    def is_connected(self) -> bool:
        client = self.clients.get(self.selected_host)
        return bool(client and client.logged_in and self.selected_host)

    @property
    def connected_host(self) -> str:
        return self.selected_host if self.is_connected() else ""

    # ---------- ارسال ----------
    def send_sms(self, phone_number: str, message: str) -> SIMSMSResult:
        if not self.is_connected():
            return SIMSMSResult(success=False, error="روتر متصل نیست")
        client = self._client_for(self.selected_host)
        try:
            ok, ref = client.send_sms(phone_number, message)
            if ok:
                return SIMSMSResult(success=True, message_id=ref)
            return SIMSMSResult(success=False, error="روتر ارسال را رد کرد (resp≠0)")
        except RouterAuthError as e:
            return SIMSMSResult(success=False, error=str(e))
        except RouterConnectionError as e:
            return SIMSMSResult(success=False, error=str(e))
        except Exception as e:
            logger.error("Router SMS send error: %s", e)
            return SIMSMSResult(success=False, error=str(e))

    def send_bulk_sms(self, phone_numbers: List[str], message: str) -> List[SIMSMSResult]:
        results = []
        for phone in phone_numbers:
            results.append(self.send_sms(phone, message))
            if results[-1].success:
                time.sleep(1)
        return results

    def get_balance(self) -> float:
        # این API روتر استعلام USSD ندارد
        return 0.0

    def get_modem_info(self) -> ModemInfo:
        return self.info

    # ---------- پایش صندوق دریافت ----------
    def _start_polling(self):
        self._stop_polling()
        self._poll_stop.clear()
        self._seen_ids.clear()
        self._first_poll = True
        self._poll_thread = Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _stop_polling(self):
        self._poll_stop.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=3)
        self._poll_thread = None

    def _poll_loop(self):
        while not self._poll_stop.is_set():
            try:
                self.poll_inbox()
            except RouterAuthError:
                logger.warning("Router polling: session lost, stopping poll thread")
                return
            except Exception:
                logger.exception("Router inbox polling failed")
            self._poll_stop.wait(self.POLL_INTERVAL)

    def poll_inbox(self) -> int:
        """خواندن صندوق دریافت؛ خروجی: تعداد پیام تازهٔ ارسال‌شده به callback"""
        if not self.is_connected():
            return 0
        client = self._client_for(self.selected_host)
        new_messages: List[RouterMessage] = []
        # صفحه‌بندی روتر ۳۰تایی است؛ چند صفحهٔ اول برای پوشش پیام‌های خوانده‌نشده کافی است
        for page in (1, 2, 3):
            messages = client.list_sms(list_type=0, page=page)
            if not messages:
                break
            for msg in messages:
                if msg.id in self._seen_ids:
                    continue
                self._seen_ids[msg.id] = None
                if len(self._seen_ids) > self.MAX_SEEN:
                    self._seen_ids.pop(next(iter(self._seen_ids)))
                if not msg.read:
                    new_messages.append(msg)
        if self._first_poll:
            # اولین خواندن پس از اتصال فقط بذر dedupe است تا پیام‌های قدیمی
            # خوانده‌نشده دوباره در سابقه ثبت نشوند
            self._first_poll = False
            return 0
        emitted = 0
        for msg in new_messages:
            callback = self.on_incoming_sms
            if callback is None:
                break
            try:
                callback(msg.address, msg.text, msg.received_at)
                emitted += 1
            except Exception:
                logger.exception("Incoming router SMS callback failed (from=%s)", msg.address)
        if emitted:
            logger.info("Emitted %d incoming SMS from router %s", emitted, self.selected_host)
        return emitted


router_pool = RouterModemPool()
