"""
Google Cloud Text-to-Speech Service
Doğal kadın sesi ile Türkçe konuşma
"""

from google.cloud import texttospeech
import os
import logging
from config import settings

# Ses profilleri import et
try:
    from tts_profiles import ACTIVE_PROFILE
except ImportError:
    # Fallback: Profil yoksa varsayılan kullan
    # Daha yumuşak ve sıcak bir kadın sesi için varsayılan profil
    # Not: Wavenet yerine genellikle daha doğal bulunan "Neural2" / "Studio" tarzı
    # sesler tercih edilir; projede tanımlı değilse bu fallback kullanılır.
    ACTIVE_PROFILE = {
        "name": "tr-TR-Wavenet-C",   # Genelde A'dan biraz daha yumuşak ton
        "speaking_rate": 0.9,        # Biraz daha yavaş, daha anlaşılır
        "pitch": 2.0,                # Hafif yüksek ton → daha sıcak/human
        "description": "Yumuşak, sıcak ve doğal kadın sesi"
    }

class TTSService:
    """Google Cloud TTS ile doğal kadın sesi"""
    
    def __init__(self):
        """TTS client'ı başlat"""
        try:
            self.client = texttospeech.TextToSpeechClient()
            
            # Aktif profili kullan
            self.voice = texttospeech.VoiceSelectionParams(
                language_code="tr-TR",
                name=ACTIVE_PROFILE["name"],
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            )
            
            # Ses ayarları - Profil bazlı (HIZ + DOĞALLIK DENGESİ)
            self.audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=ACTIVE_PROFILE["speaking_rate"],
                pitch=ACTIVE_PROFILE["pitch"],
                # Hafif oda efekti, kulaklık/telefon için daha doğal his
                effects_profile_id=["headphone-class-device"],
                # Biraz daha yüksek sample rate daha net ve doğal hissettirir
                sample_rate_hertz=22050
            )
            
            logging.info(f"✅ Google TTS - {ACTIVE_PROFILE['name']}: {ACTIVE_PROFILE['description']}")
            
        except Exception as e:
            logging.error(f"❌ TTS başlatılamadı: {e}")
            raise
    
    def text_to_speech(self, text: str) -> bytes:
        """
        Metni sese çevir
        
        Args:
            text: Konuşulacak metin
            
        Returns:
            MP3 audio bytes
        """
        try:
            # TTS isteği
            synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # Sentezle
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=self.voice,
                audio_config=self.audio_config
            )
            
            logging.info(f"🎤 TTS: {len(response.audio_content)} bytes üretildi")
            return response.audio_content
            
        except Exception as e:
            logging.error(f"TTS hatası: {e}")
            raise


# Global TTS instance (lazy load)
_tts_service = None

def get_tts_service():
    """TTS service'i al (singleton pattern)"""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
