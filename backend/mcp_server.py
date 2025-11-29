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
        logging.info(f"CMS GET Request: {url}")
        logging.info(f"CMS GET Params: {params}")
        response = requests.get(url, headers=headers, params=params)
        logging.info(f"CMS Response Status: {response.status_code}")
        logging.info(f"CMS Response: {response.text[:500]}")  # İlk 500 karakter
        if response.status_code == 200:
            data = response.json().get('data', [])
            logging.info(f"CMS Data Count: {len(data)}")
            return data
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
        # duration_minute bazen int, bazen time string (HH:MM:SS) gelebilir
        duration_raw = data[0].get('duration_minute', 60)
        duration = 60 # Default
        
        if isinstance(duration_raw, (int, float)):
            duration = int(duration_raw)
        elif isinstance(duration_raw, str):
            # "01:25:00" formatındaysa parse et
            try:
                time_parts = duration_raw.split(':')
                if len(time_parts) >= 2:
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    duration = hours * 60 + minutes
                else:
                    duration = int(duration_raw)
            except:
                logging.warning(f"[get_service_details] Duration parse edilemedi: {duration_raw}, varsayılan 60 dk kullanılıyor")
                duration = 60
        
        return {
            "id": data[0]['id'],
            "name": data[0]['name'],
            "duration": duration,
            "description": data[0].get('description', ''),
            "price": data[0].get('price')
        }
    return None

def get_all_services_from_cms() -> List[Dict]:
    """Tüm aktif hizmetleri çeker."""
    params = {
        "filter[is_active][_eq]": True,
        "filter[tenant_id][_eq]": settings.TENANT_ID
    }
    return _directus_get("voises_services", params)

def normalize_turkish(text: str) -> str:
    """Türkçe karakterleri ASCII'ye çevir ve fazla boşlukları temizle (fuzzy matching için)."""
    if not text:
        return ""
    tr_map = {
        'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
        'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
    }
    for tr_char, en_char in tr_map.items():
        text = text.replace(tr_char, en_char)
    # Fazla boşlukları tek boşluğa indir ve baş/sondaki boşlukları temizle
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_all_experts_from_cms(service_name: Optional[str] = None) -> List[Dict]:
    """Uzmanları çeker. Opsiyonel olarak hizmete göre filtreler."""
    # Directus boolean ve tenant_id filtreleri
    params = {
        "fields": "*,services.voises_services_id.*"
    }
    
    # Tenant_id filtresi ekle (1 olan uzmanları getir)
    if settings.TENANT_ID:
        params["filter[tenant_id][_eq]"] = settings.TENANT_ID

    logging.info(f"[get_all_experts_from_cms] Params: {params}")
    experts_data = _directus_get("voises_experts", params)
    logging.info(f"[get_all_experts_from_cms] Raw data count: {len(experts_data)}")
    
    formatted_experts = []
    for exp in experts_data:
        logging.info(f"[get_all_experts_from_cms] Processing expert: {exp}")
        
        # İlişkili hizmetleri listeye çevir
        specialties = []
        if 'services' in exp and exp['services'] and isinstance(exp['services'], list):
            for s in exp['services']:
                if isinstance(s, dict) and s.get('voises_services_id'):
                    service_data = s['voises_services_id']
                    if isinstance(service_data, dict) and 'name' in service_data:
                        specialties.append(service_data['name'])
        
        expert_info = {
            "name": f"{exp.get('first_name', '')} {exp.get('last_name', '')}".strip(),
            "specialties": specialties,
            "id": exp.get('id')
        }
        
        # Eğer belirli bir hizmet isteniyorsa, filtrele
        if service_name:
            if any(service_name.lower() in s.lower() for s in specialties):
                formatted_experts.append(expert_info)
        else:
            formatted_experts.append(expert_info)
    
    logging.info(f"[get_all_experts_from_cms] Formatted experts count: {len(formatted_experts)}")
    return formatted_experts

def get_active_campaigns_from_cms() -> List[Dict]:
    """Aktif kampanyaları çeker."""
    now = datetime.utcnow()
    
    # Önce tüm kampanyaları çek, sonra Python'da filtrele
    params = {"filter[tenant_id][_eq]": settings.TENANT_ID}
    logging.info(f"[get_active_campaigns_from_cms] Şu anki tarih: {now.isoformat()}")
    
    all_campaigns = _directus_get("voises_campaigns", params)
    logging.info(f"[get_active_campaigns_from_cms] Toplam kampanya sayısı: {len(all_campaigns)}")
    
    active_campaigns = []
    for c in all_campaigns:
        start_date_str = c.get('start_date')
        end_date_str = c.get('end_date')
        
        logging.info(f"[get_active_campaigns_from_cms] Kampanya: {c.get('name')} | Start: {start_date_str} | End: {end_date_str}")
        
        try:
            # Directus'tan gelen tarih formatını parse et
            if start_date_str and end_date_str:
                start_date = None
                end_date = None
                
                # ISO format dene
                try:
                    start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00').replace('+00:00', ''))
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00').replace('+00:00', ''))
                except:
                    # YYYY-MM-DD formatı dene
                    try:
                        start_date = datetime.strptime(start_date_str.split('T')[0], '%Y-%m-%d')
                        end_date = datetime.strptime(end_date_str.split('T')[0], '%Y-%m-%d')
                    except:
                        logging.warning(f"[get_active_campaigns_from_cms] Tarih parse edilemedi: {start_date_str}, {end_date_str}")
                        continue
                
                # Kampanya aktif mi kontrol et
                if start_date and end_date and start_date <= now <= end_date:
                    active_campaigns.append(c)
                    logging.info(f"[get_active_campaigns_from_cms] ✅ Aktif kampanya: {c.get('name')}")
                else:
                    logging.info(f"[get_active_campaigns_from_cms] ❌ Tarih dışı: {c.get('name')} (Now: {now}, Start: {start_date}, End: {end_date})")
        except Exception as e:
            logging.error(f"[get_active_campaigns_from_cms] Tarih parse hatası: {e}")
            continue
    
    logging.info(f"[get_active_campaigns_from_cms] Aktif kampanya sayısı: {len(active_campaigns)}")
    return active_campaigns


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
        
        logging.info(f"[check_availability] Gelen tarih: '{effective_date_str}' (type: {type(effective_date_str).__name__})")
        
        # Tarih parsing - çoklu format desteği
        requested_time = None
        current_year = datetime.now().year
        
        # ISO format dene
        try:
            requested_time = datetime.fromisoformat(effective_date_str.replace('Z', '+00:00').replace('+00:00', ''))
            logging.info(f"[check_availability] ISO parse başarılı: {requested_time}")
        except:
            pass
        
        # YYYY-MM-DD format dene  
        if not requested_time:
            try:
                requested_time = datetime.strptime(effective_date_str, '%Y-%m-%d')
                logging.info(f"[check_availability] YYYY-MM-DD parse başarılı: {requested_time}")
            except:
                pass
        
        # DD.MM.YYYY format dene
        if not requested_time:
            try:
                requested_time = datetime.strptime(effective_date_str, '%d.%m.%Y')
                logging.info(f"[check_availability] DD.MM.YYYY parse başarılı: {requested_time}")
            except:
                pass
        
        # "3 aralık" gibi Türkçe format dene
        if not requested_time:
            import re
            tr_months = {
                'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'haziran': 6,
                'temmuz': 7, 'ağustos': 8, 'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
            }
            pattern = r'(\d{1,2})\s*([a-züğışöç]+)'
            match = re.search(pattern, effective_date_str.lower())
            if match:
                day = int(match.group(1))
                month_name = match.group(2)
                month = tr_months.get(month_name)
                if month:
                    requested_time = datetime(current_year, month, day)
                    logging.info(f"[check_availability] Türkçe tarih parse başarılı: {requested_time}")
        
        if not requested_time:
            logging.error(f"[check_availability] Hiçbir format çalışmadı: {effective_date_str}")
            return {"success": False, "error": "Geçersiz tarih formatı."}

        # 1. Hizmet süresini CMS'den çek
        service_info = get_service_details(service_type)
        if not service_info:
             return {"success": False, "error": f"'{service_type}' adında bir hizmet bulunamadı."}
        
        duration = service_info['duration']

        # 1.5. Türkçe karakter normalizasyonu ile uzman eşleştirme
        normalized_expert_name = None
        expert_id = None
        if expert_name:
            experts = get_all_experts_from_cms()
            normalized_input = normalize_turkish(expert_name.lower()).replace(' ', '')
            logging.info(f"🔍 [check_availability] Uzman aranıyor: '{expert_name}' -> normalized: '{normalized_input}'")
            for e in experts:
                normalized_expert = normalize_turkish(e['name'].lower()).replace(' ', '')
                logging.info(f"🔍 [check_availability] Karşılaştırma: '{normalized_expert}' vs '{normalized_input}'")
                # Boşluksuz eşleştirme + partial matching
                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    normalized_expert_name = e['name']
                    expert_id = e['id']
                    logging.info(f"🔍 [check_availability] ✅ Uzman eşleşti: '{expert_name}' -> '{normalized_expert_name}' (ID: {expert_id})")
                    break
            
            if not normalized_expert_name:
                expert_names = [e['name'] for e in experts]
                logging.warning(f"[check_availability] Uzman bulunamadı: '{expert_name}'. Mevcut: {expert_names}")
                return {"success": False, "error": f"Belirtilen uzman bulunamadı. Mevcut uzmanlar: {expert_names}"}

        # 2. Müsaitlik kontrolü - Önce belirli saat varsa kontrol et
        appointment_repo = AppointmentRepository()
        
        # 🔍 DEBUG: Gelen parametreleri logla
        logging.info(f"[check_availability] ===== MÜSAİTLİK KONTROLÜ BAŞLADI =====")
        logging.info(f"[check_availability] service_type: {service_type}")
        logging.info(f"[check_availability] date_time param: {date_time}")
        logging.info(f"[check_availability] date param: {date}")
        logging.info(f"[check_availability] expert_name: {expert_name}")
        logging.info(f"[check_availability] effective_date_str: {effective_date_str}")
        logging.info(f"[check_availability] requested_time: {requested_time}")
        logging.info(f"[check_availability] expert_id: {expert_id}")
        logging.info(f"[check_availability] normalized_expert_name: {normalized_expert_name}")
        
        # Eğer belirli bir saat verilmişse (date_time ile VEYA date+time ayrı), o saat için kontrol et
        has_specific_time = False
        
        # date_time parametresi varsa ve saat içeriyorsa
        if date_time and ':' in str(effective_date_str):
            has_specific_time = True
            logging.info(f"[check_availability] ✓ Belirli saat tespit edildi (date_time)")
        # VEYA date var ama requested_time'da saat bilgisi varsa (00:00'dan farklı)
        elif requested_time and requested_time.hour != 0:
            has_specific_time = True
            logging.info(f"[check_availability] ✓ Belirli saat tespit edildi (hour={requested_time.hour})")
        else:
            logging.info(f"[check_availability] ⚠️ Belirli saat YOK - Tüm gün kontrolüne geçiliyor")
        
        if has_specific_time and expert_id:
            logging.info(f"[check_availability] 🔎 Belirli saat kontrolü yapılıyor: {requested_time.strftime('%Y-%m-%d %H:%M')}")
            # Uzmanın o saatte başka randevusu var mı kontrol et
            is_available = appointment_repo.check_availability(
                expert_id=expert_id,
                start_time=requested_time,
                duration_minutes=service_info['duration']
            )
            
            logging.info(f"[check_availability] Müsaitlik sonucu: is_available={is_available}")
            
            if not is_available:
                logging.info(f"[check_availability] ❌ MÜSAİT DEĞİL!")
                return {
                    "success": True,
                    "available": False,
                    "message": f"{normalized_expert_name} uzmanımızın {requested_time.strftime('%d.%m.%Y %H:%M')} saatinde başka randevusu var. Alternatif saatler önerilsin mi?"
                }
            else:
                logging.info(f"[check_availability] ✅ MÜSAİT!")
                return {
                    "success": True,
                    "available": True,
                    "message": f"{normalized_expert_name} uzmanımız {requested_time.strftime('%d.%m.%Y %H:%M')} saatinde müsait.",
                    "available_slots": {requested_time.strftime('%H:%M'): [normalized_expert_name]}
                }
        
        # Tüm gün için müsaitlik kontrolü
        logging.info(f"[check_availability] 📅 Tüm gün müsaitlik kontrolü yapılıyor...")
        slots_with_experts = appointment_repo.find_available_slots_for_day(
            service_type=service_type,
            day=requested_time.date(),
            duration_minutes=service_info['duration'],
            expert_name=normalized_expert_name
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

def get_customer_appointments(phone: str) -> Dict:
    """
    Telefon numarasına göre müşterinin mevcut randevularını listeler.
    """
    try:
        customer_repo = CustomerRepository()
        
        # Müşteri kontrolü
        customer = customer_repo.get_by_phone(phone)
        if not customer:
            return {"success": False, "error": "Bu telefon numarasına kayıtlı müşteri bulunamadı."}
        
        # DirectusItem'dan müşteri adını al (doğrudan attribute erişimi)
        customer_name = f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
        
        # Randevuları getir (sadece aktif olanlar)
        appointments = customer_repo.get_appointments(customer.id, limit=10, include_cancelled=False)
        
        if not appointments:
            return {
                "success": True,
                "customer_name": customer_name,
                "appointments": [],
                "message": "Kayıtlı randevunuz bulunmamaktadır."
            }
        
        # Randevu bilgilerini formatla (DirectusItem doğrudan attribute erişimi)
        formatted_appointments = []
        for apt in appointments:
            # date_time datetime objesi olabilir, string'e çevir
            date_time = getattr(apt, 'date_time', None)
            if date_time and hasattr(date_time, 'strftime'):
                date_str = date_time.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = str(date_time) if date_time else ''
            
            formatted_appointments.append({
                "id": getattr(apt, 'id', None),
                "date": date_str,
                "service": getattr(apt, 'service_type', ''),
                "expert": getattr(apt, 'expert_name', ''),
                "status": getattr(apt, 'status', ''),
                "notes": getattr(apt, 'notes', '')
            })
        
        return {
            "success": True,
            "customer_name": customer_name,
            "appointments": formatted_appointments,
            "count": len(formatted_appointments)
        }
    except Exception as e:
        logging.error(f"get_customer_appointments error: {e}", exc_info=True)
        return {"success": False, "error": f"Randevu sorgulanırken hata: {str(e)}"}

mcp.tool(get_customer_appointments)

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

        # 2. Tarih Formatı - çoklu format desteği
        logging.info(f"[create_appointment] Gelen tarih: '{appointment_datetime}' (type: {type(appointment_datetime).__name__})")
        
        appointment_time = None
        current_year = datetime.now().year
        
        # ISO format dene
        try:
            appointment_time = datetime.fromisoformat(appointment_datetime.replace('Z', '+00:00').replace('+00:00', ''))
            logging.info(f"[create_appointment] ISO parse başarılı: {appointment_time}")
        except:
            pass
        
        # YYYY-MM-DD HH:MM format dene
        if not appointment_time:
            try:
                appointment_time = datetime.strptime(appointment_datetime, '%Y-%m-%d %H:%M')
                logging.info(f"[create_appointment] YYYY-MM-DD HH:MM parse başarılı: {appointment_time}")
            except:
                pass
        
        # DD.MM.YYYY HH:MM format dene
        if not appointment_time:
            try:
                appointment_time = datetime.strptime(appointment_datetime, '%d.%m.%Y %H:%M')
                logging.info(f"[create_appointment] DD.MM.YYYY HH:MM parse başarılı: {appointment_time}")
            except:
                pass
        
        # "3 aralık 15:00" gibi Türkçe format dene
        if not appointment_time:
            import re
            tr_months = {
                'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'haziran': 6,
                'temmuz': 7, 'ağustos': 8, 'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
            }
            pattern = r'(\d{1,2})\s*([a-züğışöç]+)\s+(\d{1,2})[:.] (\d{2})'
            match = re.search(pattern, appointment_datetime.lower())
            if match:
                day = int(match.group(1))
                month_name = match.group(2)
                hour = int(match.group(3))
                minute = int(match.group(4))
                month = tr_months.get(month_name)
                if month:
                    appointment_time = datetime(current_year, month, day, hour, minute)
                    logging.info(f"[create_appointment] Türkçe tarih parse başarılı: {appointment_time}")
        
        if not appointment_time:
            logging.error(f"[create_appointment] Tarih parse başarısız: {appointment_datetime}")
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
            experts = get_all_experts_from_cms()
            
            # 🔧 FIX: Türkçe karakter normalizasyonu + boşluk kaldırma
            normalized_input = normalize_turkish(expert_name.lower()).replace(' ', '')
            target_expert = None
            
            for e in experts:
                normalized_expert = normalize_turkish(e['name'].lower()).replace(' ', '')
                # Çift yönlü eşleştirme (boşluksuz)
                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    target_expert = e
                    break
            
            logging.info(f"🔍 Uzman arama: '{expert_name}' -> normalized: '{normalized_input}' -> Found: {target_expert}")
            
            if not target_expert:
                 return {"success": False, "error": f"Belirtilen uzman bulunamadı. Mevcut uzmanlar: {[e['name'] for e in experts]}"}

            if appointment_repo.check_availability(target_expert['id'], appointment_time, duration):
                assigned_expert = target_expert['name']
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
            
            # 🔧 FIX: 'full_name' -> 'name'
            if len(available_experts) > 1:
                # Birden fazla varsa kullanıcıya sor veya ilkini seç (Şimdilik ilkini seçiyoruz)
                assigned_expert = available_experts[0]['name']
            else:
                assigned_expert = available_experts[0]['name']

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
                    "code": getattr(appointment, 'appointment_code', 'N/A'),
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

def cancel_appointment(
    appointment_code: Optional[str] = None, 
    phone: Optional[str] = None,
    reason: str = "Müşteri talebi"
) -> Dict:
    """
    Randevu iptal eder. 
    - appointment_code: Randevu ID'si veya kodu
    - phone: Telefon numarası (varsa en son randevuyu iptal eder)
    En az biri gerekli.
    """
    try:
        repo = AppointmentRepository()
        customer_repo = CustomerRepository()
        appt_id = None
        
        # 1. Önce appointment_code ile dene
        if appointment_code:
            try:
                appt_id = int(appointment_code)
            except ValueError:
                # Kod string ise, notes içinde arayabiliriz (opsiyonel)
                pass
        
        # 2. Telefon numarasıyla randevu bul
        if not appt_id and phone:
            customer = customer_repo.get_by_phone(phone)
            if customer:
                appointments = customer_repo.get_appointments(customer.id, limit=1, include_cancelled=False)
                if appointments:
                    appt_id = getattr(appointments[0], 'id', None)
        
        if not appt_id:
            return {"success": False, "error": "İptal edilecek randevu bulunamadı."}
        
        cancelled = repo.cancel(appt_id, reason)
        
        if cancelled:
            return {"success": True, "message": "Randevunuz başarıyla iptal edildi."}
        return {"success": False, "error": "Randevu iptal edilemedi."}
    except Exception as e:
        logging.error(f"cancel_appointment error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

mcp.tool(cancel_appointment)

def check_campaigns(customer_phone: Optional[str] = None) -> Dict:
    """Aktif kampanyaları listeler."""
    try:
        # Aktif kampanyaları çek
        campaigns = get_active_campaigns_from_cms()
        
        if not campaigns:
             return {"success": True, "campaigns": [], "message": "Şu an aktif kampanya yok."}
        
        # Kampanya detaylarını formatla (bitiş tarihini de ekle)
        formatted = []
        for c in campaigns:
            end_date_str = c.get('end_date', '')
            # Tarihi daha okunabilir formata çevir
            try:
                if end_date_str:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00').replace('+00:00', ''))
                    end_date_formatted = end_date.strftime('%d.%m.%Y')
                else:
                    end_date_formatted = None
            except:
                end_date_formatted = None
            
            formatted.append({
                "name": c['name'], 
                "code": c.get('code'), 
                "discount": c.get('discount_rate'),
                "description": c.get('description', ''),
                "end_date": end_date_formatted
            })
        
        return {"success": True, "campaigns": formatted}
    except Exception as e:
        logging.error(f"[check_campaigns] Hata: {str(e)}", exc_info=True)
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

def suggest_alternative_times(service_type: str, date: str, expert_name: Optional[str] = None) -> Dict:
    """Alternatif randevu zamanları önerir."""
    try:
        service_info = get_service_details(service_type)
        if not service_info:
            return {"success": False, "error": "Hizmet bulunamadı."}
        
        duration = service_info['duration']
        
        try:
            requested_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
        except ValueError:
            try:
                requested_date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                return {"success": False, "error": "Geçersiz tarih formatı."}
        
        # Türkçe karakter normalizasyonu ile uzman eşleştirme
        normalized_expert_name = None
        if expert_name:
            experts = get_all_experts_from_cms()
            normalized_input = normalize_turkish(expert_name.lower())
            for e in experts:
                normalized_expert = normalize_turkish(e['name'].lower())
                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    normalized_expert_name = e['name']
                    logging.info(f"🔍 [suggest_alternative] Uzman eşleşti: '{expert_name}' -> '{normalized_expert_name}'")
                    break
        
        appointment_repo = AppointmentRepository()
        
        same_day_slots = appointment_repo.find_available_slots_for_day(
            service_type=service_type,
            day=requested_date.date(),
            duration_minutes=duration,
            expert_name=normalized_expert_name
        )
        
        alternatives = []
        
        if same_day_slots:
            for slot, expert in same_day_slots[:3]:
                alternatives.append({
                    "date": slot.strftime("%d.%m.%Y"),
                    "time": slot.strftime("%H:%M"),
                    "expert": expert,
                    "day_type": "aynı gün"
                })
        
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
            return {
                "success": True,
                "alternatives": [],
                "message": "Yakın tarihlerde uygun saat bulunamadı."
            }
        
        return {
            "success": True,
            "alternatives": alternatives[:10],
            "message": f"{len(alternatives[:10])} alternatif saat bulundu."
        }
        
    except Exception as e:
        logging.error(f"suggest_alternative_times hatası: {str(e)}")
        return {"success": False, "error": f"Sistem hatası: {str(e)}"}

mcp.tool(suggest_alternative_times)

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

class CancelAppointmentRequest(BaseModel):
    appointment_code: str
    reason: Optional[str] = "Müşteri talebi"

class CreateCustomerRequest(BaseModel):
    full_name: str
    phone: str

class CheckCustomerRequest(BaseModel):
    phone: str

class CheckCampaignsRequest(BaseModel):
    customer_phone: str

class SuggestAlternativesRequest(BaseModel):
    service_type: str
    date: str
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

@app.post("/api/cancel_appointment")
async def api_cancel_appointment(request: CancelAppointmentRequest):
    return cancel_appointment(request.appointment_code, request.reason)

@app.post("/api/create_customer")
async def api_create_customer(request: CreateCustomerRequest):
    return create_new_customer(request.full_name, request.phone)

@app.post("/api/check_customer")
async def api_check_customer(request: CheckCustomerRequest):
    return check_customer(request.phone)

@app.post("/api/check_campaigns")
async def api_check_campaigns(request: CheckCampaignsRequest):
    return check_campaigns(request.customer_phone)

@app.post("/api/suggest_alternatives")
async def api_suggest_alternatives(request: SuggestAlternativesRequest):
    """Alternatif randevu zamanları önerir."""
    try:
        # Hizmet süresini al
        service_info = get_service_details(request.service_type)
        if not service_info:
            return {"success": False, "error": "Hizmet bulunamadı."}
        
        duration = service_info['duration']
        
        # Tarihi parse et
        try:
            requested_date = datetime.fromisoformat(request.date.replace('Z', '+00:00'))
        except ValueError:
            try:
                requested_date = datetime.strptime(request.date, '%Y-%m-%d')
            except ValueError:
                return {"success": False, "error": "Geçersiz tarih formatı."}
        
        # Türkçe karakter normalizasyonu ile uzman eşleştirme
        normalized_expert_name = None
        if request.expert_name:
            experts = get_all_experts_from_cms()
            normalized_input = normalize_turkish(request.expert_name.lower())
            for e in experts:
                normalized_expert = normalize_turkish(e['name'].lower())
                if normalized_input in normalized_expert or normalized_expert in normalized_input:
                    normalized_expert_name = e['name']
                    logging.info(f"🔍 [api_suggest] Uzman eşleşti: '{request.expert_name}' -> '{normalized_expert_name}'")
                    break
        
        appointment_repo = AppointmentRepository()
        
        # Önce aynı gün için alternatif saatler bul
        same_day_slots = appointment_repo.find_available_slots_for_day(
            service_type=request.service_type,
            day=requested_date.date(),
            duration_minutes=duration,
            expert_name=normalized_expert_name
        )
        
        alternatives = []
        
        # Aynı gün alternatifleri ekle
        if same_day_slots:
            for slot, expert in same_day_slots[:3]:  # İlk 3 slot
                alternatives.append({
                    "date": slot.strftime("%d.%m.%Y"),
                    "time": slot.strftime("%H:%M"),
                    "expert": expert,
                    "day_type": "aynı gün"
                })
        
        # Sonraki 3 gün için de kontrol et
        for i in range(1, 4):
            next_day = requested_date + timedelta(days=i)
            next_day_slots = appointment_repo.find_available_slots_for_day(
                service_type=request.service_type,
                day=next_day.date(),
                duration_minutes=duration,
                expert_name=normalized_expert_name
            )
            
            if next_day_slots:
                for slot, expert in next_day_slots[:2]:  # Her günden 2 slot
                    alternatives.append({
                        "date": slot.strftime("%d.%m.%Y"),
                        "time": slot.strftime("%H:%M"),
                        "expert": expert,
                        "day_type": f"{i} gün sonra"
                    })
        
        if not alternatives:
            return {
                "success": True,
                "alternatives": [],
                "message": "Yakın tarihlerde uygun saat bulunamadı."
            }
        
        return {
            "success": True,
            "alternatives": alternatives[:10],  # Maksimum 10 alternatif
            "message": f"{len(alternatives[:10])} alternatif saat bulundu."
        }
        
    except Exception as e:
        logging.error(f"suggest_alternatives hatası: {str(e)}")
        return {"success": False, "error": f"Sistem hatası: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_server:app", host=settings.MCP_SERVER_HOST, port=settings.MCP_SERVER_PORT, reload=True)