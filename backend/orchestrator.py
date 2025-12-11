"""
Orchestrator - Ana İş Akışı Yöneticisi
Google Cloud STT ile entegre
"""

import logging
import io
import numpy as np
import json
import threading
import copy
import tempfile
import os

# --- YENİ: GOOGLE CLOUD STT BAŞLATMA ---
# Google Cloud Speech-to-Text servisini başlatıyoruz
logging.info("🚀 Google Cloud STT servisi başlatılıyor...")
from stt_service_google import get_stt_service
try:
    stt_service = get_stt_service()
    logging.info("✅ Google Cloud STT servisi başarıyla başlatıldı ve hazır!")
except Exception as e:
    logging.critical(f"❌ FATAL: Google Cloud STT servisi başlatılamadı! Hata: {e}", exc_info=True)
    stt_service = None

# --- BİTTİ: GOOGLE CLOUD STT BAŞLATMA ---


from agents.orchestrator_agent import OrchestratorAgent
from config import settings

# --- V4 FEATURE FLAG ---
# Environment variable ile OrchestratorV4'e geçiş kontrolü
USE_ORCHESTRATOR_V4 = os.getenv("USE_ORCHESTRATOR_V4", "false").lower() == "true"

if USE_ORCHESTRATOR_V4:
    logging.info("🚀 Using OrchestratorV4 (2 LLM Call Strategy)")
    from agents.orchestrator_v4 import OrchestratorV4
else:
    logging.info("📌 Using OrchestratorAgent V3 (Legacy)")
# --- END V4 FEATURE FLAG ---


# --- YENİ: Dosya tabanlı, thread-safe oturum yönetimi ---
class FileSessionStore:
    """
    Konuşma durumunu bir JSON dosyasında saklayan thread-safe bir sınıf.
    Bu, uygulama yeniden başlasa veya birden çok işlemde çalışsa bile durumun korunmasını sağlar.
    """
    def __init__(self, file_path):
        self._file_path = file_path
        self._lock = threading.Lock()
        logging.info(f"FileSessionStore başlatıldı: {self._file_path}")
        if not os.path.exists(self._file_path):
            with self._lock:
                # Dosya yoksa, kilit altında tekrar kontrol et ve oluştur
                if not os.path.exists(self._file_path):
                    logging.info(f"Oturum dosyası bulunamadı, oluşturuluyor: {self._file_path}")
                    with open(self._file_path, 'w') as f:
                        json.dump({}, f)

    def _read_all(self):
        try:
            with open(self._file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logging.warning("Oturum dosyası okunamadı veya boş. Boş bir sözlük döndürülüyor.")
            return {}

    def _write_all(self, data):
        with open(self._file_path, 'w') as f:
            json.dump(data, f, indent=2)
        logging.info(f"Oturum dosyası güncellendi. {len(data)} oturum var.")


    def __contains__(self, session_id):
        with self._lock:
            contains = session_id in self._read_all()
            logging.info(f"Oturum kontrol ediliyor: '{session_id}' var mı? {contains}")
            return contains

    def __getitem__(self, session_id):
        with self._lock:
            data = self._read_all()
            # get metodu None döndüreceği için deepcopy'den önce kontrol et
            session_data = data.get(session_id)
            logging.info(f"Oturum verisi alınıyor '{session_id}': {'Var' if session_data else 'Yok'}")
            return copy.deepcopy(session_data) if session_data is not None else None

    def get(self, session_id, default=None):
        """Dict-like get method"""
        with self._lock:
            data = self._read_all()
            session_data = data.get(session_id)
            logging.info(f"Oturum verisi alınıyor (get) '{session_id}': {'Var' if session_data else 'Yok'}")
            return copy.deepcopy(session_data) if session_data is not None else default

    def __setitem__(self, session_id, value):
        with self._lock:
            logging.info(f"Oturum verisi ayarlanıyor '{session_id}'")
            data = self._read_all()
            data[session_id] = value
            self._write_all(data)
# --- BİTTİ: Dosya tabanlı, thread-safe oturum yönetimi ---


def get_stt():
    """Önceden başlatılmış Google Cloud STT servisini al (singleton)."""
    if stt_service is None:
        logging.error("Hata: Google Cloud STT servisi başlangıçta yüklenemediği için kullanılamıyor.")
        raise RuntimeError("Google Cloud STT servisi mevcut değil veya başlangıçta başlatılamadı.")
    return stt_service

# Konuşma durumunu modül seviyesinde ve dosya tabanlı olarak sakla
conversations = FileSessionStore('conversations.json')

# Orchestrator Agent'ı başlat (V3 veya V4)
logging.info("Orchestrator Agent başlatılıyor...")
if USE_ORCHESTRATOR_V4:
    # V4: Dict yerine FileSessionStore wrap etmeliyiz
    # FileSessionStore dict-like interface sağlıyor, V4 dict bekliyor
    # Geçici çözüm: conversations dict'e dönüştür
    conversations_dict = {}
    orchestrator_agent = OrchestratorV4(conversations_dict)
    logging.info("✅ OrchestratorV4 başlatıldı (conversations in-memory)")
else:
    orchestrator_agent = OrchestratorAgent(conversations)
    logging.info("✅ OrchestratorAgent V3 başlatıldı")

async def process_audio_input(session_id: str, audio_data: bytes, websocket=None) -> str:
    """Gelen ses verisini işler, Google Cloud STT ile metne çevirir ve yanıt üretir."""
    try:
        # Kullanıcıya ses alındığını göster
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "audio_received",
                "message": "🚀 Google Cloud ile işleniyor..."
            }))

        # Google Cloud STT ile metne çevir
        try:
            stt = get_stt() # Önceden yüklenmiş servisi al
            user_text, confidence = stt.transcribe_audio_bytes(audio_data)  # Auto-detect format & sample rate

            logging.info(f"🎤 Google Cloud STT: '{user_text}' (güven: {confidence:.2%})")

            # Boş veya çok kısa transcript'leri reddet
            if not user_text or len(user_text) < 3:
                logging.warning(f"⚠️ Boş veya çok kısa ses kaydı: '{user_text}'")
                return ""

            logging.info(f"Kullanıcı dedi ki (Cloud-STT) ({session_id}): {user_text}")

        except RuntimeError as e: # get_stt'den gelebilecek hatayı yakala
            logging.error(f"❌ Google Cloud STT servisi kullanılamıyor: {e}")
            return "Üzgünüm, ses tanıma servisi şu an aktif değil."
        except Exception as e:
            logging.error(f"❌ Google Cloud STT çevrim hatası: {e}", exc_info=True)
            return "Üzgünüm, sesinizi metne çevirirken bir hata oluştu."

        # WebSocket'e transkripti gönder
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "transcript",
                "text": user_text
            }))
            
            # Frontend render süresi: Kullanıcı mesajı ekranda görünsün, sonra AI cevap gelsin
            import asyncio
            await asyncio.sleep(0.15)  # 150ms - optimize edilmiş

        return await process_text_input(session_id, user_text, websocket)

    except Exception as e:
        logging.error(f"Ses işlenirken genel hata oluştu: {e}", exc_info=True)
        return "Üzgünüm, sesinizi işlerken bir sorun oluştu."

async def process_text_input(session_id: str, text_data: str, websocket=None) -> str:
    """Gelen metin verisini işler ve yanıt üretir - OPTİMİZE EDİLMİŞ"""
    try:
        # Boş veya çok kısa metinleri reddet
        text_data = text_data.strip()
        if not text_data or len(text_data) < 2:
            logging.warning(f"⚠️ Boş veya çok kısa metin, işlem yapılmıyor: '{text_data}'")
            return ""  # Boş yanıt döndür

        logging.info(f"Kullanıcı dedi ki (metin) ({session_id}): {text_data}")
        # WebSocket parametresini orchestrator'a geçir (streaming için)
        response = await orchestrator_agent.process_request(session_id, text_data, websocket)
        logging.info(f"Asistan yanıtı ({session_id}): {response}")
        return response
    except Exception as e:
        logging.error(f"Metin işlenirken hata oluştu: {e}", exc_info=True)
        return "Üzgünüm, isteğinizi işlerken bir sorun oluştu."
