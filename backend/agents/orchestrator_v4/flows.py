"""
Flow Definitions - Sabit randevu akışları ve konfigürasyon
Her flow step-by-step tanımlanmış, deterministik
"""

from typing import List, Dict, Optional
from enum import Enum

class FlowType(str, Enum):
    """Flow tipleri"""
    BOOKING = "booking"
    CANCEL = "cancel"
    QUERY = "query_appointment"
    CAMPAIGN_INQUIRY = "campaign_inquiry"
    CHAT = "chat"

class ActionType(str, Enum):
    """Action tipleri"""
    ASK_MISSING = "ask_missing"
    TOOL_CALL = "tool_call"
    CONFIRM = "confirm"
    CHAT = "chat"
    ASK_ALTERNATIVE = "ask_alternative"


# ============================================================================
# BOOKING FLOW - Randevu oluşturma akışı
# ============================================================================

BOOKING_REQUIRED_FIELDS: List[str] = [
    "phone",        # 1. Önce telefon
    "service",      # 2. Hizmet
    "expert_name",  # 3. Uzman
    "date",         # 4. Tarih
    "time"          # 5. Saat
]

BOOKING_FLOW_STEPS: List[str] = [
    "collect_phone",          # Telefon topla
    "check_customer",         # Müşteri kontrolü (tool)
    "collect_service",        # Hizmet topla
    "collect_expert",         # Uzman topla veya listele
    "list_experts",           # Uzman listesi (tool - opsiyonel)
    "collect_datetime",       # Tarih/saat topla
    "check_availability",     # Müsaitlik kontrolü (tool)
    "handle_unavailable",     # Müsait değilse alternative sor
    "suggest_alternatives",   # Alternatif saatler (tool - opsiyonel)
    "confirm_booking",        # Onay al
    "create_appointment"      # Randevu oluştur (tool)
]


# ============================================================================
# CANCEL FLOW - Randevu iptal akışı
# ============================================================================

CANCEL_REQUIRED_FIELDS: List[str] = [
    "phone"  # Sadece telefon yeterli (en son randevu iptal edilir)
]

CANCEL_FLOW_STEPS: List[str] = [
    "collect_phone",              # Telefon topla
    "get_customer_appointments",  # Randevuları getir (tool)
    "confirm_cancel",             # Onay al
    "cancel_appointment"          # İptal et (tool)
]


# ============================================================================
# QUERY APPOINTMENT FLOW - Randevu sorgulama
# ============================================================================

QUERY_REQUIRED_FIELDS: List[str] = [
    "phone"  # Sadece telefon
]

QUERY_FLOW_STEPS: List[str] = [
    "collect_phone",              # Telefon topla
    "get_customer_appointments"   # Randevuları getir (tool)
]


# ============================================================================
# MISSING FIELD MESSAGES - Her field için soru
# ============================================================================

MISSING_FIELD_MESSAGES: Dict[str, str] = {
    "phone": "Telefon numaranızı alabilir miyim?",
    "service": "Hangi hizmetimizden yararlanmak istersiniz?",
    "expert_name": "Hangi uzmanımızdan randevu almak istersiniz?",
    "date": "Hangi tarih sizin için uygun?",
    "time": "Saat kaçta uygun?",
    "datetime": "Hangi tarih ve saati tercih edersiniz?",
    "appointment_code": "İptal etmek istediğiniz randevu kodunu veya tarihini söyleyebilir misiniz?"
}


# ============================================================================
# CONFIRMATION MESSAGES - Onay mesajları
# ============================================================================

def get_booking_confirmation_message(collected: Dict) -> str:
    """Randevu onay mesajı oluştur"""
    return (
        f"{collected.get('date')} tarihinde saat {collected.get('time')}'te "
        f"{collected.get('expert_name')} uzmanımızdan {collected.get('service')} "
        f"randevusu oluşturulsun mu?"
    )

def get_cancel_confirmation_message(collected: Dict, appointment: Optional[Dict] = None) -> str:
    """İptal onay mesajı oluştur"""
    if appointment:
        return (
            f"{appointment.get('date')} tarihli {appointment.get('service')} "
            f"randevunuzu iptal etmek istediğinize emin misiniz?"
        )
    return "Randevunuzu iptal etmek istediğinize emin misiniz?"


# ============================================================================
# FLOW STATE MARKERS - State tracking için
# ============================================================================

class StateMarker:
    """Flow state'inde hangi adımların tamamlandığını track eden marker'lar"""

    CUSTOMER_CHECKED = "customer_checked"
    EXPERTS_LISTED = "experts_listed"
    AVAILABILITY_CHECKED = "availability_checked"
    AVAILABLE = "available"  # Müsaitlik sonucu
    ALTERNATIVES_SHOWN = "alternatives_shown"
    APPOINTMENTS_FETCHED = "appointments_fetched"
    CONFIRMED = "confirmed"


# ============================================================================
# TOOL MAPPING - Hangi tool hangi step'te çağrılır
# ============================================================================

TOOL_MAPPING: Dict[str, str] = {
    "check_customer": "customer_agent",
    "get_customer_appointments": "customer_agent",
    "create_customer": "customer_agent",
    "check_availability": "appointment_agent",
    "suggest_alternative_times": "appointment_agent",
    "create_appointment": "appointment_agent",
    "cancel_appointment": "appointment_agent",
    "list_experts": "appointment_agent",
    "list_services": "appointment_agent",
    "check_campaigns": "marketing_agent"
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_required_fields(flow_type: FlowType) -> List[str]:
    """Flow tipine göre required field'ları döndür"""
    mapping = {
        FlowType.BOOKING: BOOKING_REQUIRED_FIELDS,
        FlowType.CANCEL: CANCEL_REQUIRED_FIELDS,
        FlowType.QUERY: QUERY_REQUIRED_FIELDS,
        FlowType.CHAT: []
    }
    return mapping.get(flow_type, [])


def get_flow_steps(flow_type: FlowType) -> List[str]:
    """Flow tipine göre step'leri döndür"""
    mapping = {
        FlowType.BOOKING: BOOKING_FLOW_STEPS,
        FlowType.CANCEL: CANCEL_FLOW_STEPS,
        FlowType.QUERY: QUERY_FLOW_STEPS,
        FlowType.CHAT: []
    }
    return mapping.get(flow_type, [])


def get_missing_message(field: str) -> str:
    """Field için missing message döndür"""
    return MISSING_FIELD_MESSAGES.get(
        field,
        f"{field} bilgisini alabilir miyim?"
    )
