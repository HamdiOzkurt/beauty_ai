"""
Appointment Tools - LangChain @tool decorator
Randevu ile ilgili tüm işlemler
"""
from langchain_core.tools import tool
from typing import Optional
from datetime import datetime, timedelta
import json
import logging
import re

from repository import (
    AppointmentRepository,
    ServiceRepository,
    ExpertRepository
)

logger = logging.getLogger(__name__)


def normalize_turkish(text: str) -> str:
    """Türkçe karakterleri ASCII'ye çevir (fuzzy matching için)."""
    if not text:
        return ""
    tr_map = {
        'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
        'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
    }
    for tr_char, en_char in tr_map.items():
        text = text.replace(tr_char, en_char)
    return re.sub(r'\s+', ' ', text).strip()


def parse_turkish_date(date_str: str) -> Optional[datetime]:
    """Türkçe tarih formatlarını parse eder."""
    current_year = datetime.now().year

    # ISO format
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00').replace('+00:00', ''))
    except:
        pass

    # YYYY-MM-DD
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:
        pass

    # DD.MM.YYYY
    try:
        return datetime.strptime(date_str, '%d.%m.%Y')
    except:
        pass

    # "3 aralık" gibi Türkçe format
    tr_months = {
        'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4,
        'mayıs': 5, 'haziran': 6, 'temmuz': 7, 'ağustos': 8,
        'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
    }
    pattern = r'(\d{1,2})\s*([a-züğışöç]+)'
    match = re.search(pattern, date_str.lower())
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        month = tr_months.get(month_name)
        if month:
            return datetime(current_year, month, day)

    return None


@tool
def check_availability(
    service_type: str,
    date: str,
    expert_name: Optional[str] = None
) -> str:
    """
    Belirtilen hizmet, tarih ve uzman için müsaitlik kontrolü yapar.

    Args:
        service_type: Hizmet adı (örn: "saç kesimi", "manikür")
        date: Tarih (YYYY-MM-DD, DD.MM.YYYY veya "3 aralık" formatında)
        expert_name: Uzman adı (opsiyonel, verilmezse tüm uzmanlar kontrol edilir)

    Returns:
        JSON string: {"success": bool, "available": bool, "message": str, "available_slots": dict}
    """
    try:
        logger.info(f"[check_availability] service={service_type}, date={date}, expert={expert_name}")

        # Tarihi parse et
        requested_time = parse_turkish_date(date)
        if not requested_time:
            return json.dumps({
                "success": False,
                "error": "Geçersiz tarih formatı. YYYY-MM-DD veya DD.MM.YYYY kullanın."
            }, ensure_ascii=False)

        # Hizmet bilgilerini al
        service_repo = ServiceRepository()
        service = service_repo.get_by_name(service_type)

        if not service:
            return json.dumps({
                "success": False,
                "error": f"'{service_type}' adında bir hizmet bulunamadı."
            }, ensure_ascii=False)

        duration = getattr(service, 'duration_minute', 60)
        if isinstance(duration, str):
            try:
                time_parts = duration.split(':')
                duration = int(time_parts[0]) * 60 + int(time_parts[1])
            except:
                duration = 60

        # Uzman kontrolü (Türkçe karakter desteği)
        normalized_expert_name = None
        expert_id = None

        if expert_name:
            expert_repo = ExpertRepository()
            experts = expert_repo.list_all()
            normalized_input = normalize_turkish(expert_name.lower()).replace(' ', '')

            for exp in experts:
                full_name = f"{getattr(exp, 'first_name', '')} {getattr(exp, 'last_name', '')}".strip()
                normalized_expert = normalize_turkish(full_name.lower()).replace(' ', '')

                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    normalized_expert_name = full_name
                    expert_id = exp.id
                    break

            if not normalized_expert_name:
                expert_names = [f"{getattr(e, 'first_name', '')} {getattr(e, 'last_name', '')}" for e in experts]
                return json.dumps({
                    "success": False,
                    "error": f"Belirtilen uzman bulunamadı. Mevcut uzmanlar: {', '.join(expert_names)}"
                }, ensure_ascii=False)

        # Belirli saat verilmişse o saati kontrol et
        appointment_repo = AppointmentRepository()

        if expert_id and requested_time.hour != 0:
            # Belirli saat için kontrol
            is_available = appointment_repo.check_availability(
                expert_id=expert_id,
                start_time=requested_time,
                duration_minutes=duration
            )

            if not is_available:
                return json.dumps({
                    "success": True,
                    "available": False,
                    "message": f"{normalized_expert_name} uzmanımızın {requested_time.strftime('%d.%m.%Y %H:%M')} saatinde başka randevusu var."
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": True,
                    "available": True,
                    "message": f"{normalized_expert_name} uzmanımız {requested_time.strftime('%d.%m.%Y %H:%M')} saatinde müsait.",
                    "available_slots": {requested_time.strftime('%H:%M'): [normalized_expert_name]}
                }, ensure_ascii=False)

        # Tüm gün için müsaitlik kontrolü
        slots_with_experts = appointment_repo.find_available_slots_for_day(
            service_type=service_type,
            day=requested_time.date(),
            duration_minutes=duration,
            expert_name=normalized_expert_name
        )

        if not slots_with_experts:
            return json.dumps({
                "success": True,
                "available": False,
                "message": f"{requested_time.strftime('%d %B %Y')} tarihinde bu hizmet için uygun saat bulunmuyor."
            }, ensure_ascii=False)

        # Slotları grupla
        slots_by_time = {}
        for slot, expert in slots_with_experts:
            time_str = slot.strftime('%H:%M')
            if time_str not in slots_by_time:
                slots_by_time[time_str] = []
            slots_by_time[time_str].append(expert)

        return json.dumps({
            "success": True,
            "available": True,
            "message": f"{requested_time.strftime('%d %B %Y')} için uygun saatler bulundu.",
            "available_slots": slots_by_time
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"check_availability error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def create_appointment(
    customer_phone: str,
    customer_name: str,
    service_type: str,
    date: str,
    time: str,
    expert_name: Optional[str] = None
) -> str:
    """
    Yeni randevu oluşturur.

    Args:
        customer_phone: Müşteri telefon numarası (05xxxxxxxxx formatında)
        customer_name: Müşteri adı soyadı
        service_type: Hizmet adı
        date: Tarih (YYYY-MM-DD)
        time: Saat (HH:MM)
        expert_name: Uzman adı (opsiyonel)

    Returns:
        JSON string: {"success": bool, "message": str, "code": str}
    """
    try:
        logger.info(f"[create_appointment] phone={customer_phone}, service={service_type}, date={date}, time={time}")

        # Tarih-saat birleştir
        appointment_datetime_str = f"{date} {time}"
        appointment_time = None

        try:
            appointment_time = datetime.strptime(appointment_datetime_str, '%Y-%m-%d %H:%M')
        except:
            try:
                appointment_time = datetime.strptime(appointment_datetime_str, '%d.%m.%Y %H:%M')
            except:
                return json.dumps({
                    "success": False,
                    "error": "Geçersiz tarih/saat formatı."
                }, ensure_ascii=False)

        # Hizmet bilgilerini al
        service_repo = ServiceRepository()
        service = service_repo.get_by_name(service_type)

        if not service:
            return json.dumps({
                "success": False,
                "error": f"'{service_type}' hizmeti bulunamadı."
            }, ensure_ascii=False)

        duration = getattr(service, 'duration_minute', 60)
        if isinstance(duration, str):
            try:
                time_parts = duration.split(':')
                duration = int(time_parts[0]) * 60 + int(time_parts[1])
            except:
                duration = 60

        # Uzman belirleme
        assigned_expert = None

        if expert_name:
            # Belirtilen uzmanı bul
            expert_repo = ExpertRepository()
            experts = expert_repo.list_all()
            normalized_input = normalize_turkish(expert_name.lower()).replace(' ', '')

            target_expert = None
            for exp in experts:
                full_name = f"{getattr(exp, 'first_name', '')} {getattr(exp, 'last_name', '')}".strip()
                normalized_expert = normalize_turkish(full_name.lower()).replace(' ', '')

                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    target_expert = exp
                    break

            if not target_expert:
                return json.dumps({
                    "success": False,
                    "error": f"Belirtilen uzman bulunamadı: {expert_name}"
                }, ensure_ascii=False)

            # Müsaitlik kontrolü
            appointment_repo = AppointmentRepository()
            if not appointment_repo.check_availability(target_expert.id, appointment_time, duration):
                return json.dumps({
                    "success": False,
                    "error": f"{expert_name} seçilen saatte müsait değil."
                }, ensure_ascii=False)

            assigned_expert = f"{target_expert.first_name} {target_expert.last_name}"
        else:
            # Otomatik uzman bulma
            expert_repo = ExpertRepository()
            suitable_experts = expert_repo.list_all(service_name=service_type)

            if not suitable_experts:
                return json.dumps({
                    "success": False,
                    "error": "Bu hizmeti veren uzman bulunamadı."
                }, ensure_ascii=False)

            appointment_repo = AppointmentRepository()
            available_experts = []

            for exp in suitable_experts:
                if appointment_repo.check_availability(exp.id, appointment_time, duration):
                    available_experts.append(exp)

            if not available_experts:
                return json.dumps({
                    "success": False,
                    "error": "Uygun saatte müsait uzman yok."
                }, ensure_ascii=False)

            first_expert = available_experts[0]
            assigned_expert = f"{first_expert.first_name} {first_expert.last_name}"

        # Randevuyu kaydet
        appointment_repo = AppointmentRepository()
        appointment = appointment_repo.create_appointment(
            customer_phone=customer_phone,
            customer_name=customer_name,
            expert_name=assigned_expert,
            service_type=service_type,
            appointment_date=appointment_time
        )

        return json.dumps({
            "success": True,
            "message": f"Randevunuz {assigned_expert} ile oluşturuldu.",
            "code": getattr(appointment, 'appointment_code', 'N/A'),
            "appointment": {
                "customer": customer_name,
                "expert": assigned_expert,
                "service": service_type,
                "date": appointment_time.strftime("%d.%m.%Y %H:%M"),
                "duration": duration
            }
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"create_appointment error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def cancel_appointment(
    customer_phone: str,
    reason: str = "Müşteri talebi"
) -> str:
    """
    Müşterinin son randevusunu iptal eder.

    Args:
        customer_phone: Müşteri telefon numarası
        reason: İptal nedeni

    Returns:
        JSON string: {"success": bool, "message": str}
    """
    try:
        logger.info(f"[cancel_appointment] phone={customer_phone}")

        from repository import CustomerRepository
        customer_repo = CustomerRepository(None)
        customer = customer_repo.get_by_phone_directus(customer_phone)

        if not customer:
            return json.dumps({
                "success": False,
                "error": "Müşteri bulunamadı."
            }, ensure_ascii=False)

        appointments = customer_repo.get_appointments_directus(customer.id, limit=1)

        if not appointments:
            return json.dumps({
                "success": False,
                "error": "İptal edilecek randevu bulunamadı."
            }, ensure_ascii=False)

        # İptal işlemi (Directus PATCH)
        appt_id = appointments[0].id
        appointment_repo = AppointmentRepository()
        result = appointment_repo.cancel_appointment(appt_id, reason)

        if result:
            return json.dumps({
                "success": True,
                "message": "Randevunuz başarıyla iptal edildi."
            }, ensure_ascii=False)

        return json.dumps({
            "success": False,
            "error": "Randevu iptal edilemedi."
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"cancel_appointment error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def suggest_alternative_times(
    service_type: str,
    date: str,
    expert_name: Optional[str] = None
) -> str:
    """
    Belirtilen tarih için alternatif randevu saatleri önerir.

    Args:
        service_type: Hizmet adı
        date: Tarih (YYYY-MM-DD)
        expert_name: Uzman adı (opsiyonel)

    Returns:
        JSON string: {"success": bool, "alternatives": list, "message": str}
    """
    try:
        logger.info(f"[suggest_alternative_times] service={service_type}, date={date}")

        # Hizmet bilgilerini al
        service_repo = ServiceRepository()
        service = service_repo.get_by_name(service_type)

        if not service:
            return json.dumps({
                "success": False,
                "error": f"'{service_type}' hizmeti bulunamadı."
            }, ensure_ascii=False)

        duration = getattr(service, 'duration_minute', 60)
        if isinstance(duration, str):
            try:
                time_parts = duration.split(':')
                duration = int(time_parts[0]) * 60 + int(time_parts[1])
            except:
                duration = 60

        # Tarihi parse et
        requested_date = parse_turkish_date(date)
        if not requested_date:
            return json.dumps({
                "success": False,
                "error": "Geçersiz tarih formatı."
            }, ensure_ascii=False)

        # Uzman normalizasyonu
        normalized_expert_name = None
        if expert_name:
            expert_repo = ExpertRepository()
            experts = expert_repo.list_all()
            normalized_input = normalize_turkish(expert_name.lower())

            for exp in experts:
                full_name = f"{getattr(exp, 'first_name', '')} {getattr(exp, 'last_name', '')}".strip()
                normalized_expert = normalize_turkish(full_name.lower())

                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    normalized_expert_name = full_name
                    break

        # Alternatif saatleri bul
        appointment_repo = AppointmentRepository()
        alternatives = []

        # Aynı gün
        same_day_slots = appointment_repo.find_available_slots_for_day(
            service_type=service_type,
            day=requested_date.date(),
            duration_minutes=duration,
            expert_name=normalized_expert_name
        )

        if same_day_slots:
            for slot, expert in same_day_slots[:3]:
                alternatives.append({
                    "date": slot.strftime("%d.%m.%Y"),
                    "time": slot.strftime("%H:%M"),
                    "expert": expert,
                    "day_type": "aynı gün"
                })

        # Sonraki 3 gün
        for i in range(1, 4):
            next_day = requested_date + timedelta(days=i)
            next_day_slots = appointment_repo.find_available_slots_for_day(
                service_type=service_type,
                day=next_day.date(),
                duration_minutes=duration,
                expert_name=normalized_expert_name
            )

            if next_day_slots:
                for slot, expert in next_day_slots[:2]:
                    alternatives.append({
                        "date": slot.strftime("%d.%m.%Y"),
                        "time": slot.strftime("%H:%M"),
                        "expert": expert,
                        "day_type": f"{i} gün sonra"
                    })

        if not alternatives:
            return json.dumps({
                "success": True,
                "alternatives": [],
                "message": "Yakın tarihlerde uygun saat bulunamadı."
            }, ensure_ascii=False)

        return json.dumps({
            "success": True,
            "alternatives": alternatives[:10],
            "message": f"{len(alternatives[:10])} alternatif saat bulundu."
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"suggest_alternative_times error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)
