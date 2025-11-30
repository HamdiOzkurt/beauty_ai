"""
Intent & Entity Router - LLM Call #1
Focused task: Intent classification + Entity extraction
Temperature: 0.0 (Deterministic)
"""

import google.generativeai as genai
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator
from enum import Enum


# ============================================================================
# PYDANTIC MODELS - Strict validation
# ============================================================================

class IntentType(str, Enum):
    """Intent tipleri - Strict"""
    BOOKING = "booking"
    QUERY_APPOINTMENT = "query_appointment"
    CANCEL = "cancel"
    CHAT = "chat"
    CAMPAIGN_INQUIRY = "campaign_inquiry"


class ExtractedEntities(BaseModel):
    """
    LLM'den extract edilen entity'ler
    Validation: Pydantic ile type-safe
    """
    phone: Optional[str] = Field(None, description="Telefon numarası (05XXXXXXXXX)")
    service: Optional[str] = Field(None, description="Hizmet adı")
    expert_name: Optional[str] = Field(None, description="Uzman adı")
    date: Optional[str] = Field(None, description="Tarih (YYYY-MM-DD)")
    time: Optional[str] = Field(None, description="Saat (HH:MM)")
    confirmed: Optional[bool] = Field(None, description="Kullanıcının bir işlemi (örn: randevu) onaylayıp onaylamadığı")

    @validator('phone')
    def validate_phone(cls, v):
        """Telefon formatını kontrol et"""
        if v is None:
            return v
        # Boşlukları ve tire'leri temizle
        cleaned = v.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        # 05 ile başlamalı ve 11 karakter olmalı
        if cleaned.startswith("05") and len(cleaned) == 11 and cleaned.isdigit():
            return cleaned
        # Format yanlış ama telefon gibi görünüyorsa (10-11 digit), LLM'e güven
        if cleaned.isdigit() and 10 <= len(cleaned) <= 11:
            return cleaned
        # Tamamen yanlış format
        logging.warning(f"Invalid phone format: {v}")
        return None

    @validator('date')
    def validate_date(cls, v):
        """Tarih formatını kontrol et"""
        if v is None:
            return v
        # YYYY-MM-DD formatında olmalı
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            logging.warning(f"Invalid date format: {v}")
            return None

    @validator('time')
    def validate_time(cls, v):
        """Saat formatını kontrol et"""
        if v is None:
            return v
        # HH:MM formatında olmalı
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            logging.warning(f"Invalid time format: {v}")
            return None


class IntentEntityResult(BaseModel):
    """LLM'den dönen sonuç - Full result"""
    intent: IntentType = Field(..., description="Kullanıcının niyeti")
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities, description="Çıkarılan entity'ler")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="LLM'in güven skoru")


# ============================================================================
# INTENT & ENTITY ROUTER
# ============================================================================

class IntentEntityRouter:
    """
    LLM Call #1: Intent classification + Entity extraction

    Görevler:
    1. User intent'i belirle (booking, query, cancel, chat)
    2. Entity'leri extract et (phone, service, expert, date, time)
    3. Temporal expressions'ı resolve et ("yarın" → date)
    4. Fuzzy matching (service/expert names)

    Kullanılan: Gemini Function Calling (native JSON)
    """

    def __init__(self, gemini_model: genai.GenerativeModel, knowledge_base_summary: str):
        """
        Args:
            gemini_model: Gemini model instance
            knowledge_base_summary: Hizmetler, uzmanlar özeti (CMS'den)
        """
        self.model = gemini_model
        self.knowledge_base = knowledge_base_summary
        self.logger = logging.getLogger(__name__)

        # Function calling schema definition
        self.extraction_function = {
            "name": "extract_intent_entities",
            "description": "Extract user intent and booking entities from Turkish message",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["booking", "query_appointment", "cancel", "campaign_inquiry", "chat"],
                        "description": "User's intent"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number in format 05XXXXXXXXX"
                    },
                    "service": {
                        "type": "string",
                        "description": "Service name"
                    },
                    "expert_name": {
                        "type": "string",
                        "description": "Expert name"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in HH:MM format"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score 0.0-1.0"
                    }
                },
                "required": ["intent", "confidence"]
            }
        }

    async def route(
        self,
        user_message: str,
        collected_state: Dict[str, Any],
        conversation_history: List[Dict] = None,
        context: Dict[str, Any] = None
    ) -> IntentEntityResult:
        """
        User message'dan intent ve entity'leri extract et.
        Artık stateful: Confirmation gibi durumları LLM'e gitmeden çözer.
        """
        self.logger.info(f"🎯 [LLM #1] Intent & Entity extraction başladı")
        context = context or {}

        # --- STATEFUL PRE-ROUTING LOGIC ---
        if context.get("confirmation_pending"):
            self.logger.info("🚦 Confirmation pending - checking for user confirmation...")
            normalized_message = user_message.lower().strip()
            
            AFFIRMATIVE_KEYWORDS = ["evet", "onaylıyorum", "eminim", "doğru", "evd", "onayla"]
            NEGATIVE_KEYWORDS = ["hayır", "iptal", "vazgeçtim", "istemiyorum", "hayir", "kalsın"]
            
            is_affirmative = any(keyword in normalized_message for keyword in AFFIRMATIVE_KEYWORDS)
            is_negative = any(keyword in normalized_message for keyword in NEGATIVE_KEYWORDS)

            last_intent = context.get("last_intent", IntentType.CHAT)

            if is_affirmative:
                self.logger.info("✅ User confirmed action, bypassing LLM.")
                return IntentEntityResult(
                    intent=last_intent,
                    entities=ExtractedEntities(confirmed=True),
                    confidence=1.0
                )
            
            if is_negative:
                self.logger.info("❌ User denied action, bypassing LLM.")
                return IntentEntityResult(
                    intent=last_intent,
                    entities=ExtractedEntities(confirmed=False),
                    confidence=1.0
                )

        # --- LLM ROUTING (if no stateful rule matched) ---
        self.logger.info(f"🧠 No stateful rule matched, proceeding with LLM.")
        
        history_text = self._format_history(conversation_history or [])
        state_summary = self._format_collected_state(collected_state)
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")

        prompt = self._build_prompt(
            user_message=user_message,
            today=today_str,
            tomorrow=tomorrow_str,
            state_summary=state_summary,
            history_text=history_text
        )

        try:
            tools = [{"function_declarations": [self.extraction_function]}]
            response = self.model.generate_content(
                prompt,
                tools=tools,
                tool_config={"function_calling_config": {"mode": "ANY"}}
            )

            if response.candidates and response.candidates[0].content.parts:
                function_call = response.candidates[0].content.parts[0].function_call
                if function_call and function_call.name == "extract_intent_entities":
                    args = dict(function_call.args)
                    self.logger.info(f"[LLM #1] Function call args: {args}")
                    intent_str = args.get("intent", "chat")
                    confidence = args.get("confidence", 0.8)
                    entities = ExtractedEntities(
                        phone=args.get("phone"),
                        service=args.get("service"),
                        expert_name=args.get("expert_name"),
                        date=args.get("date"),
                        time=args.get("time")
                    )
                    result = IntentEntityResult(
                        intent=IntentType(intent_str),
                        entities=entities,
                        confidence=confidence
                    )
                    self.logger.info(
                        f"[OK] [LLM #1] Intent: {result.intent}, "
                        f"Entities: {len([k for k, v in result.entities.model_dump(exclude_none=True).items() if v])}"
                    )
                    return result

            self.logger.warning("[WARN] [LLM #1] No function call in response")
            return IntentEntityResult(intent=IntentType.CHAT, entities=ExtractedEntities(), confidence=0.3)

        except Exception as e:
            self.logger.error(f"[FAIL] [LLM #1] Error: {e}", exc_info=True)
            return IntentEntityResult(intent=IntentType.CHAT, entities=ExtractedEntities(), confidence=0.0)

    def _build_prompt(
        self,
        user_message: str,
        today: str,
        tomorrow: str,
        state_summary: str,
        history_text: str
    ) -> str:
        """
        Compact prompt oluştur - maksimum 40 satır

        Stratejiler:
        - Gereksiz açıklamalar yok
        - Directive'ler kısa ve net
        - Örnek vermiyoruz (model iyi)
        - Knowledge base özet (full list değil)
        """
        prompt = f"""### GÖREV ###
Kullanıcının niyetini (intent) belirle ve bilgileri (entities) çıkar.

### TARİH BİLGİSİ ###
Bugün: {today} (Referans: "bugün", "bu gün")
Yarın: {tomorrow} (Referans: "yarın")

### BİLGİ BANKASI ###
{self.knowledge_base}

### TOPLANMIŞ BİLGİLER (Hafıza) ###
{state_summary}

### KONUŞMA GEÇMİŞİ ###
{history_text}

### KULLANICI MESAJI ###
"{user_message}"

### INTENT SEÇENEKLERİ ###
1. **booking**: Randevu oluşturmak istiyor VEYA randevuyla ilgili SORU soruyor
2. **query_appointment**: Mevcut randevularını soruyor ("randevum var mı", "randevumu öğrenmek istiyorum")
3. **cancel**: Randevu iptal etmek istiyor
4. **campaign_inquiry**: Kampanya soruyor
5. **chat**: SADECE selamlaşma veya tamamen alakasız sohbet

### ⚠️ KRİTİK SINIFLANDIRMA KURALLARI ###
**BOOKING olarak sınıflandır:**
- Uzman/personel soruları: "kim var", "hangi uzmanlar", "Ayşe var mı", "kimler çalışıyor"
- Müsaitlik soruları: "müsait misiniz", "boş saatiniz", "ne zaman gelebilirim", "saat kaçta"
- Hizmet soruları: "neler yapıyorsunuz", "hangi hizmetler", "saç kesimi var mı"
- Öneri soruları: "ne önerirsiniz", "başka ne", "tamamlayıcı hizmet"
- Tarih/saat soruları: "haftaya salı", "yarın müsait mi", "bugün randevu alabilir miyim"

**CAMPAIGN_INQUIRY olarak sınıflandır:**
- Kampanya soruları: "kampanya var mı", "indirim", "fırsat", "promosyon"

**QUERY_APPOINTMENT olarak sınıflandır:**
- Mevcut randevu soruları: "randevum ne zaman", "randevularımı göster", "randevum var mı"

**CANCEL olarak sınıflandır:**
- İptal istekleri: "iptal etmek istiyorum", "randevumu iptal et", "vazgeçtim"

**CHAT olarak sınıflandır (ÇOK NADIR!):**
- SADECE selamlaşma: "merhaba", "nasılsın", "iyi günler"
- SADECE alakasız: "hava nasıl", "ne yapıyorsun"

**ÖNEMLİ:** Kullanıcı güzellik salonu hakkında BİR ŞEY soruyorsa, bu ASLA "chat" değildir!

### ENTITY ÇIKARMA KURALLARI ###
- **phone**: 05XXXXXXXXX formatı. Örn: "532 123 45 67" → "05321234567"
- **service**: Hizmet adı (Bilgi Bankası'ndan). Fuzzy matching yap: "saç kestirmek" → "saç kesimi"
- **expert_name**: Uzman adı. "Ayşe" veya "ayse abla" → isim olarak döndür (fuzzy)
- **date**: YYYY-MM-DD. Temporal: "yarın" → {tomorrow}, "bugün" → {today}, "3 aralık" → "2025-12-03"
- **time**: HH:MM. "öğleden sonra" → "14:00", "sabah" → "09:00", "akşam" → "17:00"

**ÖNEMLİ**: Eğer hafızada zaten varsa, yeniden sorma! Hafıza'da phone varsa, entity'de tekrar çıkarma.

### ÇIKTI FORMATI (JSON) ###
{{
  "intent": "booking" | "query_appointment" | "cancel" | "campaign_inquiry" | "chat",
  "entities": {{
    "phone": "05XXXXXXXXX or null",
    "service": "string or null",
    "expert_name": "string or null",
    "date": "YYYY-MM-DD or null",
    "time": "HH:MM or null"
  }},
  "confidence": 0.0-1.0
}}

SADECE JSON DÖNDÜR, BAŞKA BİR ŞEY YAZMA!
"""
        return prompt

    def _format_history(self, history: List[Dict]) -> str:
        """Son 6 mesajı formatla"""
        if not history:
            return "(Henüz konuşma geçmişi yok)"

        formatted = []
        for msg in history[-6:]:  # Son 6 mesaj
            role = "User" if msg.get("role") == "user" else "Bot"
            content = msg.get("content", "")
            formatted.append(f"{role}: {content}")

        return "\n".join(formatted)

    def _format_collected_state(self, collected: Dict[str, Any]) -> str:
        """Collected state'i okunabilir formata çevir"""
        if not collected:
            return "(Henüz bilgi toplanmadı)"

        summary = []
        if collected.get("phone"):
            summary.append(f"✓ Telefon: {collected['phone']}")
        if collected.get("service"):
            summary.append(f"✓ Hizmet: {collected['service']}")
        if collected.get("expert_name"):
            summary.append(f"✓ Uzman: {collected['expert_name']}")
        if collected.get("date"):
            summary.append(f"✓ Tarih: {collected['date']}")
        if collected.get("time"):
            summary.append(f"✓ Saat: {collected['time']}")

        return "\n".join(summary) if summary else "(Henüz bilgi toplanmadı)"


# ============================================================================
# TEST & VALIDATION
# ============================================================================

if __name__ == "__main__":
    # Mock test (Gemini olmadan)
    logging.basicConfig(level=logging.DEBUG)

    print("\n" + "="*50)
    print("INTENT & ENTITY ROUTER - VALIDATION TEST")
    print("="*50 + "\n")

    # Test Pydantic models
    test_data = {
        "intent": "booking",
        "entities": {
            "phone": "532 123 45 67",  # Validation temizleyecek
            "service": "saç kesimi",
            "date": "2025-12-01",
            "time": "14:00"
        },
        "confidence": 0.95
    }

    try:
        result = IntentEntityResult(**test_data)
        print("✅ Pydantic validation passed")
        print(f"   Phone (cleaned): {result.entities.phone}")
        print(f"   Intent: {result.intent}")
    except Exception as e:
        print(f"❌ Validation failed: {e}")
