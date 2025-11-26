import requests
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import random
import string
import logging

# Config dosyasından ayarları al
from config import settings

# Varsayılan hizmet süreleri (dakika) - Directus'tan çekilemezse kullanılır
SERVICE_DURATIONS = {
    "sac_kesimi": 30,
    "sac_boyama": 90,
    "manikur": 45,
    "pedikur": 60,
    "cilt_bakimi": 60,
    "makyaj": 45,
    "agda": 30,
    "kirpik": 45,
    "kas_dizayn": 15,
}

# Sabit Tenant ID (Bunu config'den veya environment'tan almalısınız)
# Eğer her istekte değişiyorsa __init__ metoduna parametre olarak eklenmeli.
CURRENT_TENANT_ID = getattr(settings, "TENANT_ID", 1) 

class DirectusItem:
    """Directus'tan gelen JSON verisini Python objesine çevirir."""
    def __init__(self, **entries):
        self.__dict__.update(entries)
        
        # Tarih alanlarını otomatik dönüştür (Schema'daki isimlere göre)
        date_fields = ['created_date', 'last_visited_date', 'date_time', 'end_date', 'created_at', 'start_date']
        
        for field in date_fields:
            if hasattr(self, field) and getattr(self, field):
                val = getattr(self, field)
                if isinstance(val, str):
                    try:
                        # ISO formatındaki 'Z' harfini temizle
                        setattr(self, field, datetime.fromisoformat(val.replace('Z', '+00:00')))
                    except ValueError:
                        pass # Format uymazsa string olarak kalsın

class BaseDirectusRepository:
    """Directus API bağlantısı için temel sınıf."""
    
    def __init__(self):
        self.base_url = settings.DIRECTUS_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {settings.DIRECTUS_TOKEN}",
            "Content-Type": "application/json"
        }

    def _get(self, collection: str, params: Dict = None) -> List[Dict]:
        response = requests.get(f"{self.base_url}/items/{collection}", headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json().get('data', [])
        logging.error(f"Directus GET Error ({collection}): {response.text}")
        return []

    def _post(self, collection: str, data: Dict) -> Optional[Dict]:
        response = requests.post(f"{self.base_url}/items/{collection}", headers=self.headers, json=data)
        if response.status_code in [200, 201]:
            return response.json().get('data')
        logging.error(f"Directus POST Error ({collection}): {response.text}")
        return None

    def _patch(self, collection: str, item_id: int, data: Dict) -> Optional[Dict]:
        response = requests.patch(f"{self.base_url}/items/{collection}/{item_id}", headers=self.headers, json=data)
        if response.status_code == 200:
            return response.json().get('data')
        logging.error(f"Directus PATCH Error ({collection}): {response.text}")
        return None

class CustomerRepository(BaseDirectusRepository):
    """voises_customers tablosu işlemleri"""

    def get_by_phone(self, phone: str) -> Optional[DirectusItem]:
        params = {
            "filter[_and][0][phone_number][_eq]": phone,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
            "limit": 1
        }
        data = self._get("voises_customers", params)
        return DirectusItem(**data[0]) if data else None

    def get_appointments(self, customer_id: int, limit: int = 5, include_cancelled: bool = False) -> List[DirectusItem]:
        # voises_appointments tablosundan çekiyoruz
        params = {
            "filter[_and][0][customer_id][_eq]": customer_id,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
            "sort": "-date_time", # En yeni en başta
            "limit": limit,
            "fields": "*.*" # İlişkili verileri de (uzman adı vs) çekmek için
        }
        
        if not include_cancelled:
            params["filter[_and][2][status][_neq]"] = "cancelled"

        data = self._get("voises_appointments", params)
        return [DirectusItem(**item) for item in data]

    def create(self, full_name: str, phone: str, email: str = None) -> DirectusItem:
        # İsim soyisim ayırma (Basit mantık)
        parts = full_name.strip().split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        payload = {
            "tenant_id": CURRENT_TENANT_ID,
            "first_name": first_name,
            "last_name": last_name,
            "phone_number": phone,
            "created_date": datetime.utcnow().isoformat(),
            # Email alanı şemada yoktu ama varsa ekleyebilirsiniz: "email": email
        }
        data = self._post("voises_customers", payload)
        if data:
            return DirectusItem(**data)
        raise Exception("Müşteri oluşturulamadı.")

class AppointmentRepository(BaseDirectusRepository):
    """voises_appointments tablosu işlemleri"""

    def _get_expert_id_by_name(self, first_name: str, last_name: str = "") -> Optional[int]:
        """İsimden uzman ID'sini bulmak için yardımcı metod."""
        params = {
            "filter[_and][0][first_name][_icontains]": first_name,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
            "limit": 1
        }
        # Eğer soyadı da verildiyse filtreye ekle
        if last_name:
             params["filter[_and][2][last_name][_icontains]"] = last_name

        data = self._get("voises_experts", params)
        return data[0]['id'] if data else None

    def _get_service_id_by_name(self, service_name: str) -> Optional[int]:
        """Hizmet isminden ID bulmak için."""
        params = {
            "filter[_and][0][name][_icontains]": service_name,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
            "limit": 1
        }
        data = self._get("voises_services", params)
        return data[0]['id'] if data else None

    def check_availability(
        self,
        expert_id: int, # Artık ID ile kontrol ediyoruz
        start_time: datetime,
        duration_minutes: int
    ) -> bool:
        
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Directus JSON Filtreleme
        # Mantık: Aynı uzman, iptal edilmemiş VE zaman çakışması var
        filter_query = {
            "_and": [
                {"expert_id": {"_eq": expert_id}},
                {"tenant_id": {"_eq": CURRENT_TENANT_ID}},
                {"status": {"_in": ["pending", "confirmed"]}}, # Dropdown değerlerinize göre güncelleyin
                {"_and": [
                    {"date_time": {"_lt": end_time.isoformat()}}, # Mevcut Başlangıç < Yeni Bitiş
                    {"end_date": {"_gt": start_time.isoformat()}} # Mevcut Bitiş > Yeni Başlangıç
                ]}
            ]
        }
        
        params = {"filter": json.dumps(filter_query)}
        conflicts = self._get("voises_appointments", params)
        return len(conflicts) == 0

    def get_by_id(self, appointment_id: int) -> Optional[DirectusItem]:
        # Şemada 'appointment_code' yoktu, ID üzerinden gidiyoruz.
        # Eğer 'notes' içinde kod saklıyorsanız oradan arama yapılabilir.
        data = self._get(f"voises_appointments/{appointment_id}")
        # Tekil getirme işleminde data direkt obje dönebilir veya liste dönebilir, 
        # _get metodumuz liste dönüyor, onu kontrol edelim.
        # Directus ID ile get yapınca direkt objeyi data key'inde döner.
        # Ancak bizim _get metodumuz genel kullanım için liste dönüyor.
        # Bu yüzden ID ile çekmek için özel bir request yapabiliriz veya filter kullanabiliriz.
        
        params = {"filter[id][_eq]": appointment_id}
        data = self._get("voises_appointments", params)
        return DirectusItem(**data[0]) if data else None

    def create(
        self,
        customer_id: int,
        expert_name: str, # Servis katmanından isim geliyor olabilir
        service_type: str,
        appointment_date: datetime
    ) -> DirectusItem:
        
        # 1. Uzman ID'sini bul
        # expert_name muhtemelen "Ahmet Yılmaz" gibi geliyor. Ayırmamız lazım.
        exp_parts = expert_name.split(' ', 1)
        exp_id = self._get_expert_id_by_name(exp_parts[0], exp_parts[1] if len(exp_parts)>1 else "")
        if not exp_id:
            raise Exception(f"Uzman bulunamadı: {expert_name}")

        # 2. Hizmet ID'sini bul
        service_id = self._get_service_id_by_name(service_type)
        
        # 3. Süreyi hesapla
        duration = SERVICE_DURATIONS.get(service_type, 60)
        end_time = appointment_date + timedelta(minutes=duration)
        
        # Şemada 'appointment_code' alanı yoktu. 
        # Eğer notlara yazacaksak:
        appt_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        payload = {
            "tenant_id": CURRENT_TENANT_ID,
            "customer_id": customer_id,
            "expert_id": exp_id,
            "service_id": service_id, # İlişki varsa ID gönderilmeli
            "date_time": appointment_date.isoformat(),
            "end_date": end_time.isoformat(),
            "status": "confirmed", # Dropdown değerine uygun olmalı
            "created_at": datetime.utcnow().isoformat(),
            "notes": f"Auto-generated Code: {appt_code}" # Kodu notlara ekledik
        }
        
        data = self._post("voises_appointments", payload)
        if data:
            item = DirectusItem(**data)
            # Kodun geri kalanı appointment_code bekliyorsa, objeye manuel ekleyelim
            item.appointment_code = appt_code 
            return item
        raise Exception("Randevu oluşturulamadı.")

    def cancel(self, appointment_id: int, reason: Optional[str] = None) -> Optional[DirectusItem]:
        # ID ile iptal etme
        payload = {
            "status": "cancelled",
            "notes": f"Cancellation Reason: {reason}" # İptal nedeni için ayrı alan yoksa notlara ekle
        }
        
        data = self._patch("voises_appointments", appointment_id, payload)
        return DirectusItem(**data) if data else None

    def find_available_slots_for_day(self, service_type: str, day: datetime.date, duration_minutes: int, expert_name: Optional[str] = None) -> List[Tuple[datetime, str]]:
        """
        Optimize edilmiş müsaitlik kontrolü.
        API'ye binlerce istek atmamak için o günün tüm randevularını çeker,
        hafızada (RAM) kontrol eder.
        """
        
        # 1. O günün sınırlarını belirle
        start_of_day = datetime.combine(day, datetime.min.time())
        end_of_day = datetime.combine(day, datetime.max.time())
        
        # 2. O günkü TÜM randevuları çek (Sadece bu tenant için)
        params = {
            "filter[_and][0][date_time][_gte]": start_of_day.isoformat(),
            "filter[_and][1][date_time][_lte]": end_of_day.isoformat(),
            "filter[_and][2][tenant_id][_eq]": CURRENT_TENANT_ID,
            "filter[_and][3][status][_in]": ["confirmed", "pending"],
            "fields": "date_time,end_date,expert_id,expert_id.first_name,expert_id.last_name", # İlişkili uzman adını da çek
            "limit": -1 # Hepsini getir
        }
        
        daily_appointments_data = self._get("voises_appointments", params)
        
        # 3. Aktif Uzmanları Çek
        # Eğer belirli bir uzman isteniyorsa sadece onu, yoksa hepsini çek
        expert_params = {
            "filter[_and][0][is_active][_eq]": True,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID
        }
        if expert_name:
             parts = expert_name.split(' ', 1)
             expert_params["filter[_and][2][first_name][_icontains]"] = parts[0]
        
        experts_data = self._get("voises_experts", expert_params)
        
        # --- Python Tarafında Hesaplama ---
        
        available_slots = []
        start_business = datetime.combine(day, datetime.min.time()).replace(hour=settings.BUSINESS_HOURS_START)
        end_business = datetime.combine(day, datetime.min.time()).replace(hour=settings.BUSINESS_HOURS_END)
        
        potential_slot = start_business

        while potential_slot + timedelta(minutes=duration_minutes) <= end_business:
            slot_end = potential_slot + timedelta(minutes=duration_minutes)
            
            for expert in experts_data:
                exp_id = expert['id']
                exp_full_name = f"{expert.get('first_name','')} {expert.get('last_name','')}".strip()
                
                # Bu uzmanın o saatte randevusu var mı?
                is_taken = False
                for appt in daily_appointments_data:
                    # İlişkisel veri bazen obje, bazen sadece ID dönebilir, kontrol et:
                    appt_exp_id = appt.get('expert_id')
                    if isinstance(appt_exp_id, dict): appt_exp_id = appt_exp_id.get('id')
                    
                    if appt_exp_id != exp_id:
                        continue
                        
                    # Çakışma Kontrolü
                    # Directus'tan gelen string tarihleri objeye çevir
                    appt_start = datetime.fromisoformat(appt['date_time'].replace('Z', '+00:00'))
                    appt_end = datetime.fromisoformat(appt['end_date'].replace('Z', '+00:00'))
                    
                    # (StartA < EndB) and (EndA > StartB)
                    if (potential_slot < appt_end) and (slot_end > appt_start):
                        is_taken = True
                        break
                
                if not is_taken:
                    available_slots.append((potential_slot, exp_full_name))
            
            potential_slot += timedelta(minutes=settings.APPOINTMENT_SLOT_MINUTES)
            
        return available_slots