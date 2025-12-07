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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import logging

# Logging konfigürasyonu
# Sadece konsola (terminal) yaz - app.log dosyasını kapat
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

from orchestrator import process_audio_input, process_text_input
from config import BASE_DIR # BASE_DIR'ı import et
from tts_service import get_tts_service

# FastAPI uygulamasını oluştur
app = FastAPI()

# Statik dosyaları (css, js) sunmak için
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# HTML template'ini oku (UTF-8 encoding ile)
with open(BASE_DIR / "templates/index.html", encoding="utf-8") as f:
    html_content = f.read()
logging.info(f"index.html içeriği yüklendi. Boyut: {len(html_content)} karakter.")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    """Ana arayüz sayfasını sunar."""
    logging.info("Kök dizin isteği alındı, index_new.html döndürülüyor.")
    return HTMLResponse(content=html_content)


@app.websocket("/api/ws/v1/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket iletişimini yönetir - OPTİMİZE EDİLMİŞ (Streaming destekli)"""
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

            if "bytes" in message:
                # Ses verisi geldi
                audio_data = message["bytes"]
                # WebSocket'i geç (streaming için)
                await process_audio_input(session_id, audio_data, websocket)
                # process_audio_input içinde zaten websocket.send_text yapılıyor (streaming)
            
            elif "text" in message:
                # Metin verisi geldi (JSON formatında)
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "text":
                        text_data = data.get("data", "")
                        # WebSocket'i geç (streaming için)
                        await process_text_input(session_id, text_data, websocket)
                        # process_text_input içinde zaten websocket.send_text yapılıyor (streaming)
                    else:
                        logging.warning(f"Bilinmeyen metin mesajı türü: {data}")
                except json.JSONDecodeError:
                    logging.error(f"Alınan metin mesajı JSON formatında değil: {message['text']}")
            elif message.get("type") == "websocket.disconnect":
                logging.info(f"WebSocket disconnect alındı: {session_id}")
                break

    except WebSocketDisconnect:
        logging.info(f"WebSocket bağlantısı kapandı: {session_id}")
        # TODO: Oturumla ilgili kaynakları temizle (örn: conversation_chats'ten sil)
    except Exception as e:
        logging.error(f"WebSocket hatası ({session_id}): {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Sunucu hatası")
        except:
            pass  # Zaten kapalıysa hata verme


# TTS API Endpoint
@app.post("/api/tts")
async def text_to_speech(text: str):
    """
    Metni Google TTS ile sese çevir
    
    Query params:
        text: Konuşulacak metin
        
    Returns:
        MP3 audio
    """
    try:
        tts = get_tts_service()
        audio_content = tts.text_to_speech(text)
        
        return Response(
            content=audio_content,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3"
            }
        )
    except Exception as e:
        logging.error(f"TTS API hatası: {e}")
        return Response(
            content=str(e),
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    logging.info("Web sunucusu http://localhost:8001 adresinde başlatılıyor...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
