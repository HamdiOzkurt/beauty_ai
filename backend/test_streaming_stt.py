# coding: utf-8
"""
Gerçek Zamanlı Streaming STT Test Script'i
Mikrofondan canlı ses alarak stt_service_gpu.py içindeki AudioProcessor'ı test eder.
"""

import pyaudio
import logging
import time

# Proje içindeki STT servisini import et
from stt_service_gpu import get_stt_service

# ==================================
# Logging Ayarları
# ==================================
# DEBUG seviyesi, VAD'ın her adımını görmek için faydalıdır.
# INFO seviyesi, sadece konuşma başlangıcı/bitişi ve sonuçları gösterir.
LOG_LEVEL = logging.INFO 
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==================================
# Mikrofon ve Ses Ayarlari
# ==================================
CHUNK_SIZE = 512           # Her seferinde okunacak ses parcasi boyutu (samples) - VAD icin 512 gerekli
FORMAT = pyaudio.paInt16   # 16-bit ses formati
CHANNELS = 1               # Mono
RATE = 16000               # 16kHz ornekleme hizi (Whisper ve VAD icin standart)

# AudioProcessor için VAD ayarları
# Bu değerlerle oynayarak gecikme/hassasiyet dengesini ayarlayabilirsiniz.
VAD_MIN_SILENCE_DURATION_MS = 400  # Konuşmanın bittiğini kabul etmek için gereken min sessizlik.
VAD_MIN_SPEECH_DURATION_MS = 150   # Geçerli bir konuşma olarak kabul edilecek min ses uzunluğu.
VAD_THRESHOLD = 0.4                # VAD'ın konuşma olarak algılama eşiği (0-1 arası).

def main():
    """Ana test fonksiyonu"""
    print("=" * 60)
    print("[MIC] Real-Time Streaming STT Testi")
    print("=" * 60)
    
    # 1. STT Servisini ve AudioProcessor'ı Başlat
    try:
        print("1. STT servisi yukleniyor (Bu islem model boyutuna gore zaman alabilir)...")
        stt_service = get_stt_service()
        audio_processor = stt_service.create_audio_processor(
            min_silence_duration_ms=VAD_MIN_SILENCE_DURATION_MS,
            min_speech_duration_ms=VAD_MIN_SPEECH_DURATION_MS,
            vad_threshold=VAD_THRESHOLD
        )
        print("[OK] STT servisi ve Audio Processor hazir.")
    except Exception as e:
        logging.error(f"[ERROR] Servis baslatilamadi: {e}")
        return

    # 2. Mikrofonu Baslat
    p = pyaudio.PyAudio()
    stream = None
    try:
        print("\n2. Mikrofon baslatiliyor...")
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )
        print("[OK] Mikrofon aktif. Simdi konusabilirsiniz...")
        print("   (Cikmak icin Ctrl+C)")

    except Exception as e:
        logging.error(f"[ERROR] Mikrofon baslatilamadi. Lutfen mikrofonunuzun bagli oldugunu emin olun. Hata: {e}")
        p.terminate()
        return

    # 3. Sürekli Ses Oku ve İşle
    try:
        while True:
            # Ses parçasını (chunk) mikrofondan oku
            chunk = stream.read(CHUNK_SIZE)
            
            # Ses parçasını AudioProcessor'a gönder
            result = audio_processor.process_chunk(chunk)
            
            # Eger bir transkript donduyse (konusma bittiyse), ekrana yazdir
            if result:
                print("\n" + "="*30)
                print(f"[SPEECH] Tespit Edilen Metin: {result}")
                print("="*30 + "\n")
                print("Dinlemeye devam ediyor...")

    except KeyboardInterrupt:
        print("\n\n[STOP] Test sonlandiriliyor...")
    except Exception as e:
        logging.error(f"Bir hata olustu: {e}")
    finally:
        # 4. Kaynaklari Temizle
        if stream:
            stream.stop_stream()
            stream.close()
        p.terminate()
        print("[OK] Kaynaklar temizlendi. Gorusmek uzere!")


if __name__ == "__main__":
    main()
