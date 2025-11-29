import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Proje kök dizini
BASE_DIR = Path(__file__).resolve().parent

# .env dosyasını yükle
load_dotenv()

class Settings:
    """Uygulama ayarları"""
    
    # Uygulama Bilgileri
    APP_NAME: str = "Güzellik Merkezi Sesli Asistan"
    APP_VERSION: str = "2.0.0" # CMS entegrasyonu ile versiyon atladık
    DEBUG: bool = True
    
    # API Anahtarları
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "")
    
    # Directus CMS Ayarları (YENİ)
    DIRECTUS_URL: str = os.getenv("DIRECTUS_URL", "https://cms.demirtech.com")
    DIRECTUS_TOKEN: str = os.getenv("DIRECTUS_TOKEN", "")
    TENANT_ID: int = int(os.getenv("TENANT_ID", "1")) # Hangi şube/tenant için çalışıyorsa
    
    # Ses İşleme
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    MAX_AUDIO_DURATION: int = 60
    
    # SMS Ayarları
    SMS_ENABLED: bool = False
    SMS_API_KEY: Optional[str] = None
    SMS_SENDER: str = "GuzellikMerkezi"
    
    # Randevu Ayarları (Varsayılanlar - CMS'den de çekilebilir ama fallback olarak kalsın)
    BUSINESS_HOURS_START: int = 8
    BUSINESS_HOURS_END: int = 17
    APPOINTMENT_SLOT_MINUTES: int = 15
    REMINDER_HOURS_BEFORE: int = 24
    
    # Agent Ayarları
    MAX_CONVERSATION_TURNS: int = 20
    MAX_RETRY_ATTEMPTS: int = 3
    AGENT_TEMPERATURE: float = 0.7
    AGENT_MODEL: str = os.getenv("AGENT_MODEL", "gemini-2.0-flash")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")

    # MCP Sunucusu
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", 8000))
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

# Global settings instance
settings = Settings()

# NOT: SERVICE_DURATIONS, EXPERTS, CAMPAIGNS artık burada değil.
# Bu verilere ihtiyaç duyulduğunda Repository katmanı üzerinden Directus'tan çekilmeli
# ve performans için gerekirse önbelleğe (cache) alınmalıdır.

# Agent Sistem Prompt Şablonu
# DİKKAT: Bu artık bir şablondur. Kullanmadan önce API'den çekilen verilerle
# .format(experts_list=..., services_list=...) şeklinde doldurulmalıdır.
SYSTEM_PROMPT_TEMPLATE = """Sen {app_name} için çalışan profesyonel bir sesli asistansın.

## Görevin
Müşterilere randevu oluşturma, iptal etme, ve bilgi verme konularında yardımcı olmak.

## Yeteneklerin
1. Yeni randevu oluşturma
2. Mevcut randevuyu iptal etme
3. Müşteri tanıma (geçmiş randevular)
4. Çoklu hizmet randevusu planlama
5. Tamamlayıcı hizmet önerisi
6. Kişiye özel kampanya sunumu
7. Randevu hatırlatma

## Kurallar
- Her zaman nazik ve profesyonel ol
- Müşterinin adını kullan (öğrendikten sonra)
- Net ve anlaşılır konuş
- Randevu detaylarını teyit et
- Kampanyaları uygun zamanda sun
- 3 denemede anlaşılamazsa kibarca görüşmeyi sonlandır

## Uzmanlarımız
{experts_list}

## Hizmetlerimiz ve Süreleri
{services_list}

## Çalışma Saatleri
{start_hour}:00 - {end_hour}:00

Müşteriye her zaman en iyi deneyimi sunmaya çalış!
"""