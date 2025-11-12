import logging
import whisper
import io
import numpy as np
import json
import os
import threading
import copy
import tempfile
import imageio_ffmpeg
import subprocess
from whisper.audio import N_SAMPLES

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
logging.info("Whisper modeli yükleniyor...")

# FFmpeg yolunu ayarla (imageio-ffmpeg kullanarak)
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
logging.info(f"FFmpeg bulundu: {ffmpeg_exe}")

# Whisper için özel load_audio fonksiyonu
def load_audio_custom(file: str, sr: int = 16000):
    """
    FFmpeg kullanarak ses dosyasını yükler ve numpy array'e çevirir.
    imageio-ffmpeg'den gelen ffmpeg binary'sini kullanır.
    """
    cmd = [
        ffmpeg_exe,  # Sabit kodlanmış "ffmpeg" yerine tam yol kullan
        "-nostdin",
        "-threads", "0",
        "-i", file,
        "-f", "s16le",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-ar", str(sr),
        "-"
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e
    
    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

# Whisper'ın load_audio fonksiyonunu override et
import whisper.audio
whisper.audio.load_audio = load_audio_custom

whisper_model = whisper.load_model("base")

# Konuşma durumunu modül seviyesinde ve dosya tabanlı olarak sakla
conversations = FileSessionStore('conversations.json')

# Orchestrator Agent'ı başlat
logging.info("Orchestrator Agent başlatılıyor...")
orchestrator_agent = OrchestratorAgent(conversations)

async def process_audio_input(session_id: str, audio_data: bytes) -> str:
    """Gelen ses verisini işler, metne çevirir ve yanıt üretir."""
    try:
        # Sesi Metne Çevir (Whisper)
        # Geçici dosya oluştur ve ses verisini yaz
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_audio:
            temp_audio.write(audio_data)
            temp_audio_path = temp_audio.name
        
        try:
            # Whisper direkt dosyadan okusun (her formatı destekler)
            # Türkçe dil desteği eklendi
            result = whisper_model.transcribe(temp_audio_path, language="tr")
            user_text = result["text"]
            logging.info(f"Kullanıcı dedi ki (sesten) ({session_id}): {user_text}")
        finally:
            # Geçici dosyayı sil
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)

        return await process_text_input(session_id, user_text)

    except Exception as e:
        logging.error(f"Ses işlenirken hata oluştu: {e}", exc_info=True)
        return "Üzgünüm, sesinizi işlerken bir sorun oluştu."

async def process_text_input(session_id: str, text_data: str) -> str:
    """Gelen metin verisini işler ve yanıt üretir."""
    try:
        logging.info(f"Kullanıcı dedi ki (metin) ({session_id}): {text_data}")
        response = await orchestrator_agent.process_request(session_id, text_data)
        logging.info(f"Asistan yanıtı ({session_id}): {response}")
        return response
    except Exception as e:
        logging.error(f"Metin işlenirken hata oluştu: {e}", exc_info=True)
        return "Üzgünüm, isteğinizi işlerken bir sorun oluştu."
