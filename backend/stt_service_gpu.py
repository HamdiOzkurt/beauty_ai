"""
GPU-Accelerated Speech-to-Text Service
Faster-Whisper ile CUDA destekli hızlı transkripsiyon
"""

# ⚠️ KRİTİK: CUDA/cuDNN ortamını hazırla - TÜM import'lardan ÖNCE!
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1) PATH ayarları
import cuda_setup

# 2) DLL'leri önceden yükle
import cudnn_preload

import warnings

# cuDNN / CUDA ile ilgili uyarıları kıs
warnings.filterwarnings("ignore", category=UserWarning)

# CUDA modüllerini lazy yükle (Whisper/Faster-Whisper önerisi)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")


# ==================================================
# KÜTÜPHANE İTHALATLARI (DLL yolları ayarlandıktan sonra)
# ==================================================
import time
import logging
import numpy as np
from faster_whisper import WhisperModel
import io
import wave

# ==========================================
# GPU HIZ OPTİMİZASYONU AYARLARI
# ==========================================

# FFmpeg yolu (Windows için sabit path)
FFMPEG_PATH = r"C:\Users\hamdi\Downloads\ffmpeg-8.0-full_build\ffmpeg-8.0-full_build\bin\ffmpeg.exe"

# Model Boyutu: 'tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3'
# Türkçe için en iyi: large-v3 (en ağır ama maksimum doğruluk)
MODEL_SIZE = "large-v3"

# Hesaplama Tipi: RTX serisi için "float16", eski kartlar için "int8"
# cuDNN hatası varsa "int8" kullan (yine de GPU hızlı çalışır)
COMPUTE_TYPE = "int8"  # Genel amaçlı compute tipi (bilgi amaçlı)

# Daha ince ayar için ayrı GPU/CPU compute tipleri
GPU_COMPUTE_TYPE = "float16"  # GPU'da daha doğal ve doğru sonuçlar
CPU_COMPUTE_TYPE = "int8"     # CPU fallback için hafif ve hızlı

# Cihaz: GPU için "cuda", CPU için "cpu"
DEVICE = "cuda"

class GPUWhisperSTT:
    """GPU hızlandırmalı Whisper STT servisi"""
    
    def __init__(self):
        """Faster-Whisper modelini GPU ile yükle"""
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Modeli yükle - önce kalite, sonra hız odaklı fallback ile."""

        # 1) Tercih: GPU + float16 (RTX 4050 için ideal)
        try:
            logging.info(f"🚀 Model yükleniyor: CUDA - {GPU_COMPUTE_TYPE} ({MODEL_SIZE})...")
            
            self.model = WhisperModel(
                MODEL_SIZE, 
                device="cuda", 
                compute_type=GPU_COMPUTE_TYPE,
                num_workers=2,
                cpu_threads=4,
                download_root=None
            )
            
            logging.info(f"✅ Model başarıyla yüklendi: CUDA ({MODEL_SIZE}/{GPU_COMPUTE_TYPE})")
            return
            
        except Exception as e:
            logging.warning(f"⚠️ CUDA/{GPU_COMPUTE_TYPE} yüklenemedi: {str(e)[:120]}")
            logging.info("🔄 CPU moduna geçiliyor...")
            
            try:
                self.model = WhisperModel(
                    MODEL_SIZE, 
                    device="cpu", 
                    compute_type=CPU_COMPUTE_TYPE,
                    num_workers=2,
                    download_root=None
                )
                logging.info(f"✅ Model başarıyla yüklendi: CPU ({MODEL_SIZE}/{CPU_COMPUTE_TYPE})")
                return
            except Exception as e2:
                raise RuntimeError(f"❌ Model yüklenemedi: {str(e2)}")
    
    def transcribe_audio_bytes(self, audio_bytes: bytes, language: str = "tr") -> tuple:
        """
        Ses verisini metne çevir (GPU hızlandırmalı)
        
        Args:
            audio_bytes: WebM/WAV/MP3 formatında ses verisi
            language: Dil kodu (varsayılan: "tr")
            
        Returns:
            tuple: (metin, işlem süresi)
        """
        if not self.model:
            raise RuntimeError("Whisper modeli yüklenmemiş!")
        
        start_time = time.time()
        
        try:
            # WebM → WAV dönüşümü (tarayıcıdan gelen ses kalitesini iyileştir)
            import tempfile
            import subprocess
            
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_input:
                temp_input.write(audio_bytes)
                temp_input_path = temp_input.name
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_output:
                temp_output_path = temp_output.name
            
            try:
                # FFmpeg ile yüksek kaliteli WAV'a çevir
                subprocess.run([
                    FFMPEG_PATH, "-y", "-i", temp_input_path,
                    "-ar", "16000",  # 16kHz sampling rate (Whisper için optimal)
                    "-ac", "1",       # Mono
                    "-c:a", "pcm_s16le",  # 16-bit PCM
                    temp_output_path
                ], check=True, capture_output=True)
                
                # Dönüştürülmüş WAV'ı oku
                with open(temp_output_path, "rb") as f:
                    audio_file = io.BytesIO(f.read())
            finally:
                # Geçici dosyaları temizle
                try:
                    os.unlink(temp_input_path)
                    os.unlink(temp_output_path)
                except:
                    pass
            
            # --- MAKSIMUM KALİTE TRANSKRİPSİYON (Türkçe optimizasyonu) ---
            segments, info = self.model.transcribe(
                audio_file,
                language=language,      # Türkçe sabit,

                beam_size=5,            # Beam search: en iyi 5 yolu tara
                best_of=5,              # Her segment için 5 deneme, en iyisini seç
                temperature=0.0,        # Deterministik çıktı
                patience=2.0,           # Daha sabırlı decode (kalite için)
                length_penalty=1.0,     # Uzun cümleleri penalize etme
                repetition_penalty=1.1, # Tekrar eden kelimeleri hafifçe engelleyip
                vad_filter=True,        # Sessiz kısımları atla
                vad_parameters=dict(
                    min_silence_duration_ms=700,  # Cümle sonunu daha iyi yakala
                    threshold=0.5,
                    min_speech_duration_ms=250
                ),
                condition_on_previous_text=True,  # Önceki bağlamı kullan (cümle tutarlılığı)
                initial_prompt="Merhaba, randevu almak istiyorum. Yarın için müsait misiniz?",  # Türkçe kontext
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4
            )
            
            # Segmentleri birleştir
            text = " ".join([segment.text.strip() for segment in segments])
            
            end_time = time.time()
            process_time = end_time - start_time
            
            # Detaylı log
            logging.info(f"🎤 STT: '{text[:50]}...' ({process_time:.2f}s - {info.language})")
            
            return text.strip(), process_time
            
        except Exception as e:
            logging.error(f"❌ Transkripsiyon hatası: {e}")
            raise
    
    def transcribe_audio_file(self, file_path: str, language: str = "tr") -> tuple:
        """
        Dosyadan ses çevir
        
        Args:
            file_path: Ses dosyası yolu
            language: Dil kodu
            
        Returns:
            tuple: (metin, işlem süresi)
        """
        start_time = time.time()
        
        try:
            segments, info = self.model.transcribe(
                file_path,
                language=language,
                beam_size=1,
                vad_filter=True,
                temperature=0.0,
                condition_on_previous_text=False
            )
            
            text = " ".join([segment.text.strip() for segment in segments])
            process_time = time.time() - start_time
            
            logging.info(f"🎤 STT (dosya): '{text[:50]}...' ({process_time:.2f}s)")
            
            return text.strip(), process_time
            
        except Exception as e:
            logging.error(f"❌ Dosya transkripsiyon hatası: {e}")
            raise


# Global STT instance (singleton pattern - lazy load)
_stt_service = None

def get_stt_service() -> GPUWhisperSTT:
    """STT service'i al (singleton)"""
    global _stt_service
    if _stt_service is None:
        _stt_service = GPUWhisperSTT()
    return _stt_service


# Test fonksiyonu
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🎤 GPU Whisper STT Servisi Test")
    print("=" * 60)
    
    stt = get_stt_service()
    
    print("\n✅ STT servisi hazır ve kullanıma açık!")
    print(f"   📊 Model Bilgileri:")
    print(f"   - Model: {MODEL_SIZE}")
    print(f"   - Cihaz: {DEVICE}")
    print(f"   - Compute: {COMPUTE_TYPE}")
    print("\n💡 Kullanım:")
    print("   from stt_service_gpu import get_stt_service")
    print("   stt = get_stt_service()")
    print("   text, duration = stt.transcribe_audio_bytes(audio_bytes)")
    print("\n🎙️  Mikrofon testi için: python test_gpu_stt.py")
    print("=" * 60)
