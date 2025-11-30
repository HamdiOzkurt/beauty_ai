import google.generativeai as genai
from typing import Dict, Any, List
import logging
import json
import re
from datetime import datetime, timedelta

# Agent importlarını kendi yapılandırmana göre korudum
from agents.appointment_agent import AppointmentAgent
from agents.customer_agent import CustomerAgent
from agents.marketing_agent import MarketingAgent
from config import settings
from repository import ServiceRepository # ServiceRepository'yi içe aktar

class OrchestratorAgent:
    """
    Sesli Asistan için Orchestrator (V3.0 - Stable JSON Edition)
    Doğal, sıcak, akıcı ve JSON tabanlı kararlı yapı.
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
                "temperature": 0.3,  # Daha kararlı JSON için düşürdük
                "top_p": 0.95,
                "top_k": 20,
                "response_mime_type": "application/json", # Gemini'ye JSON zorlaması
                "max_output_tokens": 300
            }
        )
        self.conversations = conversations
        
        # Bilgi bankasını dinamik olarak yükle
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """Veritabanından güncel verileri çekerek bilgi bankasını oluşturur."""
        try:
            # Hizmetleri veritabanından çek
            service_repo = ServiceRepository()
            services = service_repo.list_all()
            service_names = [service.name for service in services if hasattr(service, 'name')]
            
            # Hizmet listesini bir string'e dönüştür
            if service_names:
                hizmetler_str = ", ".join(service_names)
            else:
                hizmetler_str = "şu anda tanımlı bir hizmetimiz bulunmuyor"
            
            # Bilgi bankası özetini oluştur
            self.knowledge_base_summary = (
                f"Biz Güzellik Merkeziyiz. 09:00-19:00 arası açığız. "
                f"Sunduğumuz hizmetler: {hizmetler_str}. "
                f"Adresimiz: İstanbul, Şişli."
            )
            logging.info(f"📚 Bilgi bankası güncellendi: {self.knowledge_base_summary}")

        except Exception as e:
            logging.error(f"Bilgi bankası yüklenirken hata oluştu: {e}", exc_info=True)
            # Hata durumunda varsayılan (fallback) bir değer ata
            self.knowledge_base_summary = "Biz Güzellik Merkeziyiz. 09:00-19:00 arası açığız. Adresimiz: İstanbul, Şişli. Hizmetlerimizi öğrenmek için lütfen tekrar deneyin."

    def _extract_info_with_regex(self, user_message: str) -> Dict:
        """Gelişmiş regex ile hızlı bilgi çıkarma - V3.1"""
        info = {}
        msg_lower = user_message.lower()
        
        # Telefon (Daha esnek - boşluklar ve tire ile, başta sıfır olabilir)
        # Format örnekleri: 05027225522, 0-502-722-5522, 0 502 722 55 22
        phone_match = re.search(r'0?[\s\-]?(5\d{2})[\s\-]?(\d{3})[\s\-]?(\d{2,3})[\s\-]?(\d{2})', user_message)
        if phone_match:
            info["phone"] = f"0{phone_match.group(1)}{phone_match.group(2)}{phone_match.group(3)}{phone_match.group(4)}"
        
        # Saat
        time_match = re.search(r'(\d{1,2})[:.](\d{2})', user_message)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            info["time"] = f"{hour:02d}:{minute:02d}"
        
        # İsim (Türkçe isim formatı: İki kelime, her biri büyük harfle başlamalı)
        # Örnek: "Osman Kara", "Ayşe Yılmaz"
        name_match = re.search(r'\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)\b', user_message)
        if name_match:
            info["name"] = f"{name_match.group(1)} {name_match.group(2)}"
        
        # Hizmetler (Anahtar kelimeler - daha geniş pattern'lar)
        services = {
            "saç kesimi": r"saç\s*kes|kesim|saçım|traş",
            "saç boyama": r"boya|boyat",
            "manikür": r"manikür|tırnak\s*bakım",
            "pedikür": r"pedikür|ayak\s*bakım",
            "cilt bakımı": r"cilt|yüz\s*bakım",
            "kaş alımı": r"kaş|kaşlar",
            "epilasyon": r"epilasyon|ağda|lazer"
        }
        for svc, pattern in services.items():
            if re.search(pattern, msg_lower):
                info["service"] = svc
                logging.debug(f"🔍 Regex hizmet buldu: {svc} (pattern: {pattern})")
                break
        
        # Debug log
        if info:
            logging.info(f"🔍 Regex çıkarımları: {info}")
                
        return info
    
    def _format_date_time(self, date: str, time: str = None) -> str:
        if not date: return None
        if time and len(time) == 5: time += ":00"
        return f"{date}T{time}" if time else f"{date}T09:00:00"
    
    def _clean_llm_response(self, text: str) -> str:
        """
        LLM'den gelen yanıtı temizle (JSON wrapper'ları kaldır)
        """
        if not text or not isinstance(text, str):
            return "Üzgünüm, bir hata oluştu."
        
        text = text.strip()
        
        # JSON wrapper'ı kaldır
        if text.startswith('{') and text.endswith('}'):
            try:
                parsed = json.loads(text)
                # Farklı key'leri dene
                for key in ["response", "ask_user", "message", "text"]:
                    if key in parsed:
                        return parsed[key]
                # Eğer sadece bir value varsa onu al
                if len(parsed) == 1:
                    return list(parsed.values())[0]
            except json.JSONDecodeError:
                pass
        
        # Markdown code block temizleme
        text = text.replace("```json", "").replace("```", "").strip()
        
        return text

    async def _extract_and_plan_unified(self, user_message: str, conv: Dict) -> Dict:
        """
        V3.1 PROMPT ENTEGRASYONU - Memory-Safe Edition
        Tek çağrıda: Niyet analizi + Bilgi Çıkarma + Planlama + Kullanıcı Yanıtı
        """
        today = datetime.now()
        
        # Geçmiş
        history = conv.get("history", [])
        history_text = "\n".join([f"{'User' if h['role']=='user' else 'AI'}: {h['content']}" for h in history[-12:]])
        
        # Veriler
        collected = conv.get("collected", {})
        context = conv.get("context", {})
        regex_extracted = self._extract_info_with_regex(user_message)
        
        # Regex bulduklarını collected ile birleştir (Prompt'a yardımcı olsun)
        current_state = {**collected, **regex_extracted}
        
        # DEBUG: State takibi
        logging.info(f"📦 COLLECTED STATE: {json.dumps(current_state, ensure_ascii=False)}")

        # State'i daha okunabilir formata çevir
        state_summary = []
        if current_state.get("phone"):
            state_summary.append(f"✓ Telefon: {current_state['phone']}")
        if current_state.get("service"):
            state_summary.append(f"✓ Hizmet: {current_state['service']}")
        if current_state.get("expert_name"):
            state_summary.append(f"✓ Uzman: {current_state['expert_name']}")
        if current_state.get("date"):
            state_summary.append(f"✓ Tarih: {current_state['date']}")
        if current_state.get("time"):
            state_summary.append(f"✓ Saat: {current_state['time']}")
        
        state_display = "\n".join(state_summary) if state_summary else "(Henüz bilgi toplanmadı)"
        
        # Müşteri ismi bilgisi (context'ten)
        customer_greeting = ""
        if context.get("customer_name"):
            customer_greeting = f"\n### 👤 CUSTOMER INFO ###\nRegistered Customer Name: {context['customer_name']}\n**IMPORTANT:** Always address this customer by their name (e.g., 'Merhaba {context['customer_name']}' or '{context['customer_name']} Hanım/Bey'). Be warm and personal!\n"
        
        # Kampanya bilgilerini prompt'a ekle
        campaign_info = ""
        if context.get("active_campaigns"):
            campaigns = context["active_campaigns"]
            campaign_details = []
            for c in campaigns:
                campaign_details.append(f"- {c.get('name')}: %{c.get('discount')} indirim (Bitiş: {c.get('end_date')})")
            campaign_info = f"""
### 🎁 ACTIVE CAMPAIGNS (Use this info when user asks about campaigns or their duration) ###
{chr(10).join(campaign_details)}
"""

        # --- V3.2 PROMPT - Refactored & Compact ---
        prompt = f"""### ROLE & GOAL ###
You are a Beauty Center AI Orchestrator. Your goal is to manage conversations, extract information, plan tool usage, and respond to the user.
Your output MUST be a single JSON object. The 'ask_user' field must be in natural, warm, and concise Turkish.

### CORE DATA ###
- Current Date: {today.strftime('%Y-%m-%d %H:%M')}
- Knowledge Base: {self.knowledge_base_summary}
- Conversation History:
{history_text}
{customer_greeting}
- Active Campaigns:
{campaign_info}

### CURRENT STATE (MEMORY) ###
- Summary: {state_display}
- Raw JSON: {json.dumps(current_state, ensure_ascii=False)}

### ⚠️ CORE DIRECTIVES (MUST FOLLOW) ###
1.  **MEMORY IS KEY**: NEVER ask for information already present in "CURRENT STATE". Always check the Raw JSON first.
2.  **BOOKING FLOW**:
    a. Get `phone` (05xxxxxxxxx format).
    b. Immediately use `customer_agent.check_customer` to get the customer's name. Greet them personally.
    c. Get `service`.
    d. Get `expert_name`. If missing, use `booking_agent.list_experts` and ask user to choose.
    e. Get `date` (YYYY-MM-DD) and `time` (HH:MM).
    f. Use `booking_agent.check_availability`. **CRITICAL**: If user gives booking details (date/time/expert) before phone, run `check_availability` FIRST. ALWAYS include `expert_name` if user mentioned one.
    g. If unavailable, ask user if they want alternatives. If user says YES ("evet", "tabii", "öner", "bekliyorum"), immediately use `booking_agent.suggest_alternative_times` with current service, date, and expert_name from state.
    h. Once all info is collected and availability is confirmed, ask for final confirmation.
    i. On confirmation, use `booking_agent.create_appointment`.
3.  **INTENT ROUTING**:
    - **Greetings/General Info/Price**: Classify as `chat` or use `list_services` for prices. DO NOT start the booking flow.
    - **Booking/Cancellation**: Follow the booking flow or use cancellation tools.
    - **Info Request (experts, services)**: Use `list_experts` or `list_services`.
    - **Query Appointment**: Use `customer_agent.get_customer_appointments`.
4.  **TOOLS**:
    - `booking_agent`: create_appointment, cancel_appointment, check_availability, suggest_alternative_times, list_experts, list_services.
    - `customer_agent`: check_customer, create_customer, get_customer_appointments.
    - `marketing_agent`: check_campaigns.

### JSON OUTPUT FORMAT ###
{{
  "extracted": {{ "date": "YYYY-MM-DD", "time": "HH:MM", "service": "string", "expert_name": "string" }},
  "plan": {{
    "action": "chat" | "inform_missing" | "confirm" | "execute_tool",
    "missing_info": ["field_name"],
    "ask_user": "A natural Turkish response for the user. Plain string, no JSON/Markdown.",
    "steps": [ {{ "agent": "agent_name", "operation": "tool_name", "params": {{}} }} ]
  }}
}}

### USER INPUT ###
"{user_message}"
"""

        try:
            response = self.model.generate_content(prompt)
            # JSON temizliği
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            
            # Validation
            if "extracted" not in result: result["extracted"] = {}
            if "plan" not in result: result["plan"] = {"action": "chat", "ask_user": "Anlaşılamadı, tekrar eder misiniz?", "steps": []}
            
            logging.info(f"🎯 V3 Plan: {result['plan']['action']} | Msg: {result['plan'].get('ask_user')}")
            return result
            
        except Exception as e:
            logging.error(f"Unified call hatası: {e}", exc_info=True)
            # Fallback
            return {
                "extracted": {},
                "plan": {
                    "action": "chat",
                    "ask_user": "Sistemsel bir yoğunluk var, lütfen tekrar dener misiniz?",
                    "steps": []
                }
            }

    def _update_context(self, results: Dict, conversation: Dict):
        """Tool sonuçlarını context'e işle"""
        context = conversation.setdefault("context", {})
        collected = conversation.setdefault("collected", {})
        
        for res in results.values():
            if not isinstance(res, dict): continue
            
            # Müşteri verisi güncelleme
            if "customer" in res and "phone" in res["customer"]:
                context["customer_phone"] = res["customer"]["phone"]
                collected["phone"] = res["customer"]["phone"]
                if "name" in res["customer"]:
                    context["customer_name"] = res["customer"]["name"]
            
            # 🆕 Randevu bilgilerini kaydet (get_customer_appointments sonucu)
            if "appointments" in res and res.get("appointments"):
                # İlk (en güncel) randevuyu kaydet
                latest_apt = res["appointments"][0]
                collected["appointment_id"] = latest_apt.get("id")
                collected["appointment_date"] = latest_apt.get("date")
                collected["appointment_service"] = latest_apt.get("service")
                # Notes içinde randevu kodu olabilir
                notes = latest_apt.get("notes", "")
                if notes:
                    collected["appointment_code"] = notes
                logging.info(f"📋 Randevu bilgisi kaydedildi: ID={latest_apt.get('id')}, Kod={notes}")
            
            # 🆕 Kampanya bilgilerini kaydet (check_campaigns sonucu)
            if "campaigns" in res and res.get("success"):
                campaigns = res.get("campaigns", [])
                if campaigns:
                    context["active_campaigns"] = campaigns
                    # İlk kampanyanın detaylarını kolay erişim için ayrı tut
                    first_campaign = campaigns[0]
                    context["campaign_name"] = first_campaign.get("name")
                    context["campaign_discount"] = first_campaign.get("discount")
                    context["campaign_end_date"] = first_campaign.get("end_date")
                    logging.info(f"🎁 Kampanya bilgisi kaydedildi: {first_campaign.get('name')} - %{first_campaign.get('discount')} (Bitiş: {first_campaign.get('end_date')})")

    async def process_request(self, session_id: str, user_message: str, websocket=None) -> str:
        """
        Ana İşlem Akışı - V3.2 Memory-Fixed
        """
        logging.info(f"\n{'='*50}\n🎯 İSTEK: {user_message}\n{'='*50}")

        conv = self.conversations.get(session_id)
        if not conv:
            conv = {"context": {}, "collected": {}, "history": []}
            self.conversations[session_id] = conv
        
        # ⚠️ ÖNCE KULLANICI MESAJINI HISTORY'YE EKLE
        conv["history"].append({"role": "user", "content": user_message})
        
        # Debug: Önceki state
        logging.info(f"📥 Mevcut collected (işlem öncesi): {json.dumps(conv.get('collected', {}), ensure_ascii=False)}")
        
        # 1. Regex (Ön Hazırlık)
        regex_info = self._extract_info_with_regex(user_message)
        conv["collected"].update({k:v for k,v in regex_info.items() if v})
        
        # Debug: Güncellenen state
        logging.info(f"📤 Güncel collected (regex sonrası): {json.dumps(conv['collected'], ensure_ascii=False)}")

        # 2. AI Unified Call (Tek Çağrı)
        unified = await self._extract_and_plan_unified(user_message, conv)
        
        # Çıkarılan yeni bilgileri kaydet
        new_extracted = unified.get("extracted", {})
        for k, v in new_extracted.items():
            if v and v != "null" and v != "": 
                conv["collected"][k] = v
        
        # ⚠️ SON STATE'İ LOGLA
        logging.info(f"🧠 FINAL COLLECTED STATE: {json.dumps(conv['collected'], ensure_ascii=False)}")
            
        plan = unified.get("plan", {})
        action = plan.get("action")
        
        # ⚠️ ask_user ALAN TEMİZLEME (Geliştirilmiş)
        response_text = plan.get("ask_user", "")
        response_text = self._clean_llm_response(response_text)
        
        # 3. Aksiyon Yönetimi
        
        # DURUM A: Sadece Konuşma veya Eksik Bilgi İsteme (Tool çalıştırmaya gerek yok)
        if action in ["chat", "inform_missing", "confirm"] and not plan.get("steps"):
            # Model zaten cevabı üretti, direkt dön
            await self._send_response(response_text, conv, websocket, session_id)
            return response_text
            
        # DURUM B: Tool Çalıştırma (Veritabanı işlemleri, Müsaitlik kontrolü vb.)
        if action == "execute_tool" or plan.get("steps"):
            
            # Parametreleri tamamla (Phone eksikse context'ten al)
            for step in plan["steps"]:
                if "customer_phone" not in step.get("params", {}) and conv["collected"].get("phone"):
                    step["params"]["customer_phone"] = conv["collected"]["phone"]
                
                # check_campaigns için customer_phone opsiyonel, yoksa None gönder
                if step.get("operation") == "check_campaigns" and "customer_phone" not in step.get("params", {}):
                    step["params"]["customer_phone"] = conv["collected"].get("phone")
                
                # Eğer operation check_availability ise ve service_type eksikse, collected'dan tamamla
                if step.get("operation") == "check_availability" and \
                   "service_type" not in step.get("params", {}) and \
                   conv["collected"].get("service"):
                    step["params"]["service_type"] = conv["collected"]["service"]
                
                # Expert name düzeltme (Model bazen 'Ayşe' gönderir, 'Ayşe Yılmaz' gerekir mi bakılabilir)
                # Burası agent içinde handle ediliyor varsayıyoruz.

            # Planı uygula
            results = await self._execute_plan(plan, conv)
            self._update_context(results, conv)
            
            # Tool sonuçlarına göre yeni bir cevap üretmemiz gerekebilir
            # Eğer model 'ask_user' vermişse ve işlem başarılıysa onu kullan,
            # ama genellikle tool sonucuna göre (örn: "Randevu kodunuz: XYZ") dinamik cevap gerekir.
            
            final_response = await self._generate_tool_response(user_message, plan, results, conv)
            await self._send_response(final_response, conv, websocket, session_id)
            return final_response

        # Fallback (Hiçbir şeye girmezse)
        await self._send_response(response_text, conv, websocket, session_id)
        return response_text

    async def _execute_plan(self, plan: Dict, conv: Dict) -> Dict:
        """Agent Toollarını Çalıştır"""
        results = {}
        # Agent isim haritası (Prompt ismi -> Class instance)
        agent_map = {
            "booking_agent": self.agents["appointment"],
            "customer_agent": self.agents["customer"],
            "marketing_agent": self.agents["marketing"]
        }

        for i, step in enumerate(plan.get("steps", [])):
            agent_key = step.get("agent")
            operation = step.get("operation")
            params = step.get("params", {})
            
            # 🔧 FIX: Collected state'i params'a ekle (eğer yoksa)
            collected = conv.get("collected", {})
            
            # check_customer için telefon ekle
            if operation == "check_customer":
                if "phone" not in params and collected.get("phone"):
                    params["phone"] = collected["phone"]
            
            # create_customer için isim ve telefon ekle
            if operation == "create_customer":
                if "phone" not in params and collected.get("phone"):
                    params["phone"] = collected["phone"]
                if "full_name" not in params and "name" not in params:
                    if collected.get("name"):
                        params["full_name"] = collected["name"]
                    elif collected.get("full_name"):
                        params["full_name"] = collected["full_name"]
            
            # check_availability için tarih/saat bilgisini ekle
            if operation == "check_availability":
                if "date" not in params and collected.get("date"):
                    params["date"] = collected["date"]
                if "date_time" not in params and collected.get("date") and collected.get("time"):
                    # ISO format: YYYY-MM-DDTHH:MM:SS
                    params["date_time"] = f"{collected['date']}T{collected['time']}:00"
                if "expert_name" not in params and collected.get("expert_name"):
                    params["expert_name"] = collected["expert_name"]
            
            # suggest_alternative_times için parametreleri ekle
            if operation == "suggest_alternative_times":
                if "service_type" not in params and collected.get("service"):
                    params["service_type"] = collected["service"]
                if "date" not in params and collected.get("date"):
                    params["date"] = collected["date"]
                if "expert_name" not in params and collected.get("expert_name"):
                    params["expert_name"] = collected["expert_name"]
            
            # create_appointment için tüm bilgileri ekle
            if operation == "create_appointment":
                if "customer_phone" not in params and collected.get("phone"):
                    params["customer_phone"] = collected["phone"]
                if "service_type" not in params and collected.get("service"):
                    params["service_type"] = collected["service"]
                if "appointment_datetime" not in params and collected.get("date") and collected.get("time"):
                    # ISO format: YYYY-MM-DDTHH:MM:SS
                    params["appointment_datetime"] = f"{collected['date']}T{collected['time']}:00"
                if "expert_name" not in params and collected.get("expert_name"):
                    params["expert_name"] = collected["expert_name"]
            
            agent = agent_map.get(agent_key)
            if not agent:
                logging.warning(f"⚠️ Bilinmeyen agent: {agent_key}")
                continue
                
            try:
                logging.info(f"▶ ÇALIŞTIRILIYOR: {agent_key}.{operation} | Params: {params}")
                
                # Agent'ın beklediği format ("task" yapısı)
                task_payload = {"task": operation, "parameters": params}
                
                # Execute
                result = await agent.execute(task_payload, conv)
                results[f"{operation}"] = result
                logging.info(f"✅ Sonuç: {result.get('success')}")
                
            except Exception as e:
                logging.error(f"❌ Tool hatası: {e}", exc_info=True)
                results[f"{operation}_error"] = {"success": False, "error": str(e)}
        
        return results

    async def _generate_tool_response(self, user_msg: str, plan: Dict, results: Dict, conv: Dict) -> str:
        """
        Tool (Araç) sonuçlarını yorumlayıp kullanıcıya nihai yanıtı üretir.
        Örnek: Database'den 'success: True' döndüyse -> "Randevunuz oluşturuldu."
        """
        
        # Context'ten ve sonuçlardan özet bilgi çıkar
        context_summary = {
            "customer_name": conv["context"].get("customer_name"),
            "tool_outputs": results
        }

        # Eğer sonuçlarda hata varsa logla
        has_error = any("error" in str(v).lower() for k, v in results.items())
        
        prompt = f"""### RESPONSE GENERATION ###
ROLE: Beauty Center Assistant.
GOAL: Create a short and natural Turkish response based on TOOL RESULTS.

USER SAID: "{user_msg}"

TOOL RESULTS (Technical):
{json.dumps(results, ensure_ascii=False, indent=2)}

CONTEXT:
{json.dumps(context_summary, ensure_ascii=False)}

RULES:
1. **APPOINTMENT CREATED:** If result has 'success': true and a 'code', say: "Harika! Randevunuz oluşturuldu. Randevu Kodunuz: [CODE]. Sizi bekliyoruz!"
2. **QUERY APPOINTMENTS:** If result has 'appointments' array:
   - If array is EMPTY or has 0 items: "Kayıtlı randevunuz bulunmuyor."
   - If array has items with status='confirmed': List them with date, time, service and expert. DO NOT mention cancelled appointments.
   - NEVER say "iptal edilmiş" or "cancelled" for appointments with status='confirmed'!
3. **ALTERNATIVE TIMES:** If the result is an 'alternatives' array, concisely list up to 3 options and the nearest available time:
   - "5 Aralık: 09:00, 11:30, 14:00 müsait. Hangisini tercih edersiniz?" (max 1 sentence!)
   - DO NOT list same time that user requested!
   - DO NOT repeat dates, just list times.
4. **AVAILABILITY:** If result lists 'slots' or 'times', list them clearly but concisely (e.g., "Sabah 09:00 ve 10:30 müsait").
5. **EXPERTS:** If result lists experts, say: "Şu uzmanlarımız hizmet veriyor: [Expert Names]. Hangisini tercih edersiniz?"
6. **ERROR:** If 'success': false, apologize politely and ask for missing info or suggest an alternative.
7. **TONE:** Warm, professional, NO emojis. Max 2 sentences.
8. NO NESTED JSON: The 'ask_user' field must be a PLAIN STRING. NEVER wrap the user response in curly braces {{}}, JSON objects (like {{"response": "..."}}), or labels. Just write the natural Turkish sentence directly.
OUTPUT (A plain, natural Turkish String ONLY. NEVER wrap the user response in JSON, curly braces, or labels):"""

        try:
            # Tool sonuçlarını yorumlaması için LLM'e gönderiyoruz
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # JSON formatında geldiyse parse et ve sadece mesajı al
            try:
                response_json = json.loads(response_text)
                if isinstance(response_json, dict) and "response" in response_json:
                    return response_json["response"]
            except (json.JSONDecodeError, KeyError):
                pass
            
            return response_text
        except Exception as e:
            logging.error(f"Tool yanıtı oluşturma hatası: {e}")
            # Fallback (Acil durum) mesajları
            if "create_appointment" in json.dumps(results):
                return "İşleminizi gerçekleştirdim, sistemimize kaydettim."
            return "Şu anda işleminizi tamamlamaya çalışıyorum ancak ufak bir gecikme var. Lütfen bekleyin."

    async def _send_response(self, text: str, conv: Dict, websocket, session_id: str = None):
        """
        Cevabı kaydeder ve WebSocket üzerinden (varsa) gönderir.
        ⚠️ User mesajı artık process_request'te ekleniyor!
        """
        # ⚠️ SADECE ASSISTANT CEVABINI EKLE (User mesajı zaten process_request'te eklendi)
        conv["history"].append({"role": "assistant", "content": text})
        
        # Geçmişin şişmesini engelle (Son 20 mesaj - 10 soru/cevap)
        if len(conv["history"]) > 20:
            conv["history"] = conv["history"][-20:]
        
        # Debug log
        logging.info(f"💬 HISTORY COUNT: {len(conv['history'])}")
        logging.info(f"📝 LAST 4 MESSAGES: {conv['history'][-4:]}")
        
        # ⚠️ KRİTİK: Session'ı burada da kaydet (her response'dan önce)
        if session_id:
            self.conversations[session_id] = conv
            logging.debug(f"💾 Session kaydedildi: {session_id}")
            
        # WebSocket Gönderimi
        if websocket:
            try:
                # Metin tabanlı gönderim (Frontend'de TTS için kullanılabilir)
                await websocket.send_text(text)
                
                # Akışın bittiğini belirten sinyal
                await websocket.send_text(json.dumps({"type": "stream_end"}))
                
                logging.info(f"📤 Yanıt gönderildi: {text[:100]}...")
            except Exception as e:
                logging.error(f"WebSocket gönderim hatası: {e}")

    # --- YARDIMCI METODLAR (Update) ---

    def _reset_conversation(self, session_id: str):
        """Oturumu sıfırlamak gerekirse (örn: "başa dön" dediğinde)"""
        self.conversations[session_id] = {
            "context": {},
            "collected": {},
            "history": []
        }
        logging.info(f"♻️ Oturum sıfırlandı: {session_id}")