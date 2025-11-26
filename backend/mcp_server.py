# ⚠ KRİTİK: CUDA/cuDNN ortamını hazırla - TÜM import'lardan ÖNCE!
import sys
import os
import requests
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1) PATH ayarları
import cuda_setup

# 2) DLL'leri önceden yükle (ctranslate2'den ÖNCE!)
import cudnn_preload

from fastapi import FastAPI
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

# Logging konfigürasyonu
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Repository ve Config
from repository import CustomerRepository, AppointmentRepository
from config import settings

# --------------------------------------------------------------------------
# CMS Yardımcı Fonksiyonları (Metadata Fetching)
# --------------------------------------------------------------------------
# Bu fonksiyonlar statik sözlüklerin (SERVICE_DURATIONS vb.) yerini alır.

def _directus_get(collection: str, params: Dict = None) -> List[Dict]:
    """Directus API'den veri çekmek için genel yardımcı fonksiyon."""
    url = f"{settings.DIRECTUS_URL.rstrip('/')}/items/{collection}"
    headers = {
        "Authorization": f"Bearer {settings.DIRECTUS_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get('data', [])
        logging.error(f"CMS GET Error ({collection}): {response.text}")
        return []
    except Exception as e:
        logging.error(f"CMS Connection Error: {e}")
        return []

def get_service_details(service_name: str) -> Optional[Dict]:
    """Hizmet adına göre detayları (süre, fiyat vb.) çeker."""
    params = {
        "filter[name][_icontains]": service_name,
        "filter[tenant_id][_eq]": settings.TENANT_ID,
        "limit": 1
    }
    data = _directus_get("voises_services", params)
    if data:
        # duration_minute bazen int bazen string gelebilir, kontrol et
        duration = data[0].get('duration_minute', 60)
        if isinstance(duration, str):
            # Eğer "01:00:00" gibi geliyorsa parse etmek gerekebilir, 
            # ama şemada Datetime/Int karışıklığı olabilir. Varsayılan 60 dk.
            try:
                # Basitçe int'e çevirmeyi dene veya varsayılanı kullan
                duration = int(duration) 
            except:
                duration = 60 
        
        return {
            "id": data[0]['id'],
            "name": data[0]['name'],
            "duration": duration,
            "description": data[0].get('description', '')
        }
    return None

def get_all_services_from_cms() -> List[Dict]:
    """Tüm aktif hizmetleri çeker."""
    params = {
        "filter[is_active][_eq]": True,
        "filter[tenant_id][_eq]": settings.TENANT_ID
    }
    return _directus_get("voises_services", params)

def get_all_experts_from_cms(service_name: Optional[str] = None) -> List[Dict]:
    """Uzmanları çeker. Opsiyonel olarak hizmete göre filtreler."""
    # Uzmanları ve ilişkili hizmetlerini çek
    params = {
        "filter[is_active][_eq]": True,
        "filter[tenant_id][_eq]": settings.TENANT_ID,
        "fields": "*,services.voises_services_id.name" # İlişkili hizmet isimlerini al
    }
    
    if service_name:
        # Directus'ta derin filtreleme (Deep Filtering)
        # Uzmanın hizmetleri arasında ismi X olan var mı?
        params["filter[services][voises_services_id][name][_icontains]"] = service_name

    experts_data = _directus_get("voises_experts", params)
    
    formatted_experts = []
    for exp in experts_data:
        # İlişkili hizmetleri listeye çevir
        specialties = []
        if 'services' in exp and exp['services']:
            for s in exp['services']:
                if s.get('voises_services_id'):
                    specialties.append(s['voises_services_id']['name'])
        
        formatted_experts.append({
            "full_name": f"{exp.get('first_name', '')} {exp.get('last_name', '')}".strip(),
            "specialties": specialties,
            "id": exp.get('id')
        })
    return formatted_experts

def get_active_campaigns_from_cms() -> List[Dict]:
    """Aktif kampanyaları çeker."""
    now = datetime.utcnow().isoformat()
    params = {
        "filter[start_date][_lte]": now,
        "filter[end_date][_gte]": now,
        "filter[tenant_id][_eq]": settings.TENANT_ID
    }
    return _directus_get("voises_campaigns", params)


# --------------------------------------------------------------------------
# Ana FastAPI uygulamasını oluştur
# --------------------------------------------------------------------------
app = FastAPI(
    title="Güzellik Merkezi Asistanı API",
    description="Bu API, Güzellik Merkezi Asistanı'nın kullandığı araçları (tools) içerir.",
    version="2.0.0",
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
    ]
)

# FastMCP sunucusunu oluştur
mcp = FastMCP("Güzellik Merkezi Asistanı MCP Sunucusu")

# --------------------------------------------------------------------------
# MCP Araçları (Tools)
# --------------------------------------------------------------------------

def check_availability(
    service_type: str,
    date_time: Optional[str] = None,
    date: Optional[str] = None,
    expert_name: Optional[str] = None
) -> Dict:
    """
    Belirtilen hizmet ve tarih için uygun saat aralıklarını bulur.
    """
    try:
        if not date_time and not date:
            return {"success": False, "error": "Tarih ('date' veya 'date_time') parametresi zorunludur."}

        effective_date_str = date_time if date_time else date
        
        try:
            requested_time = datetime.fromisoformat(effective_date_str.replace('Z', '+00:00'))
        except ValueError:
            try:
                requested_time = datetime.strptime(effective_date_str, '%Y-%m-%d')
            except ValueError:
                return {"success": False, "error": "Geçersiz tarih formatı."}

        # 1. Hizmet süresini CMS'den çek
        service_info = get_service_details(service_type)
        if not service_info:
             return {"success": False, "error": f"'{service_type}' adında bir hizmet bulunamadı."}
        
        duration = service_info['duration']

        # 2. Müsaitlik kontrolü (Repository üzerinden)
        appointment_repo = AppointmentRepository()
        slots_with_experts = appointment_repo.find_available_slots_for_day(
            service_type=service_type,
            day=requested_time.date(),
            duration_minutes=duration,
            expert_name=expert_name
        )

        if not slots_with_experts:
            return {
                "success": True, 
                "available": False, 
                "message": f"{requested_time.strftime('%d %B %Y')} tarihinde bu hizmet için hiç uygun saat bulunmuyor."
            }
        
        slots_by_time = {}
        for slot, expert in slots_with_experts:
            time_str = slot.strftime('%H:%M')
            if time_str not in slots_by_time:
                slots_by_time[time_str] = []
            slots_by_time[time_str].append(expert)

        return {
            "success": True,
            "available": True,
            "message": f"{requested_time.strftime('%d %B %Y')} için uygun saatler bulundu.",
            "available_slots": slots_by_time
        }
    except Exception as e:
        logging.error(f"check_availability hatası: {str(e)}")
        return {"success": False, "error": f"Sistem hatası: {str(e)}"}

mcp.tool(check_availability)


def suggest_complementary_service(service_type: str) -> Dict:
    """
    Seçilen bir ana hizmete dayalı olarak tamamlayıcı hizmetleri önerir.
    (CMS'de henüz ilişki tablosu olmadığı için basit bir mantık veya tüm hizmetleri döndürür)
    """
    # İdealde CMS'de 'related_services' alanı olmalı. 
    # Şimdilik tüm hizmetleri çekip, mevcut hizmet dışındakileri öneri olarak sunabiliriz 
    # veya basit bir kelime eşleşmesi yapabiliriz.
    
    all_services = get_all_services_from_cms()
    suggestions = []
    
    # Basit mantık: Aynı kelimeyi içermeyen rastgele 2 hizmet öner (Örn: Saç -> Manikür)
    import random
    possible_services = [s['name'] for s in all_services if service_type.lower() not in s['name'].lower()]
    
    if possible_services:
        suggestions = random.sample(possible_services, min(2, len(possible_services)))

    return {
        "success": True,
        "service": service_type,
        "suggestions": suggestions
    }

mcp.tool(suggest_complementary_service)

def check_customer(phone: str) -> Dict:
    """
    Telefon numarasına göre müşteri bilgilerini kontrol et.
    """
    try:
        repo = CustomerRepository()
        customer = repo.get_by_phone(phone)

        if not customer:
            return {"success": False, "message": "Müşteri bulunamadı"}

        # DirectusItem objesinden verileri al
        # Not: DirectusItem dinamik attribute'lara sahip
        appointments = repo.get_appointments(customer.id, limit=5)

        # Müşteri istatistiklerini hesapla (CMS'de tutulmuyorsa)
        # Basitçe randevu sayısını alıyoruz
        total_appts = len(repo.get_appointments(customer.id, limit=100))

        return {
            "success": True,
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "phone": customer.phone_number,
                "total_appointments": total_appts,
                "is_first_appointment": total_appts == 0
            },
            "recent_appointments": [
                {
                    "service": getattr(apt, 'service_id', {}).get('name') if isinstance(getattr(apt, 'service_id', None), dict) else "Hizmet",
                    "date": apt.date_time.isoformat(),
                    "status": apt.status
                } for apt in appointments
            ]
        }
    except Exception as e:
        logging.error(f"check_customer hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı hatası: {str(e)}"}

mcp.tool(check_customer)

def create_appointment(
    customer_phone: str, 
    service_type: str, 
    appointment_datetime: str,
    customer_name: Optional[str] = None,
    expert_name: Optional[str] = None
) -> Dict:
    """
    Müşteri için yeni bir randevu oluşturur.
    """
    try:
        customer_repo = CustomerRepository()
        appointment_repo = AppointmentRepository()

        # 1. Müşteri Kontrolü / Oluşturma
        customer = customer_repo.get_by_phone(customer_phone)
        if not customer:
            if customer_name:
                try:
                    customer = customer_repo.create(customer_name, customer_phone)
                except Exception as e:
                    return {"success": False, "error": f"Müşteri oluşturulamadı: {str(e)}"}
            else:
                return {"success": False, "error": "Müşteri bulunamadı. İsim bilgisi gerekli."}

        # 2. Tarih Formatı
        try:
            appointment_time = datetime.fromisoformat(appointment_datetime.replace('Z', '+00:00'))
        except ValueError:
            return {"success": False, "error": "Geçersiz tarih formatı."}

        # 3. Hizmet Detaylarını Çek
        service_info = get_service_details(service_type)
        if not service_info:
            return {"success": False, "error": "Hizmet bulunamadı."}
        
        duration = service_info['duration']

        # 4. Uzman Atama Mantığı
        assigned_expert = None
        
        if expert_name:
            # Belirtilen uzmanı kontrol et (ID'sini bulmamız lazım)
            # AppointmentRepository içinde _get_expert_id_by_name var ama private.
            # CMS Helper ile ID bulalım:
            experts = get_all_experts_from_cms()
            target_expert = next((e for e in experts if expert_name.lower() in e['full_name'].lower()), None)
            
            if not target_expert:
                 return {"success": False, "error": "Belirtilen uzman bulunamadı."}

            if appointment_repo.check_availability(target_expert['id'], appointment_time, duration):
                assigned_expert = target_expert['full_name']
            else:
                return {"success": False, "error": f"{expert_name} seçilen saatte müsait değil."}
        else:
            # Otomatik Uzman Bulma
            # Hizmeti veren uzmanları çek
            suitable_experts = get_all_experts_from_cms(service_name=service_type)
            
            if not suitable_experts:
                return {"success": False, "error": "Bu hizmeti veren uzman bulunamadı."}

            available_experts = []
            for exp in suitable_experts:
                if appointment_repo.check_availability(exp['id'], appointment_time, duration):
                    available_experts.append(exp)
            
            if not available_experts:
                return {"success": False, "error": "Uygun saatte müsait uzman yok."}
            
            if len(available_experts) > 1:
                # Birden fazla varsa kullanıcıya sor veya ilkini seç (Şimdilik ilkini seçiyoruz)
                assigned_expert = available_experts[0]['full_name']
            else:
                assigned_expert = available_experts[0]['full_name']

        # 5. Randevuyu Kaydet
        try:
            appointment = appointment_repo.create(
                customer_id=customer.id,
                expert_name=assigned_expert,
                service_type=service_type,
                appointment_date=appointment_time
            )

            return {
                "success": True,
                "message": f"Randevunuz {assigned_expert} ile oluşturuldu.",
                "appointment": {
                    "customer": f"{customer.first_name} {customer.last_name}",
                    "expert": assigned_expert,
                    "service": service_type,
                    "date": appointment_time.strftime("%d.%m.%Y %H:%M"),
                    "duration": duration
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Kayıt hatası: {str(e)}"}

    except Exception as e:
        logging.error(f"create_appointment hatası: {str(e)}")
        return {"success": False, "error": f"Sistem hatası: {str(e)}"}

mcp.tool(create_appointment)

def create_new_customer(full_name: str, phone: str) -> Dict:
    """Yeni müşteri kaydeder."""
    try:
        repo = CustomerRepository()
        existing = repo.get_by_phone(phone)
        if existing:
            return {"success": False, "error": "Bu numara zaten kayıtlı."}

        new_customer = repo.create(full_name, phone)
        return {
            "success": True,
            "customer": {
                "id": new_customer.id,
                "name": f"{new_customer.first_name} {new_customer.last_name}",
                "phone": new_customer.phone_number
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

mcp.tool(create_new_customer)

def cancel_appointment(appointment_code: str, reason: str = "Müşteri talebi") -> Dict:
    """
    Randevu iptal eder. 
    Not: CMS şemasında appointment_code yoktu, ID veya Notes içindeki kod kullanılmalı.
    Burada kodun ID olduğunu veya Notes içinde arandığını varsayıyoruz.
    """
    try:
        repo = AppointmentRepository()
        # Not: Repository'deki cancel metodu ID bekliyor olabilir, 
        # ancak kodda repository'yi ID ile çalışacak şekilde güncellemiştik.
        # Eğer appointment_code bir ID ise (int):
        try:
            appt_id = int(appointment_code)
            cancelled = repo.cancel(appt_id, reason)
        except ValueError:
            # Eğer kod ise (String), repository'de get_by_code mantığına ihtiyaç var.
            # Şimdilik hata dönüyoruz veya repository'nin bunu hallettiğini varsayıyoruz.
            return {"success": False, "error": "Lütfen randevu ID'sini belirtin."}

        if cancelled:
            return {"success": True, "message": "Randevu iptal edildi."}
        return {"success": False, "error": "Randevu bulunamadı."}
    except Exception as e:
        return {"success": False, "error": str(e)}

mcp.tool(cancel_appointment)

def check_campaigns(customer_phone: str) -> Dict:
    """Aktif kampanyaları listeler."""
    try:
        campaigns = get_active_campaigns_from_cms()
        if not campaigns:
             return {"success": True, "campaigns": [], "message": "Şu an aktif kampanya yok."}
        
        # Kampanya detaylarını formatla
        formatted = [{"name": c['name'], "code": c.get('code'), "discount": c.get('discount_rate')} for c in campaigns]
        
        return {"success": True, "campaigns": formatted}
    except Exception as e:
        return {"success": False, "error": str(e)}

mcp.tool(check_campaigns)

def list_services() -> Dict:
    """Tüm hizmetleri listeler."""
    services = get_all_services_from_cms()
    names = [s['name'] for s in services]
    return {"success": True, "services": names}

mcp.tool(list_services)

def list_experts(service_type: Optional[str] = None) -> Dict:
    """Uzmanları listeler."""
    experts = get_all_experts_from_cms(service_type)
    return {"success": True, "experts": experts}

mcp.tool(list_experts)

# --------------------------------------------------------------------------
# MCP Mount & Pydantic Models
# --------------------------------------------------------------------------
from fastmcp.server.http import create_sse_app
sse_app = create_sse_app(server=mcp, sse_path="/sse", message_path="/messages")
app.mount("/mcp", sse_app)

# Pydantic Modelleri (Swagger için)
class CheckAvailabilityRequest(BaseModel):
    service_type: str
    date_time: Optional[str] = None
    date: Optional[str] = None
    expert_name: Optional[str] = None

class CreateAppointmentRequest(BaseModel):
    customer_phone: str
    service_type: str
    appointment_datetime: str
    customer_name: Optional[str] = None
    expert_name: Optional[str] = None

# API Endpointleri
@app.post("/api/check_availability")
async def api_check_availability(request: CheckAvailabilityRequest):
    return check_availability(request.service_type, request.date_time, request.date, request.expert_name)

@app.post("/api/create_appointment")
async def api_create_appointment(request: CreateAppointmentRequest):
    return create_appointment(request.customer_phone, request.service_type, request.appointment_datetime, request.customer_name, request.expert_name)

@app.get("/api/list_services")
async def api_list_services():
    return list_services()

@app.get("/api/list_experts")
async def api_list_experts():
    return list_experts()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_server:app", host=settings.MCP_SERVER_HOST, port=settings.MCP_SERVER_PORT, reload=True)