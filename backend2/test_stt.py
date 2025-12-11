"""
Streaming STT Test - Mikrofondan canlı Türkçe konuşma tanıma
Senin verdiğin örneğin aynısı, backend2 için uyarlanmış versiyon
"""
import os
import sys
import queue
from google.cloud import speech
import pyaudio

# Google Cloud credentials (main.py'deki gibi)
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "cobalt-duality-468620-v7-f6a3f73bd9ba.json")
if os.path.exists(CREDENTIALS_PATH):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_PATH
    print(f"✅ Credentials loaded: {CREDENTIALS_PATH}")
else:
    print("❌ Credentials file not found!")
    sys.exit(1)

# Ses kayıt ayarları
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms'lik parçalar


class MicrophoneStream:
    """Mikrofon sesini sürekli akış (stream) olarak Google'a gönderen sınıf."""

    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk,
            stream_callback=self._fill_buffer,
        )
        self.closed = False
        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Sesi parçalara ayırıp kuyruğa ekler."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b"".join(data)


def dinle_ve_yaz():
    """Mikrofondan canlı Türkçe konuşma tanıma"""
    language_code = "tr-TR"

    client = speech.SpeechClient()

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=language_code,
        enable_automatic_punctuation=True,  # Noktalama işaretleri ekle
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True  # True: Kelimeleri tam bitmeden anlık gösterir
    )

    print(f"\n" + "="*60)
    print(f"🎤 Streaming STT Test - Türkçe Konuşma Tanıma")
    print(f"="*60)
    print(f"Dinleniyor... (Durdurmak için Ctrl+C)\n")

    with MicrophoneStream(RATE, CHUNK) as stream:
        audio_generator = stream.generator()

        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in audio_generator
        )

        responses = client.streaming_recognize(streaming_config, requests)

        # Gelen cevapları döngüye sokup ekrana basıyoruz
        for response in responses:
            if not response.results:
                continue

            result = response.results[0]
            if not result.alternatives:
                continue

            transcript = result.alternatives[0].transcript

            # 'is_final=True' demek cümle bitti, karar verildi demek.
            # 'is_final=False' ise o an algıladığını yazar (canlı altyazı gibi).

            if result.is_final:
                # Cümle bittiğinde kalıcı olarak yazdır
                confidence = result.alternatives[0].confidence
                sys.stdout.write(f"\r✅ Final: {transcript} (güven: {confidence:.2%})\n")
            else:
                # Henüz bitmediyse aynı satırda güncelle (Overwrite)
                sys.stdout.write(f"\r⏳ Anlık: {transcript}")
                sys.stdout.flush()


if __name__ == "__main__":
    try:
        dinle_ve_yaz()
    except KeyboardInterrupt:
        print("\n\n🛑 Program durduruldu.")
    except Exception as e:
        print(f"\n❌ Hata: {e}")
