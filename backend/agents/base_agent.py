from abc import ABC, abstractmethod
from typing import Dict, Any, List
from fastmcp import Client
import logging
import json
from config import settings

class BaseAgent(ABC):
    """Tüm agent'ların base sınıfı - MCP desteği ile."""
    
    def __init__(self, name: str, model: str, capabilities: List[str]):
        self.name = name
        self.model = model
        self.capabilities = capabilities
        self.memory = []
        # FastMCP SSE endpoint
        self.mcp_url = f"http://{settings.MCP_SERVER_HOST}:{settings.MCP_SERVER_PORT}/mcp/sse"
    
    # <-- DEĞİŞİKLİK 1: Metodun imzasına 'conversation' parametresi eklendi.
    # Bu, tüm alt agent sınıflarının bu yeni yapıyı uygulamasını zorunlu kılar.
    @abstractmethod
    async def execute(self, task: Dict[str, Any], conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Agent'ın ana görevi."""
        pass
    
    async def call_mcp_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """MCP Server'daki bir aracı çağırır ve sonucu JSON uyumlu bir sözlük olarak döner."""
        logging.info(f"[{self.name}] --> MCP Tool Çağrılıyor: {tool_name}")
        logging.debug(f"[{self.name}]     Parametreler: {json.dumps(params, indent=2, ensure_ascii=False)}")
        try:
            async with Client(self.mcp_url) as mcp_client:
                result_obj = await mcp_client.call_tool(tool_name, params)
                
                logging.info(f"[{self.name}] <-- MCP Tool Sonucu: {tool_name}")
                
                if hasattr(result_obj, 'content') and result_obj.content:
                    first_content = result_obj.content[0]
                    if hasattr(first_content, 'text'):
                        raw_text = first_content.text
                        logging.debug(f"[{self.name}]     Ham Metin: {raw_text}")
                        try:
                            # ÖNEMLİ: MCP'den gelen sonuç bir string içinde JSON olabilir.
                            # Başarılı bir arama sonucu bile string olarak dönebilir.
                            mcp_response = json.loads(raw_text)
                            # Bazen fastmcp, hatayı text içinde döndürür.
                            # Bu durumu yakalayıp standart bir formata çevirelim.
                            if isinstance(mcp_response, dict) and mcp_response.get("isError"):
                                error_text = mcp_response.get('content', [{}])[0].get('text', 'Bilinmeyen MCP hatası')
                                logging.error(f"[{self.name}] MCP aracı hata döndürdü: {error_text}")
                                raise Exception(error_text)
                            return mcp_response

                        except json.JSONDecodeError:
                            # Eğer JSON değilse, düz metin olarak kabul et ve bir yapıya oturt.
                            return {"success": True, "message": raw_text}
                
                if hasattr(result_obj, 'structured_content') and result_obj.structured_content:
                    logging.debug(f"[{self.name}]     Yapılandırılmış: {json.dumps(result_obj.structured_content, indent=2, ensure_ascii=False)}")
                    return result_obj.structured_content
                
                logging.warning(f"[{self.name}] Beklenmeyen yanıt formatı veya boş yanıt.")
                # Başarılı ama içerik döndürmeyen durumlar için varsayılan başarılı yanıtı dön.
                return {"success": True, "message": "İşlem başarıyla tamamlandı ancak içerik dönmedi."}

        except Exception as e:
            # Hata mesajını daha temiz hale getirelim. fastmcp.exceptions.ToolError'dan gelen mesajı alalım.
            error_message = str(e)
            logging.error(f"[{self.name}] MCP Tool hatası ({tool_name}): {error_message}", exc_info=True)
            return {"success": False, "error": f"MCP araç çağrısı başarısız: {error_message}"}
    
    def can_handle(self, task: Dict[str, Any]) -> bool:
        """Bu agent bu görevi yapabilir mi?"""
        # <-- DEĞİŞİKLİK 2: Görev tipini 'type' yerine 'task' anahtarından okuyoruz.
        task_type = task.get("task")
        return task_type in self.capabilities
    
    def add_to_memory(self, item: str):
        """Hafızaya ekle."""
        self.memory.append(item)
        if len(self.memory) > 10:
            self.memory.pop(0)
    
    def get_context(self) -> str:
        """Agent'ın mevcut context'ini döndür."""
        if not self.memory:
            return "Henüz hafızamda bir şey yok."
        return "\n".join([f"- {item}" for item in self.memory[-3:]])