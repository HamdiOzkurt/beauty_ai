import requests
import json
from typing import Dict, Any
from agents.base_agent import BaseAgent
from config import settings
import logging

class MarketingAgent(BaseAgent):
    """Kampanya ve çapraz satıştan sorumlu - MCP ve AI kombinasyonu."""
    
    def __init__(self):
        super().__init__(
            name="MarketingAgent",
            model=settings.OLLAMA_MODEL,
            capabilities=[
                "suggest_complementary_service", 
                "check_campaigns", 
                "personalize_offer",
                "list_services" # list_services gibi genel görevleri de buraya ekleyebiliriz.
            ]
        )
    
    async def execute(self, task: Dict[str, Any], conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Marketing görevini gerçekleştir."""
        task_type = task.get("task")
        params = task.get("parameters", {})
        
        logging.info(f"[{self.name}] Görev alındı: {task_type}")

        if task_type == "suggest_complementary_service":
            return await self._suggest_complementary_service(params, conversation)
        elif task_type == "check_campaigns":
            return await self._check_campaigns(params, conversation)
        elif task_type == "personalize_offer":
            return await self._personalize_offer(params, conversation)
        elif task_type == "list_services":
            # list_services parametresiz çağrılır
            return await self.call_mcp_tool("list_services", {})
        elif task_type == "list_experts":
            # list_experts sadece service_type parametresi alabilir
            service_type = params.get("service_type") or conversation.get("collected", {}).get("service")
            mcp_params = {"service_type": service_type} if service_type else {}
            return await self.call_mcp_tool("list_experts", mcp_params)
        
        return {"success": False, "error": "Bilinmeyen görev tipi"}
    
    async def _suggest_complementary_service(self, params: Dict, conversation: Dict) -> Dict:
        """
        Akıllı hizmet önerisi:
        1. MCP'den statik önerileri al
        2. MCP'den müşteri geçmişini al (eğer varsa)
        3. Ollama ile kişiselleştir
        """
        service = params.get("service_type")
        if not service:
            return {"success": False, "error": "Hizmet önermek için bir ana hizmet tipi belirtilmelidir."}

        # Telefon numarasını önce parametrelerden, sonra konuşma hafızasından al
        customer_phone = params.get("customer_phone") or conversation.get("user_info", {}).get("phone")
        
        basic_suggestions_result = await self.call_mcp_tool(
            "suggest_complementary_service",
            {"service_type": service}
        )
        basic_suggestions = basic_suggestions_result if basic_suggestions_result.get("success") else {"suggestions": []}
        
        customer_history = []
        if customer_phone:
            customer_data = await self.call_mcp_tool(
                "check_customer",
                {"phone": customer_phone}
            )
            if customer_data.get("success"):
                customer_history = [
                    apt["service"] 
                    for apt in customer_data.get("recent_appointments", [])
                ]
        
        personalization_prompt = f"""
Müşteri "{service}" hizmeti alacak veya bu hizmetle ilgileniyor.

Müşterinin geçmiş hizmetleri:
{chr(10).join([f"- {h}" for h in customer_history]) if customer_history else "Bu müşteri yeni veya geçmiş hizmet bilgisi yok."}

Standart tamamlayıcı hizmet önerileri: {basic_suggestions.get('suggestions', [])}

Görevlerin:
1. Müşterinin geçmişine dayanarak, standart öneriler arasından en uygun 2-3 hizmeti seç.
2. Her öneri için müşteriyi ikna edecek kısa bir neden yaz.
3. Önerileri en olasıdan en az olasıya doğru önceliklendir.
4. Tüm bu önerileri sunacak, müşteriye özel, samimi ve kısa bir pazarlama mesajı oluştur.

JSON formatında şu yapıda bir yanıt ver:
{{
  "suggestions": [
    {{"service": "önerilen_hizmet_1", "reason": "neden_1", "priority": 1}},
    {{"service": "önerilen_hizmet_2", "reason": "neden_2", "priority": 2}}
  ],
  "marketing_message": "Müşteriye söylenecek ikna edici ve kişiselleştirilmiş mesaj."
}}
"""
        logging.debug(f"[{self.name}] Ollama Hizmet Öneri Prompt'u:\n{personalization_prompt}")

        try:
            payload = {
                "model": self.model, 
                "prompt": personalization_prompt, 
                "stream": False, 
                "format": "json",
                "options": {
                    "num_gpu": 99,  # Tüm katmanları GPU'ya yükle
                    "num_thread": 4,
                    "temperature": 0.7
                }
            }
            response = requests.post(f"{settings.OLLAMA_HOST}/api/generate", json=payload, timeout=30)
            response.raise_for_status()
            
            personalized = json.loads(response.json()["response"])
            logging.debug(f"[{self.name}] Ollama Hizmet Öneri Sonucu:\n{json.dumps(personalized, indent=2, ensure_ascii=False)}")

            self.add_to_memory(f"Hizmet önerisi: {service} -> {personalized.get('suggestions')}")
            
            return {
                "success": True,
                "service": service,
                "suggestions": personalized.get("suggestions", []),
                "message": personalized.get("marketing_message", "Size özel bazı ek hizmetlerimiz olabilir.")
            }
        except Exception as e:
            logging.error(f"[{self.name}] Kişiselleştirilmiş öneri hatası: {e}. Standart öneriler kullanılacak.")
            return basic_suggestions
    
    async def _check_campaigns(self, params: Dict, conversation: Dict) -> Dict:
        """
        Kampanya kontrolü - MCP'den gelen bilgiyi doğrudan kullan.
        """
        mcp_result = await self.call_mcp_tool("check_campaigns", params)
        
        if not mcp_result.get("success") or not mcp_result.get("campaigns"):
            mcp_result["marketing_message"] = "Şu an aktif bir kampanyamız bulunmuyor."
            return mcp_result
        
        campaigns = mcp_result["campaigns"]
        
        # MCP'den gelen bilgiyi kullanarak basit, doğru mesaj oluştur
        campaign_messages = []
        for c in campaigns:
            name = c.get('name', '')
            discount = c.get('discount', '')
            end_date = c.get('end_date', '')
            
            # Basit ve doğru mesaj
            if end_date:
                msg = f"{name} kampanyamız var. {end_date} tarihine kadar geçerli."
            else:
                msg = f"{name} kampanyamız var."
            campaign_messages.append(msg)
        
        marketing_message = " ".join(campaign_messages)
        mcp_result["marketing_message"] = marketing_message
        
        logging.info(f"[{self.name}] Kampanya mesajı: {marketing_message}")
        return mcp_result
    
    async def _personalize_offer(self, params: Dict, conversation: Dict) -> Dict:
        """Kişiye özel teklif oluştur (gelecek özellik)."""
        # Bu kısım gelecekte, müşterinin harcama alışkanlıklarına göre
        # dinamik indirimler veya paketler oluşturmak için kullanılabilir.
        return {"success": True, "message": "Kişiselleştirilmiş teklif özelliği gelecekte eklenecektir."}