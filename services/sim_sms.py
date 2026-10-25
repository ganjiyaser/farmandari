import serial
import serial.tools.list_ports
import time
import logging
import re
import subprocess
import threading
import queue
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Thread, Event

logger = logging.getLogger(__name__)


class ModemStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    READY = "ready"


class InternetStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ModemInfo:
    port: str = ""
    manufacturer: str = ""
    model: str = ""
    imei: str = ""
    signal_strength: int = 0
    status: ModemStatus = ModemStatus.DISCONNECTED
    sim_ready: bool = False
    sim_number: str = ""
    operator: str = ""
    network_type: str = ""


@dataclass
class InternetInfo:
    status: InternetStatus = InternetStatus.DISCONNECTED
    apn: str = ""
    ip_address: str = ""
    dns1: str = ""
    dns2: str = ""
    interface_name: str = ""
    connection_time: float = 0
    bytes_sent: int = 0
    bytes_received: int = 0


@dataclass
class SIMSMSResult:
    success: bool
    message_id: str = ""
    error: str = ""
    raw_response: str = ""


@dataclass
class DetectedModem:
    """نتیجهٔ شناسایی یک پورت COM"""
    port: str = ""
    description: str = ""
    manufacturer: str = ""
    is_modem: bool = False
    in_use: bool = False
    detail: str = ""
    baud: int = 0


# کلیدواژه‌هایی که احتمال مودم بودن پورت را بالا می‌برند؛ فقط برای اولویت‌دهی
# استفاده می‌شوند، نه حذف — مودم‌های USB-سریال عمومی ممکن است هیچ‌کدام را نداشته باشند.
MODEM_HINTS = (
    "modem", "hspa", "hsupa", "hsdpa", "gprs", "gsm", "umts", "wwan", "lte",
    "zte", "huawei", "sierra", "quectel", "simcom", "telit", "option",
    "broadband", "mobile", "3g", "4g", "5g",
)

# پورت‌هایی که پروب AT روی آن‌ها بی‌فایده است (باز کردن پورت بلوتوث می‌تواند
# دقیقه‌ها معلق بماند)
SKIP_PROBE_HINTS = ("bluetooth", "bthmodem", "bluetooth link")

# کد وضعیت گزارش تحویل (TP-ST در 3GPP TS 23.040)
DELIVERY_STATUS_REASONS = {
    0: "",
    1: "تحویل تایید نشد",
    2: "پیامک با پیامک دیگری جایگزین شد",
    0x20: "ازدحام شبکه",
    0x21: "مشترک مشغول است",
    0x22: "پاسخی از مشترک دریافت نشد",
    0x23: "سرویس رد شد",
    0x24: "کیفیت سرویس کافی نبود",
    0x25: "خطا در دستگاه مشترک",
    0x40: "خطای رویهٔ از راه دور",
    0x41: "مقصد ناسازگار",
    0x42: "ارتباط توسط مشترک رد شد",
    0x43: "اطلاعات در دسترس نیست",
    0x44: "کیفیت سرویس در دسترس نیست",
    0x45: "همکاری بین‌شبکه‌ای موجود نیست",
    0x46: "اعتبار پیامک به پایان رسید",
    0x47: "پیامک توسط فرستنده حذف شد",
    0x48: "پیامک توسط مرکز مدیریت حذف شد",
    0x49: "پیامک موجود نیست",
}


def delivery_reason(st: int) -> str:
    """توضیح فارسی کد وضعیت گزارش تحویل (خالی = تحویل شده)"""
    if st in DELIVERY_STATUS_REASONS:
        return DELIVERY_STATUS_REASONS[st]
    if st & 0x60:
        return f"خطای دائم شبکه (کد {st})"
    return f"عدم تحویل (کد {st})"


def parse_cds_text(payload: str):
    """استخراج (mr, st) از +CDS حالت متنی

    قالب (3GPP TS 27.005): +CDS: <fo>,<mr>,[<ra>],[<tora>],<scts>,<dt>,<st>
    """
    parts = [p.strip().strip('"') for p in payload.split(",")]
    if len(parts) < 3:
        return None
    try:
        mr = int(parts[1])
    except ValueError:
        return None
    st = None
    for token in reversed(parts):
        if re.fullmatch(r'\d+', token):
            st = int(token)
            break
    if st is None:
        return None
    return mr, st


def parse_cds_pdu(pdu_hex: str):
    """استخراج (mr, st) از PDU گزارش وضعیت

    ساختار: [SCA][FO][MR][RA][SCTS 7][DT 7][ST] — فقط MR و آخرین بایت لازم است.
    """
    clean = re.sub(r'[^0-9A-Fa-f]', '', pdu_hex or "")
    if len(clean) < 8:
        return None
    try:
        sca_len = int(clean[0:2], 16)
        tpdu_start = 1 + (sca_len + 1) // 2
        mr = int(clean[tpdu_start * 2 + 2: tpdu_start * 2 + 4], 16)
        st = int(clean[-2:], 16)
    except ValueError:
        return None
    return mr, st


class SIMCardModem:
    """ارسال پیامک و اتصال اینترنت از طریق سیمکارت و مودم USB با دستورات AT"""

    def __init__(self):
        self.serial = None
        self.port = None
        self.baud_rate = 115200
        self.info = ModemInfo()
        self.internet = InternetInfo()
        self._read_thread = None
        self._stop_event = Event()
        # پورت سریال از سه مسیر (مانیتور اینترنت، ارسال، استعلام موجودی/سیگنال)
        # همزمان استفاده می‌شود؛ بدون قفل، پاسخ‌های AT قاطی و متن پیامک آلوده
        # می‌شود. RLock تا فراخوانی‌های تودرتو (مانیتور→_query_at) ایمن باشد.
        self._serial_lock = threading.RLock()
        self._response_buffer = []
        self._callback = None
        self._internet_monitor_thread = None
        self._apn = ""
        self._apn_user = ""
        self._apn_pass = ""
        # گزارش تحویل: مودم به‌صورت خودجوش +CDS می‌فرستد؛ باید همیشه یک نخ
        # گوش‌دهنده فعال باشد وگرنه تاییدیه‌ها در بافر سریال گم می‌شوند.
        self.on_delivery_report = None
        self.delivery_reports_enabled = False
        self._listener_thread = None
        self._listener_stop = Event()
        self._unsolicited_buf = ""
        self._pending_pdu = False
        self._unsolicited_lock = threading.Lock()
        # پیامک دریافتی: mt=2 یعنی +CMT مستقیم می‌آید؛ mt=1 یعنی اعلان +CMTI
        # و خواندن با AT+CMGR. هر دو حالت پشتیبانی می‌شود.
        self.on_incoming_sms = None
        self.incoming_direct = False
        self._pending_cmt = None  # (number, scts) تا خط متن برسد
        self._cmti_queue = None  # type: Optional[queue.Queue]
        self._cmti_thread = None
        self._recent_incoming = {}  # type: Dict[str, float]

    def scan_ports(self) -> List[Dict[str, str]]:
        """اسکن پورت‌های COM موجود"""
        try:
            ports = serial.tools.list_ports.comports()
            result = []
            for port in ports:
                result.append({
                    'port': port.device,
                    'description': port.description,
                    'manufacturer': port.manufacturer or '',
                    'hwid': port.hwid or '',
                })
            return result
        except Exception as e:
            logger.error(f"Port scan error: {e}")
            return []

    def probe_port(self, port: str, baud_rate: int = 115200, timeout: float = 0.8) -> DetectedModem:
        """باز کردن پورت و پرسیدن AT؛ اگر «OK» بیاید یعنی مودم است"""
        if self.serial and self.serial.is_open and self.port == port:
            return DetectedModem(port=port, is_modem=True, in_use=True,
                                 detail="در حال استفاده توسط برنامه", baud=baud_rate)

        ser = None
        try:
            ser = serial.Serial(port=port, baudrate=baud_rate, timeout=0.3, write_timeout=1)
            ser.reset_input_buffer()
            ser.write(b"AT\r")
            buffer = ""
            end_time = time.time() + timeout
            while time.time() < end_time:
                waiting = ser.in_waiting
                if waiting:
                    buffer += ser.read(waiting).decode('utf-8', errors='ignore')
                    if "OK" in buffer:
                        return DetectedModem(port=port, is_modem=True, baud=baud_rate)
                time.sleep(0.05)
            return DetectedModem(port=port, is_modem=False, baud=baud_rate,
                                 detail=(buffer.strip()[:60] or "پاسخی دریافت نشد"))
        except PermissionError:
            return DetectedModem(port=port, is_modem=False, in_use=True,
                                 detail="پورت در اختیار برنامهٔ دیگری است")
        except OSError as e:
            # درایور بارگذاری نشده (مثل Code 39 ویندوز) هم به همین شکل ظاهر می‌شود
            return DetectedModem(port=port, is_modem=False, detail=str(e)[:80])
        except Exception as e:
            return DetectedModem(port=port, is_modem=False, detail=str(e)[:80])
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    def detect_modems(self, baud_rates=(115200, 9600)) -> List[DetectedModem]:
        """شناسایی مودم بین همهٔ پورت‌های COM متصل به سیستم

        پورت‌هایی که توضیح درایورشان نشانهٔ مودم دارد اول پروب می‌شوند و اگر
        پاسخ ندادند با Baud پایین‌تر هم امتحان می‌شوند.
        """
        results: List[DetectedModem] = []
        try:
            ports = self.scan_ports()
        except Exception as e:
            logger.error(f"Modem detection error: {e}")
            return results

        def rank(p):
            text = " ".join(filter(None, (p.get('description'), p.get('manufacturer'), p.get('hwid')))).lower()
            hinted = any(k in text for k in MODEM_HINTS)
            return (0 if hinted else 1), p.get('port', '')

        for p in sorted(ports, key=rank):
            port = p.get('port', '')
            text = " ".join(filter(None, (p.get('description'), p.get('manufacturer')))).lower()
            detected = None
            if any(k in text for k in SKIP_PROBE_HINTS):
                detected = DetectedModem(port=port, is_modem=False, detail="پورت بلوتوث")
            else:
                hinted = any(k in text for k in MODEM_HINTS)
                tries = baud_rates if hinted else baud_rates[:1]
                for baud in tries:
                    detected = self.probe_port(port, baud)
                    if detected.is_modem:
                        break

            detected.description = p.get('description', '')
            detected.manufacturer = p.get('manufacturer', '')
            results.append(detected)

        return results

    def connect(self, port: str, baud_rate: int = 115200, pin: str = None) -> bool:
        """اتصال به مودم

        Args:
            port: پورت سریال (مثال: COM3)
            baud_rate: نرخ باند (پیش‌فرض 115200)
            pin: کد PIN سیمکارت (اختیاری). اگر سیمکارت قفل شده باشد، این کد ارسال می‌شود.
        """
        # اتصال مجدد: پورت باز قبلی باید بسته شود وگرنه ویندوز آن را قفل
        # می‌کند و باز کردن دوباره با PermissionError رد می‌شود
        if self.serial is not None:
            try:
                if self.serial.is_open:
                    self.serial.close()
            except Exception:
                pass
            self.serial = None
        try:
            self.port = port
            self.baud_rate = baud_rate
            self.info.status = ModemStatus.CONNECTING
            self.info.port = port

            self.serial = serial.Serial(
                port=port,
                baudrate=baud_rate,
                timeout=3,
                write_timeout=3,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )

            time.sleep(1)

            if not self._send_at_command("AT"):
                self.info.status = ModemStatus.ERROR
                self._close_failed_port()
                return False

            # بررسی وضعیت PIN سیمکارت
            sim_status = self._query_at("AT+CPIN?")
            if sim_status:
                if "SIM PIN" in sim_status:
                    if pin:
                        if not self._send_at_command(f'AT+CPIN="{pin}"'):
                            self.info.status = ModemStatus.ERROR
                            self._close_failed_port()
                            return False
                        time.sleep(2)
                        # بررسی مجدد پس از وارد کردن PIN
                        sim_status = self._query_at("AT+CPIN?")
                    else:
                        logger.warning("SIM PIN required but not provided")
                        self.info.status = ModemStatus.ERROR
                        self._close_failed_port()
                        return False
                if "READY" in sim_status:
                    self.info.sim_ready = True

            self._send_at_command("AT+CMGF=1")
            # UCS2 (UTF-16BE) برای پشتیبانی از حروف فارسی؛ با GSM=«7بیتی»
            # متن فارسی به‌صورت mojibake یا رد‌شده تحویل می‌شد.
            self._send_at_command("AT+CSCS=\"UCS2\"")
            # DCS=8 → کدگذاری UCS2 در شبکه تا گیرنده درست رمزگشایی کند
            self._send_at_command("AT+CSMP=17,167,0,8")

            # خواندن/تنظیم آدرس مرکز پیامک (SMSC)
            # اگر SMSC تنظیم نشده باشد، ارسال پیامک شکست می‌خورد
            smsc = self._query_at("AT+CSCA?")
            if smsc and '""' in smsc:
                # SMSC خالی است - تلاش برای تنظیم خودکار (بعضی مودم‌ها از سیمکارت می‌خوانند)
                logger.info("SMSC not set, attempting auto-config...")
                # در بسیاری از مودم‌ها SMSC از سیمکارت خوانده می‌شود؛ اینجا فقط لاگ می‌کنیم

            # ds=2 → گزارش تحویل (+CDS) مستقیم به برنامه فرستاده شود (نه در حافظهٔ مودم)
            # mt=2 → پیام دریافتی به‌صورت +CMT مستقیم برسد و نیازی به AT+CMGR نباشد
            if self._send_at_command("AT+CNMI=2,2,0,2,0"):
                self.incoming_direct = True
                self.delivery_reports_enabled = True
            elif self._send_at_command("AT+CNMI=2,1,0,2,0"):
                # برخی مودم‌ها mt=2 را رد می‌کنند → اعلان +CMTI و خواندن از حافظه
                self.incoming_direct = False
                self.delivery_reports_enabled = True
            else:
                self.incoming_direct = False
                self.delivery_reports_enabled = self._send_at_command("AT+CNMI=2,1,0,1,0")
            logger.info(
                "Incoming SMS mode: %s",
                "+CMT direct" if self.incoming_direct else "+CMTI storage",
            )

            self.info.manufacturer = self._clean_at_value(self._query_at("AT+CGMI")) or "Unknown"
            self.info.model = self._clean_at_value(self._query_at("AT+CGMM")) or "Unknown"
            self.info.imei = self._clean_at_value(self._query_at("AT+CGSN"))

            signal = self._query_at("AT+CSQ")
            if signal:
                match = re.search(r'\+CSQ:\s*(\d+)', signal)
                if match:
                    self.info.signal_strength = int(match.group(1))

            if self.info.sim_ready:
                msisdn = self._query_at("AT+CNUM")
                if msisdn:
                    match = re.search(r'\+CNUM:.*?"(\d+)"', msisdn)
                    if match:
                        self.info.sim_number = match.group(1)

                operator = self._query_at("AT+COPS?")
                if operator:
                    match = re.search(r'\+COPS:\s*\d+,\d+,"([^"]+)"', operator)
                    if match:
                        self.info.operator = match.group(1)

            self.info.status = ModemStatus.READY
            self._start_delivery_listener()
            return True

        except serial.SerialException as e:
            logger.error(f"Serial port error: {e}")
            self.info.status = ModemStatus.ERROR
            self._close_failed_port()
            return False

    def _close_failed_port(self):
        """بستن پورت پس از اتصال ناموفق تا در ویندوز برای اتصال بعدی قفل نماند"""
        if self.serial is not None:
            try:
                if self.serial.is_open:
                    self.serial.close()
            except Exception:
                pass
            self.serial = None

    def disconnect(self):
        """قطع اتصال"""
        self._stop_delivery_listener()
        self.disconnect_internet()
        self._stop_event.set()
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2)

        if self.serial and self.serial.is_open:
            self.serial.close()

        self.info.status = ModemStatus.DISCONNECTED
        self.serial = None

    def is_connected(self) -> bool:
        return self.serial and self.serial.is_open and self.info.status == ModemStatus.READY

    @staticmethod
    def _clean_at_value(response: str) -> str:
        """مقدار خالص از پاسخ AT: بدون پژواک دستور و بدون خط‌های OK/ERROR"""
        if not response:
            return ""
        for line in re.split(r'\r\n|\r|\n', response):
            value = line.strip()
            if not value or value in ("OK", "ERROR"):
                continue
            if value.startswith(("+CME ERROR", "+CMS ERROR", "AT+")):
                continue
            return value
        return ""

    def send_sms(self, phone_number: str, message: str) -> SIMSMSResult:
        """ارسال پیامک با سیمکارت (متن فارسی با UCS2)"""
        if not self.is_connected():
            return SIMSMSResult(success=False, error="Modem not connected")
        if not self.info.sim_ready:
            return SIMSMSResult(success=False, error="SIM not ready (PIN required or SIM error)")

        phone_number = self._clean_phone_number(phone_number)

        with self._serial_lock:
            try:
                # اطمینان از حالت UCS2 (ممکن است مانیتور/سایر مسیرها تغییرش دهند)
                self._send_at_command("AT+CMGF=1")
                self._send_at_command("AT+CSCS=\"UCS2\"")
                self._send_at_command("AT+CSMP=17,167,0,8")

                self._flush_serial_input()

                # در حالت CSCS="UCS2" هم شماره و هم متن باید به‌صورت HEXِ
                # UCS2 (UTF-16BE) ارسال شوند (طبق 3GPP TS 27.005).
                da_hex = self._to_ucs2_hex(phone_number)
                cmd = f'AT+CMGS="{da_hex}"\r'
                self.serial.write(cmd.encode('ascii'))

                response = self._read_response(timeout=5, terminators=(">",))
                if ">" not in response and "CMGS" not in response:
                    return SIMSMSResult(
                        success=False,
                        error=f"Modem not ready for CMGS: {response}",
                        raw_response=response
                    )

                message_hex = self._to_ucs2_hex(message)
                self.serial.write(message_hex.encode('ascii'))
                self.serial.write(b"\x1a")  # Ctrl-Z = پایان متن

                # مرکز پیام تا چند ثانیه بعد از Ctrl-Z پاسخ می‌دهد؛ خواندن با
                # خروج زودتر به‌محض دیدن OK/+CMGS از هدر‌رفتن وقت جلوگیری می‌کند.
                final_response = self._read_response(timeout=30)

                if "+CMGS:" in final_response:
                    match = re.search(r'\+CMGS:\s*(\d+)', final_response)
                    msg_id = match.group(1) if match else ""
                    return SIMSMSResult(
                        success=True,
                        message_id=msg_id,
                        raw_response=final_response
                    )
                elif "OK" in final_response:
                    return SIMSMSResult(success=True, raw_response=final_response)
                elif "ERROR" in final_response:
                    # تلاش برای استخراج کد خطای CMS
                    cms_match = re.search(r'\+CMS ERROR:\s*(\d+)', final_response)
                    if cms_match:
                        code = int(cms_match.group(1))
                        error_msg = self._cms_error_str(code)
                        return SIMSMSResult(
                            success=False,
                            error=f"CMS Error {code}: {error_msg}",
                            raw_response=final_response
                        )
                    return SIMSMSResult(
                        success=False,
                        error=f"Send failed: {final_response}",
                        raw_response=final_response
                    )
                else:
                    return SIMSMSResult(
                        success=False,
                        error=f"Unexpected response: {final_response}",
                        raw_response=final_response
                    )

            except Exception as e:
                logger.error(f"SMS send error: {e}")
                return SIMSMSResult(success=False, error=str(e))

    def _cms_error_str(self, code: int) -> str:
        """توضیح فارسی کدهای خطای +CMS ERROR (3GPP TS 27.005)"""
        errors = {
            1: "Unassigned number",
            8: "Operator determined barring",
            10: "Call barred",
            17: "Network failure",
            21: "Short message transfer rejected",
            22: "Memory capacity exceeded",
            27: "Destination out of service",
            28: "Unidentified subscriber",
            29: "Facility rejected",
            30: "Unknown subscriber",
            38: "Network out of order",
            41: "Temporary failure",
            42: "Congestion",
            47: "Resources unavailable, unspecified",
            50: "Requested facility not subscribed",
            69: "Requested facility not implemented",
            81: "Invalid short message transfer reference value",
            95: "Invalid message, unspecified",
            96: "Invalid mandatory information",
            97: "Message type non-existent or not implemented",
            98: "Message not compatible with short message protocol state",
            99: "Information element non-existent or not implemented",
            111: "Protocol error, unspecified",
            127: "Interworking, unspecified",
            128: "Telematic interworking not supported",
            129: "Short message type 0 not supported",
            130: "Cannot replace short message",
            143: "Unspecified TP-PID error",
            144: "Data coding scheme not supported",
            145: "Message class not supported",
            159: "Unspecified TP-DCS error",
            160: "Command cannot be actioned",
            161: "Command unsupported",
            162: "Unspecified TP-Command error",
            167: "Extended internal error",
            168: "Unspecified error",
            171: "Wrong SMSC address",
            172: "SMSC busy",
            173: "SMSC no response",
            174: "SMSC timeout",
            175: "SMSC delivery failed",
            255: "Unspecified error cause",
            300: "ME failure",
            301: "SMS service of ME reserved",
            302: "Operation not allowed",
            303: "Operation not supported",
            304: "Invalid PDU mode parameter",
            305: "Invalid text mode parameter",
            310: "SIM not inserted",
            311: "SIM PIN required",
            312: "PH-SIM PIN required",
            313: "SIM failure",
            314: "SIM busy",
            315: "SIM wrong",
            316: "SIM PUK required",
            317: "SIM PIN2 required",
            318: "SIM PUK2 required",
            320: "Memory failure",
            321: "Invalid memory index",
            322: "Memory full",
            330: "SMSC address unknown",
            331: "No network service",
            332: "Network timeout",
            340: "No +CNMA acknowledgement expected",
            500: "Unknown error",
            512: "User abort",
            513: "Unable to store",
            514: "Invalid status",
            515: "Invalid character in address string",
            516: "Invalid character in text",
        }
        return errors.get(code, f"Unknown error code {code}")

    @staticmethod
    def _to_ucs2_hex(text: str) -> str:
        """تبدیل متن به رشتهٔ HEX بر پایهٔ UCS2 (UTF-16BE) برای ارسال AT"""
        return text.encode('utf-16-be').hex().upper()

    def send_bulk_sms(self, phone_numbers: List[str], message: str) -> List[SIMSMSResult]:
        """ارسال گروهی پیامک"""
        results = []
        for phone in phone_numbers:
            result = self.send_sms(phone, message)
            results.append(result)
            if result.success:
                time.sleep(2)
        return results

    def connect_internet(self, apn: str, username: str = "", password: str = "") -> bool:
        """اتصال اینترنت از طریق مودم"""
        if not self.is_connected():
            logger.error("Modem not connected")
            return False

        try:
            self._apn = apn
            self._apn_user = username
            self._apn_pass = password

            self.internet.status = InternetStatus.CONNECTING
            self.internet.apn = apn

            self._send_at_command("AT+CFUN=1")
            time.sleep(1)

            if username and password:
                self._send_at_command(f'AT+CGDCONT=1,"IP","{apn}"')
                self._send_at_command(f'AT+CGAUTH=1,1,"{password}","{username}"')
            else:
                self._send_at_command(f'AT+CGDCONT=1,"IP","{apn}"')

            time.sleep(1)

            activate = self._query_at("AT+CGACT=1,1")
            if "ERROR" in (activate or ""):
                self.internet.status = InternetStatus.ERROR
                return False

            time.sleep(2)

            ip_response = self._query_at("AT+CGPADDR=1")
            if ip_response:
                match = re.search(r'\+CGPADDR:\s*1,"([^"]+)"', ip_response)
                if match:
                    self.internet.ip_address = match.group(1)

            dns_response = self._query_at("AT+CDNSCFG?")
            if dns_response:
                match = re.search(r'\+CDNSCFG:\s*"[^"]*","([^"]+)","([^"]+)"', dns_response)
                if match:
                    self.internet.dns1 = match.group(1)
                    self.internet.dns2 = match.group(2)

            self.internet.status = InternetStatus.CONNECTED
            self.internet.connection_time = time.time()

            self._start_internet_monitor()

            logger.info(f"Internet connected via APN: {apn}, IP: {self.internet.ip_address}")
            return True

        except Exception as e:
            logger.error(f"Internet connection error: {e}")
            self.internet.status = InternetStatus.ERROR
            return False

    def disconnect_internet(self):
        """قطع اتصال اینترنت"""
        self._stop_internet_monitor()

        if self.is_connected():
            self._send_at_command("AT+CGACT=0,1")

        self.internet.status = InternetStatus.DISCONNECTED
        self.internet.ip_address = ""
        self.internet.connection_time = 0

    def is_internet_connected(self) -> bool:
        return self.internet.status == InternetStatus.CONNECTED

    def get_internet_info(self) -> InternetInfo:
        return self.internet

    def get_balance(self) -> float:
        """موجودی سیمکارت با USSD

        دو نکته: با CSCS="UCS2" رشتهٔ شماره‌گیری هم باید UCS2 hex باشد؛ و
        پاسخ +CUSD معمولاً بعد از OKِ دستور، خودجوش می‌رسد — پس باید مستقیم
        از پورت خوانده شود، نه از پاسخِ همان دستور.
        """
        if not self.is_connected():
            return 0.0
        result = 0.0
        with self._serial_lock:
            try:
                self._send_at_command('AT+CSCS="GSM"')
                self._flush_serial_input()
                self.serial.write(b'AT+CUSD=1,"*140*1*1#",15\r')
                buffer = ""
                end_time = time.time() + 25
                while time.time() < end_time:
                    if self.serial.in_waiting:
                        chunk = self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
                        buffer += chunk
                        self._feed_unsolicited(chunk)
                        if "+CUSD:" in buffer and self._is_final_at_line(buffer):
                            break
                    time.sleep(0.1)
                result = self._parse_ussd_balance(buffer)
            except Exception as e:
                logger.error(f"USSD balance error: {e}")
            finally:
                # بازگرداندن charset به UCS2 برای ادامهٔ کار پیامک
                try:
                    self._send_at_command('AT+CSCS="UCS2"')
                except Exception:
                    pass
        return result

    @staticmethod
    def _parse_ussd_balance(raw: str) -> float:
        """استخراج اولین عدد از پاسخ USSD (متن ساده یا هگز UCS2)"""
        m = re.search(r'\+CUSD:\s*(\d+)\s*,\s*"([^"]*)"', raw or "")
        if not m:
            return 0.0
        text = m.group(2)
        # برخی مودم‌ها متن پاسخ را با DCS=72 به‌صورت هگز UCS2 می‌دهند
        if re.fullmatch(r'(?:[0-9A-Fa-f]{4})+', text or ""):
            try:
                decoded = bytes.fromhex(text).decode('utf-16-be')
                if decoded.strip():
                    text = decoded
            except Exception:
                pass
        # ماندهٔ ریالی بزرگ معمولاً جداکنندهٔ هزارگان دارد («12,500»)؛ اگر
        # کاما را ممیز فرض کنیم ۱۲٬۵۰۰ به‌اشتباه ۱۲٫۵ نمایش داده می‌شود.
        # پس اول الگوی هزارگان (کاما + دقیقاً ۳ رقم) را می‌گیریم و کاماها را
        # حذف می‌کنیم؛ در غیر این صورت کاما را ممیز تلقی می‌کنیم.
        m = re.search(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?', text)
        if m:
            num = m.group(0).replace(',', '')
        else:
            m = re.search(r'\d+(?:[.,]\d+)?', text)
            if not m:
                return 0.0
            num = m.group(0).replace(',', '.')
        try:
            return float(num)
        except ValueError:
            return 0.0

    def get_signal_strength(self) -> int:
        """قدرت سیگنال"""
        if not self.is_connected():
            return 0
        response = self._query_at("AT+CSQ")
        if response:
            match = re.search(r'\+CSQ:\s*(\d+)', response)
            if match:
                return int(match.group(1))
        return 0

    def get_modem_info(self) -> ModemInfo:
        if self.is_connected():
            self.info.signal_strength = self.get_signal_strength()
        return self.info

    def _start_internet_monitor(self):
        """شروع مانیتورینگ اتصال اینترنت"""
        self._stop_internet_monitor()
        # رویداد توقف باید پاک شود؛ وگرنه بعد از اولین disconnect/reconnect
        # مانیتور برای همیشه مرده می‌ماند (حلقه بلافاصله شرط را true می‌بیند).
        self._stop_event.clear()
        self._internet_monitor_thread = Thread(target=self._monitor_internet, daemon=True)
        self._internet_monitor_thread.start()

    def _stop_internet_monitor(self):
        """توقف مانیتورینگ"""
        if self._internet_monitor_thread and self._internet_monitor_thread.is_alive():
            self._stop_event.set()
            self._internet_monitor_thread.join(timeout=2)

    def _monitor_internet(self):
        """مانیتورینگ وضعیت اتصال اینترنت"""
        while not self._stop_event.is_set():
            if self.is_connected():
                response = self._query_at("AT+CGACT?")
                if response:
                    if "+CGACT: 1,1" in response:
                        self.internet.status = InternetStatus.CONNECTED
                    else:
                        self.internet.status = InternetStatus.DISCONNECTED
                        self.disconnect_internet()
                        break

                signal = self.get_signal_strength()
                self.info.signal_strength = signal

            time.sleep(10)

    # ---------- گزارش تحویل پیامک (Delivery Report / +CDS) ----------

    def _start_delivery_listener(self):
        """شروع نخ گوش‌دهندهٔ گزارش تحویل و پیامک دریافتی"""
        self._stop_delivery_listener()
        self._listener_stop.clear()
        self._unsolicited_buf = ""
        self._pending_pdu = False
        self._pending_cmt = None
        self._cmti_queue = queue.Queue()
        self._cmti_thread = Thread(target=self._cmti_worker, args=(self._cmti_queue,), daemon=True)
        self._cmti_thread.start()
        self._listener_thread = Thread(target=self._listen_unsolicited, daemon=True)
        self._listener_thread.start()

    def _stop_delivery_listener(self):
        """توقف نخ گوش‌دهندهٔ گزارش تحویل و پیامک دریافتی"""
        self._listener_stop.set()
        if self._cmti_queue is not None:
            # بیدار کردن نخ خواندن +CMTI تا در انتظار نماند
            try:
                self._cmti_queue.put_nowait(None)
            except Exception:
                pass
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2)
        if self._cmti_thread and self._cmti_thread.is_alive():
            self._cmti_thread.join(timeout=3)
        self._listener_thread = None
        self._cmti_thread = None
        self._cmti_queue = None

    def _listen_unsolicited(self):
        """خواندن مداوم پورت و جدا کردن خطوط خودجوش مودم

        قفل سریال فقط برای خواندن کوتاه گرفته می‌شود و هرگز هنگام خواب نگه
        داشته نمی‌شود؛ دستورات AT کل چرخهٔ نوشتن/خواندن را در قفل انجام
        می‌دهند، پس گوش‌دهنده نمی‌تواند پاسخ آن‌ها را بدزدد.
        """
        while not self._listener_stop.is_set():
            try:
                if not (self.serial and self.serial.is_open):
                    break
                if self.serial.in_waiting:
                    with self._serial_lock:
                        raw = self.serial.read(self.serial.in_waiting)
                    self._feed_unsolicited(raw.decode('utf-8', errors='ignore'))
            except Exception as e:
                logger.debug("Delivery listener stopped: %s", e)
                break
            time.sleep(0.1)

    def _feed_unsolicited(self, text: str):
        """افزودن متن خام به بافر و پردازش خطوط کامل

        خطوط ناقص در بافر می‌مانند تا خط بعدی برسد؛ داده‌های غیرگزارش (پاسخ
        دستورات) نادیده گرفته می‌شوند.
        """
        with self._unsolicited_lock:
            self._unsolicited_buf += text
            lines = re.split(r'\r\n|\r|\n', self._unsolicited_buf)
            self._unsolicited_buf = lines.pop() if lines else ""
            for line in lines:
                self._dispatch_unsolicited(line.strip())

    def _dispatch_unsolicited(self, line: str):
        """پردازش یک خط خودجوش: پیامک دریافتی، گزارش تحویل متنی یا PDU"""
        if not line:
            return
        if self._pending_pdu:
            # خط بعد از «+CDS: <length>» خودِ PDU است
            self._pending_pdu = False
            parsed = parse_cds_pdu(line)
            if parsed:
                self._emit_delivery_report(*parsed)
            return
        if self._pending_cmt is not None and not line.startswith("+"):
            # خط بعد از «+CMT: ...» متن پیام است
            if line.upper() not in ("OK", "ERROR"):
                number, scts = self._pending_cmt
                self._pending_cmt = None
                self._emit_incoming_sms(number, line, scts)
            else:
                # هدر با متن خالی آمد؛ پاک شود تا هدر بعدی بلعیده نشود
                self._pending_cmt = None
            return
        # هدرهای دیگر (+CDS و…) نباید در انتظار متن +CMT بمانند
        self._pending_cmt = None
        upper = line.upper()
        if upper.startswith("+CMTI:"):
            index = self._parse_cmti_index(line)
            if index is not None:
                # خواندن حافظهٔ مودم فقط در نخ جدا؛ قفل _unsolicited_lock اینجا
                # گرفته شده و AT زدن همان‌جا باعث قفل شدگی (deadlock) می‌شود.
                if self._cmti_queue is not None:
                    self._cmti_queue.put(index)
            return
        if upper.startswith("+CMT:"):
            header = line.split(":", 1)[1].strip()
            number = self._first_quoted(header) or ""
            self._pending_cmt = (number, self._extract_scts(header))
            return
        if not upper.startswith("+CDS:"):
            return
        payload = line.split(":", 1)[1].strip()
        if re.fullmatch(r'\d+', payload):
            self._pending_pdu = True
            return
        parsed = parse_cds_text(payload)
        if parsed:
            self._emit_delivery_report(*parsed)

    @staticmethod
    def _parse_cmti_index(line: str) -> Optional[int]:
        """استخراج شمارهٔ ایندکس از «+CMTI: "SM",<idx>»"""
        payload = line.split(":", 1)[1] if ":" in line else ""
        numbers = re.findall(r'\d+', payload)
        return int(numbers[-1]) if numbers else None

    @staticmethod
    def _first_quoted(text: str) -> Optional[str]:
        match = re.search(r'"([^"]*)"', text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_scts(header: str) -> Optional[str]:
        """زمان مرکز پیام از هدر (+CMT/+CMGR) به‌صورت yy/MM/dd,hh:mm:ss±zz

        قالب استاندارد 3GPP ساعت منطقه را به‌صورت ±zz می‌دهد؛ برخی مودم‌ها
        ±zz:zz یا ±zzzz می‌فرستند که هر سه پذیرفته می‌شود.
        """
        pattern = r'(\d{2}/\d{2}/\d{2},\d{2}:\d{2}:\d{2}(?:[+-]\d{2}(?::\d{2})|[+-]\d{2,4})?)'
        match = re.search(pattern, header)
        return match.group(1) if match else None

    @staticmethod
    def _parse_scts(scts: Optional[str]) -> Optional[datetime]:
        if not scts:
            return None
        match = re.match(r'(\d{2})/(\d{2})/(\d{2})[, ]+(\d{2}):(\d{2}):(\d{2})', scts)
        if not match:
            return None
        year, month, day, hour, minute, second = (int(g) for g in match.groups())
        try:
            return datetime(2000 + year, month, day, hour, minute, second)
        except ValueError:
            return None

    def _cmti_worker(self, pending: "queue.Queue"):
        """خواندن پیام‌های اعلان‌شده با +CMTI از حافظهٔ مودم

        AT+CMGR باید دور از _unsolicited_lock اجرا شود؛ شنونده هنگام صدا زدن
        این متد قفل را در اختیار دارد و اجرای هم‌روند آن قفل می‌گرفت.
        """
        while not self._listener_stop.is_set():
            try:
                index = pending.get(timeout=0.5)
            except Exception:
                continue
            if index is None:
                break
            try:
                self._read_stored_sms(int(index))
            except Exception:
                logger.exception("Could not read stored SMS index %s", index)

    def _read_stored_sms(self, index: int):
        """خواندن یک پیام از حافظهٔ مودم با AT+CMGR (این عمل پیام را خوانده می‌کند)"""
        response = self._query_at("AT+CMGR=%d" % index, timeout=4)
        if not response:
            return
        number = ""
        scts = None
        body = []
        in_body = False
        for line in re.split(r'\r\n|\r|\n', response):
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith("+CMGR:"):
                header = line.split(":", 1)[1]
                number = self._first_quoted(header) or ""
                scts = self._extract_scts(header)
                in_body = True
                body = []
                continue
            if in_body:
                if line in ("OK", "ERROR") or line.startswith("+CME ERROR") or line.startswith("+CMS ERROR"):
                    in_body = False
                    continue
                if re.match(r'^\+C[A-Z]+:', line):
                    # پاسخ به دستور دیگر یا گزارش تحویل که در میانه رسیده است
                    continue
                body.append(line)
        if in_body:
            self._emit_incoming_sms(number, "\n".join(body), scts)

    def _emit_incoming_sms(self, number: str, body: str, scts: Optional[str] = None):
        """اطلاع پیام دریافتی به callback ثبت‌شده"""
        text = self._decode_sms_body(body)
        number = self._decode_sms_body(number or "")
        if number:
            try:
                number = self._clean_phone_number(number)
            except Exception:
                pass
        if not text and not number:
            return
        now = time.time()
        key = "%s|%s|%s" % (number, scts or "", text)
        for stale_key, stamp in list(self._recent_incoming.items()):
            if now - stamp > 60:
                self._recent_incoming.pop(stale_key, None)
        if key in self._recent_incoming:
            # برخی مودم‌ها هم +CMT و هم +CMTI را برای یک پیام می‌فرستند
            logger.debug("Duplicate incoming SMS ignored (%s)", number)
            return
        self._recent_incoming[key] = now
        callback = self.on_incoming_sms
        received_at = self._parse_scts(scts)
        if callback is None:
            logger.info("Incoming SMS from %s (no callback registered)", number)
            return
        try:
            callback(number, text, received_at)
        except Exception:
            logger.exception("Incoming SMS callback failed (from=%s)", number)

    # بازهٔ کاراکترهایی که در متن پیامک معنی‌دارند؛ برای تشخیص اینکه آیا هگز
    # واقعاً UCS2 است یا صرفاً رشته‌ای که اتفاقی شبیه هگز است (مثل کد یکبارمصرف).
    # عمداً بدون CJK (3000-9FFF): متن ASCIIِ تصادفی‌نما مثل «48201176» در
    # UTF-16BE به همان محدوده رمزگشایی می‌شود و بدون این شرط به‌جای کد اصیل،
    # آشغال چینی برمی‌گشت. این برنامه هرگز پیامک چینی ارسال نمی‌کند.
    _TEXTISH = re.compile(
        "[\u0020-\u007E\u00A0-\u024F\u0600-\u06FF\u2000-\u206F"
        "\uFB50-\uFDFF\uFE70-\uFEFF\r\n\t]+"
    )

    @classmethod
    def _decode_sms_body(cls, body: str) -> str:
        """بازگرداندن متن UCS2 (هگز) که مودم با CSCS=UCS2 ارسال می‌کند

        متن انگلیسی به‌صورت 00xx00xx و متن فارسی به‌صورت هگز UTF-16BE می‌آید؛
        اگر رشتهٔ خام از قبل متن قابل خواندن باشد دست نمی‌خورد.
        """
        text = (body or "").strip()
        if len(text) < 4 or len(text) % 4 != 0 or not re.fullmatch(r'[0-9A-Fa-f]+', text):
            return text
        try:
            decoded = bytes.fromhex(text).decode("utf-16-be")
        except Exception:
            return text
        if not decoded or not cls._TEXTISH.fullmatch(decoded):
            return text
        if re.fullmatch(r'(?:00[0-9A-Fa-f]{2})+', text) or any(ord(ch) > 127 for ch in decoded):
            return decoded
        return text

    def _emit_delivery_report(self, mr: int, st: int):
        """اطلاع نتیجهٔ تحویل به callback ثبت‌شده"""
        callback = self.on_delivery_report
        if callback is None:
            logger.info("Delivery report mr=%s st=%s (no callback registered)", mr, st)
            return
        try:
            callback(int(mr), int(st))
        except Exception:
            logger.exception("Delivery report callback failed (mr=%s, st=%s)", mr, st)

    def _flush_serial_input(self):
        """تخلیهٔ بافر ورودی؛ دادهٔ خودجوش به‌جای حذف پردازش می‌شود"""
        try:
            if self.serial and self.serial.in_waiting:
                raw = self.serial.read(self.serial.in_waiting)
                self._feed_unsolicited(raw.decode('utf-8', errors='ignore'))
        except Exception:
            pass

    def _send_at_command(self, command: str, timeout: float = 3) -> bool:
        with self._serial_lock:
            try:
                self._flush_serial_input()
                self.serial.write((command + "\r").encode('ascii'))
                response = self._read_response(timeout)
                return "OK" in response
            except Exception as e:
                logger.error(f"AT command error: {e}")
                return False

    def _query_at(self, command: str, timeout: float = 3) -> Optional[str]:
        with self._serial_lock:
            try:
                self._flush_serial_input()
                self.serial.write((command + "\r").encode('ascii'))
                return self._read_response(timeout)
            except Exception as e:
                logger.error(f"AT query error: {e}")
                return None

    @staticmethod
    def _is_final_at_line(text: str) -> bool:
        """آیا پاسخ به خط پایانی رسیده است؟ (OK/ERROR/CME/CMS)"""
        for line in re.split(r'\r\n|\r|\n', text):
            line = line.strip()
            if line in ("OK", "ERROR"):
                return True
            if line.startswith("+CME ERROR") or line.startswith("+CMS ERROR"):
                return True
        return False

    def _read_response(self, timeout: float = 3, terminators=None, settle: float = 0.15) -> str:
        """خواندن پاسخ تا رسیدن خط پایانی یا چند میلی‌ثانیه سکوت

        بدون خروج زودتر، هر دستور AT تمام مهلت را می‌خوابید و اتصال/ارسال
        ده‌ها ثانیه طول می‌کشید.
        """
        terms = tuple(terminators) if terminators else ()
        buffer = ""
        end_time = time.time() + timeout
        settle_until = None
        while time.time() < end_time:
            if self.serial.in_waiting:
                chunk = self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
                buffer += chunk
                self._feed_unsolicited(chunk)
                if settle_until is None and (self._is_final_at_line(buffer) or any(t in buffer for t in terms)):
                    settle_until = time.time() + settle
            if settle_until is not None and time.time() >= settle_until:
                break
            time.sleep(0.05)
        return buffer

    def _clean_phone_number(self, number: str) -> str:
        number = number.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if number.startswith("0098"):
            number = "+98" + number[4:]
        elif number.startswith("+98"):
            pass
        elif number.startswith("098"):
            number = "+98" + number[3:]
        elif number.startswith("98"):
            number = "+" + number
        elif number.startswith("09"):
            number = "+98" + number[1:]
        else:
            number = "+98" + number
        return number

    def set_smsc(self, smsc_number: str) -> bool:
        """تنظیم آدرس مرکز پیامک (SMSC)

        Args:
            smsc_number: شماره مرکز پیامک با پیش‌شمارهٔ کشور (مثال: +989123456789)

        Returns:
            True اگر با موفقیت تنظیم شد
        """
        if not self.is_connected():
            return False
        # فرمت بین‌المللی برای AT+CSCA
        if not smsc_number.startswith("+"):
            smsc_number = "+" + smsc_number.lstrip("0")
        with self._serial_lock:
            try:
                self._flush_serial_input()
                self.serial.write(f'AT+CSCA="{smsc_number}"\r'.encode('ascii'))
                response = self._read_response(timeout=5)
                return "OK" in response
            except Exception as e:
                logger.error(f"Set SMSC error: {e}")
                return False

    def get_smsc(self) -> Optional[str]:
        """خواندن آدرس مرکز پیامک (SMSC) فعلی"""
        if not self.is_connected():
            return None
        with self._serial_lock:
            try:
                self._flush_serial_input()
                self.serial.write(b'AT+CSCA?\r')
                response = self._read_response(timeout=5)
                match = re.search(r'\+CSCA:\s*"([^"]+)"', response)
                if match:
                    return match.group(1)
            except Exception as e:
                logger.error(f"Get SMSC error: {e}")
        return None


sim_modem = SIMCardModem()
