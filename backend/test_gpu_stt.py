"""
GPU STT Test - Mikrofon ile Canlı Test
"""

import os
# cuDNN bypass - import'lardan önce ayarla
os.environ['CUDA_MODULE_LOADING'] = 'LAZY'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import time
import logging
import speech_recognition as sr
from stt_service_gpu import get_stt_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    print("=" * 50)
    print("🎤 GPU-Accelerated STT Test")
    print("=" * 50)
    
    # STT servisini başlat
    try:
        stt = get_stt_service()
        print("\n✅ STT servisi hazır!\n")
    except Exception as e:
        print(f"❌ STT servisi başlatılamadı: {e}")
        return
    
    # Mikrofon recognizer
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 1000
    recognizer.dynamic_energy_threshold = False
    
    print("🎙️  Mikrofon dinleniyor...")
    print("   Konuşun ve susunca işlem başlayacak")
    print("   CTRL+C ile çıkış yapabilirsiniz\n")
    print("-" * 50)
    
    try:
        while True:
            try:
                with sr.Microphone() as source:
                    print("🎧 Dinleniyor...", end="\r")
                    
                    # Sesi dinle (max 10 saniye)
                    audio = recognizer.listen(source, phrase_time_limit=10)
                    
                    print("⚙️  GPU'da işleniyor...      ", end="\r")
                    
                    # WAV verisini al
                    audio_bytes = audio.get_wav_data()
                    
                    # GPU ile çevir
                    text, duration = stt.transcribe_audio_bytes(audio_bytes, language="tr")
                    
                    # Renklendirme (1.5 saniyeden hızlıysa yeşil)
                    if duration < 1.5:
                        color = "\033[92m"  # Yeşil
                        speed_icon = "⚡"
                    elif duration < 3.0:
                        color = "\033[93m"  # Sarı
                        speed_icon = "⚡"
                    else:
                        color = "\033[91m"  # Kırmızı
                        speed_icon = "🐢"
                    
                    reset = "\033[0m"
                    
                    if text:
                        print(f"\n{speed_icon} Metin: {text}")
                        print(f"   Süre : {color}{duration:.2f}s{reset}")
                        print("-" * 50)
                    else:
                        print("⚠️  Ses algılandı ama metin çıkarılamadı")
                        print("-" * 50)
                
            except sr.WaitTimeoutError:
                print("⏱️  Zaman aşımı - Tekrar deneyin")
            except Exception as e:
                print(f"❌ Hata: {e}")
                
    except KeyboardInterrupt:
        print("\n\n👋 Test sonlandırılıyor...")
        print("=" * 50)

if __name__ == "__main__":
    main()
