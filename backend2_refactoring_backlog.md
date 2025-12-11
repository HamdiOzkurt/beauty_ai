# Güzellik Merkezi AI Asistanı - Agentic Refactoring Backlog'u

## 🎯 Projenin Amacı

Bu belgenin amacı, mevcut `backend` uygulamasını modernize ederek, LangChain ve LangGraph kütüphanelerini kullanan, daha sağlam, sürdürülebilir ve ölçeklenebilir yeni bir mimari oluşturmaktır. Tüm yeni kodlar, mevcut yapıya dokunulmadan `backend2` adlı yeni bir klasör içinde sıfırdan yazılacaktır.

---

## 🚀 Epic 1: Proje Kurulumu ve Yapılandırma

**Kullanıcı Hikayesi:** Geliştirici olarak, yeni `backend2` projesinin temel iskeletini ve bağımlılıklarını oluşturmak istiyorum, böylece geliştirmeye temiz bir başlangıç yapabilirim.

### Görevler:

1.  **Yeni Klasör Oluştur:** Proje ana dizininde `backend2` adında yeni bir klasör oluştur.
2.  **Bağımlılıkları Tanımla (`requirements.txt`):** `backend2` klasörü içine bir `requirements.txt` dosyası oluştur ve aşağıdaki temel kütüphaneleri ekle:
    ```
    fastapi
    uvicorn[standard]
    websockets
    sqlalchemy
    psycopg2-binary
    python-dotenv
    google-generativeai
    langchain
    langgraph
    langchain-google-genai
    pydantic
    ```
3.  **Yapılandırma Dosyası (`config.py`):** `backend2` içine bir `config.py` dosyası oluştur. Bu dosya, `.env` dosyasındaki ortam değişkenlerini (API anahtarları, veritabanı URL'si vb.) okumak için Pydantic `Settings` sınıfını içermelidir.
4.  **Veritabanı Kurulumu (`database.py`):** `backend2` içine bir `database.py` dosyası oluştur. SQLAlchemy `create_engine` ve `sessionmaker` kullanarak veritabanı bağlantı havuzunu ve oturum yönetimini yapılandır.

---

## 📚 Epic 2: Veritabanı Modelleri ve Veri Erişim Katmanı

**Kullanıcı Hikayesi:** Geliştirici olarak, uygulamanın veri yapılarını tanımlamak ve bu verilere erişmek için merkezi bir katman oluşturmak istiyorum.

### Görevler:

1.  **SQLAlchemy Modelleri (`models.py`):** `backend2` içine bir `models.py` dosyası oluştur. Mevcut `backend/models.py` dosyasındaki `Customer`, `Appointment` gibi SQLAlchemy sınıflarını buraya kopyala.
2.  **Repository Katmanı (`repository.py`):** `backend2` içine bir `repository.py` dosyası oluştur. Bu dosya, hem Directus CMS'ten veri çeken (hizmetler, uzmanlar, kampanyalar) hem de yerel PostgreSQL veritabanına yazan (randevu, müşteri kaydı) tüm fonksiyonları içerecektir. Bu katman, iş mantığının geri kalanından veri erişim detaylarını soyutlamalıdır. Mevcut `backend/repository.py`'deki mantık büyük ölçüde buraya taşınabilir.

---

## 🛠️ Epic 3: Araçların (Tools) Tanımlanması

**Kullanıcı Hikayesi:** Geliştirici olarak, agent'ın dış dünya ile etkileşime geçmek için kullanabileceği tüm yetenekleri (veritabanı işlemleri, müsaitlik kontrolü vb.) modüler ve yeniden kullanılabilir fonksiyonlar olarak tanımlamak istiyorum. **`mcp_server` ve `fastmcp` tamamen kaldırılacaktır.**

### Görevler:

1.  **Araçlar Paketi Oluştur:** `backend2/tools/` adında bir paket (içinde `__init__.py` olan bir klasör) oluştur.
2.  **Randevu Araçları (`tools/appointment_tools.py`):**
    - Bu dosyayı oluştur.
    - Mevcut `mcp_server.py`'deki `check_availability`, `create_appointment`, `cancel_appointment`, `suggest_alternative_times` fonksiyonlarının mantığını buraya taşı.
    - Her fonksiyonu `langchain_core.tools`'dan gelen `@tool` decorator'ı ile işaretle.
    - Fonksiyonların docstring'lerini, LLM'in aracın ne işe yaradığını ve hangi parametreleri aldığını anlaması için detaylı bir şekilde yaz.
    - Fonksiyonlar artık `mcp` üzerinden değil, doğrudan `repository.py`'deki fonksiyonları çağırarak çalışmalıdır.
3.  **Diğer Araçlar (`tools/customer_tools.py`, `tools/info_tools.py`):**
    - Benzer şekilde, `check_customer`, `get_customer_appointments`, `list_services`, `list_experts`, `check_campaigns` gibi diğer tüm araçları ilgili dosyalarda `@tool` decorator'ı ile tanımla.

**Örnek Araç Tanımı:**
```python
# backend2/tools/appointment_tools.py
from langchain_core.tools import tool
from typing import Optional

@tool
def check_availability(service_type: str, date: str, expert_name: Optional[str] = None) -> str:
    """
    Belirtilen hizmet ve tarih için uygun saat aralıklarını bulur.
    Sonucu JSON formatında bir string olarak döndürür.
    """
    # ... repository.py'yi kullanarak veritabanından müsaitliği kontrol et ...
    # return json.dumps({"status": "success", "slots": [...]})
```

---

## 🧠 Epic 4: LangGraph Agent Grafiğini Oluşturma

**Kullanıcı Hikayesi:** Geliştirici olarak, konuşma akışını, durum yönetimini ve araç kullanımını yöneten merkezi bir "beyin" oluşturmak için LangGraph kullanmak istiyorum.

### Görevler:

1.  **Grafik Dosyası (`graph.py`):** `backend2` içine `graph.py` adında bir dosya oluştur.
2.  **Durum (State) Tanımla:** Konuşma boyunca taşınacak tüm verileri içeren bir `AgentState` `TypedDict` sınıfı tanımla. Bu sınıf `input`, `chat_history`, `collected_info` (toplanan bilgiler), `agent_outcome` (araç sonuçları) gibi alanları içermelidir.
3.  **Düğümleri (Nodes) Tanımla:**
    - **`call_model` Node'u:** Kullanıcı girdisini ve mevcut durumu analiz ederek ya bir sonraki adımda hangi aracın çağrılacağına karar veren ya da doğrudan kullanıcıya bir yanıt verilmesi gerektiğini belirleyen bir LLM çağrısı yapar.
    - **`call_tool` Node'u:** `langgraph.prebuilt`'ten `ToolNode`'u kullanarak, `call_model` düğümünden gelen aracı çalıştırmakla sorumlu düğümü tanımla.
4.  **Kenarları (Edges) Tanımla:**
    - **`should_continue` Kenarı:** `call_model`'dan sonra bir araç mı çağrılmalı yoksa akış sonlanmalı mı diye karar veren koşullu kenarı (conditional edge) tanımla.
5.  **Grafiği Derle (`compile`):**
    - Bir `StatefulGraph` nesnesi oluştur.
    - Giriş noktasını (`entry_point`) ve düğümleri (`add_node`) tanımla.
    - Düğümler arasındaki akışı (`add_edge`, `add_conditional_edges`) belirle.
    - Grafiği `.compile()` metodu ile derleyerek kullanılabilir hale getir.

---

## 🌐 Epic 5: API Sunucusunu Oluşturma ve Entegrasyon

**Kullanıcı Hikayesi:** Geliştirici olarak, derlenmiş LangGraph agent'ını bir FastAPI WebSocket endpoint'i üzerinden dış dünyaya sunmak ve kullanıcılarla gerçek zamanlı iletişim kurmasını sağlamak istiyorum.

### Görevler:

1.  **Ana Sunucu Dosyası (`main.py`):** `backend2` içinde `main.py` dosyasını oluştur.
2.  **WebSocket Endpoint'i (`/api/ws/v2/chat`):**
    - Yeni bir WebSocket endpoint'i oluştur.
    - Her yeni bağlantı için `graph.py`'de derlenen agent grafiğini (`graph.astream(...)` veya `graph.ainvoke(...)`) çağır.
    - Konuşma geçmişinin her kullanıcıya özel olması için LangChain'in `configurable` özelliğini (`RunnableConfig`) kullanarak `session_id`'yi grafiğe geçir.
3.  **STT/TTS Entegrasyonu:** Mevcut `backend`'deki `stt_service_google.py` ve `tts_service.py` mantığını `main.py`'ye entegre et. Gelen sesleri metne çevirip grafa gönder ve grafdan gelen metin yanıtını sese çevirip kullanıcıya ilet.
4.  **Statik Dosyaları Sun:** `index.html` ve diğer `static` dosyaları sunmak için gerekli endpoint'leri ekle. Arayüzün yeni `/api/ws/v2/chat` endpoint'i ile konuşacak şekilde güncellenmesi gerektiğini unutma.
