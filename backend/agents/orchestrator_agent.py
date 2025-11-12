import google.generativeai as genai
from typing import Dict, Any, List
import logging
import json
import re
from datetime import datetime, timedelta

from agents.appointment_agent import AppointmentAgent
from agents.customer_agent import CustomerAgent
from agents.marketing_agent import MarketingAgent
from config import settings

class OrchestratorAgent:
    """
    Sesli Asistan için Orchestrator: Doğal, sıcak ve akıcı konuşmalar.
    """
    
    def __init__(self, conversations):
        self.agents = {
            "appointment": AppointmentAgent(),
            "customer": CustomerAgent(),
            "marketing": MarketingAgent(),
        }
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            settings.AGENT_MODEL,
            generation_config={
                "temperature": 0.4,  # Doğal konuşma için biraz kreativite
                "top_p": 0.95,
                "top_k": 40
            }
        )
        self.conversations = conversations

    def _extract_info_with_regex(self, user_message: str) -> Dict:
        """Regex ile hızlı bilgi çıkarma"""
        info = {}
        
        # Telefon
        phone_match = re.search(r'0?5\d{9}', user_message.replace(" ", "").replace("-", ""))
        if phone_match:
            info["phone"] = '0' + phone_match.group()[-10:]
        
        # Tarih formatı 1: DD.MM.YYYY veya DD/MM/YYYY (örn: 23.11.2025, 23/11/2025)
        date_match_dot = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', user_message)
        if date_match_dot:
            day = int(date_match_dot.group(1))
            month = int(date_match_dot.group(2))
            year = int(date_match_dot.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                info["date"] = f"{year}-{month:02d}-{day:02d}"
        
        # Tarih formatı 2: DD ay YYYY (örn: 23 kasım 2025, 23 Kasım 2025)
        if "date" not in info:  # Eğer dot format bulunamadıysa
            date_match = re.search(r'(\d{1,2})\s*(?:kasım|kasim|aralık|aralik|ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim)\s*(\d{4})', user_message.lower())
            if date_match:
                months = {"kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12, "ocak": 1, "şubat": 2, "subat": 2,
                          "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
                          "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10}
                day = int(date_match.group(1))
                month_str = re.search(r'(kasım|kasim|aralık|aralik|ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim)', date_match.group(0).lower())
                if month_str:
                    month = months.get(month_str.group(1))
                    year = int(date_match.group(2))
                    if month:
                        info["date"] = f"{year}-{month:02d}-{day:02d}"
        
        return info
    
    def _format_date_time(self, date: str, time: str = None) -> str:
        """Date ve time'ı ISO 8601 formatına çevir"""
        if not date:
            return None
        
        if time:
            # Time formatını kontrol et: "15:00" -> "15:00:00"
            if len(time) == 5 and ":" in time:  # HH:MM formatı
                time = f"{time}:00"
            return f"{date}T{time}"
        else:
            return f"{date}T09:00:00"
    
    async def _extract_with_gemini(self, user_message: str, conversation: Dict) -> Dict:
        """Gemini ile bilgi çıkarma - Konuşma geçmişinden de bilgi çıkarır"""
        
        today = datetime.now()
        
        # Konuşma geçmişini al (son 6 mesaj)
        history = conversation.get("history", [])
        history_text = "\n".join([
            f"{'Müşteri' if h['role'] == 'user' else 'Asistan'}: {h['content']}" 
            for h in history[-6:]
        ])
        
        # Daha önce toplanan bilgileri göster (Gemini'nin neyi hatırlaması gerektiğini bilsin)
        collected = conversation.get("collected", {})
        existing_info = ""
        if collected:
            # Bu kısmı daha net hale getirelim
            existing_info = f"\nMEVCUT TOPLANMIŞ BİLGİLER (BU BİLGİLERİ KORU VE GEREKİRSE GÜNCELLE):\n{json.dumps(collected, ensure_ascii=False)}\n"
        
        prompt = f"""Kullanıcının SON mesajından VE konuşma geçmişinden bilgi çıkar.

BUGÜNÜN TARİHİ: {today.strftime('%d %B %Y')}

KONUŞMA GEÇMİŞİ:
{history_text if history_text else "İlk mesaj"}

{existing_info}

SON KULLANICI MESAJI: "{user_message}"

GÖREV: Hem SON MESAJI hem de MEVCUT TOPLANMIŞ BİLGİLERİ dikkate alarak, aşağıdaki JSON yapısını DOLDUR.

KURALLAR:
1. Eğer bir bilgi (örn: service) MEVCUT TOPLANMIŞ BİLGİLER'de zaten varsa, onu koru.
2. Eğer son mesajda bu bilgi güncelleniyorsa (örn: kullanıcı fikrini değiştirip 'manikür' dediyse), o zaman YENİ değerle değiştir.
3. Eğer bir bilgi ne mevcut durumda ne de son mesajda varsa, null bırak.
4. Mesajda tarih formatı farklı olabilir (23.11.2025, 23 Kasım 2025, vb.) - bunları YYYY-MM-DD formatına çevir.

ÖRNEK ÇIKTI:
{{
  "service": "saç kesimi",  // Varsa korunur veya güncellenir
  "date": "2025-11-21",      // Varsa korunur veya güncellenir
  "time": null,
  "phone": null
}}

ÇIKTI (Sadece JSON):"""

        try:
            response = self.model.generate_content(prompt)
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            extracted = json.loads(raw)
            # Sadece null olmayan değerleri değil, tümünü alıp mevcutla birleştirelim
            # Bu sayede modelin "eskiyi hatırla" mantığı daha iyi çalışır
            result = {}
            for key, value in extracted.items():
                if value and value != "null":  # Sadece dolu değerleri al
                    result[key] = value
            return result
        except Exception as e:
            logging.error(f"Gemini bilgi çıkarma hatası: {e}")
            return {}

    def _update_context(self, results: Dict, conversation: Dict):
        """Agent sonuçlarıyla context'i güncelle"""
        context = conversation.setdefault("context", {})
        collected = conversation.setdefault("collected", {})
        
        for result in results.values():
            if not isinstance(result, dict) or not result.get("success"):
                continue
            
            if "customer" in result:
                if "phone" in result["customer"]:
                    context["customer_phone"] = result["customer"]["phone"]
                    collected["phone"] = result["customer"]["phone"]  # collected'a da ekle
                if "name" in result["customer"]:
                    context["customer_name"] = result["customer"]["name"]
            
            if "appointment" in result:
                if "code" in result["appointment"]:
                    context["last_appointment_code"] = result["appointment"]["code"]
                    logging.info(f"✅ Context güncellendi: Randevu kodu = {context['last_appointment_code']}")
                
                # Son randevu bilgilerini context'te sakla (onay mesajları için)
                context["last_appointment"] = {
                    "service": collected.get("service") or context.get("last_appointment_service"),
                    "date": collected.get("date") or context.get("last_appointment_date"),
                    "time": collected.get("time") or context.get("last_appointment_time"),
                    "code": result["appointment"].get("code")
                }
                if collected.get("service"):
                    context["last_appointment_service"] = collected["service"]
                if collected.get("date"):
                    context["last_appointment_date"] = collected["date"]
                if collected.get("time"):
                    context["last_appointment_time"] = collected["time"]

    async def process_request(self, session_id: str, user_message: str) -> str:
        """Ana işlem akışı"""
        logging.info(f"\n{'='*70}\n🎯 YENİ İSTEK: {user_message}\n{'='*70}")

        conv = self.conversations[session_id]
        if conv is None:
            conv = {
                "context": {},
                "collected": {},
                "history": []
            }
        
        try:
            # 1. Intent classification - onay mesajlarını tespit et
            user_lower = user_message.lower()
            is_confirmation = any(word in user_lower for word in ["evet", "onayla", "tamam", "olur", "istiyorum", "hatırlatma"])
            
            if is_confirmation:
                if "hatırlatma" in user_lower:
                    logging.info("ℹ️ Hatırlatma mesajı algılandı - mevcut randevu bilgilerini koruyoruz")
                    if conv.get("context", {}).get("last_appointment"):
                        last_appt = conv["context"]["last_appointment"]
                        if "service" not in conv["collected"] and last_appt.get("service"):
                            conv["collected"]["service"] = last_appt["service"]
                        if "date" not in conv["collected"] and last_appt.get("date"):
                            conv["collected"]["date"] = last_appt["date"]
                        if "time" not in conv["collected"] and last_appt.get("time"):
                            conv["collected"]["time"] = last_appt["time"]
                elif conv.get("context", {}).get("last_appointment"):
                    last_appt = conv["context"]["last_appointment"]
                    if "service" not in conv["collected"] and last_appt.get("service"):
                        conv["collected"]["service"] = last_appt["service"]
                    if "date" not in conv["collected"] and last_appt.get("date"):
                        conv["collected"]["date"] = last_appt["date"]
                    if "time" not in conv["collected"] and last_appt.get("time"):
                        conv["collected"]["time"] = last_appt["time"]
            
            regex_info = self._extract_info_with_regex(user_message)
            gemini_info = await self._extract_with_gemini(user_message, conv)
            
            new_info = {**gemini_info, **regex_info}
            
            for key, value in new_info.items():
                if value and value != "null":
                    conv["collected"][key] = value
            
            logging.info(f"📥 Toplanan: {json.dumps(conv['collected'], ensure_ascii=False)}")
            logging.info(f"💾 Context: {json.dumps(conv['context'], ensure_ascii=False)}")
            logging.info(f"📝 History uzunluğu: {len(conv.get('history', []))}")
            
            action_plan = await self._create_plan(user_message, conv)
            logging.info(f"📋 Plan: {json.dumps(action_plan, indent=2, ensure_ascii=False)}")
            
            if action_plan.get("missing_info") and not action_plan.get("steps"):
                response = action_plan["ask_user"]
                conv["history"].append({"role": "user", "content": user_message})
                conv["history"].append({"role": "assistant", "content": response})
                return response
            
            if action_plan.get("action") == "chat":
                response = await self._general_chat(user_message, conv)
                conv["history"].append({"role": "user", "content": user_message})
                conv["history"].append({"role": "assistant", "content": response})
                return response
            
            if action_plan.get("action") == "create_appointment" and not action_plan.get("steps"):
                all_collected = {**conv.get("context", {}), **conv.get("collected", {})}
                if all_collected.get("service") and all_collected.get("date") and all_collected.get("time") and (all_collected.get("phone") or all_collected.get("customer_phone")):
                    action_plan["steps"] = [{
                        "agent": "appointment",
                        "operation": "create_appointment",
                        "params": {
                            "service_type": all_collected["service"],
                            "date_time": self._format_date_time(
                                all_collected['date'],
                                all_collected.get('time')
                            ),
                            "customer_phone": all_collected.get("phone") or all_collected.get("customer_phone")
                        }
                    }]
                    logging.info("📝 create_appointment için steps otomatik oluşturuldu")
            
            results = await self._execute_plan(action_plan, conv)
            self._update_context(results, conv)

            # YENİ EKLENEN KISIM: Uzman seçimi için kullanıcıya soru sorma
            for result in results.values():
                if isinstance(result, dict) and result.get("action_required") == "ask_user_to_choose_expert":
                    experts = result.get("available_experts", [])
                    if experts:
                        expert_list_str = ", ".join(experts)
                        # Uzmanların unvanlarını ve kısa bir özelliğini ekleyerek daha bilgilendirici bir soru oluştur
                        # Not: Bu kısım için config'den uzman detaylarını çekmek gerekebilir.
                        # Şimdilik sadece isimleri listeliyoruz.
                        response = f"Elbette. Belirttiğiniz saatte {expert_list_str} gibi harika uzmanlarımız müsait. Hangi uzmanımızla devam etmek istersiniz?"
                        
                        # Geçmişe ekle ve hemen yanıtı döndür
                        conv["history"].append({"role": "user", "content": user_message})
                        conv["history"].append({"role": "assistant", "content": response})
                        return response
            
            if not results and action_plan.get("action") in ["book_appointment", "create_appointment"]:
                all_collected = {**conv.get("context", {}), **conv.get("collected", {})}
                if all_collected.get("service") and all_collected.get("date") and all_collected.get("time") and (all_collected.get("phone") or all_collected.get("customer_phone")):
                    logging.info("⚠️ Plan başarısız ama yeterli bilgi var, fallback ile randevu oluşturmayı deniyoruz")
                    fallback_plan = {
                        "action": "book_appointment",
                        "missing_info": None,
                        "steps": [{
                            "agent": "appointment",
                            "operation": "create_appointment",
                            "params": {
                                "service_type": all_collected["service"],
                                "date_time": self._format_date_time(
                                    all_collected['date'],
                                    all_collected.get('time')
                                ),
                                "customer_phone": all_collected.get("phone") or all_collected.get("customer_phone")
                            }
                        }]
                    }
                    results = await self._execute_plan(fallback_plan, conv)
                    self._update_context(results, conv)
            
            response = await self._generate_response(user_message, action_plan, results, conv)
            
            conv["history"].append({"role": "user", "content": user_message})
            conv["history"].append({"role": "assistant", "content": response})
            
            if len(conv["history"]) > 20:
                conv["history"] = conv["history"][-20:]

            return response
        finally:
            # Değişikliklerin kalıcı olması için oturum durumunu güncelle
            self.conversations[session_id] = conv

    async def _create_plan(self, user_message: str, conv: Dict) -> Dict:
        """Eylem planı oluştur - Doğal konuşma odaklı"""
        
        all_info = {
            **conv.get("context", {}),
            **conv.get("collected", {})
        }
        
        history = "\n".join([
            f"{'Müşteri' if h['role'] == 'user' else 'Asistan'}: {h['content']}" 
            for h in conv["history"][-6:]
        ])
        
        prompt = f"""Sen bir güzellik salonu asistanısın ve görevin, kullanıcı konuşmasına göre bir sonraki adımı planlamak.

KONUŞMA GEÇMİŞİ:

{history if history else "İlk mesaj"}

SON KULLANICI MESAJI: "{user_message}"

MEVCUT DURUM (BİLDİĞİMİZ BİLGİLER):

{json.dumps(conv['collected'], ensure_ascii=False, indent=2) if conv.get('collected') else "Henüz bilgi toplanmadı."}
CONTEXT (Gizli Bilgiler): {json.dumps(conv.get('context'), ensure_ascii=False, indent=2) if conv.get('context') else "Context boş."}

GÖREV: Aşağıdaki düşünce adımlarını takip ederek bir JSON planı oluştur.

DÜŞÜNCE ADIMLARI (Sırayla Düşün):

1.  **Analiz:** Kullanıcının son mesajı ne anlama geliyor? Yeni bir bilgi mi veriyor? Bir soru mu soruyor? Onay mı veriyor? Randevu mu **iptal** etmek istiyor? Yoksa telefon numarasıyla **kaydını, kim adına kayıtlı olduğunu veya randevularını** mı sorguluyor?

2.  **Bilgileri Birleştir:** Son mesajdaki yeni bilgileri MEVCUT DURUM ve CONTEXT'teki bilgilerle birleştir.

3.  **Eksik Bilgi Tespiti:**
    *   Randevu **oluşturmak** için: `service`, `date`, `time`, `phone`.
    *   Randevu **iptal etmek** için: `appointment_code`.
    *   Müşteri **kontrol etmek** için: `phone`.

4.  **Karar:**

    *   Eğer kullanıcı bir listeleme istiyorsa (uzmanları, hizmetleri), action'ı "inform" olarak ayarla ve `steps` listesini ilgili `list_experts` veya `list_services` aracıyla doldur.

    *   Eğer kullanıcı telefon numarası verip **kayıtlı olup olmadığını, kim adına kayıtlı olduğunu veya randevularını** soruyorsa, **action: "check_customer"** kullan ve `steps` listesini `customer` agent'ı ile doldur.

    *   Eğer kullanıcı randevu **iptal etmek** istiyorsa (`iptal` kelimesi geçiyorsa), **action: "cancel_appointment"** kullan ve `steps` listesini doldur.

    *   Eğer `service` ve `date` var ama `time` yoksa ve kullanıcı müsaitlik soruyorsa, **action: "check_availability"** kullan ve `steps` listesini doldur.

    *   Eğer randevu oluşturmak için bir bilgi eksikse, `action: "book_appointment"` kullan ve `missing_info`'yu doldurarak SADECE İLK EKSİK BİLGİYİ sor.

    *   Eğer randevu oluşturmak için TÜM bilgiler tamamsa, **action: "create_appointment"** kullan ve `steps` listesini doldur.

    *   Yukarıdakilerin hiçbiri değilse, `action: "chat"` kullan.

KURALLAR:

- **ASLA AMA ASLA** "MEVCUT DURUM" veya "CONTEXT" içinde zaten var olan bir bilgiyi `missing_info` listesine ekleme veya kullanıcıya tekrar sorma!
- `ask_user` cümlesi her zaman doğal, samimi ve kısa olmalı.
- Bir eylem kararı verdiysen (`check_availability`, `create_appointment`, `check_customer`, vb.), `steps` listesini MUTLAKA ilgili agent çağrısıyla doldur!
- **ÇOK ÖNEMLİ:** Uzman adı için her zaman `expert_name` parametresini kullan, ASLA `specialist_name` veya başka bir şey kullanma.

Şimdi bu adımları izleyerek aşağıdaki formatta bir JSON çıktısı oluştur.

ÖRNEK 1 - Eksik bilgi varsa (saat sorma):
{{
  "thought": "Kullanıcı tarih verdi, şimdi saat sormam gerekiyor.",
  "plan": {{
    "action": "book_appointment",
    "missing_info": ["time", "phone"],
    "ask_user": "Harika, 21 Kasım 2025 tarihini not aldım. Hangi saat sizin için uygun olurdu?",
    "steps": []
  }}
}}

ÖRNEK 2 - Müsaitlik kontrolü:
{{
  "thought": "Kullanıcı müsaitlik soruyor, check_availability kullanmalıyım.",
  "plan": {{
    "action": "check_availability",
    "missing_info": null,
    "ask_user": null,
    "steps": [
      {{
        "agent": "appointment",
        "operation": "check_availability",
        "params": {{ "service_type": "saç kesimi", "date_time": "2025-11-21T09:00:00" }}
      }}
    ]
  }}
}}

ÖRNEK 3 - Randevu oluşturma (Uzman ile):
{{
  "thought": "Tüm bilgiler tamam, 'Ayşe Demir' için randevu oluşturuyorum.",
  "plan": {{
    "action": "create_appointment",
    "missing_info": null,
    "ask_user": null,
    "steps": [
      {{
        "agent": "appointment",
        "operation": "create_appointment",
        "params": {{
          "service_type": "saç kesimi",
          "date_time": "2025-11-21T15:00:00",
          "customer_phone": "05551234567",
          "expert_name": "Ayşe Demir"
        }}
      }}
    ]
  }}
}}

ÖRNEK 4 - Randevu İptali (Kod CONTEXT'te mevcut):
{{
  "thought": "Kullanıcı iptal etmek istiyor. Kodu context'ten biliyorum. Doğrudan iptal aracını çağıracağım.",
  "plan": {{
    "action": "cancel_appointment",
    "missing_info": null,
    "ask_user": null,
    "steps": [
      {{
        "agent": "appointment",
        "operation": "cancel_appointment",
        "params": {{ "appointment_code": "0V21FV" }}
      }}
    ]
  }}
}}

ÖRNEK 5 - Müşteri Bilgisi ve Randevu Sorgulama:
{{
  "thought": "Kullanıcı telefon numarasını vererek kayıtlı olup olmadığını, kim adına kayıtlı olduğunu veya randevularını soruyor. `check_customer` aracını kullanmalıyım.",
  "plan": {{
    "action": "check_customer",
    "missing_info": null,
    "ask_user": null,
    "steps": [
      {{
        "agent": "customer",
        "operation": "check_customer",
        "params": {{ "phone": "05057142752" }}
      }}
    ]
  }}
}}

ÖRNEK 6 - Uzmanları Listeleme:
{{
  "thought": "Kullanıcı tüm uzmanları listelememi istiyor. 'list_experts' aracını kullanacağım.",
  "plan": {{
    "action": "inform",
    "missing_info": null,
    "ask_user": null,
    "steps": [
      {{
        "agent": "appointment",
        "operation": "list_experts",
        "params": {{}}
      }}
    ]
  }}
}}

ÖRNEK 7 - Hizmetleri Listeleme:
{{
  "thought": "Kullanıcı merkezdeki hizmetleri soruyor. 'list_services' aracını kullanacağım.",
  "plan": {{
    "action": "inform",
    "missing_info": null,
    "ask_user": null,
    "steps": [
      {{
        "agent": "appointment",
        "operation": "list_services",
        "params": {{}}
      }}
    ]
  }}
}}

ŞİMDİ KARAR VER (JSON):"""

        # JSON parse için retry mekanizması
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                raw = response.text.strip()
                
                # Daha kapsamlı temizleme
                raw = raw.replace("```json", "").replace("```", "")
                raw = raw.strip()
                
                # Eğer boş veya çok kısa ise retry
                if not raw or len(raw) < 10:
                    if attempt < max_retries - 1:
                        logging.warning(f"Boş response, retry {attempt + 1}/{max_retries}")
                        continue
                    raise ValueError("Boş response alındı")
                
                # JSON parse dene
                try:
                    parsed_json = json.loads(raw)
                except json.JSONDecodeError as json_err:
                    # JSON içinde JSON aramaya çalış
                    import re
                    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
                    if json_match:
                        try:
                            parsed_json = json.loads(json_match.group(0))
                            logging.info("JSON regex ile bulundu ve parse edildi")
                        except:
                            raise json_err
                    else:
                        raise json_err
                
                # Yeni yapıya göre parse et
                plan = parsed_json.get("plan", {})  # Asıl plan 'plan' anahtarı altında
                thought = parsed_json.get("thought", "")  # Düşünceyi loglamak için al
                
                logging.info(f"🧠 Model Düşüncesi: {thought}")
                
                if "action" not in plan:
                    plan["action"] = "chat"
                if "steps" not in plan:
                    plan["steps"] = []
                if "missing_info" not in plan:
                    plan["missing_info"] = None
                
                # Önemli: Toplanan bilgileri kontrol et, eğer bir bilgi collected'da varsa missing_info'dan çıkar
                collected = conv.get("collected", {})
                if plan.get("missing_info") and isinstance(plan["missing_info"], list):
                    # missing_info listesini filtrele
                    filtered_missing = []
                    missing_to_key = {
                        "hizmet": "service",
                        "service": "service",
                        "tarih": "date",
                        "date": "date",
                        "saat": "time",
                        "time": "time",
                        "telefon": "phone",
                        "phone": "customer_phone"  # customer_phone context'te olabilir
                    }
                    
                    for missing_item in plan["missing_info"]:
                        missing_key = missing_to_key.get(missing_item.lower(), missing_item.lower())
                        # Hem collected hem de context'te kontrol et
                        if missing_key in collected:
                            logging.info(f"✅ {missing_item} aslında toplanmış (collected'da var), missing'den çıkarıldı")
                            continue
                        # customer_phone context'te olabilir
                        if missing_key == "customer_phone" and all_info.get("customer_phone"):
                            logging.info(f"✅ {missing_item} aslında toplanmış (context'te var), missing'den çıkarıldı")
                            continue
                        filtered_missing.append(missing_item)
                    
                    plan["missing_info"] = filtered_missing if filtered_missing else None
                
                return plan
                
            except Exception as e:
                logging.error(f"Plan hatası (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    # Son denemede fallback plan oluştur
                    return self._create_fallback_plan(user_message, conv, all_info)
    
    def _create_fallback_plan(self, user_message: str, conv: Dict, all_info: Dict) -> Dict:
        """Gemini başarısız olduğunda akıllı fallback plan oluştur"""
        collected = conv.get("collected", {})
        context = conv.get("context", {})
        
        # Basit intent classification
        user_lower = user_message.lower()
        
        # Onay mesajları mı?
        if any(word in user_lower for word in ["evet", "onayla", "tamam", "olur", "istiyorum"]):
            # Son mesajlarda randevu oluşturma bahsedildi mi?
            history_text = " ".join([h.get("content", "") for h in conv.get("history", [])[-4:]])
            if any(word in history_text.lower() for word in ["randevu", "oluştur", "onayla", "saat"]):
                # Randevu oluşturma onayı - eksik bilgileri kontrol et
                missing = []
                if not collected.get("service") and not all_info.get("service"):
                    missing.append("hizmet")
                if not collected.get("date") and not all_info.get("date"):
                    missing.append("tarih")
                if not collected.get("time") and not all_info.get("time"):
                    missing.append("saat")
                if not collected.get("phone") and not all_info.get("customer_phone"):
                    missing.append("telefon")
                
                if missing:
                    return {
                        "action": "book_appointment",
                        "missing_info": missing,
                        "ask_user": f"Randevu oluşturmak için şu bilgiler eksik: {', '.join(missing)}. Lütfen eksik bilgileri verin.",
                        "steps": []
                    }
                else:
                    # Tüm bilgiler var, randevu oluştur
                    return {
                        "action": "book_appointment",
                        "missing_info": None,
                        "steps": [{
                            "agent": "appointment",
                            "operation": "create_appointment",
                            "params": {
                                "service_type": collected.get("service") or all_info.get("service"),
                                "date_time": self._format_date_time(
                                    collected.get('date') or all_info.get('date'),
                                    collected.get('time') or all_info.get('time')
                                ),
                                "customer_phone": collected.get("phone") or all_info.get("customer_phone")
                            }
                        }]
                    }
        
        # Müsaitlik sorgusu mu?
        if any(word in user_lower for word in ["müsait", "boş", "saatler", "açık", "uygun"]):
            if collected.get("service") and collected.get("date"):
                return {
                    "action": "check_availability",
                    "missing_info": None,
                    "steps": [{
                        "agent": "appointment",
                        "operation": "check_availability",
                        "params": {
                            "service_type": collected["service"],
                            "date_time": self._format_date_time(collected['date'], None)
                        }
                    }]
                }
        
        # Varsayılan chat
        return {
            "action": "chat",
            "missing_info": None,
            "steps": []
        }

    async def _execute_plan(self, plan: Dict, conv: Dict) -> Dict:
        """Planı uygula"""
        results = {}
        all_info = {**conv.get("context", {}), **conv.get("collected", {})}
        
        for i, step in enumerate(plan.get("steps", [])):
            agent_name = step.get("agent")
            operation = step.get("operation")
            params = step.get("params", {})
            
            if "customer_phone" not in params and all_info.get("customer_phone"):
                params["customer_phone"] = all_info["customer_phone"]
            
            if not agent_name or agent_name not in self.agents:
                continue
            
            agent = self.agents[agent_name]
            
            try:
                logging.info(f"▶  {operation.upper()} | Params: {params}")
                task = {"task": operation, "parameters": params}
                result = await agent.execute(task, conv)
                results[f"step_{i}_{operation}"] = result
                logging.info(f"✅ Başarı: {result.get('success', False)}")
                
            except Exception as e:
                logging.error(f"❌ Agent hatası: {e}", exc_info=True)
                results[f"step_{i}_error"] = {"success": False, "error": str(e)}
        
        return results

    async def _generate_response(self, user_message: str, plan: Dict, results: Dict, conv: Dict) -> str:
        """Kullanıcıya DOĞAL ve SAMIMI yanıt oluştur"""
        
        context = conv.get("context", {})
        all_info = {**context, **conv.get("collected", {})}
        
        history = "\n".join([
            f"{'Müşteri' if h['role'] == 'user' else 'Asistan'}: {h['content']}" 
            for h in conv["history"][-6:]
        ])
        
        prompt = f"""Sen bir güzellik salonu asistanısın ve bir GERÇEK KİŞİ gibi konuşuyorsun. Sesli asistan olarak görev yapıyorsun.

KONUŞMA GEÇMİŞİ:
{history}

KULLANICI ŞİMDİ DEDİ Kİ: "{user_message}"

BİLİNEN BİLGİLER:
- Müşteri: {all_info.get('customer_name', 'Henüz tanışmadık')}
- Hizmet: {all_info.get('service', 'Belirlenmedi')}
- Tarih: {all_info.get('date', 'Belirlenmedi')}
- Saat: {all_info.get('time', 'Belirlenmedi')}

YAPILAN İŞLEMLER VE SONUÇLAR:
{json.dumps(results, indent=2, ensure_ascii=False)}

GÖREV: Yukarıdaki sonuçları kullanarak DOĞAL, SAMIMI ve AKICI bir yanıt oluştur.

KURALLAR:
1. İNSAN GİBİ KONUŞ - Robotik değil, samimi ve sıcak
2. KISA ve ÖZ ol - Maksimum 3-4 cümle. Uzun açıklamalar yapma, gereksiz detaylar verme
3. Randevu oluştuysa → Randevu kodunu vurgula ama doğal bir şekilde: "Randevu kodunuz ABC123"
4. Müsait saatler varsa → Seçenekler sun ama kısa tut
5. Direkt ve net konuş - Gereksiz uzatma
6. Empatik ol ama özlü ol
7. **LİSTELEME SONUÇLARI:** `results` içindeki listeleri işlerken akıllı davran:
    - **Uzman veya Hizmet Listesi:** Bu listeleri HER ZAMAN tam ve eksiksiz olarak sun. Kısaltma yapma.
    - **Müsait Saatler (`available_slots`):** Eğer çok fazla ardışık saat varsa (örneğin, günün tamamı boşsa), listeyi özetle. Örneğin, "Saat 8'den 16'ya kadar her 15 dakikada bir yerimiz var" veya "Sabah saatleri tamamen müsait" gibi doğal bir özet yap. Eğer sadece birkaç dağınık saat varsa, o saatleri listele.

YANIT ÖRNEKLERİ:

ÖRNEK 1 - Müsait saatler gösterirken (ÖZETLENMİŞ):
"24 Kasım için günün büyük bir bölümü müsait görünüyor, sabah 9'dan akşam 4'e kadar yerimiz var. Özellikle tercih ettiğiniz bir zaman dilimi var mı?"

ÖRNEK 2 - Randevu oluştururken (KISA):
"Randevunuz oluşturuldu! Kodunuz: KG7H9F. Randevunuzdan önce hatırlatma mesajı göndereceğiz."

ÖRNEK 3 - Genel konuşma (KISA):
"Merhaba! Size nasıl yardımcı olabilirim? Randevu almak ister misiniz?"

ŞİMDİ SEN YANIT VER (sadece yanıt metni, JSON değil):"""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logging.error(f"Yanıt hatası: {e}")
            return "Harika! İşleminizi tamamladım. Başka bir konuda yardımcı olabilir miyim?"

    async def _general_chat(self, user_message: str, conv: Dict) -> str:
        """Genel sohbet - Doğal ve samimi"""
        
        history = "\n".join([
            f"{'Müşteri' if h['role'] == 'user' else 'Asistan'}: {h['content']}" 
            for h in conv["history"][-8:]
        ])
        
        context = conv.get("context", {})
        customer_name = context.get("customer_name", "")
        
        prompt = f"""Sen bir güzellik salonu asistanısın ve GERÇEK bir insan gibi konuşuyorsun. Sesli asistan olarak çalışıyorsun.

{"Müşteri: " + customer_name if customer_name else ""}

KONUŞMA GEÇMİŞİ:
{history if history else "İlk konuşma"}

MÜŞTERİ ŞİMDİ DEDİ Kİ: "{user_message}"

GÖREV: DOĞAL, SAMIMI ama KISA ve ÖZ yanıt ver (maksimum 2-3 cümle).

KURALLAR:
1. KISA ve NET ol - Gereksiz uzatma
2. İnsan gibi konuş ama özlü ol
3. Direkt sorunu çöz
4. Müşteriye değer ver ama uzun konuşma

ÖRNEKLERİ (KISA):
- "Merhaba! Size nasıl yardımcı olabilirim? Randevu almak ister misiniz?"
- "Saç kesimi, manikür, pedikür, cilt bakımı hizmetlerimiz var. Hangisi?"
- "Hangi tarih size uygun?"

ŞİMDİ YANIT VER (sadece yanıt metni):"""

        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except:
            return "Merhaba! Size nasıl yardımcı olabilirim? Randevu almak ister misiniz?"