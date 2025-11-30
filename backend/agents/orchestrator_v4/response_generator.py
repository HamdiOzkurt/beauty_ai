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

    def _clean_tool_result(self, tool_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tool result'ı temizle - Gemini'ye göndermeden önce.

        Traceback, stack trace, teknik hata mesajlarını kısa özet haline getir.
        """
        if not isinstance(tool_result, dict):
            return {"success": False, "error": "Invalid tool result"}

        cleaned = {}

        for key, value in tool_result.items():
            # Error mesajlarını temizle
            if key == "error" and isinstance(value, str):
                # Traceback varsa sadece ilk satırını al
                if "Traceback" in value or "File " in value:
                    # Sadece hata tipini ve mesajını al
                    lines = value.split("\n")
                    error_line = lines[-1] if lines else value
                    # RuntimeError, ConnectionError gibi bilgiler yeterli
                    if ":" in error_line:
                        cleaned[key] = error_line.split(":", 1)[-1].strip()
                    else:
                        cleaned[key] = "Connection failed"
                else:
                    # Uzun hata mesajını kısalt (max 100 karakter)
                    cleaned[key] = value[:100] if len(value) > 100 else value
            else:
                cleaned[key] = value

        return cleaned

    def _get_fallback_response(self, tool_name: str, tool_result: Dict[str, Any]) -> str:
        """
        LLM hata verdiğinde tool-specific fallback mesaj döndür.

        Bu, Gemini'nin safety filter'ına takıldığında veya boş yanıt döndüğünde devreye girer.
        """
        success = tool_result.get("success", False)

        # Tool-specific fallback messages
        fallback_messages = {
            "check_customer": {
                True: "Müşteri bilgileriniz bulundu. Devam edebiliriz.",
                False: "Telefon numaranızı sistemde bulamadım. Yeni kayıt oluşturabiliriz."
            },
            "create_appointment": {
                True: f"Randevunuz oluşturuldu. {tool_result.get('appointment', {}).get('code', '')}",
                False: "Randevu oluşturulurken bir sorun oluştu. Lütfen tekrar deneyin."
            },
            "cancel_appointment": {
                True: "Randevunuz iptal edildi.",
                False: "Randevu iptal edilirken bir sorun oluştu."
            },
            "get_customer_appointments": {
                True: "Randevu bilgileriniz bulundu." if tool_result.get("appointments") else "Kayıtlı randevunuz bulunmuyor.",
                False: "Randevularınız sorgulanırken bir sorun oluştu."
            },
            "check_availability": {
                True: "Müsaitlik durumu kontrol edildi.",
                False: "Müsaitlik kontrol edilirken bir sorun oluştu."
            },
            "list_experts": {
                True: "Uzman listesi hazır.",
                False: "Uzmanlar listelenirken bir sorun oluştu."
            },
            "list_services": {
                True: "Hizmet listesi hazır.",
                False: "Hizmetler listelenirken bir sorun oluştu."
            },
            "check_campaigns": {
                True: "Kampanya bilgileri hazır.",
                False: "Kampanyalar kontrol edilirken bir sorun oluştu."
            }
        }

        # Get fallback message
        tool_fallbacks = fallback_messages.get(tool_name, {
            True: "İşleminiz tamamlandı.",
            False: "Üzgünüm, bir sorun oluştu. Lütfen tekrar deneyin."
        })

        return tool_fallbacks.get(success, "İşleminiz tamamlandı.")

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

            # Güvenlik filtresi veya boş yanıt kontrolü
            if not response.candidates:
                self.logger.warning("⚠️ [LLM #2] No candidates in response (safety filter?)")
                raise ValueError("No candidates in response")

            candidate = response.candidates[0]

            # finish_reason kontrolü (2 = SAFETY, 3 = RECITATION)
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason in [2, 3]:
                self.logger.warning(f"⚠️ [LLM #2] Response blocked (finish_reason={candidate.finish_reason})")
                raise ValueError(f"Response blocked by safety filter (reason={candidate.finish_reason})")

            # Text extraction
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

        except ValueError as e:
            # Safety filter veya boş yanıt hatası
            self.logger.error(f"❌ [LLM #2] Safety/Empty response error: {e}")
            # Tool-specific fallback
            return self._get_fallback_response(tool_name, tool_result)

        except Exception as e:
            self.logger.error(f"❌ [LLM #2] Generation error: {e}", exc_info=True)
            # Tool-specific fallback
            return self._get_fallback_response(tool_name, tool_result)

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
        - Hata mesajlarını temizle (Traceback'leri gösterme)
        """
        # Tool result'ı temizle ve formatla
        cleaned_result = self._clean_tool_result(tool_result)
        tool_result_str = json.dumps(cleaned_result, ensure_ascii=False, indent=2)

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
