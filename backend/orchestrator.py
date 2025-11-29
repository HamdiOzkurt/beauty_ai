"""
Orchestrator - Ana İş Akışı Yöneticisi
GPU STT ile entegre
"""

import os
# ⚠️ KRİTİK: cuDNN bypass ve GPU ayarları - TÜM import'lardan ÖNCE!
os.environ['CUDA_MODULE_LOADING'] = 'LAZY'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# PyTorch'un cuDNN kütüphanelerini PATH'e ekle
import torch
torch_lib_path = os.path.join(os.path.dirname(torch.__file__), 'lib')

# Windows PATH'e ekle (CTranslate2 için)
if torch_lib_path not in os.environ.get('PATH', ''):
    os.environ['PATH'] = torch_lib_path + os.pathsep + os.environ.get('PATH', '')
    
# Ek olarak DLL directory'ye de ekle
try:
    os.add_dll_directory(torch_lib_path)
except (OSError, AttributeError):
    pass

import logging
import io
import numpy as np
import json
import threading
import copy
import tempfile

# --- YENİ: PROAKTİF GPU STT BAŞLATMA ---
# Diğer tüm uygulama import'larından ÖNCE STT servisini import edip başlatıyoruz.
# Bu, GPU'nun doğru kütüphaneler tarafından (PyTorch/faster-whisper) ilk olarak
# "rezerve edilmesini" sağlar ve cuDNN çakışmalarını önler.
logging.info("🚀 GPU STT servisi proaktif olarak başlatılıyor...")
from stt_service_gpu import get_stt_service
try:
    gpu_stt_service = get_stt_service()
    logging.info("✅ GPU STT servisi başarıyla başlatıldı ve hazır!")
except Exception as e:
    logging.critical(f"❌ FATAL: GPU STT servisi başlatılamadı! Uygulama durduruluyor. Hata: {e}", exc_info=True)
    # Eğer STT kritikse, burada uygulamayı durdurmak en sağlıklısıdır.
    # raise RuntimeError("GPU STT servisi başlatılamadığı için uygulama başlatılamadı.") from e
    gpu_stt_service = None # Veya hata durumunda None olarak ayarla

# --- BİTTİ: PROAKTİF GPU STT BAŞLATMA ---


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


def get_gpu_stt():
    """Önceden başlatılmış GPU STT servisini al (singleton)."""
    if gpu_stt_service is None:
        # Bu artık bir hata durumudur çünkü servisin başlangıçta yüklenmesi gerekir.
        logging.error("Hata: GPU STT servisi başlangıçta yüklenemediği için kullanılamıyor.")
        raise RuntimeError("GPU STT servisi mevcut değil veya başlangıçta başlatılamadı.")
    return gpu_stt_service

# Konuşma durumunu modül seviyesinde ve dosya tabanlı olarak sakla
conversations = FileSessionStore('conversations.json')

# Orchestrator Agent'ı başlat
logging.info("Orchestrator Agent başlatılıyor...")
orchestrator_agent = OrchestratorAgent(conversations)

async def process_audio_input(session_id: str, audio_data: bytes, websocket=None) -> str:
    """Gelen ses verisini işler, GPU ile metne çevirir ve yanıt üretir."""
    try:
        # Kullanıcıya ses alındığını göster
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "audio_received",
                "message": "🚀 GPU ile işleniyor..."
            }))

        # GPU STT ile metne çevir (ULTRA HIZLI)
        try:
            stt_service = get_gpu_stt() # Önceden yüklenmiş servisi al
            user_text, process_time = stt_service.transcribe_audio_bytes(audio_data, language="tr")

            logging.info(f"🎤 GPU STT: '{user_text}' ({process_time:.2f}s)")

            # Boş veya çok kısa transcript'leri reddet
            if not user_text or len(user_text) < 3:
                logging.warning(f"⚠️ Boş veya çok kısa ses kaydı: '{user_text}'")
                return ""

            logging.info(f"Kullanıcı dedi ki (GPU-STT) ({session_id}): {user_text}")

        except RuntimeError as e: # get_gpu_stt'den gelebilecek hatayı yakala
            logging.error(f"❌ GPU STT servisi kullanılamıyor: {e}")
            return "Üzgünüm, ses tanıma servisi şu an aktif değil."
        except Exception as e:
            logging.error(f"❌ GPU STT çevrim hatası: {e}", exc_info=True)
            return "Üzgünüm, sesinizi metne çevirirken bir hata oluştu."

        # WebSocket'e transkripti gönder
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "transcript",
                "text": user_text
            }))
            
            # Frontend render süresi: Kullanıcı mesajı ekranda görünsün, sonra AI cevap gelsin
            import asyncio
            await asyncio.sleep(0.15)  # 150ms - optimize edilmiş (300ms → 150ms)

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
