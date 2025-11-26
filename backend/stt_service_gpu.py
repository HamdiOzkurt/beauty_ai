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
import torch

# ==========================================
# GPU HIZ OPTİMİZASYONU AYARLARI
# ==========================================

# FFmpeg yolu (Windows için sabit path)
FFMPEG_PATH = r"C:\Users\hamdi\Downloads\ffmpeg-8.0-full_build\ffmpeg-8.0-full_build\bin\ffmpeg.exe"

# Model Boyutu: 'tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3'
# Türkçe için en iyi: large-v3 (en ağır ama maksimum doğruluk)
MODEL_SIZE = "small"

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
        """Faster-Whisper ve VAD modellerini GPU ile yükle"""
        self.model = None
        self.vad_model = None
        self.vad_utils = None
        
        self._load_model()
        self._load_vad_model()
    
    def _load_vad_model(self):
        """Silero VAD modelini yükle."""
        try:
            logging.info("🔊 VAD modeli yükleniyor (silero-vad)...")
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False  # ONNX sürümü CPU'da daha iyi, biz PyTorch istiyoruz
            )
            self.vad_model = model
            self.vad_utils = utils
            logging.info("✅ VAD modeli başarıyla yüklendi.")
        except Exception as e:
            logging.error(f"❌ VAD modeli yüklenemedi: {e}")
            # VAD olmadan devam edilebilir ama streaming çalışmaz.
            # Şimdilik hata verip durdurmak yerine sadece uyarıyoruz.
            self.vad_model = None
            self.vad_utils = None
            
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
            logging.warning(f"[WARN] CUDA/{GPU_COMPUTE_TYPE} yuklenemedi: {str(e)[:120]}")
            logging.info("[INFO] CPU moduna geciliyor...")
            
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
                language=language,      # Türkçe sabit
                beam_size=2,            # Beam search: en iyi 5 yolu tara
                best_of=3,              # Her segment için 5 deneme, en iyisini seç
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

    def transcribe_tensor(self, audio_tensor, language: str = "tr") -> tuple:
        """
        Bir ses tensörünü (veya numpy dizisini) doğrudan transkribe eder.
        Streaming için optimize edilmiştir, FFmpeg dönüşümü yapmaz.
        """
        if not self.model:
            raise RuntimeError("Whisper modeli yüklenmemiş!")

        start_time = time.time()
        
        try:
            # --- STREAMING İÇİN OPTİMİZE EDİLMİŞ TRANSKRİPSİYON ---
            # VAD filtresi burada harici olarak yapıldığı için kapatılabilir.
            # Ancak yine de içerideki VAD'nin küçük sessizlikleri temizlemesi faydalı olabilir.
            segments, info = self.model.transcribe(
                audio_tensor,
                language=language,
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=True,
                initial_prompt="Merhaba, randevu almak istiyorum. Yarın için müsait misiniz?",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=100) # İç VAD için daha agresif ayar
            )
            
            text = " ".join([segment.text.strip() for segment in segments])
            process_time = time.time() - start_time
            
            logging.info(f"🎤 STT (Stream): '{text[:50]}...' ({process_time:.2f}s - {info.language})")
            
            return text.strip(), process_time

        except Exception as e:
            logging.error(f"❌ Tensor transkripsiyon hatası: {e}")
            raise

    def create_audio_processor(self, **kwargs):
        """Streaming için bir AudioProcessor nesnesi oluşturur."""
        if not self.vad_model:
            raise RuntimeError("VAD modeli yüklenemediği için streaming processor oluşturulamıyor.")
        return AudioProcessor(stt_service=self, **kwargs)


class AudioProcessor:
    """
    Gerçek zamanlı ses akışını işler, VAD kullanarak konuşmayı algılar,
    biriktirir ve transkripsiyon için GPUWhisperSTT'ye gönderir.
    """
    def __init__(self, stt_service: GPUWhisperSTT, 
                 vad_threshold: float = 0.5, 
                 min_silence_duration_ms: int = 300, # Daha hassas ayar
                 min_speech_duration_ms: int = 100, # Kısa sesleri de yakala
                 sampling_rate: int = 16000):
        
        self.stt_service = stt_service
        self.vad_threshold = vad_threshold
        self.min_silence_duration_ms = min_silence_duration_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.sampling_rate = sampling_rate

        self._reset_stream()

    def _reset_stream(self):
        """Akış durumunu ve buffer'ı sıfırla."""
        logging.debug("[RESET] Akis sifirlaniyor...")
        self.audio_buffer = []
        self.speaking = False
        self.silence_frames = 0
        self.speech_frames = 0

    def process_chunk(self, chunk: bytes):
        """
        Gelen ses parçasını (chunk) işle.
        Konuşma algılarsa buffer'a ekler.
        Sessizlik algılarsa ve buffer doluysa transkripsiyonu tetikler.
        """
        # Gelen chunk'ı PyTorch tensor'a çevir
        # Silero VAD 1D tensor bekler
        audio_float32 = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float32)

        if audio_tensor.numel() == 0:
            return None # Boş chunk'ı atla

        # VAD ile konuşma olasılığını hesapla
        speech_prob = self.stt_service.vad_model(audio_tensor, self.sampling_rate).item()

        chunk_duration_ms = (len(chunk) / 2) / self.sampling_rate * 1000

        if speech_prob > self.vad_threshold:
            # Konuşma algılandı
            self.silence_frames = 0
            if not self.speaking:
                logging.info("▶️ Konuşma başladı.")
                self.speaking = True
            
            self.speech_frames += 1
            self.audio_buffer.append(audio_tensor)
            return None # Henüz transkript yok
        else:
            # Sessizlik algılandı
            if self.speaking:
                self.silence_frames += 1
                total_silence_ms = self.silence_frames * chunk_duration_ms

                if total_silence_ms >= self.min_silence_duration_ms:
                    logging.info(f"⏹️ Konuşma bitti ({total_silence_ms:.0f}ms sessizlik). Transkripsiyon tetikleniyor.")
                    
                    full_audio = torch.cat(self.audio_buffer)
                    
                    # Konuşma çok kısaysa (gürültü olabilir), işlemi atla
                    total_speech_ms = self.speech_frames * chunk_duration_ms
                    if total_speech_ms < self.min_speech_duration_ms:
                        logging.info(f"⏭️  Konuşma çok kısa ({total_speech_ms:.0f}ms), gürültü olarak kabul edildi ve atlandı.")
                        self._reset_stream()
                        return None

                    # Buffer'daki sesi birleştir ve transkribe et
                    try:
                        transcript, _ = self.stt_service.transcribe_tensor(full_audio.numpy())
                        self._reset_stream()
                        return transcript
                    except Exception as e:
                        logging.error(f"STREAMING TRANSCRIBE ERROR: {e}")
                        self._reset_stream()
                        return None
            
            return None # Sessizlik devam ediyor veya konuşma hiç başlamadı


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
