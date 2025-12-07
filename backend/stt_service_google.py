"""
Google Cloud Speech-to-Text Service
Bulut tabanlı, yüksek doğruluklu Türkçe ses tanıma
"""

import logging
import io
from google.cloud import speech
from config import settings

class GoogleSTTService:
    """Google Cloud Speech-to-Text servisi"""
    
    def __init__(self):
        """Speech-to-Text client'ı başlat"""
        try:
            self.client = speech.SpeechClient()
            
            # Türkçe için optimize edilmiş config
            self.config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code="tr-TR",
                # Model seçimi: command_and_search = kısa komutlar için optimize
                # default = genel amaçlı
                # phone_call = telefon görüşmeleri için (bizim case'imiz)
                model="phone_call",
                # Alternatif transkriptler için (en iyi 3 sonucu al)
                max_alternatives=1,
                # Noktalama işaretleri ekle
                enable_automatic_punctuation=True,
                # Profanity filtreleme (isteğe bağlı)
                profanity_filter=False,
                # Konuşmacı diarizasyonu (kim konuşuyor) - isteğe bağlı
                enable_speaker_diarization=False,
                # Kelime zaman damgaları
                enable_word_time_offsets=False,
            )
            
            logging.info("✅ Google Cloud Speech-to-Text başlatıldı (Türkçe/phone_call modeli)")
            
        except Exception as e:
            logging.error(f"❌ Google STT başlatılamadı: {e}")
            raise
    
    def transcribe_audio_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> tuple[str, float]:
        """
        Ses dosyasını metne çevir (synchronous - kısa sesler için)
        
        Args:
            audio_bytes: WAV formatında ses verisi (PCM 16-bit)
            sample_rate: Örnekleme hızı (Hz)
            
        Returns:
            (metin, güven_skoru) tuple
        """
        try:
            # Sample rate'i güncelle
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=sample_rate,
                language_code="tr-TR",
                model="phone_call",
                max_alternatives=1,
                enable_automatic_punctuation=True,
            )
            
            audio = speech.RecognitionAudio(content=audio_bytes)
            
            # Synchronous tanıma (1 dakikaya kadar)
            response = self.client.recognize(config=config, audio=audio)
            
            # Sonuçları işle
            if not response.results:
                logging.warning("⚠️ STT: Sonuç bulunamadı (sessizlik veya tanınmayan ses)")
                return "", 0.0
            
            # En iyi sonucu al
            result = response.results[0]
            if not result.alternatives:
                return "", 0.0
                
            alternative = result.alternatives[0]
            transcript = alternative.transcript.strip()
            confidence = alternative.confidence
            
            logging.info(f"🎤 STT: '{transcript}' (güven: {confidence:.2%})")
            return transcript, confidence
            
        except Exception as e:
            logging.error(f"❌ Google STT transkripsiyon hatası: {e}")
            return "", 0.0
    
    def transcribe_stream(self, audio_generator):
        """
        Streaming ses tanıma (gerçek zamanlı, uzun sesler için)
        
        Args:
            audio_generator: Ses chunk'larını üreten generator
            
        Yields:
            Transkript sonuçları
        """
        try:
            # Streaming config
            streaming_config = speech.StreamingRecognitionConfig(
                config=self.config,
                interim_results=True,  # Ara sonuçlar da gelsin
            )
            
            # Ses stream'ini oluştur
            requests = (
                speech.StreamingRecognizeRequest(audio_content=chunk)
                for chunk in audio_generator
            )
            
            # Streaming tanıma başlat
            responses = self.client.streaming_recognize(
                config=streaming_config,
                requests=requests
            )
            
            # Sonuçları işle
            for response in responses:
                if not response.results:
                    continue
                
                # En son sonucu al
                result = response.results[0]
                if not result.alternatives:
                    continue
                
                alternative = result.alternatives[0]
                transcript = alternative.transcript
                is_final = result.is_final
                
                if is_final:
                    logging.info(f"🎤 STT (final): '{transcript}'")
                else:
                    logging.debug(f"🎤 STT (interim): '{transcript}'")
                
                yield {
                    'transcript': transcript,
                    'is_final': is_final,
                    'confidence': alternative.confidence if is_final else 0.0
                }
                
        except Exception as e:
            logging.error(f"❌ Google STT streaming hatası: {e}")
            yield {'transcript': '', 'is_final': True, 'confidence': 0.0}


class AudioProcessor:
    """
    Gerçek zamanlı ses akışını işler ve Google Cloud STT'ye gönderir.
    Basitleştirilmiş versiyon - VAD Google tarafında yapılır.
    """
    def __init__(self, stt_service: GoogleSTTService, 
                 chunk_size: int = 1024,
                 sampling_rate: int = 16000):
        
        self.stt_service = stt_service
        self.chunk_size = chunk_size
        self.sampling_rate = sampling_rate
        self.audio_buffer = []
        
    def add_chunk(self, chunk: bytes):
        """Ses chunk'ı ekle"""
        self.audio_buffer.append(chunk)
    
    def get_audio_bytes(self) -> bytes:
        """Biriktirilen ses datasını al"""
        return b''.join(self.audio_buffer)
    
    def clear_buffer(self):
        """Buffer'ı temizle"""
        self.audio_buffer = []
    
    def transcribe_buffer(self) -> tuple[str, float]:
        """Buffer'daki sesi transkribe et"""
        audio_bytes = self.get_audio_bytes()
        if not audio_bytes:
            return "", 0.0
        
        result = self.stt_service.transcribe_audio_bytes(audio_bytes, self.sampling_rate)
        self.clear_buffer()
        return result


# Global STT instance (singleton pattern - lazy load)
_stt_service = None

def get_stt_service() -> GoogleSTTService:
    """STT service'i al (singleton)"""
    global _stt_service
    if _stt_service is None:
        _stt_service = GoogleSTTService()
    return _stt_service


# Test fonksiyonu
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🎤 Google Cloud Speech-to-Text Servisi Test")
    print("=" * 60)
    
    stt = get_stt_service()
    
    print("\n✅ STT servisi hazır ve kullanıma açık!")
    print(f"   📊 Model Bilgileri:")
    print(f"   - Model: phone_call (telefon konuşmaları için optimize)")
    print(f"   - Dil: tr-TR (Türkçe)")
    print(f"   - Noktalama: Otomatik")
    print("\n💡 Kullanım:")
    print("   from stt_service_google import get_stt_service")
    print("   stt = get_stt_service()")
    print("   text, confidence = stt.transcribe_audio_bytes(audio_bytes)")
    print("=" * 60)
