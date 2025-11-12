"""
Ana Web Sunucusu Dosyası

Bu dosya, FastAPI kullanarak web arayüzünü sunar ve 
WebSocket üzerinden istemci ile iletişim kurar.
"""

import sys
import os

# Projenin kök dizinini (backend) Python yoluna ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uuid
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import logging

# Logging konfigürasyonu
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)

from .orchestrator import process_audio_input, process_text_input
from .config import BASE_DIR # BASE_DIR'ı import et

# FastAPI uygulamasını oluştur
app = FastAPI()

# Statik dosyaları (css, js) sunmak için
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# HTML template'ini oku
with open(BASE_DIR / "templates/index.html") as f:
    html_content = f.read()
logging.info(f"index.html içeriği yüklendi. Boyut: {len(html_content)} karakter.")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    """Ana arayüz sayfasını sunar."""
    logging.info("Kök dizin isteği alındı, index.html döndürülüyor.")
    return HTMLResponse(content=html_content)


@app.websocket("/api/ws/v1/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket iletişimini yönetir."""
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logging.info(f"Yeni WebSocket bağlantısı kabul edildi: {session_id}")
    
    try:
        while True:
            # İstemciden genel bir mesaj bekle (metin veya byte olabilir)
            try:
                message = await websocket.receive()
            except RuntimeError:
                # Disconnect sonrası receive çağrısı hatası
                logging.info(f"WebSocket bağlantısı kapandı (disconnect sonrası receive): {session_id}")
                break
            response_text = ""

            if "bytes" in message:
                # Ses verisi geldi
                audio_data = message["bytes"]
                response_text = await process_audio_input(session_id, audio_data)
            
            elif "text" in message:
                # Metin verisi geldi (JSON formatında)
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "text":
                        text_data = data.get("data", "")
                        response_text = await process_text_input(session_id, text_data)
                    else:
                        logging.warning(f"Bilinmeyen metin mesajı türü: {data}")
                except json.JSONDecodeError:
                    logging.error(f"Alınan metin mesajı JSON formatında değil: {message['text']}")
            elif message.get("type") == "websocket.disconnect":
                logging.info(f"WebSocket disconnect alındı: {session_id}")
                break

            # Metin yanıtını istemciye geri gönder
            if response_text:
                await websocket.send_text(response_text)

    except WebSocketDisconnect:
        logging.info(f"WebSocket bağlantısı kapandı: {session_id}")
        # TODO: Oturumla ilgili kaynakları temizle (örn: conversation_chats'ten sil)
    except Exception as e:
        logging.error(f"WebSocket hatası ({session_id}): {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Sunucu hatası")
        except:
            pass  # Zaten kapalıysa hata verme


if __name__ == "__main__":
    import uvicorn
    logging.info("Web sunucusu http://localhost:8001 adresinde başlatılıyor...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
