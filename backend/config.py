import os
from pathlib import Path
from typing import Optional, Dict, List
from dotenv import load_dotenv

# Proje kök dizini
BASE_DIR = Path(__file__).resolve().parent

# .env dosyasını yükle
load_dotenv()


class Settings:
    """Uygulama ayarları"""
    
    # Uygulama Bilgileri
    APP_NAME: str = "Güzellik Merkezi Sesli Asistan"
    APP_VERSION: str = "1.1.0"
    DEBUG: bool = True
    
    # API Anahtarları
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "")
    
    # Veritabanı (PostgreSQL - Docker)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/db_name")
    
    # Ses İşleme
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    MAX_AUDIO_DURATION: int = 60
    
    # SMS Ayarları
    SMS_ENABLED: bool = False
    SMS_API_KEY: Optional[str] = None
    SMS_SENDER: str = "GuzellikMerkezi"
    
    # Randevu Ayarları
    BUSINESS_HOURS_START: int = 8
    BUSINESS_HOURS_END: int = 17
    APPOINTMENT_SLOT_MINUTES: int = 15
    REMINDER_HOURS_BEFORE: int = 24
    
    # Agent Ayarları
    MAX_CONVERSATION_TURNS: int = 20
    MAX_RETRY_ATTEMPTS: int = 3
    AGENT_TEMPERATURE: float = 0.7
    AGENT_MODEL: str = os.getenv("AGENT_MODEL", "gemini-2.5-flash")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")

    # MCP Sunucusu
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", 8000))
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    # ===== BU KISMI EKLEDİK =====
    # Hizmet Tipleri ve Süreleri (dakika)
    SERVICE_DURATIONS: Dict[str, int] = {
        "saç_kesimi": 60,
        "saç_boyama": 120,
        "manikür": 45,
        "pedikür": 60,
        "cilt_bakımı": 90,
        "kaş_dizaynı": 30,
        "makyaj": 60,
        "masaj": 90,
        "epilasyon": 60,
        "kirpik_lifting": 45,
    }

    # Uzmanlar ve Uzmanlık Alanları
    EXPERTS: Dict[str, Dict] = {
        "ceyda": {
            "full_name": "Ceyda Yılmaz",
            "specialties": ["manikür", "pedikür", "kaş_dizaynı"],
            "title": "Tırnak Uzmanı"
        },
        "ayşe": {
            "full_name": "Ayşe Demir",
            "specialties": ["saç_kesimi", "saç_boyama", "makyaj"],
            "title": "Kuaför"
        },
        "zeynep": {
            "full_name": "Zeynep Kaya",
            "specialties": ["cilt_bakımı", "masaj", "epilasyon"],
            "title": "Estetisyen"
        },
        "elif": {
            "full_name": "Elif Şahin",
            "specialties": ["makyaj", "kirpik_lifting", "saç_kesimi"],
            "title": "Makyaj Uzmanı"
        },
        "fatma": {
            "full_name": "Fatma Can",
            "specialties": ["saç_kesimi", "saç_boyama"],
            "title": "Kuaför Asistanı"
        },
        "deniz": {
            "full_name": "Deniz Aksoy",
            "specialties": ["manikür", "pedikür"],
            "title": "Tırnak Teknisyeni"
        }
    }

    # Kampanya ve Promosyonlar
    CAMPAIGNS: Dict[str, Dict] = {
        "yeni_müşteri": {
            "name": "Yeni Müşteri İndirimi",
            "discount": 20,
            "description": "İlk randevunuzda %20 indirim!",
            "conditions": {"first_appointment": True}
        },
        "kombo_paket": {
            "name": "Kombo Paket",
            "discount": 15,
            "description": "2 veya daha fazla hizmet alana %15 indirim!",
            "conditions": {"min_services": 2}
        },
        "sadakat": {
            "name": "Sadakat İndirimi",
            "discount": 10,
            "description": "5. randevunuzda %10 indirim!",
            "conditions": {"appointment_count": 5}
        }
    }

    # Tamamlayıcı Hizmet Önerileri
    COMPLEMENTARY_SERVICES: Dict[str, List[str]] = {
        "manikür": ["pedikür", "kaş_dizaynı"],
        "saç_kesimi": ["saç_boyama", "makyaj"],
        "cilt_bakımı": ["masaj", "makyaj"],
        "pedikür": ["manikür"],
        "kaş_dizaynı": ["kirpik_lifting", "makyaj"],
    }


# Global settings instance
settings = Settings()

# Geriye dönük uyumluluk için global değişkenleri koruyun (opsiyonel)
SERVICE_DURATIONS = settings.SERVICE_DURATIONS
EXPERTS = settings.EXPERTS
AVAILABLE_EXPERTS = [expert["full_name"] for expert in EXPERTS.values()]
CAMPAIGNS = settings.CAMPAIGNS
COMPLEMENTARY_SERVICES = settings.COMPLEMENTARY_SERVICES

# Agent Sistem Promptu
SYSTEM_PROMPT = f"""Sen {settings.APP_NAME} için çalışan profesyonel bir sesli asistansın.

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
{chr(10).join([f"- {e['full_name']} ({e['title']}): {', '.join(e['specialties'])}" for e in EXPERTS.values()])}

## Hizmetlerimiz ve Süreleri
{chr(10).join([f"- {k.replace('_', ' ').title()}: {v} dakika" for k, v in SERVICE_DURATIONS.items()])}

## Çalışma Saatleri
{settings.BUSINESS_HOURS_START}:00 - {settings.BUSINESS_HOURS_END}:00

Müşteriye her zaman en iyi deneyimi sunmaya çalış!
"""