import logging
from faster_whisper import WhisperModel
import io
import numpy as np
import json
import os
import threading
import copy
import tempfile

from agents.orchestrator_agent import OrchestratorAgent
from config import settings

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
        with open(self._file_path, 'r') as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                logging.warning("Oturum dosyası okunamadı veya boş.")
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
            session_data = data.get(session_id)
            logging.info(f"Oturum verisi alınıyor '{session_id}': {session_data}")
            # Referans sorunlarını önlemek için derin bir kopya döndür
            return copy.deepcopy(session_data) if session_data else None

    def __setitem__(self, session_id, value):
        with self._lock:
            logging.info(f"Oturum verisi ayarlanıyor '{session_id}'")
            data = self._read_all()
            data[session_id] = value
            self._write_all(data)
# --- BİTTİ: Dosya tabanlı, thread-safe oturum yönetimi ---


# Modelleri ve istemcileri bir kere yükle
logging.info("Faster-Whisper modeli hazırlanıyor...")

# Faster-Whisper Model - MANUEL YÜKLEME (check_whisper_model.bat ile önce yükle!)
# Model zaten yüklü olmalı, burada sadece referans alıyoruz
whisper_model = None

def get_whisper_model():
    """Model cache'den yüklenir (manuel olarak önceden indirilmiş olmalı)"""
    global whisper_model
    if whisper_model is None:
        logging.info("🎤 Whisper modeli cache'den yükleniyor...")
        try:
            # Small model - CPU'da 3-4x daha hızlı, yeterli doğruluk
            whisper_model = WhisperModel(
                "small",  # medium → small (hız optimizasyonu)
                device="cpu",
                compute_type="int8",
                download_root=None,
                local_files_only=True
            )
            logging.info("✅ Faster-Whisper Small modeli yüklendi (INT8 - HIZ OPTİMİZE)")
        except Exception as e:
            logging.error(f"❌ Small model yüklenemedi, tiny deneniyor: {e}")
            try:
                # Fallback: tiny model (en hızlı)
                whisper_model = WhisperModel(
                    "tiny",
                    device="cpu",
                    compute_type="int8",
                    download_root=None,
                    local_files_only=True
                )
                logging.info("✅ Faster-Whisper Tiny modeli yüklendi (Fallback - ÇOK HIZLI)")
            except Exception as e2:
                logging.error(f"❌ Model yüklenemedi! download_whisper_medium.bat çalıştırın: {e2}")
                raise RuntimeError(
                    "Whisper modeli bulunamadı! "
                    "Lütfen 'download_whisper_medium.bat' ile modeli indirin."
                )
    return whisper_model

# Konuşma durumunu modül seviyesinde ve dosya tabanlı olarak sakla
conversations = FileSessionStore('conversations.json')

# Orchestrator Agent'ı başlat
logging.info("Orchestrator Agent başlatılıyor...")
orchestrator_agent = OrchestratorAgent(conversations)

async def process_audio_input(session_id: str, audio_data: bytes, websocket=None) -> str:
    """Gelen ses verisini işler, metne çevirir ve yanıt üretir."""
    try:
        # Kullanıcıya ses alındığını göster
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "audio_received",
                "message": "Ses işleniyor..."
            }))
        
        # Sesi Metne Çevir (Whisper Medium)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_audio:
            temp_audio.write(audio_data)
            temp_audio_path = temp_audio.name
        
        try:
            # Faster-Whisper Medium model
            model = get_whisper_model()
            
            # GÜÇLENDİRİLMİŞ Context Prompt - Model'e domain bilgisi ver
            context_prompt = """Güzellik salonu randevu sistemi.
Hizmetler: saç kesimi, saç boyama, manikür, pedikür, cilt bakımı, kaş dizaynı, makyaj, masaj, epilasyon, kirpik lifting.
Uzmanlar: Ayşe Demir, Zeynep Kaya, Elif Şahin, Ceyda Yılmaz, Fatma Can, Deniz Aksoy.
Örnek müşteriler: Ahmet Hamdi Özkurt, Ayşe Yılmaz, Mehmet Kaya.
Telefon formatı: 0555 123 45 67"""
            
            segments, info = model.transcribe(
                temp_audio_path,
                language="tr",
                beam_size=5,  # 10 → 5 (hız optimizasyonu, yeterli doğruluk)
                temperature=0.0,  # Deterministik (tutarlı)
                vad_filter=True,
                initial_prompt=context_prompt  # Domain bilgisi
            )
            
            # Segments'i birleştir
            user_text = " ".join([segment.text for segment in segments]).strip()
            
            logging.info(f"🎤 Algılanan dil: {info.language} (olasılık: {info.language_probability:.2%})")
            
            # Boş veya çok kısa transcript'leri reddet
            if not user_text or len(user_text) < 3:
                logging.warning(f"⚠️ Boş veya çok kısa ses kaydı, işlem yapılmıyor: '{user_text}'")
                return ""  # Boş yanıt döndür, işlem yapma
            
            logging.info(f"Kullanıcı dedi ki (sesten) ({session_id}): {user_text}")
            
        finally:
            # Geçici dosyayı sil
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)

        # WebSocket'e transkripti gönder
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "transcript",
                "text": user_text
            }))
            
            # KÜÇÜK GECİKME: Kullanıcı mesajının frontend'de render olması için bekle
            import asyncio
            await asyncio.sleep(0.3)  # 300ms - kullanıcı balonu göründükten sonra AI yanıtı gelsin
        
        return await process_text_input(session_id, user_text, websocket)

    except Exception as e:
        logging.error(f"Ses işlenirken hata oluştu: {e}", exc_info=True)
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
