from fastapi import FastAPI
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

# Logging konfigürasyonu
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp_server.log', encoding='utf-8')
    ]
)

from repository import CustomerRepository, AppointmentRepository
from config import settings, SERVICE_DURATIONS, COMPLEMENTARY_SERVICES, CAMPAIGNS, EXPERTS

# --------------------------------------------------------------------------
# Ana FastAPI uygulamasını oluştur
# --------------------------------------------------------------------------
app = FastAPI(
    title="Güzellik Merkezi Asistanı API",
    description="Bu API, Güzellik Merkezi Asistanı'nın kullandığı araçları (tools) içerir ve interaktif olarak test edilebilir.",
    version="1.0.0",
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
mcp = FastMCP(
    "Güzellik Merkezi Asistanı MCP Sunucusu",
)

# MCP araçlarını tanımla

def check_availability(
    service_type: str,
    date_time: Optional[str] = None,
    date: Optional[str] = None,
    expert_name: Optional[str] = None
) -> Dict:
    """
    Belirtilen hizmet ve tarih için uygun saat aralıklarını ve ilgili uzmanları bulur.
    Kullanıcı genel bir sorgu yaptıysa (örn. günün tamamı), birden fazla uygun saat listeler.

    Args:
        service_type: İstenen hizmetin türü.
        date_time: (Opsiyonel) İstenen tarih ve saat (ISO 8601 formatı).
        date: (Opsiyonel) İstenen tarih (YYYY-MM-DD formatı).
        expert_name: (Opsiyonel) Tercih edilen uzmanın adı.

    Returns:
        Müsaitlik durumunu ve saatlere göre gruplanmış uzman listesini içeren bir sözlük.
    """
    try:
        if not date_time and not date:
            return {"success": False, "error": "Tarih ('date' veya 'date_time') parametresi zorunludur."}

        effective_date_str = date_time if date_time else date
        
        try:
            requested_time = datetime.fromisoformat(effective_date_str)
        except ValueError:
            try:
                requested_time = datetime.strptime(effective_date_str, '%Y-%m-%d')
            except ValueError:
                return {"success": False, "error": "Geçersiz tarih formatı. Lütfen YYYY-MM-DD veya YYYY-MM-DDTHH:MM:SS formatında girin."}

        duration = SERVICE_DURATIONS.get(service_type.replace(' ', '_'), 60)

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
            "message": f"{requested_time.strftime('%d %B %Y')} için uygun saatler ve uzmanlar bulundu.",
            "available_slots": slots_by_time
        }
    except Exception as e:
        logging.error(f"check_availability hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı bağlantı hatası: {str(e)}"}

# MCP'ye kaydet
mcp.tool(check_availability)


def suggest_complementary_service(service_type: str) -> Dict:
    """
    Seçilen bir ana hizmete dayalı olarak tamamlayıcı veya çapraz satış hizmetleri önerir.
    """
    suggestions = COMPLEMENTARY_SERVICES.get(service_type, [])
    return {
        "success": True,
        "service": service_type,
        "suggestions": suggestions
    }

mcp.tool(suggest_complementary_service)

def check_customer(phone: str) -> Dict:
    """
    Telefon numarasına göre müşteri bilgilerini kontrol et ve geçmiş randevularını getir.
    """
    try:
        repo = CustomerRepository()
        customer = repo.get_by_phone(phone)

        if not customer:
            return {"success": False, "message": "Müşteri bulunamadı"}

        appointments = repo.get_appointments(customer.id, limit=5)

        return {
            "success": True,
            "customer": {
                "id": customer.id,
                "name": customer.full_name,
                "phone": customer.phone,
                "total_appointments": customer.total_appointments,
                "is_first_appointment": customer.is_first_appointment,
                "loyalty_points": customer.loyalty_points
            },
            "recent_appointments": [
                {
                    "code": apt.appointment_code,
                    "service": apt.service_type,
                    "expert": apt.expert_name,
                    "date": apt.appointment_date.isoformat(),
                    "status": apt.status.value
                } for apt in appointments
            ]
        }
    except Exception as e:
        logging.error(f"check_customer hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı bağlantı hatası: {str(e)}"}

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

        customer = customer_repo.get_by_phone(customer_phone)
        if not customer:
            if customer_name:
                logging.info(f"{customer_phone} numaralı müşteri bulunamadı, '{customer_name}' adıyla yeni müşteri oluşturuluyor.")
                try:
                    existing_customer = customer_repo.get_by_phone(customer_phone)
                    if existing_customer:
                        customer = existing_customer
                    else:
                        customer = customer_repo.create(customer_name, customer_phone)
                except Exception as e:
                    logging.error(f"Yeni müşteri oluşturulurken hata: {e}")
                    return {"success": False, "error": f"Yeni müşteri '{customer_name}' oluşturulurken bir hata oluştu: {str(e)}"}
            else:
                return {"success": False, "error": f"{customer_phone} numaralı müşteri bulunamadı. Lütfen önce müşterinin adını alarak kayıt oluşturun."}

        try:
            appointment_time = datetime.fromisoformat(appointment_datetime)
            duration = SERVICE_DURATIONS.get(service_type.replace(' ', '_'), 60)
        except ValueError:
            return {"success": False, "error": "Geçersiz tarih formatı. Lütfen YYYY-MM-DDTHH:MM:SS formatında girin."}

        assigned_expert = None
        if expert_name:
            # Eğer uzman adı verildiyse, sadece o uzmanın müsaitliğini kontrol et
            if appointment_repo.check_availability(expert_name, appointment_time, duration):
                assigned_expert = expert_name
            else:
                return {"success": False, "error": f"Maalesef {expert_name} seçtiğiniz saatte müsait değil. Lütfen başka bir uzman veya farklı bir saat seçin."}
        else:
            # Gelen hizmet adını " ve " bağlacına göre ayırarak birden fazla hizmeti işle
            requested_services = [s.strip().replace(' ', '_') for s in service_type.split(' ve ')]
            if not requested_services or not all(requested_services):
                return {"success": False, "error": "Geçerli bir hizmet türü belirtilmedi."}

            # Belirtilen tüm hizmetleri verebilen uzmanları bul
            suitable_experts = []
            for expert in EXPERTS.values():
                expert_specialties = expert.get("specialties", [])
                if all(service in expert_specialties for service in requested_services):
                    suitable_experts.append(expert["full_name"])

            if not suitable_experts:
                return {"success": False, "error": f"'{service_type}' hizmetini verebilecek bir uzman bulunamadı."}

            # Uygun uzmanlar arasından o saatte müsait olanları bul
            available_and_suitable_experts = []
            for expert_name_to_check in suitable_experts:
                if appointment_repo.check_availability(expert_name_to_check, appointment_time, duration):
                    available_and_suitable_experts.append(expert_name_to_check)
            
            if not available_and_suitable_experts:
                return {"success": False, "error": f"'{service_type}' hizmeti için belirtilen saatte uygun bir uzman bulunamadı."}

            # Eğer birden fazla uzman müsaitse, kullanıcıya sorması için hata döndür
            if len(available_and_suitable_experts) > 1:
                return {
                    "success": False, 
                    "error": "Birden fazla uygun uzman bulundu. Lütfen kullanıcıdan bir uzman seçmesini isteyin.",
                    "action_required": "ask_user_to_choose_expert",
                    "available_experts": available_and_suitable_experts
                }
            
            # Tek bir uzman müsaitse, otomatik ata
            assigned_expert = available_and_suitable_experts[0]
            logging.info(f"Otomatik atama başarılı: '{assigned_expert}' uzmanı '{service_type}' hizmeti için atandı.")
                     
        try:
            appointment = appointment_repo.create(
                customer_id=customer.id,
                expert_name=assigned_expert,
                service_type=service_type,
                appointment_date=appointment_time
            )

            message = f"Randevunuz {assigned_expert} için başarıyla oluşturuldu."
            
            return {
                "success": True,
                "message": message,
                "appointment": {
                    "code": appointment.appointment_code,
                    "customer": customer.full_name,
                    "expert": assigned_expert,
                    "service": service_type,
                    "date": appointment_time.strftime("%d.%m.%Y"),
                    "time": appointment_time.strftime("%H:%M"),
                    "duration": duration
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Randevu oluşturulurken beklenmedik bir hata oluştu: {str(e)}"}
    except Exception as e:
        logging.error(f"create_appointment hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı bağlantı hatası: {str(e)}"}

mcp.tool(create_appointment)

def create_new_customer(full_name: str, phone: str) -> Dict:
    """
    Verilen bilgilerle yeni bir müşteri profili oluşturur.
    """
    try:
        repo = CustomerRepository()
        
        existing_customer = repo.get_by_phone(phone)
        if existing_customer:
            return {
                "success": False, 
                "error": f"Bu telefon numarası ({phone}) zaten {existing_customer.full_name} adına kayıtlı."
            }

        try:
            new_customer = repo.create(full_name, phone)
            return {
                "success": True,
                "customer": {
                    "id": new_customer.id,
                    "name": new_customer.full_name,
                    "phone": new_customer.phone
                }
            }
        except Exception as e:
            return {
                "success": False, 
                "error": f"Müşteri oluşturulurken hata: {str(e)}"
            }
    except Exception as e:
        logging.error(f"create_new_customer hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı bağlantı hatası: {str(e)}"}

mcp.tool(create_new_customer)

def cancel_appointment(appointment_code: str, reason: str = "Müşteri talebi", customer_phone: Optional[str] = None) -> Dict:
    """
    Verilen 6 haneli randevu kodunu kullanarak mevcut bir randevuyu iptal eder.
    """
    try:
        repo = AppointmentRepository()
        logging.info(f"Randevu iptal talebi alindi. Kod: {appointment_code}, Neden: {reason}")
        
        try:
            cancelled_appointment = repo.cancel(appointment_code, reason)
            logging.info(f"repo.cancel sonucu: {cancelled_appointment}")

            if not cancelled_appointment:
                logging.warning(f"İptal basarisiz: {appointment_code} kodlu randevu bulunamadi veya zaten iptal edilmis.")
                return {"success": False, "error": f'{appointment_code} kodlu bir randevu bulunamadı veya zaten iptal edilmiş.'}

            logging.info(f"İptal basarili: {appointment_code}")
            return {
                "success": True,
                "message": f"{appointment_code} kodlu randevu başarıyla iptal edildi.",
                "cancelled_appointment": {
                    "code": cancelled_appointment.appointment_code,
                    "service": cancelled_appointment.service_type,
                    "date": cancelled_appointment.appointment_date.isoformat()
                }
            }
        except Exception as e:
            logging.error(f"cancel_appointment aracinda beklenmedik hata: {e}", exc_info=True)
            return {"success": False, "error": f"Randevu iptal edilirken sunucuda bir hata oluştu: {str(e)}"}
    except Exception as e:
        logging.error(f"cancel_appointment hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı bağlantı hatası: {str(e)}"}

mcp.tool(cancel_appointment)

def check_campaigns(customer_phone: str) -> Dict:
    """
    Bir müşteri için geçerli olan aktif kampanyaları kontrol eder.
    """
    try:
        customer_repo = CustomerRepository()
        customer = customer_repo.get_by_phone(customer_phone)

        if not customer:
            return {"success": False, "error": f"{customer_phone} numaralı müşteri bulunamadı."}

        applicable_campaigns = []
        
        if customer.is_first_appointment:
            applicable_campaigns.append(CAMPAIGNS["yeni_müşteri"])
        
        if customer.total_appointments > 0 and customer.total_appointments % 5 == 0:
            if "sadakat" in CAMPAIGNS:
                applicable_campaigns.append(CAMPAIGNS["sadakat"])
        
        if not applicable_campaigns:
            return {"success": True, "campaigns": [], "message": "Şu anda size özel bir kampanya bulunmuyor."}

        return {
            "success": True,
            "campaigns": applicable_campaigns
        }
    except Exception as e:
        logging.error(f"check_campaigns hatası: {str(e)}")
        return {"success": False, "error": f"Veritabanı bağlantı hatası: {str(e)}"}

mcp.tool(check_campaigns)

def list_services() -> Dict:
    """
    Merkezde sunulan tüm hizmetlerin bir listesini döndürür.
    """
    formatted_services = [name.replace('_', ' ').title() for name in SERVICE_DURATIONS.keys()]
    return {
        "success": True,
        "services": formatted_services
    }

mcp.tool(list_services)

def list_experts() -> Dict:
    """
    Merkezde çalışan tüm uzmanların listesini ve uzmanlık alanlarını döndürür.
    """
    experts_info = []
    for key, data in settings.EXPERTS.items():
        name = data.get("full_name", key)
        specialties = data.get("specialties") or data.get("services") or []
        formatted = [s.replace('_', ' ').title() for s in specialties]
        experts_info.append({"name": name, "specialties": formatted})
    if not experts_info:
        return {"success": False, "error": "Uzman listesi yapılandırması bulunamadı."}
        
    return {
        "success": True,
        "experts": experts_info
    }

mcp.tool(list_experts)

# --------------------------------------------------------------------------
# MCP uygulamasını mount et - API endpoint'lerinden ÖNCE
# --------------------------------------------------------------------------
# Modern FastMCP kullanımı - SSE endpoint'leri ile
from fastmcp.server.http import create_sse_app
sse_app = create_sse_app(
    server=mcp, 
    sse_path="/sse",
    message_path="/messages"
)
# MCP'yi /mcp prefix'i altına mount ediyoruz böylece /api ve /docs çalışmaya devam eder
app.mount("/mcp", sse_app)

# --------------------------------------------------------------------------
# Pydantic Request Models - Swagger UI için
# --------------------------------------------------------------------------
class CheckAvailabilityRequest(BaseModel):
    service_type: str = Field(..., description="İstenen hizmetin türü")
    date_time: Optional[str] = Field(None, description="İstenen tarih ve saat (ISO 8601 formatı)")
    date: Optional[str] = Field(None, description="İstenen tarih (YYYY-MM-DD formatı)")
    expert_name: Optional[str] = Field(None, description="Tercih edilen uzmanın adı")

class ComplementaryServiceRequest(BaseModel):
    service_type: str = Field(..., description="Ana hizmet türü")

class CheckCustomerRequest(BaseModel):
    phone: str = Field(..., description="Müşteri telefon numarası")

class RegisterCustomerRequest(BaseModel):
    phone: str = Field(..., description="Müşteri telefon numarası")
    name: str = Field(..., description="Müşteri adı")

class CreateAppointmentRequest(BaseModel):
    customer_phone: str = Field(..., description="Müşteri telefon numarası")
    service_type: str = Field(..., description="Hizmet türü")
    appointment_datetime: str = Field(..., description="Randevu tarihi ve saati (YYYY-MM-DDTHH:MM:SS formatında)")
    customer_name: Optional[str] = Field(None, description="Müşteri adı (yeni müşteri için)")
    expert_name: Optional[str] = Field(None, description="Uzman adı")

class CancelAppointmentRequest(BaseModel):
    appointment_code: str = Field(..., description="Randevu kodu")
    reason: Optional[str] = Field(None, description="İptal nedeni")

class CheckCampaignsRequest(BaseModel):
    customer_phone: str = Field(..., description="Müşteri telefon numarası")

# --------------------------------------------------------------------------
# FastAPI Endpoints - Swagger UI'da görünecek
# --------------------------------------------------------------------------

@app.post("/api/check_availability", tags=["Randevu Yönetimi"], summary="Müsaitlik Kontrol")
async def api_check_availability(request: CheckAvailabilityRequest):
    """Belirtilen hizmet ve tarih için uygun saat aralıklarını ve uzmanları bulur."""
    return check_availability(
        service_type=request.service_type,
        date_time=request.date_time,
        date=request.date,
        expert_name=request.expert_name
    )

@app.post("/api/suggest_complementary_service", tags=["Hizmet Önerileri"], summary="Tamamlayıcı Hizmet Öner")
async def api_suggest_complementary_service(request: ComplementaryServiceRequest):
    """Seçilen ana hizmete tamamlayıcı hizmetler önerir."""
    return suggest_complementary_service(service_type=request.service_type)

@app.post("/api/check_customer", tags=["Müşteri Yönetimi"], summary="Müşteri Sorgula")
async def api_check_customer(request: CheckCustomerRequest):
    """Telefon numarasına göre müşteri bilgilerini sorgular."""
    return check_customer(phone=request.phone)

@app.post("/api/create_new_customer", tags=["Müşteri Yönetimi"], summary="Yeni Müşteri Kaydet")
async def api_create_new_customer(request: RegisterCustomerRequest):
    """Yeni bir müşteri kaydeder."""
    return create_new_customer(full_name=request.name, phone=request.phone)

@app.post("/api/create_appointment", tags=["Randevu Yönetimi"], summary="Randevu Oluştur")
async def api_create_appointment(request: CreateAppointmentRequest):
    """Yeni bir randevu oluşturur."""
    try:
        return create_appointment(
            customer_phone=request.customer_phone,
            service_type=request.service_type,
            appointment_datetime=request.appointment_datetime,
            customer_name=request.customer_name,
            expert_name=request.expert_name
        )
    except Exception as e:
        return {"success": False, "error": f"Hata: {str(e)}"}

@app.post("/api/cancel_appointment", tags=["Randevu Yönetimi"], summary="Randevu İptal")
async def api_cancel_appointment(request: CancelAppointmentRequest):
    """Bir randevuyu iptal eder."""
    return cancel_appointment(
        appointment_code=request.appointment_code,
        reason=request.reason or "Müşteri talebi"
    )

@app.post("/api/check_campaigns", tags=["Kampanyalar"], summary="Kampanya Kontrol")
async def api_check_campaigns(request: CheckCampaignsRequest):
    """Müşteri için geçerli kampanyaları kontrol eder."""
    return check_campaigns(customer_phone=request.customer_phone)

@app.get("/api/list_services", tags=["Hizmetler"], summary="Hizmet Listesi")
async def api_list_services():
    """Merkezde sunulan tüm hizmetleri listeler."""
    return list_services()

@app.get("/api/list_experts", tags=["Uzmanlar"], summary="Uzman Listesi")
async def api_list_experts():
    """Merkezde çalışan tüm uzmanları ve uzmanlık alanlarını listeler."""
    return list_experts()

# --------------------------------------------------------------------------
# Sunucuyu çalıştırma
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from config import settings
    
    uvicorn.run(
        "mcp_server:app",
        host=settings.MCP_SERVER_HOST,
        port=settings.MCP_SERVER_PORT,
        reload=True
    )