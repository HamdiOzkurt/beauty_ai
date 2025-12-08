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
                "temperature": 0.2,  # Daha ciddi olması için sıcaklığı biraz daha düşürdüm
                "top_p": 0.95,
                "top_k": 20,
                "response_mime_type": "application/json", # Gemini'ye JSON zorlaması
                "max_output_tokens": 1500
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
            customer_greeting = f"\n### 👤 CUSTOMER INFO ###\nRegistered Customer Name: {context['customer_name']}\n**IMPORTANT:** Always address this customer by their name (e.g., 'Merhaba {context['customer_name']}' or '{context['customer_name']} Hanım/Bey').\n"
        
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
        # BURADA HARİKA KELİMESİNİ ENGELLEYEN KISIM GÜNCELLENDİ
        prompt = f"""### ROLE AND GOAL ###
You are a professional Beauty Spa AI Orchestrator. Your goal is to manage conversations, extract information, plan tool usage, and respond to the user.
Your output MUST be a single JSON object. The 'ask_user' field should be in natural, polite, and concise Turkish.

### STYLE & TONE GUIDELINES ###
1. **NO OVER-ENTHUSIASM:** NEVER start sentences with excitement words like "Harika", "Süper", "Mükemmel", "Şahane".
2. **PROFESSIONALISM:** Be polite, direct, and helpful. Use a calm and welcoming tone.
3. **FORMAT:** Keep the `ask_user` response short and clear.

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

### ⚠️ BASIC GUIDELINES (MUST-FOLLOW) ###
1. **MEMORY IS KEY**: NEVER ask for information already in the "CURRENT STATUS". Always check the raw JSON first.
2. **BOOK FLOW**:
a. Get the `phone` (in the format 05xxxxxxxxx). If `name` is missing, ask for it politely to create a record.
b. Get the `service` command.
c. Get the `expert_name` command. If missing, use the `booking_agent.list_experts` command and ask the user to choose.
d. Get `date` (YYYY-MM-DD) and `time` (HH:MM).
e. Use the `booking_agent.check_availability` command. **CRITICAL**: If the user provides details, run `check_availability` FIRST.
f. If unavailable, ask for alternatives. If user agrees, use `booking_agent.suggest_alternative_times`.
g. Once confirmed, use `booking_agent.create_appointment`.
3. **INTENT FORWARDING**:
- **Greetings/General**: Classify as `chat` or use `list_services`.
- **Booking**: Follow the booking flow.
- **Appointment Inquiry**: Use `customer_agent.get_customer_appointments`.
4. **TOOLS**:
- `booking_agent`: create_appointment, cancel_appointment, check_availability, suggest_alternative_times, expert_list, service_list.
- `customer_agent`: check_customer, create_customer, get_customer_appointments.
- `marketing_agent`: campaign_control_set.

### JSON OUTPUT FORMAT ###
{{
"extracted": {{ "date": "YYYY-MM-DD", "time": "HH:MM", "service": "string", "expert_name": "string" }},
"plan": {{
"action": "chat" | "inform_missing" | "confirm" | "execute_tool",
"missing_info": ["alan_adı"],
"ask_user": "A natural, professional Turkish response. Do NOT start with 'Harika'.",
"steps": [ {{ "agent": "agent_name", "operation": "tool_name", "params": {{}} }} ]
}}
}}

### USER INPUT ###
"{user_message}"
"""

        try:
            response = self.model.generate_content(prompt)
            raw = ""
            if response.candidates:
                # Check for safety ratings
                if response.prompt_feedback and response.prompt_feedback.safety_ratings:
                    for rating in response.prompt_feedback.safety_ratings:
                        if rating.block_reason: 
                            logging.warning(f"⚠️ Model yanıtı güvenlik nedeniyle engellendi: Kategori={rating.category}, Nedeni={rating.block_reason}")
                            return {
                                "extracted": {},
                                "plan": {
                                    "action": "chat",
                                    "ask_user": "Üzgünüm, isteğinizi işlerken bir sorun oluştu. Daha basit sorabilir misiniz?",
                                    "steps": []
                                }
                            }
                try:
                    raw = response.text.strip().replace("```json", "").replace("```", "").strip()
                except ValueError as ve:
                    logging.error(f"❌ Model yanıtından metin alınamadı: {ve}")
                    return {
                        "extracted": {},
                        "plan": {
                            "action": "chat",
                            "ask_user": "İsteğinizi tam olarak anlayamadım, tekrar eder misiniz?",
                            "steps": []
                        }
                    }
            else:
                logging.error(f"❌ Model yanıtı boş döndü.")
                return {
                    "extracted": {},
                    "plan": {
                        "action": "chat",
                        "ask_user": "Şu an yanıt veremiyorum, lütfen tekrar deneyin.",
                        "steps": []
                    }
                }
            
            try:
                result = json.loads(raw)
            except json.JSONDecodeError as json_e:
                logging.error(f"❌ JSON Parse Hatası: {json_e}")
                logging.error(f"❌ RAW: {raw}")
                return {
                    "extracted": {},
                    "plan": {
                        "action": "chat",
                        "ask_user": "Bir hata oluştu, lütfen tekrar deneyin.",
                        "steps": []
                    }
                }
            
            # Validation
            if "extracted" not in result: result["extracted"] = {}
            if "plan" not in result: result["plan"] = {"action": "chat", "ask_user": "Anlaşılamadı.", "steps": []}
            
            logging.info(f"🎯 V3 Plan: {result['plan']['action']} | Msg: {result['plan'].get('ask_user')}")
            return result

        except Exception as e:
            logging.error(f"Unified call hatası: {e}", exc_info=True)
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
            
            if "customer" in res and "phone" in res["customer"]:
                context["customer_phone"] = res["customer"]["phone"]
                collected["phone"] = res["customer"]["phone"]
                if "name" in res["customer"]:
                    context["customer_name"] = res["customer"]["name"]
            
            if "appointments" in res and res.get("appointments"):
                latest_apt = res["appointments"][0]
                collected["appointment_id"] = latest_apt.get("id")
                collected["appointment_date"] = latest_apt.get("date")
                collected["appointment_service"] = latest_apt.get("service")
                notes = latest_apt.get("notes", "")
                if notes:
                    collected["appointment_code"] = notes
                logging.info(f"📋 Randevu bilgisi kaydedildi: ID={latest_apt.get('id')}")
            
            if "campaigns" in res and res.get("success"):
                campaigns = res.get("campaigns", [])
                if campaigns:
                    context["active_campaigns"] = campaigns
                    first_campaign = campaigns[0]
                    context["campaign_name"] = first_campaign.get("name")
                    context["campaign_discount"] = first_campaign.get("discount")
                    context["campaign_end_date"] = first_campaign.get("end_date")

    async def process_request(self, session_id: str, user_message: str, websocket=None) -> str:
        """Ana İşlem Akışı"""
        logging.info(f"\n{'='*50}\n🎯 İSTEK: {user_message}\n{'='*50}")

        conv = self.conversations.get(session_id)
        if not conv:
            conv = {"context": {}, "collected": {}, "history": []}
            self.conversations[session_id] = conv
        
        conv["history"].append({"role": "user", "content": user_message})
        
        regex_info = self._extract_info_with_regex(user_message)
        conv["collected"].update({k:v for k,v in regex_info.items() if v})
        
        unified = await self._extract_and_plan_unified(user_message, conv)
        
        new_extracted = unified.get("extracted", {})
        for k, v in new_extracted.items():
            if v and v != "null" and v != "": 
                conv["collected"][k] = v
        
        logging.info(f"🧠 FINAL COLLECTED STATE: {json.dumps(conv['collected'], ensure_ascii=False)}")
            
        plan = unified.get("plan", {})
        action = plan.get("action")
        
        response_text = plan.get("ask_user", "")
        response_text = self._clean_llm_response(response_text)
        
        if action in ["chat", "inform_missing", "confirm"] and not plan.get("steps"):
            await self._send_response(response_text, conv, websocket, session_id)
            return response_text
            
        if action == "execute_tool" or plan.get("steps"):
            for step in plan["steps"]:
                if "customer_phone" not in step.get("params", {}) and conv["collected"].get("phone"):
                    step["params"]["customer_phone"] = conv["collected"]["phone"]
                
                if step.get("operation") == "check_campaigns" and "customer_phone" not in step.get("params", {}):
                    step["params"]["customer_phone"] = conv["collected"].get("phone")
                
                if step.get("operation") == "check_availability" and \
                   "service_type" not in step.get("params", {}) and \
                   conv["collected"].get("service"):
                    step["params"]["service_type"] = conv["collected"]["service"]

            results = await self._execute_plan(plan, conv)
            self._update_context(results, conv)
            
            final_response = await self._generate_tool_response(user_message, plan, results, conv)
            await self._send_response(final_response, conv, websocket, session_id)
            return final_response

        await self._send_response(response_text, conv, websocket, session_id)
        return response_text

    async def _execute_plan(self, plan: Dict, conv: Dict) -> Dict:
        """Agent Toollarını Çalıştır"""
        results = {}
        agent_map = {
            "booking_agent": self.agents["appointment"],
            "customer_agent": self.agents["customer"],
            "marketing_agent": self.agents["marketing"]
        }

        for i, step in enumerate(plan.get("steps", [])):
            agent_key = step.get("agent")
            operation = step.get("operation")
            params = step.get("params", {})
            collected = conv.get("collected", {})
            
            if operation == "check_customer":
                if "phone" not in params and collected.get("phone"):
                    params["phone"] = collected["phone"]
            
            if operation == "create_customer":
                if "phone" not in params and collected.get("phone"):
                    params["phone"] = collected["phone"]
                if "full_name" not in params and "name" not in params:
                    if collected.get("name"):
                        params["full_name"] = collected["name"]
                    elif collected.get("full_name"):
                        params["full_name"] = collected["full_name"]
            
            if operation == "check_availability":
                if "date" not in params and collected.get("date"):
                    params["date"] = collected["date"]
                if "date_time" not in params and collected.get("date") and collected.get("time"):
                    params["date_time"] = f"{collected['date']}T{collected['time']}:00"
                if "expert_name" not in params and collected.get("expert_name"):
                    params["expert_name"] = collected["expert_name"]
            
            if operation == "suggest_alternative_times":
                if "service_type" not in params and collected.get("service"):
                    params["service_type"] = collected["service"]
                if "date" not in params and collected.get("date"):
                    params["date"] = collected["date"]
                if "expert_name" not in params and collected.get("expert_name"):
                    params["expert_name"] = collected["expert_name"]
            
            if operation == "create_appointment":
                if "customer_phone" not in params and collected.get("phone"):
                    params["customer_phone"] = collected["phone"]
                if "service_type" not in params and collected.get("service"):
                    params["service_type"] = collected["service"]
                if "appointment_datetime" not in params and collected.get("date") and collected.get("time"):
                    params["appointment_datetime"] = f"{collected['date']}T{collected['time']}:00"
                if "expert_name" not in params and collected.get("expert_name"):
                    params["expert_name"] = collected["expert_name"]
            
            agent = agent_map.get(agent_key)
            if not agent:
                logging.warning(f"⚠️ Bilinmeyen agent: {agent_key}")
                continue
                
            try:
                logging.info(f"▶ ÇALIŞTIRILIYOR: {agent_key}.{operation} | Params: {params}")
                task_payload = {"task": operation, "parameters": params}
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
        BURADA 'HARİKA' DEMESİ ENGELLENDİ.
        """
        
        context_summary = {
            "customer_name": conv["context"].get("customer_name"),
            "tool_outputs": results
        }

        prompt = f"""### RESPONSE GENERATION ###
ROLE: Beauty Center Assistant.
GOAL: Create a short and natural Turkish response based on TOOL RESULTS.

USER SAID: "{user_msg}"

TOOL RESULTS (Technical):
{json.dumps(results, ensure_ascii=False, indent=2)}

CONTEXT:
{json.dumps(context_summary, ensure_ascii=False)}

RULES:
1. **APPOINTMENT CREATED:** If result has 'success': true and a 'code', say: "Randevunuz başarıyla oluşturuldu. Randevu Kodunuz: [CODE]. Sizi bekliyoruz!" (DO NOT start with 'Harika').
2. **QUERY APPOINTMENTS:** If result has 'appointments' array:
   - If array is EMPTY: "Kayıtlı randevunuz bulunmuyor."
   - If array has confirmed items: List them with date, time, service and expert.
3. **ALTERNATIVE TIMES:** List options concisely (e.g., "5 Aralık: 09:00, 11:30 müsait.").
4. **AVAILABILITY:** List slots clearly.
5. **EXPERTS:** "Şu uzmanlarımız hizmet veriyor: [Names]. Hangisini tercih edersiniz?"
6. **ERROR:** If 'success': false, apologize politely.
7. **TONE:** Professional, polite, helpful. NO generic excitement words like "Harika", "Süper".
8. **OUTPUT:** A plain, natural Turkish String ONLY.

OUTPUT (Plain text only):"""

        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            try:
                response_json = json.loads(response_text)
                if isinstance(response_json, dict) and "response" in response_json:
                    return response_json["response"]
            except (json.JSONDecodeError, KeyError):
                pass
            
            return response_text
        except Exception as e:
            logging.error(f"Tool yanıtı oluşturma hatası: {e}")
            if "create_appointment" in json.dumps(results):
                return "İşleminizi gerçekleştirdim, sistemimize kaydettim."
            return "İşleminizi tamamlarken bir gecikme oldu, lütfen bekleyin."

    async def _send_response(self, text: str, conv: Dict, websocket, session_id: str = None):
        """Cevabı kaydeder ve WebSocket üzerinden gönderir."""
        conv["history"].append({"role": "assistant", "content": text})
        
        if len(conv["history"]) > 20:
            conv["history"] = conv["history"][-20:]
        
        logging.info(f"💬 HISTORY COUNT: {len(conv['history'])}")
        
        if session_id:
            self.conversations[session_id] = conv
            
        if websocket:
            try:
                await websocket.send_text(text)
                await websocket.send_text(json.dumps({"type": "stream_end"}))
                logging.info(f"📤 Yanıt gönderildi: {text[:100]}...")
            except Exception as e:
                logging.error(f"WebSocket gönderim hatası: {e}")

    def _reset_conversation(self, session_id: str):
        """Oturumu sıfırla"""
        self.conversations[session_id] = {
            "context": {},
            "collected": {},
            "history": []
        }
        logging.info(f"♻️ Oturum sıfırlandı: {session_id}")