import requests
import json
from typing import Dict, Any
from agents.base_agent import BaseAgent
from config import settings
import logging

class CustomerAgent(BaseAgent):
    """Müşteri ilişkilerinden sorumlu agent - MCP ile veri erişimi."""
    
    def __init__(self):
        super().__init__(
            name="CustomerAgent",
            model=settings.OLLAMA_MODEL,
            capabilities=[
                "check_customer", 
                "create_customer", 
                "get_customer_appointments",
                "analyze_customer",
                "get_customer_insights"
            ]
        )
    
    async def execute(self, task: Dict[str, Any], conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Müşteri görevini gerçekleştir."""
        task_type = task.get("task")
        params = task.get("parameters", {})
        
        logging.info(f"[{self.name}] Görev alındı: {task_type}")
        
        if task_type == "check_customer":
            return await self._check_customer(params, conversation)
        elif task_type == "create_customer":
            return await self._create_customer(params, conversation)
        elif task_type == "get_customer_appointments":
            return await self._get_customer_appointments(params, conversation)
        elif task_type == "analyze_customer":
            return await self._analyze_customer_behavior(params, conversation)
        elif task_type == "get_customer_insights":
            return await self._get_insights(params, conversation)
        
        return {"success": False, "error": "Bilinmeyen görev tipi"}
    
    async def _check_customer(self, params: Dict, conversation: Dict) -> Dict:
        """MCP'den müşteri bilgilerini getir - TIMEOUT korumalı."""
        
        # Telefon numarasını parametrelerden veya konuşma hafızasından al
        phone = params.get("phone") or conversation.get("user_info", {}).get("phone")
        if not phone:
            return {"success": False, "error": "Müşteri kontrolü için telefon numarası gerekli."}
        
        try:
            mcp_params = {"phone": phone}
            
            # TIMEOUT: 5 saniye içinde cevap gelmezse iptal et
            import asyncio
            mcp_result = await asyncio.wait_for(
                self.call_mcp_tool("check_customer", mcp_params),
                timeout=5.0
            )
            
            return mcp_result
        except asyncio.TimeoutError:
            logging.error(f"[{self.name}] Müşteri kontrolü timeout!")
            return {"success": False, "error": "Müşteri kontrolü zaman aşımına uğradı."}
        except Exception as e:
            logging.error(f"[{self.name}] Müşteri kontrolü hatası: {e}", exc_info=True)
            return {"success": False, "error": f"Müşteri kontrolü sırasında hata: {str(e)}"}
    
    async def _get_customer_appointments(self, params: Dict, conversation: Dict) -> Dict:
        """Müşterinin mevcut randevularını getir - TIMEOUT korumalı."""
        
        # Telefon numarasını parametrelerden veya konuşma hafızasından al
        phone = params.get("phone") or conversation.get("collected", {}).get("phone")
        if not phone:
            return {"success": False, "error": "Randevu sorgulamak için telefon numarası gerekli."}
        
        try:
            mcp_params = {"phone": phone}
            
            # TIMEOUT: 5 saniye içinde cevap gelmezse iptal et
            import asyncio
            mcp_result = await asyncio.wait_for(
                self.call_mcp_tool("get_customer_appointments", mcp_params),
                timeout=5.0
            )
            
            return mcp_result
            
        except asyncio.TimeoutError:
            logging.error(f"[{self.name}] Database timeout - müşteri sorgusu 5 saniyede tamamlanamadı")
            return {
                "success": False, 
                "error": "Sistemde geçici bir yavaşlık var, devam edebiliriz.",
                "timeout": True
            }
        except Exception as e:
            logging.error(f"[{self.name}] Randevu sorgulama hatası: {e}")
            return {"success": False, "error": str(e)}
    
    async def _create_customer(self, params: Dict, conversation: Dict) -> Dict:
        """Yeni müşteri oluştur - MCP tool."""
        
        # Parametreleri hem görevden (Gemini'den gelen) hem de konuşma hafızasından alarak sistemi sağlamlaştırıyoruz.
        full_name = params.get("full_name") or conversation.get("user_info", {}).get("full_name")
        phone = params.get("phone") or conversation.get("user_info", {}).get("phone")

        # Eğer hala eksik bilgi varsa, hata döndür. Bu, MCP'ye boş istek gitmesini engeller.
        if not full_name or not phone:
            error_msg = "Müşteri oluşturmak için isim ve telefon bilgisi eksik."
            logging.error(f"[{self.name}] {error_msg} | Gelen Parametreler: {params} | Hafıza: {conversation.get('user_info')}")
            return {"success": False, "error": error_msg}

        # İsim formatlaması - Boşluklara dikkat!
        # .title() her kelimenin ilk harfini büyük yapar ama boşlukları korur
        formatted_name = " ".join(word.strip().capitalize() for word in full_name.split() if word.strip())
        
        # MCP aracını çağırmak için son parametreleri oluştur
        mcp_params = {
            "full_name": formatted_name,
            "phone": phone
        }
        
        mcp_result = await self.call_mcp_tool("create_new_customer", mcp_params)
        
        if mcp_result.get("success"):
            self.add_to_memory(f"Yeni müşteri oluşturuldu: {formatted_name}")
        
        return mcp_result
    
    async def _analyze_customer_behavior(self, params: Dict, conversation: Dict) -> Dict:
        """Müşteri davranışını analiz et."""
        
        phone = params.get("phone") or conversation.get("user_info", {}).get("phone")
        if not phone:
            return {"success": False, "error": "Müşteri analizi için telefon numarası gerekli."}
        
        mcp_params = {"phone": phone}
        mcp_result = await self.call_mcp_tool("check_customer", mcp_params)
        
        if not mcp_result.get("success"):
            return mcp_result
        
        customer = mcp_result.get("customer", {})
        appointments = mcp_result.get("recent_appointments", [])
        
        analysis_prompt = f"""
Müşteri davranış analizi yap:

Müşteri: {customer.get('name', 'N/A')}
Toplam Randevu: {customer.get('total_appointments', 'N/A')}
İlk Randevu: {'Evet' if customer.get('is_first_appointment') else 'Hayır'}
Sadakat Puanı: {customer.get('loyalty_points', 'N/A')}

Son Randevular:
{chr(10).join([f"- {apt.get('date')}: {apt.get('service')} - {apt.get('status')}" for apt in appointments]) if appointments else 'Yok'}

Analiz et ve JSON formatında döndür:
{{
  "customer_type": "yeni/sadık/risk", 
  "behavior_pattern": "düzenli/düzensiz/tek_seferlik",
  "preferences": ["tercih1", "tercih2"],
  "recommendations": ["öneri1", "öneri2"],
  "risk_level": "düşük/orta/yüksek",
  "next_action": "önerilecek aksiyon"
}}
"""
        logging.debug(f"[{self.name}] Ollama Müşteri Davranış Analizi Prompt'u:\n{analysis_prompt}")
        try:
            payload = {
                "model": self.model, 
                "prompt": analysis_prompt, 
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
            analysis = json.loads(response.json()["response"])
            return {"success": True, "customer": customer, "analysis": analysis}
        except Exception as e:
            logging.error(f"[{self.name}] Müşteri davranış analizi hatası: {e}")
            return {"success": False, "error": f"Müşteri analizi sırasında bir hata oluştu: {e}"}

    async def _get_insights(self, params: Dict, conversation: Dict) -> Dict:
        """Müşteri için özel bilgiler oluştur."""
        # Bu metod, 'analyze_customer_behavior' metoduna benzer şekilde implemente edilebilir.
        return await self._analyze_customer_behavior(params, conversation)

