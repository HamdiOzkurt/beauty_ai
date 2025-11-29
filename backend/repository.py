import requests
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import random
import string
import logging

# Config dosyanızda bu ayarların olduğunu varsayıyoruz
# Config dosyasından ayarları al
from config import settings


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

class ServiceRepository(BaseDirectusRepository):
    """voises_services tablosu işlemleri"""

    def list_all(self) -> List[DirectusItem]:
        """Belirli bir tenant'a ait tüm aktif hizmetleri listeler."""
        params = {
            "filter[_and][0][is_active][_eq]": True,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
            "fields": "name" # Sadece hizmet ismini çekmek yeterli
        }
        data = self._get("voises_services", params)
        return [DirectusItem(**item) for item in data]

class CustomerRepository(BaseDirectusRepository):
    """voises_customers tablosu işlemleri"""
    
    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Telefon numarasını +90 ile başlayan formata çevirir"""
        # Boşlukları ve özel karakterleri temizle
        phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # +90 ile başlıyorsa olduğu gibi döndür
        if phone.startswith('+90'):
            return phone
        
        # 0 ile başlıyorsa 0'ı kaldır ve +90 ekle
        if phone.startswith('0'):
            return '+90' + phone[1:]
        
        # Hiçbiri değilse direkt +90 ekle (5057142752 gibi)
        return '+90' + phone

    def get_by_phone(self, phone: str) -> Optional[DirectusItem]:
        # Telefon numarasını normalize et
        normalized_phone = self.normalize_phone(phone)
        
        params = {
            "filter[_and][0][phone_number][_eq]": normalized_phone,
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
        
        # ⚠️ FIX: Sadece confirmed (aktif) randevuları getir
        # _neq kullanmak yerine, pozitif olarak confirmed olanları filtrele
        if not include_cancelled:
            params["filter[_and][2][status][_eq]"] = "confirmed"
        
        # 🔍 DEBUG: Sorgu parametrelerini logla
        logging.info(f"[get_appointments] Customer ID: {customer_id}, Params: {params}")

        data = self._get("voises_appointments", params)
        
        # 🔍 DEBUG: Dönen veriyi logla
        logging.info(f"[get_appointments] Dönen veri sayısı: {len(data)}")
        if data:
            logging.info(f"[get_appointments] İlk randevu örneği: {data[0]}")
        else:
            logging.warning(f"[get_appointments] ⚠️ Hiç randevu bulunamadı! Customer ID: {customer_id}")
            # Tüm randevuları çek (status filtresi olmadan) debug için
            debug_params = {
                "filter[_and][0][customer_id][_eq]": customer_id,
                "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
                "sort": "-date_time",
                "limit": limit,
                "fields": "*.*"
            }
            all_data = self._get("voises_appointments", debug_params)
            logging.info(f"[get_appointments] DEBUG - Status filtresi olmadan: {len(all_data)} randevu bulundu")
            if all_data:
                for apt in all_data:
                    logging.info(f"[get_appointments] DEBUG - Randevu: ID={apt.get('id')}, Status={apt.get('status')}, Date={apt.get('date_time')}")
        
        return [DirectusItem(**item) for item in data]

    def create(self, full_name: str, phone: str, email: str = None) -> DirectusItem:
        # Telefon numarasını normalize et
        normalized_phone = self.normalize_phone(phone)
        
        # İsim soyisim ayırma (Basit mantık)
        parts = full_name.strip().split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        payload = {
            "tenant_id": CURRENT_TENANT_ID,
            "first_name": first_name,
            "last_name": last_name,
            "phone_number": normalized_phone,  # Normalize edilmiş telefon
            "created_date": datetime.now().replace(tzinfo=None).isoformat(),
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

    def _get_service_by_name(self, service_name: str) -> Optional[Dict]:
        """Hizmet isminden hizmet bilgisini (ID, duration vb.) bulmak için."""
        params = {
            "filter[_and][0][name][_icontains]": service_name,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID,
            "limit": 1
        }
        data = self._get("voises_services", params)
        return data[0] if data else None

    def check_availability(
        self,
        expert_id: int,
        start_time: datetime,
        duration_minutes: int
    ) -> bool:
        """Belirli bir uzmanın belirli bir zamanda müsait olup olmadığını kontrol eder."""
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # ÖNCE: Basit sorgu - sadece aynı gün ve aynı uzman
        params = {
            "filter[expert_id][_eq]": expert_id,
            "filter[tenant_id][_eq]": CURRENT_TENANT_ID,
            "fields": "id,date_time,end_date,status",
            "limit": -1
        }
        
        logging.info(f"[check_availability] Uzman ID: {expert_id}, Zaman: {start_time.isoformat()}")
        logging.info(f"[check_availability] Sorgu: {params}")
        
        all_appointments = self._get("voises_appointments", params)
        logging.info(f"[check_availability] Bulunan TÜM randevu: {len(all_appointments)}")
        
        # Python'da hem tarih hem status filtrele
        conflicts = []
        for appt in all_appointments:
            status = appt.get('status', '').lower()  # 🔧 FIX: Küçük harfe çevir
            # Aktif randevuları kontrol et (pending, confirmed, Pending, Confirmed hepsi)
            if status not in ['pending', 'confirmed']:
                logging.debug(f"[check_availability] Randevu {appt.get('id')} atlandı (Status={appt.get('status')})")
                continue
            
            try:
                appt_start_str = appt.get('date_time')
                appt_end_str = appt.get('end_date')
                
                if not appt_start_str or not appt_end_str:
                    logging.warning(f"[check_availability] Randevu {appt.get('id')} tarih bilgisi eksik!")
                    continue
                
                # Timezone'u temizle ve parse et
                appt_start = datetime.fromisoformat(appt_start_str.replace('Z', '+00:00').replace('+00:00', ''))
                appt_end = datetime.fromisoformat(appt_end_str.replace('Z', '+00:00').replace('+00:00', ''))
                
                # Çakışma kontrolü: (StartA < EndB) and (EndA > StartB)
                if (start_time < appt_end) and (end_time > appt_start):
                    conflicts.append(appt)
                    logging.info(f"[check_availability] ❌ ÇAKIŞMA! Randevu ID={appt.get('id')}, {appt_start} - {appt_end}, Status={status}")
            except Exception as e:
                logging.error(f"[check_availability] Tarih parse hatası (ID={appt.get('id')}): {e}")
                continue
        
        logging.info(f"[check_availability] Toplam çakışma: {len(conflicts)}")
        return len(conflicts) == 0

    def get_appointments_for_expert_and_time(
        self,
        expert_id: int,
        start_time: datetime,
        duration_minutes: int
    ) -> List[Dict]:
        """Belirli bir uzmanın belirli bir zamandaki randevularını döndürür."""
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        params = {
            "filter[expert_id][_eq]": expert_id,
            "filter[tenant_id][_eq]": CURRENT_TENANT_ID,
            "filter[date_time][_lt]": end_time.isoformat(),
            "filter[end_date][_gt]": start_time.isoformat(),
            "fields": "id,date_time,end_date,status",
            "limit": -1
        }
        
        logging.info(f"[check_availability] Uzman ID: {expert_id}, Zaman: {start_time.isoformat()}, Parametreler: {params}")
        
        all_appointments = self._get("voises_appointments", params)
        
        # Status kontrolü - sadece pending ve confirmed olanları say
        active_appointments = [
            apt for apt in all_appointments 
            if apt.get('status') in ['pending', 'confirmed']
        ]
        
        logging.info(f"[check_availability] Bulunan çakışan randevu: {len(active_appointments)}")
        return active_appointments

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

        # 2. Hizmet bilgisini bul (ID ve duration)
        service = self._get_service_by_name(service_type)
        if not service:
            raise Exception(f"Hizmet bulunamadı: {service_type}")

        service_id = service['id']

        # 3. Süreyi CMS'ten al (yoksa varsayılan 60 dk)
        duration = service.get('duration', 60)
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
            "created_at": datetime.now().replace(tzinfo=None).isoformat(),
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
        # NOT: Status filtresini Python tarafında yapalım, Directus _in bazen sorunlu
        params = {
            "filter[date_time][_gte]": start_of_day.isoformat(),
            "filter[date_time][_lte]": end_of_day.isoformat(),
            "filter[tenant_id][_eq]": CURRENT_TENANT_ID,
            "fields": "id,date_time,end_date,status,expert_id.id,expert_id.first_name,expert_id.last_name",  # 🔧 FIX: expert_id.id eklendi
            "limit": -1
        }
        
        logging.info(f"[find_available_slots_for_day] Sorgu parametreleri: {params}")
        all_appointments = self._get("voises_appointments", params)
        
        # 🔍 DEBUG: Raw data'yı logla
        if all_appointments:
            logging.info(f"[find_available_slots_for_day] ⚠️ RAW DATA SAMPLE: {all_appointments[0]}")
        
        # Python tarafında status filtrele
        daily_appointments_data = [
            appt for appt in all_appointments 
            if appt.get('status', '').lower() in ['confirmed', 'pending']  # 🔧 FIX: Küçük harfe çevir
        ]
        
        # DEBUG: Gelen randevuları logla
        logging.info(f"[find_available_slots_for_day] Tarih: {day}, Bulunan randevu sayısı: {len(daily_appointments_data)}")
        for appt in daily_appointments_data:
            logging.info(f"[find_available_slots_for_day] ⚠️ RANDEVU DETAYI: ID={appt.get('id')}, DateTime={appt.get('date_time')}, EndDate={appt.get('end_date')}, Expert={appt.get('expert_id')}, Status={appt.get('status')}")
        
        # 3. Aktif Uzmanları Çek
        # Eğer belirli bir uzman isteniyorsa sadece onu, yoksa hepsini çek
        expert_params = {
            "filter[_and][0][is_active][_eq]": True,
            "filter[_and][1][tenant_id][_eq]": CURRENT_TENANT_ID
        }
        if expert_name:
             parts = expert_name.split(' ', 1)
             expert_params["filter[_and][2][first_name][_icontains]"] = parts[0]
             logging.info(f"[find_available_slots_for_day] 🔍 Sadece '{expert_name}' uzmanı için arama yapılıyor")
        
        experts_data = self._get("voises_experts", expert_params)
        logging.info(f"[find_available_slots_for_day] Bulunan uzman sayısı: {len(experts_data)} (Filtre: {expert_name or 'Tüm uzmanlar'})")
        
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
                    if isinstance(appt_exp_id, dict): 
                        appt_exp_id = appt_exp_id.get('id')
                    
                    logging.debug(f"[find_available_slots_for_day] Karşılaştırma: Expert ID {exp_id} vs Appt Expert ID {appt_exp_id}")
                    
                    if appt_exp_id != exp_id:
                        continue
                        
                    # Çakışma Kontrolü
                    # Directus'tan gelen string tarihleri objeye çevir (timezone-naive olarak)
                    appt_start = datetime.fromisoformat(appt['date_time'].replace('Z', '+00:00')).replace(tzinfo=None)
                    appt_end = datetime.fromisoformat(appt['end_date'].replace('Z', '+00:00')).replace(tzinfo=None)
                    
                    logging.info(f"[find_available_slots_for_day] 🔍 Çakışma kontrol: Slot({potential_slot.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}) vs Appt({appt_start.strftime('%H:%M')}-{appt_end.strftime('%H:%M')})")
                    
                    # (StartA < EndB) and (EndA > StartB)
                    if (potential_slot < appt_end) and (slot_end > appt_start):
                        is_taken = True
                        logging.info(f"[find_available_slots_for_day] ❌ ÇAKIŞMA! {exp_full_name} saat {potential_slot.strftime('%H:%M')} DOLU (Randevu: {appt_start.strftime('%H:%M')}-{appt_end.strftime('%H:%M')})")
                        break
                    else:
                        logging.debug(f"[find_available_slots_for_day] ✅ Çakışma yok: {potential_slot.strftime('%H:%M')}")
                
                if not is_taken:
                    available_slots.append((potential_slot, exp_full_name))
            
            potential_slot += timedelta(minutes=settings.APPOINTMENT_SLOT_MINUTES)
            
        return available_slots