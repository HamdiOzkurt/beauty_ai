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


def parse_time_from_text(text: str) -> Optional[int]:
    """
    Metinden saat çıkarır.
    Örnekler: "saat 2'de" → 14, "14:00" → 14, "saat ikide" → 14
    """
    text_lower = text.lower().strip()

    # Önce "saat" kelimesinden sonra sayı ara
    saat_pattern = r'saat\s+(\d{1,2})[:\.]?(\d{2})?'
    match = re.search(saat_pattern, text_lower)

    # Bulunamazsa genel sayısal saat formatı ara (ama sadece saat formatında: XX:XX veya XX.XX)
    if not match:
        time_pattern = r'(\d{1,2})[:\.](\d{2})'
        match = re.search(time_pattern, text)

    if match:
        hour = int(match.group(1))
        # Saat 1-12 arası ise AM/PM kontrolü yap
        if 1 <= hour <= 12:
            # Açıkça sabah/gece belirtilmişse sabah olarak al
            if 'sabah' in text_lower or 'gece' in text_lower:
                # Sabah/gece olarak bırak (değiştirme)
                pass
            # Açıkça öğleden sonra/akşam belirtilmişse +12
            elif 'öğleden sonra' in text_lower or 'ogleden sonra' in text_lower or 'akşam' in text_lower or 'aksam' in text_lower:
                hour += 12
            # Hiçbir şey belirtilmemişse ve saat 8'den küçükse muhtemelen öğleden sonra
            elif hour < 8:
                hour += 12
        return hour if 0 <= hour <= 23 else None

    # Yazılı saatler
    number_words = {
        'bir': 1, 'iki': 2, 'üç': 3, 'uc': 3, 'dört': 4, 'dort': 4,
        'beş': 5, 'bes': 5, 'altı': 6, 'alti': 6, 'yedi': 7,
        'sekiz': 8, 'dokuz': 9, 'on': 10, 'on bir': 11, 'on iki': 12
    }

    for word, num in number_words.items():
        if word in text_lower and ('saat' in text_lower or 'de' in text_lower):
            hour = num
            # AM/PM kontrolü
            if 1 <= hour <= 12:
                # Açıkça sabah/gece belirtilmişse sabah olarak al
                if 'sabah' in text_lower or 'gece' in text_lower:
                    pass
                # Açıkça öğleden sonra/akşam belirtilmişse +12
                elif 'öğleden sonra' in text_lower or 'ogleden sonra' in text_lower or 'akşam' in text_lower or 'aksam' in text_lower:
                    hour += 12
                # Hiçbir şey belirtilmemişse ve saat 8'den küçükse muhtemelen öğleden sonra
                elif hour < 8:
                    hour += 12
            return hour

    return None


def parse_turkish_date(date_str: str) -> Optional[datetime]:
    """
    Türkçe tarih formatlarını parse eder.
    Desteklenen formatlar:
    - "bugün", "yarın", "öbür gün"
    - "pazartesi", "salı", "önümüzdeki cuma"
    - "15 aralık", "3 ocak"
    - "2024-12-15", "15.12.2024"
    """
    date_str_lower = date_str.lower().strip()
    now = datetime.now()
    current_year = now.year

    # Özel kelimeler: bugün, yarın, öbür gün
    if 'bugün' in date_str_lower or 'bugun' in date_str_lower:
        return now
    if 'yarın' in date_str_lower or 'yarin' in date_str_lower:
        return now + timedelta(days=1)
    if 'öbür gün' in date_str_lower or 'obur gun' in date_str_lower or 'ertesi gün' in date_str_lower:
        return now + timedelta(days=2)

    # Gün isimleri (pazartesi, salı, etc.)
    turkish_days = {
        'pazartesi': 0, 'salı': 1, 'sali': 1, 'çarşamba': 2, 'carsamba': 2,
        'perşembe': 3, 'persembe': 3, 'cuma': 4, 'cumartesi': 5, 'pazar': 6
    }

    for day_name, day_num in turkish_days.items():
        if day_name in date_str_lower:
            # Bugünün gün numarası
            current_day = now.weekday()
            # Hedef güne kadar gün sayısı
            days_ahead = (day_num - current_day) % 7
            if days_ahead == 0:
                days_ahead = 7  # Önümüzdeki haftaya git
            target_date = now + timedelta(days=days_ahead)
            return target_date

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
        'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4,
        'mayıs': 5, 'mayis': 5, 'haziran': 6, 'temmuz': 7,
        'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9,
        'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12
    }
    pattern = r'(\d{1,2})\s*([a-züğışöç]+)'
    match = re.search(pattern, date_str_lower)
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
        date: Tarih ve saat (doğal dil: "yarın saat 2'de", "15 aralık", "pazartesi saat 10'da")
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
                "error": "Tarih anlaşılamadı. Lütfen tekrar söyler misiniz?"
            }, ensure_ascii=False)

        # Saat bilgisi varsa ekle
        hour = parse_time_from_text(date)
        if hour is not None:
            requested_time = requested_time.replace(hour=hour, minute=0, second=0)
            logger.info(f"[check_availability] Parsed time: {requested_time}")

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

        # DÜZELTME: Saat belirtilmişse (uzman yoksa bile) o saati kontrol et
        if requested_time.hour != 0:
            # Belirli saat için kontrol
            if expert_id:
                # Uzman belirtilmişse sadece o uzmanı kontrol et
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
            else:
                # Uzman belirtilmemişse o saat için müsait uzmanları bul
                slots_with_experts = appointment_repo.find_available_slots_for_day(
                    service_type=service_type,
                    day=requested_time.date(),
                    duration_minutes=duration,
                    expert_name=None
                )

                logger.info(f"[check_availability] DEBUG: Found {len(slots_with_experts)} total slots")
                logger.info(f"[check_availability] DEBUG: Requested hour: {requested_time.hour}")
                for slot, expert in slots_with_experts[:5]:  # İlk 5 slot'u göster
                    logger.info(f"[check_availability] DEBUG: Slot: {slot.strftime('%Y-%m-%d %H:%M')}, Expert: {expert}")

                # O saatte müsait olan var mı kontrol et
                available_at_time = [
                    (slot, expert) for slot, expert in slots_with_experts
                    if slot.hour == requested_time.hour
                ]

                logger.info(f"[check_availability] DEBUG: Matching slots at hour {requested_time.hour}: {len(available_at_time)}")

                if available_at_time:
                    experts_available = [expert for _, expert in available_at_time]
                    return json.dumps({
                        "success": True,
                        "available": True,
                        "message": f"{requested_time.strftime('%d %B %Y %H:%M')} saatinde müsait uzmanlarımız var.",
                        "available_slots": {requested_time.strftime('%H:%M'): experts_available}
                    }, ensure_ascii=False)
                else:
                    return json.dumps({
                        "success": True,
                        "available": False,
                        "message": f"{requested_time.strftime('%d %B %Y %H:%M')} saatinde maalesef müsait uzmanımız yok."
                    }, ensure_ascii=False)

        # Tüm gün için müsaitlik kontrolü (saat belirtilmemişse)
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
    time: str = "",
    expert_name: Optional[str] = None
) -> str:
    """
    Yeni randevu oluşturur.

    Args:
        customer_phone: Müşteri telefon numarası (05xxxxxxxxx formatında)
        customer_name: Müşteri adı soyadı
        service_type: Hizmet adı
        date: Tarih (doğal dil: "yarın", "15 aralık", "pazartesi")
        time: Saat (doğal dil: "saat 2'de", "14:00", opsiyonel - date içinde olabilir)
        expert_name: Uzman adı (opsiyonel)

    Returns:
        JSON string: {"success": bool, "message": str, "code": str}
    """
    try:
        logger.info(f"[create_appointment] phone={customer_phone}, service={service_type}, date={date}, time={time}")

        # Tarihi parse et (date + time birleşik de olabilir)
        full_date_string = f"{date} {time}".strip()
        appointment_time = parse_turkish_date(full_date_string)

        if not appointment_time:
            return json.dumps({
                "success": False,
                "error": "Tarih anlaşılamadı."
            }, ensure_ascii=False)

        # Saat bilgisini parse et
        hour = parse_time_from_text(full_date_string)
        if hour is not None:
            appointment_time = appointment_time.replace(hour=hour, minute=0, second=0)
        else:
            # Saat belirtilmemişse hata
            return json.dumps({
                "success": False,
                "error": "Lütfen randevu saatini belirtir misiniz?"
            }, ensure_ascii=False)

        logger.info(f"[create_appointment] Parsed datetime: {appointment_time}")

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
        customer_repo = CustomerRepository()
        customer = customer_repo.get_by_phone(customer_phone)

        if not customer:
            return json.dumps({
                "success": False,
                "error": "Müşteri bulunamadı."
            }, ensure_ascii=False)

        appointments = customer_repo.get_appointments(customer.id, limit=1)

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
