"""
Response Generator - LLM Call #2
Tool sonuçlarını natural Turkish response'a çevir
Temperature: 0.7 (Natural but consistent)
"""

import google.generativeai as genai
import logging
import json
from typing import Dict, Any, Optional


class ResponseGenerator:
    """
    LLM Call #2: Tool result → Natural language response

    Görevler:
    1. Tool sonuçlarını yorumla
    2. Context-aware yanıt üret (customer name, campaigns)
    3. Doğal, sıcak, profesyonel ton
    4. Kısa ve öz (max 2-3 cümle)
    5. Emoji yok!

    Kullanılan: Gemini text generation (NO function calling)
    """

    def __init__(self, gemini_model: genai.GenerativeModel):
        """
        Args:
            gemini_model: Gemini model instance
        """
        self.model = gemini_model
        self.logger = logging.getLogger(__name__)

    async def generate(
        self,
        action: Dict[str, Any],
        tool_result: Optional[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> str:
        """
        Tool result ve action'a göre natural response üret.

        Args:
            action: FlowManager'dan gelen action
            tool_result: Tool execution sonucu (None olabilir)
            context: Konuşma context'i (customer_name, campaigns, vb.)

        Returns:
            Natural Turkish response string
        """
        self.logger.info(f"💬 [LLM #2] Response generation başladı")

        action_type = action.get("action")

        # Eğer action "ask_missing" veya "confirm" ise, LLM'e gitmeye gerek yok
        # FlowManager zaten message hazırlamış
        if action_type in ["ask_missing", "confirm", "ask_alternative"]:
            response = action.get("message", "Anlayamadım, tekrar eder misiniz?")
            self.logger.info(f"✅ [LLM #2] Direct message (no LLM): {response[:50]}...")
            return response

        # Eğer tool result varsa, LLM ile yorumla
        if tool_result and action_type == "tool_call":
            return await self._generate_tool_response(
                tool_name=action.get("tool"),
                tool_result=tool_result,
                context=context
            )

        # Chat mode - genel sohbet
        if action_type == "chat":
            return "Başka bir konuda yardımcı olabilir miyim?"

        # Fallback
        return "Anlayamadım, tekrar eder misiniz?"

    async def _generate_tool_response(
        self,
        tool_name: str,
        tool_result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """
        Tool sonucunu LLM ile natural language'e çevir.

        Args:
            tool_name: Çağrılan tool'un adı
            tool_result: Tool'dan dönen sonuç
            context: Customer name, campaigns, vb.

        Returns:
            Natural Turkish response
        """
        # Context'ten bilgileri al
        customer_name = context.get("customer_name", "Müşteri")
        active_campaigns = context.get("active_campaigns", [])

        # Prompt oluştur - COMPACT
        prompt = self._build_response_prompt(
            tool_name=tool_name,
            tool_result=tool_result,
            customer_name=customer_name,
            active_campaigns=active_campaigns
        )

        try:
            # Gemini'ye gönder (text generation, temperature=0.7)
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()

            # Validation - JSON döndürmüş mü? (hata)
            if response_text.startswith("{") or response_text.startswith("["):
                self.logger.warning("⚠️ [LLM #2] LLM returned JSON instead of text")
                # JSON parse et ve içinden text'i çıkar
                try:
                    parsed = json.loads(response_text)
                    if isinstance(parsed, dict):
                        response_text = parsed.get("response", parsed.get("message", response_text))
                except:
                    pass

            # Max length check (300 karakter yeterli)
            if len(response_text) > 300:
                self.logger.warning(f"⚠️ [LLM #2] Response too long ({len(response_text)} chars)")
                response_text = response_text[:300] + "..."

            self.logger.info(f"✅ [LLM #2] Generated response: {response_text[:50]}...")
            return response_text

        except Exception as e:
            self.logger.error(f"❌ [LLM #2] Generation error: {e}", exc_info=True)
            # Fallback - tool success/failure'a göre generic message
            if tool_result.get("success"):
                return "İşleminizi tamamladım."
            else:
                return "Üzgünüm, bir sorun oluştu. Lütfen tekrar deneyin."

    def _build_response_prompt(
        self,
        tool_name: str,
        tool_result: Dict[str, Any],
        customer_name: str,
        active_campaigns: list
    ) -> str:
        """
        Response generation için compact prompt.

        Stratejiler:
        - Tool-specific rules
        - Examples vermiyoruz (model iyi)
        - Max 30 satır
        """
        # Tool result'ı formatla (pretty print)
        tool_result_str = json.dumps(tool_result, ensure_ascii=False, indent=2)

        # Kampanya bilgisi (varsa)
        campaign_str = ""
        if active_campaigns:
            campaign_str = "\n### AKTİF KAMPANYALAR ###\n"
            for c in active_campaigns[:2]:  # Max 2 kampanya
                campaign_str += f"- {c.get('name')}: %{c.get('discount')} indirim\n"

        prompt = f"""### GÖREV ###
Tool sonucunu doğal Türkçe yanıta çevir.

### BAĞLAM ###
Müşteri Adı: {customer_name}
{campaign_str}
### TOOL SONUCU ###
Tool: {tool_name}
Result:
{tool_result_str}

### YANIT KURALLARI ###
1. **Randevu Oluşturuldu**: 'success': true ve 'code' varsa → "Randevunuz oluşturuldu. Kod: [CODE]. Sizi bekliyoruz!"
2. **Randevu Sorgu**:
   - Appointments boş → "Kayıtlı randevunuz bulunmuyor."
   - Appointments var, status='confirmed' → Tarih,1 saat, hizmet, uzman listele. İPTAL edilmiş olanları GÖSTERME!
   - ASLA "iptal edilmiş" veya "cancelled" deme confirmed randevular için!
3. **Alternatif Saatler**: Max 3 seçenek, kısa liste. "5 Aralık: 09:00, 11:30, 14:00 müsait. Hangisi uygun?"
4. **Müsaitlik**: Slots varsa kısaca listele. "Sabah 09:00 ve 10:30 müsait."
5. **Uzmanlar**: "Şu uzmanlarımız hizmet veriyor: [İsimler]. Hangisini tercih edersiniz?"
6. **Kampanyalar**: Varsa kısaca bahset. "{customer_name} Bey/Hanım, %20 indirim kampanyamız var."
7. **Hata**: 'success': false → Özür dile, alternatif öner veya eksik bilgi sor.
8. **Ton**: Sıcak, profesyonel. Müşteri adını kullan ("{customer_name} Bey/Hanım").
9. **Uzunluk**: Max 2-3 cümle. Kısa ve öz.
10. **EMOJİ YOK**: Hiç emoji kullanma!

### ÇIKTI ###
Sadece doğal Türkçe yanıt yaz. JSON, kod, markup YOK!
"""
        return prompt


# ============================================================================
# TEST & VALIDATION
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("\n" + "="*50)
    print("RESPONSE GENERATOR - VALIDATION TEST")
    print("="*50 + "\n")

    # Mock tool results
    test_cases = [
        {
            "tool": "create_appointment",
            "result": {
                "success": True,
                "appointment": {
                    "code": "RNV2025120114"
                }
            },
            "expected_keywords": ["randevu", "kod", "RNV2025120114"]
        },
        {
            "tool": "get_customer_appointments",
            "result": {
                "success": True,
                "appointments": []
            },
            "expected_keywords": ["kayıtlı", "randevu", "bulunmuyor"]
        },
        {
            "tool": "check_availability",
            "result": {
                "success": True,
                "available": False
            },
            "expected_keywords": ["dolu", "müsait değil"]
        }
    ]

    print("Mock test cases prepared.")
    print("(Actual LLM test requires Gemini API key)")
    print("\n" + "="*50)
