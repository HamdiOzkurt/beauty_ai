"""
Customer Tools - LangChain @tool decorator
Müşteri ile ilgili tüm işlemler
"""
from langchain_core.tools import tool
import json
import logging

from repository import CustomerRepository

logger = logging.getLogger(__name__)


@tool
def check_customer(phone: str) -> str:
    """
    Telefon numarasına göre müşteri bilgilerini sorgular.

    Args:
        phone: Müşteri telefon numarası (05xxxxxxxxx formatında)

    Returns:
        JSON string: {"success": bool, "customer": dict, "is_first_appointment": bool}
    """
    try:
        logger.info(f"[check_customer] phone={phone}")

        customer_repo = CustomerRepository()
        customer = customer_repo.get_by_phone(phone)

        if not customer:
            return json.dumps({
                "success": False,
                "message": "Müşteri bulunamadı. Yeni müşteri olarak kayıt edilebilir."
            }, ensure_ascii=False)

        # Randevu sayısını hesapla
        appointments = customer_repo.get_appointments(customer.id, limit=100)
        total_appointments = len(appointments)

        customer_info = {
            "id": customer.id,
            "name": f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip(),
            "phone": getattr(customer, 'phone_number', phone),
            "total_appointments": total_appointments,
            "is_first_appointment": total_appointments == 0
        }

        return json.dumps({
            "success": True,
            "customer": customer_info,
            "is_first_appointment": total_appointments == 0
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"check_customer error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def get_customer_appointments(phone: str) -> str:
    """
    Müşterinin randevularını listeler.

    Args:
        phone: Müşteri telefon numarası

    Returns:
        JSON string: {"success": bool, "appointments": list, "count": int}
    """
    try:
        logger.info(f"[get_customer_appointments] phone={phone}")

        customer_repo = CustomerRepository()
        customer = customer_repo.get_by_phone(phone)

        if not customer:
            return json.dumps({
                "success": False,
                "error": "Bu telefon numarasına kayıtlı müşteri bulunamadı."
            }, ensure_ascii=False)

        customer_name = f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()

        # Randevuları getir
        appointments = customer_repo.get_appointments(customer.id, limit=10)

        if not appointments:
            return json.dumps({
                "success": True,
                "customer_name": customer_name,
                "appointments": [],
                "message": "Kayıtlı randevunuz bulunmamaktadır."
            }, ensure_ascii=False)

        # Randevu bilgilerini formatla
        formatted_appointments = []
        for apt in appointments:
            date_time = getattr(apt, 'date_time', None)
            if date_time and hasattr(date_time, 'strftime'):
                date_str = date_time.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = str(date_time) if date_time else ''

            # Service bilgisi (ilişkisel veri)
            service_data = getattr(apt, 'service_id', None)
            service_name = ''
            if isinstance(service_data, dict):
                service_name = service_data.get('name', '')

            # Expert bilgisi
            expert_data = getattr(apt, 'expert_id', None)
            expert_name = ''
            if isinstance(expert_data, dict):
                expert_name = f"{expert_data.get('first_name', '')} {expert_data.get('last_name', '')}".strip()

            formatted_appointments.append({
                "id": getattr(apt, 'id', None),
                "date": date_str,
                "service": service_name,
                "expert": expert_name,
                "status": getattr(apt, 'status', ''),
                "notes": getattr(apt, 'notes', '')
            })

        return json.dumps({
            "success": True,
            "customer_name": customer_name,
            "appointments": formatted_appointments,
            "count": len(formatted_appointments)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"get_customer_appointments error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def create_customer(full_name: str, phone: str) -> str:
    """
    Yeni müşteri kaydı oluşturur.

    Args:
        full_name: Müşteri adı soyadı
        phone: Telefon numarası (05xxxxxxxxx)

    Returns:
        JSON string: {"success": bool, "customer": dict}
    """
    try:
        logger.info(f"[create_customer] name={full_name}, phone={phone}")

        customer_repo = CustomerRepository()

        # Önce kontrol et
        existing = customer_repo.get_by_phone(phone)
        if existing:
            return json.dumps({
                "success": False,
                "error": "Bu numara zaten kayıtlı."
            }, ensure_ascii=False)

        # Yeni müşteri oluştur
        new_customer = customer_repo.create_customer(full_name, phone)

        return json.dumps({
            "success": True,
            "customer": {
                "id": new_customer.id,
                "name": f"{new_customer.first_name} {new_customer.last_name}",
                "phone": new_customer.phone_number
            },
            "message": "Müşteri kaydı başarıyla oluşturuldu."
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"create_customer error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)
