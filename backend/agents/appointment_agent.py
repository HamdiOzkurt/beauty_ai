import requests
from typing import Dict, Any
from agents.base_agent import BaseAgent
from config import settings
from datetime import datetime
import logging
import json

class AppointmentAgent(BaseAgent):
    """Randevu işlemlerinden sorumlu agent - MCP ile veri yönetimi."""
    
    def __init__(self):
        super().__init__(
            name="AppointmentAgent",
            model=settings.OLLAMA_MODEL,
            capabilities=[
                "create_appointment", 
                "cancel_appointment", 
                "check_availability",
                "suggest_alternative_times"
            ]
        )
    
    # <-- DEĞİŞİKLİK 1: Metodun imzası değişti, 'conversation' parametresi eklendi.
    async def execute(self, task: Dict[str, Any], conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Randevu görevini gerçekleştir."""
        # <-- DEĞİŞİKLİK 2: 'type' yerine 'task', 'params' yerine 'parameters' kullanılıyor.
        task_type = task.get("task") 
        params = task.get("parameters", {})
        
        logging.info(f"[{self.name}] Görev alındı: {task_type}")
        
        # <-- DEĞİŞİKLİK 3: İç metotlara 'conversation' parametresi de aktarılıyor.
        if task_type == "create_appointment":
            return await self._create_appointment(params, conversation)
        elif task_type == "cancel_appointment":
            return await self._cancel_appointment(params, conversation)
        elif task_type == "check_availability":
            return await self._check_availability(params, conversation)
        elif task_type == "suggest_alternative_times":
            return await self._suggest_alternatives(params, conversation)
        # YENİ EKLENEN KISIM: list_services ve list_experts görevlerini işle
        elif task_type == "list_services":
            logging.info(f"[{self.name}] Hizmet listesi için MCP aracı çağrılıyor.")
            return await self.call_mcp_tool("list_services", params)
        elif task_type == "list_experts":
            logging.info(f"[{self.name}] Uzman listesi için MCP aracı çağrılıyor.")
            # Eğer params veya conversation'da service_type varsa, filtreleme için geç
            service_type = params.get("service_type") or conversation.get("collected", {}).get("service")
            mcp_params = {"service_type": service_type} if service_type else {}
            return await self.call_mcp_tool("list_experts", mcp_params)
        
        return {"success": False, "error": f"Bilinmeyen görev tipi: {task_type}"}
    
    # <-- DEĞİŞİKLİK 4: Tüm iç metotların imzasına 'conversation' ekleniyor.
    async def _create_appointment(self, params: Dict, conversation: Dict) -> Dict:
        """
        Randevu oluşturma görevini doğrudan MCP aracına yönlendirir.
        """
        # YENİ EKLENEN GÜÇLENDİRME: Eğer Gemini telefon numarasını parametre olarak vermeyi unutursa,
        # biz bunu konuşma hafızasından (conversation) alıp ekleyebiliriz.
        # Bu, sistemi daha sağlam hale getirir.
        if 'customer_phone' not in params and conversation.get("user_info", {}).get("phone"):
            logging.info(f"[{self.name}] Parametrelerde telefon yok, hafızadan alınıyor.")
            params['customer_phone'] = conversation["user_info"]["phone"]

        logging.info(f"[{self.name}] Randevu oluşturma MCP aracına yönlendiriliyor. Parametreler: {params}")
        
        # Parametre adını MCP tool'un beklediği şekilde düzenle
        # Agent genelde 'date_time' gönderir ama MCP 'appointment_datetime' bekler
        appointment_dt = params.get('date_time') or params.get('appointment_datetime')
        
        mcp_params = {
            'customer_phone': params.get('customer_phone'),
            'service_type': params.get('service_type'),
            'appointment_datetime': appointment_dt,
            'customer_name': params.get('customer_name'),
            'expert_name': params.get('expert_name')
        }
        
        # None değerlerini temizle
        mcp_params = {k: v for k, v in mcp_params.items() if v is not None}
        
        try:
            mcp_result = await self.call_mcp_tool("create_appointment", mcp_params)
            
            if mcp_result.get("success"):
                self.add_to_memory(
                    f"Randevu oluşturma denemesi başarılı: {params.get('service_type')} - "
                    f"{params.get('date_time')}"
                )
            else:
                self.add_to_memory(f"Randevu oluşturma denemesi başarısız: {mcp_result.get('error')}")

            return mcp_result
                
        except Exception as e:
            logging.error(f"[{self.name}] Randevu oluşturma hatası: {e}", exc_info=True)
            return {
                "success": False, 
                "error": f"Randevu oluşturulurken bir istisna oluştu: {str(e)}"
            }
    
    async def _cancel_appointment(self, params: Dict, conversation: Dict) -> Dict:
        # ...
        # Bu fonksiyonun içinde de 'conversation' içindeki bilgilere erişebilirsiniz.
        # Örneğin, iptal edilecek randevu kodu hafızada varsa onu kullanabilirsiniz.
        if 'appointment_code' not in params and conversation.get("user_info", {}).get("appointment_code"):
            params['appointment_code'] = conversation['user_info']['appointment_code']
        
        # ... geri kalan kod aynı ...
        # ...
        mcp_result = await self.call_mcp_tool("cancel_appointment", params)
        return mcp_result
    
    async def _check_availability(self, params: Dict, conversation: Dict) -> Dict:
        """
        Müsaitlik kontrolü - MCP aracını çağırır.
        Sadece `check_availability` aracının beklediği parametreleri gönderir.
        """
        logging.info(f"[{self.name}] Müsaitlik kontrolü için MCP aracı çağrılıyor.")
        
        # 'date_time' yerine 'date' parametresini de kabul et
        date_param = params.get('date')
        datetime_param = params.get('date_time')

        if not date_param and not datetime_param:
             logging.warning(f"[{self.name}] Müsaitlik kontrolü için 'date' veya 'date_time' parametresi gerekli.")
             # Belki burada bir hata döndürmek daha iyi olabilir.
             # return {"success": False, "error": "Tarih parametresi eksik."}

        # Sadece izin verilen parametreleri filtrele
        allowed_params = ["service_type", "date_time", "date", "expert_name"]
        filtered_params = {k: v for k, v in params.items() if k in allowed_params}

        logging.info(f"[{self.name}] Filtrelenmiş parametreler: {filtered_params}")
        
        return await self.call_mcp_tool("check_availability", filtered_params)
    
    async def _suggest_alternatives(self, params: Dict, conversation: Dict) -> Dict:
        """
        Randevu dolu ise alternatif saatler öner.
        """
        # Evet, tam olarak burası da 'conversation' parametresini almalı.
        # Böylece müşterinin geçmiş tercihlerine göre öneri yapabilirsiniz.
        logging.info(f"[{self.name}] {conversation.get('user_info')} için alternatifler aranıyor.")
        # TODO: Implement logic
        return {"success": True, "message": "Alternatif zamanlar için geliştirme yapılacak."}