"""
Info Tools - LangChain @tool decorator
Bilgi sorgulama araçları (hizmetler, uzmanlar, kampanyalar)
"""
from langchain_core.tools import tool
from typing import Optional
import json
import logging

from repository import ServiceRepository, ExpertRepository, CampaignRepository

logger = logging.getLogger(__name__)


@tool
def list_services() -> str:
    """
    Tüm aktif hizmetleri listeler.

    Returns:
        JSON string: {"success": bool, "services": list}
    """
    try:
        logger.info("[list_services] Listing all services")

        service_repo = ServiceRepository()
        services = service_repo.list_all()

        formatted_services = []
        for s in services:
            duration = getattr(s, 'duration_minute', 60)
            if isinstance(duration, str):
                try:
                    time_parts = duration.split(':')
                    duration = int(time_parts[0]) * 60 + int(time_parts[1])
                except:
                    duration = 60

            formatted_services.append({
                "name": getattr(s, 'name', ''),
                "price": getattr(s, 'price', 0),
                "description": getattr(s, 'description', ''),
                "duration": duration
            })

        return json.dumps({
            "success": True,
            "services": formatted_services,
            "count": len(formatted_services)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"list_services error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def list_experts(service_type: Optional[str] = None) -> str:
    """
    Uzmanları listeler. Opsiyonel olarak hizmete göre filtreler.

    Args:
        service_type: Hizmet adı (opsiyonel)

    Returns:
        JSON string: {"success": bool, "experts": list}
    """
    try:
        logger.info(f"[list_experts] service_type={service_type}")

        expert_repo = ExpertRepository()
        experts = expert_repo.list_all(service_name=service_type)

        formatted_experts = []
        for exp in experts:
            full_name = f"{getattr(exp, 'first_name', '')} {getattr(exp, 'last_name', '')}".strip()
            specialties = getattr(exp, 'specialties', [])

            formatted_experts.append({
                "name": full_name,
                "specialties": specialties,
                "id": getattr(exp, 'id', None)
            })

        return json.dumps({
            "success": True,
            "experts": formatted_experts,
            "count": len(formatted_experts)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"list_experts error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)


@tool
def check_campaigns(customer_phone: Optional[str] = None) -> str:
    """
    Aktif kampanyaları listeler.

    Args:
        customer_phone: Müşteri telefon numarası (opsiyonel, gelecekte kişiselleştirme için)

    Returns:
        JSON string: {"success": bool, "campaigns": list}
    """
    try:
        logger.info(f"[check_campaigns] customer_phone={customer_phone}")

        campaign_repo = CampaignRepository()
        campaigns = campaign_repo.list_active()

        if not campaigns:
            return json.dumps({
                "success": True,
                "campaigns": [],
                "message": "Şu an aktif kampanya yok."
            }, ensure_ascii=False)

        formatted_campaigns = []
        for c in campaigns:
            end_date_str = getattr(c, 'end_date', None)
            end_date_formatted = None

            if end_date_str:
                try:
                    if hasattr(end_date_str, 'strftime'):
                        end_date_formatted = end_date_str.strftime('%d.%m.%Y')
                    else:
                        from datetime import datetime
                        end_date = datetime.fromisoformat(str(end_date_str).replace('Z', '+00:00').replace('+00:00', ''))
                        end_date_formatted = end_date.strftime('%d.%m.%Y')
                except:
                    pass

            formatted_campaigns.append({
                "name": getattr(c, 'name', ''),
                "code": getattr(c, 'code', ''),
                "discount": getattr(c, 'discount_rate', 0),
                "description": getattr(c, 'description', ''),
                "end_date": end_date_formatted
            })

        return json.dumps({
            "success": True,
            "campaigns": formatted_campaigns,
            "count": len(formatted_campaigns)
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"check_campaigns error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Sistem hatası: {str(e)}"}, ensure_ascii=False)
