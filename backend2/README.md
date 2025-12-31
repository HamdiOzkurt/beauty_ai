# Beauty AI Backend v2

Modern, LangGraph tabanlı AI Asistan backend'i.

## 🎯 Özellikler

- **LangGraph + LangChain**: Modern agentic AI mimarisi
- **Google Gemini 2.0**: Güçlü dil modeli
- **Directus CMS**: Tüm veri yönetimi (NO local PostgreSQL)
- **WebSocket**: Gerçek zamanlı iletişim
- **STT**: Google Cloud Speech-to-Text
- **TTS**: ElevenLabs (eleven_multilingual_v2 - Türkçe destekli)

## 🏗️ Mimari

```
backend2/
├── config.py              # Pydantic Settings
├── database.py            # Directus connection
├── models.py              # Directus data classes (no ORM)
├── repository.py          # Directus data access layer
├── tools/                 # LangChain tools
│   ├── appointment_tools.py
│   ├── customer_tools.py
│   └── info_tools.py
├── graph.py               # LangGraph agent
└── main.py                # FastAPI server
```

## 🚀 Kurulum

### 1. Bağımlılıkları Yükle

```bash
cd backend2
pip install -r requirements.txt
```

### 2. Environment Variables

`.env` dosyası oluştur (`.env.example`'dan kopyala):

```bash
cp .env.example .env
```

Gerekli değerleri doldur:
- `GEMINI_API_KEY`: Google Gemini API key
- `DIRECTUS_URL`: Directus CMS URL
- `DIRECTUS_TOKEN`: Directus access token
- `GOOGLE_APPLICATION_CREDENTIALS`: Google Cloud service account JSON path (STT için)
- `ELEVENLABS_API_KEY`: ElevenLabs API key (TTS için)
- `ELEVENLABS_VOICE_ID`: (Opsiyonel) Ses ID'si (varsayılan: Rachel)
- `ELEVENLABS_MODEL`: (Opsiyonel) Model (varsayılan: eleven_multilingual_v2)

### 3. Directus Bağlantısını Test Et

```bash
python database.py
```

Bu komut Directus bağlantısını test eder ve gerekli collection'ları kontrol eder.

### 4. Sunucuyu Çalıştır

```bash
python main.py
```

veya uvicorn ile:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 📡 API Endpoints

### WebSocket

**URL:** `ws://localhost:8000/api/ws/v2/chat`

**İstemci → Sunucu:**
```json
{
  "type": "text" | "audio",
  "session_id": "unique-session-id",
  "data": "message" | "base64_audio",
  "sample_rate": 16000
}
```

**Sunucu → İstemci:**
```json
{
  "type": "text" | "audio" | "transcription" | "error" | "stream_end",
  "content": "response",
  "session_id": "session-id",
  "timestamp": "2024-01-01T00:00:00"
}
```

### REST API (Test için)

**POST /api/v2/chat**
```json
{
  "message": "Merhaba, randevu almak istiyorum",
  "session_id": "optional-session-id"
}
```

**GET /health**
- Sistem sağlık kontrolü

**GET /**
- Ana sayfa bilgileri

## 🛠️ Araçlar (Tools)

### Randevu Araçları
- `check_availability`: Müsaitlik kontrolü
- `create_appointment`: Randevu oluştur
- `cancel_appointment`: Randevu iptal et
- `suggest_alternative_times`: Alternatif saatler öner

### Müşteri Araçları
- `check_customer`: Müşteri bilgilerini sorgula
- `get_customer_appointments`: Müşteri randevularını listele
- `create_customer`: Yeni müşteri oluştur

### Bilgi Araçları
- `list_services`: Hizmetleri listele
- `list_experts`: Uzmanları listele
- `check_campaigns`: Kampanyaları sorgula

## 🧠 LangGraph Agent

Agent, şu akışı takip eder:

1. **Kullanıcı Mesajı** → `call_model` node
2. **LLM Kararı**:
   - Tool çağrısı gerekiyorsa → `tools` node → tekrar `call_model`
   - Yanıt veriyorsa → END
3. **State Yönetimi**:
   - `messages`: Konuşma geçmişi
   - `collected_info`: Toplanan bilgiler (telefon, isim, tarih, saat)
   - `context`: Kontekst bilgileri (müşteri adı, kampanyalar)

## 🔧 Geliştirme

### Debug Modu

`.env` dosyasında:
```env
DEBUG=True
LOG_LEVEL=DEBUG
```

### Test

```python
from graph import invoke_agent

response = invoke_agent(
    user_message="Merhaba",
    session_id="test-session"
)
print(response)
```

## 📊 Directus Collections

Kullanılan Directus collection'ları:
- `voises_customers`: Müşteri bilgileri
- `voises_appointments`: Randevu kayıtları
- `voises_services`: Hizmetler
- `voises_experts`: Uzmanlar
- `voises_campaigns`: Kampanyalar

**NOT**: Tüm veri Directus CMS'te saklanır, yerel PostgreSQL kullanılmaz.

## 🔐 Güvenlik

- API anahtarları `.env` dosyasında saklanır
- `.env` dosyası `.gitignore`'a eklenmelidir
- Production'da HTTPS kullanın
- CORS ayarlarını production'a göre güncelleyin

## 🚦 Production

1. `DEBUG=False` yap
2. `ALLOWED_ORIGINS` listesini kısıtla
3. Directus production ortamını güvenli yap
4. HTTPS sertifikası ekle
5. Rate limiting uygula
6. Monitoring ekle (Sentry, etc.)

## 📝 Lisans

Proprietary - Beauty AI Project

## 👥 Katkıda Bulunanlar

- Backend Development: AI Staff Engineer
- Architecture: LangGraph + LangChain
- Voice Services: Google Cloud STT + ElevenLabs TTS
