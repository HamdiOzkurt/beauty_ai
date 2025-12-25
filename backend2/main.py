"""
Backend2 - Main FastAPI Application
WebSocket endpoint with LangGraph agent + STT/TTS integration
"""
import os
import logging
import json
import uuid
from typing import Dict, Optional
from datetime import datetime
import asyncio
from queue import Queue
import threading
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from graph import stream_agent, agent_graph

# Set Google Cloud credentials BEFORE importing google.cloud
# Use absolute path to ensure it works
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "cobalt-duality-468620-v7-f6a3f73bd9ba.json")
if os.path.exists(CREDENTIALS_PATH):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_PATH
    logging.info(f"✅ Google Cloud credentials set: {CREDENTIALS_PATH}")
elif settings.GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = settings.GOOGLE_APPLICATION_CREDENTIALS
    logging.info(f"✅ Google Cloud credentials set from config: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
else:
    logging.warning("⚠️ Google Cloud credentials file not found!")

# Google Cloud imports (STT/TTS) - AFTER setting credentials
from google.cloud import speech, texttospeech
from google.api_core.exceptions import DeadlineExceeded
import time

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Explicitly set log level for Google Cloud Speech client and related handlers
# This might be necessary if they use their own loggers that aren't caught by root.
google_cloud_speech_logger = logging.getLogger('google.cloud.speech')
google_cloud_speech_logger.setLevel(logging.DEBUG)
for handler in google_cloud_speech_logger.handlers:
    if handler.level > logging.DEBUG: # Only lower the level if it's higher than DEBUG
        handler.setLevel(logging.DEBUG)

# Ensure Uvicorn and other loggers also respect the DEBUG level
# This is often necessary when uvicorn overrides default logging.
# Iterate through all existing loggers and set their level.
for log_name in logging.root.manager.loggerDict:
    # Avoid re-configuring google.cloud.speech if already done
    if not log_name.startswith('google.cloud.speech'):
        current_logger = logging.getLogger(log_name)
        if current_logger.level > getattr(logging, settings.LOG_LEVEL): # Only lower the level if it's higher
            current_logger.setLevel(getattr(logging, settings.LOG_LEVEL))



# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Beauty AI Backend v2",
    description="LangGraph + LangChain based AI Assistant for Beauty Center",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# STT/TTS Services
# ============================================================================

class GoogleSTTService:
    """Google Cloud Speech-to-Text service with streaming support"""

    def __init__(self):
        try:
            self.client = speech.SpeechClient()

            # Özel kelimeler (randevu, hizmetler için)
            # Bu kelimeler daha iyi tanınacak
            speech_contexts = speech.SpeechContext(
                phrases=[
                    # Onay kelimeleri (ÖNEMLI: İlk sırada)
                    "evet", "hayır", "olur", "tamam", "peki", "yok", "var",
                    # Randevu kelimeleri
                    "randevu", "randevu almak", "randevu oluştur",
                    "cilt bakımı", "saç kesimi", "pedikür", "manikür",
                    "yarın", "bugün", "pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar",
                    "saat", "müsait", "dolu", "uygun", "uzman", "kampanya",
                    "telefon numarası", "isim", "soyisim"
                ],
                boost=12.0  # 15'ten düşürüldü
            )

            # EN İYİ Config - Enhanced model kullan
            self.config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code="tr-TR",
                model="latest_long",  # En yeni, en iyi model
                use_enhanced=False,  # Premium model - %30 daha iyi doğruluk!
                max_alternatives=2,  # 2 alternatif al, en iyisini seç
                enable_automatic_punctuation=True,
                enable_spoken_punctuation=True,  # Noktalama işaretlerini sesli söylenirse tanı
                enable_spoken_emojis=False,
                profanity_filter=False,  # Randevu sisteminde gerek yok
                speech_contexts=[speech_contexts],  # Özel kelimeler
                enable_word_confidence=True  # Kelime bazında güven skoru
            )
            # Streaming STT için config
            self.streaming_config = speech.StreamingRecognitionConfig(
                config=self.config,
                interim_results=True  # Anlık sonuçları al (daha iyi tanıma)
            )
            logger.info("✅ Google STT initialized (tr-TR/enhanced+latest_long model)")
        except Exception as e:
            logger.error(f"❌ STT initialization failed: {e}")
            raise

    def transcribe_audio_bytes(self, audio_bytes: bytes, sample_rate: int = None) -> tuple:
        """Transcribe audio bytes to text (supports WebM Opus and PCM WAV)"""
        try:
            # Auto-detect WebM format
            is_webm = audio_bytes[:4] == b'\x1a\x45\xdf\xa3'  # WebM magic number

            if is_webm:
                # WebM Opus config - EN İYİ ayarlar
                speech_contexts = speech.SpeechContext(
                    phrases=[
                        "randevu", "randevu almak", "cilt bakımı", "saç kesimi", "pedikür", "manikür",
                        "yarın", "bugün", "pazartesi", "salı", "müsait", "dolu", "saat", "uzman"
                    ],
                    boost=15.0
                )

                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                    language_code="tr-TR",
                    model="latest_long",  # En iyi model
                    use_enhanced=False,  # Premium - %30 daha iyi!
                    max_alternatives=2,
                    enable_automatic_punctuation=True,
                    enable_spoken_punctuation=True,
                    speech_contexts=[speech_contexts],
                    enable_word_confidence=True
                )
            else:
                # PCM/WAV config - EN İYİ ayarlar
                if sample_rate is None:
                    sample_rate = 16000

                speech_contexts = speech.SpeechContext(
                    phrases=[
                        "randevu", "randevu almak", "cilt bakımı", "saç kesimi", "pedikür", "manikür",
                        "yarın", "bugün", "pazartesi", "salı", "müsait", "dolu", "saat", "uzman"
                    ],
                    boost=15.0
                )

                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=sample_rate,
                    language_code="tr-TR",
                    model="latest_long",  # En iyi model
                    use_enhanced=False,  # Premium - %30 daha iyi!
                    max_alternatives=2,
                    enable_automatic_punctuation=True,
                    enable_spoken_punctuation=True,
                    speech_contexts=[speech_contexts],
                    enable_word_confidence=True
                )

            audio = speech.RecognitionAudio(content=audio_bytes)
            response = self.client.recognize(config=config, audio=audio)

            if not response.results:
                return "", 0.0

            result = response.results[0]
            transcript = result.alternatives[0].transcript
            confidence = result.alternatives[0].confidence

            logger.info(f"🎤 STT: {transcript} (confidence: {confidence:.2f})")
            return transcript, confidence

        except Exception as e:
            logger.error(f"STT error: {e}", exc_info=True)
            return "", 0.0

    def transcribe_audio_streaming(self, audio_bytes: bytes, sample_rate: int = 16000) -> tuple:
        """
        Streaming transcription - Daha iyi Türkçe tanıma için interim_results kullanır.
        Verdiğiniz örnekteki gibi streaming API kullanır.

        Args:
            audio_bytes: Ses verisi (PCM LINEAR16 formatında)
            sample_rate: Örnekleme oranı (varsayılan: 16000)

        Returns:
            (transcript, confidence) tuple
        """
        try:
            # Özel kelimeler
            speech_contexts = speech.SpeechContext(
                phrases=[
                    "randevu", "randevu almak", "cilt bakımı", "saç kesimi", "pedikür", "manikür",
                    "yarın", "bugün", "pazartesi", "salı", "müsait", "dolu", "saat", "uzman"
                ],
                boost=15.0
            )

            # Streaming config - EN İYİ ayarlar
            streaming_config = speech.StreamingRecognitionConfig(
                config=speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=sample_rate,
                    language_code="tr-TR",
                    model="latest_long",  # En iyi model
                    use_enhanced=False,  # Premium - %30 daha iyi!
                    max_alternatives=2,
                    enable_automatic_punctuation=True,
                    enable_spoken_punctuation=True,
                    speech_contexts=[speech_contexts],
                    enable_word_confidence=True
                ),
                interim_results=True  # Anlık sonuçlar - daha iyi tanıma!
            )

            # Audio'yu chunk'lara böl (streaming için)
            chunk_size = int(sample_rate / 10)  # 100ms chunks

            def audio_generator():
                """Audio bytes'ı chunk'lara bölerek yield eder"""
                for i in range(0, len(audio_bytes), chunk_size * 2):  # *2 çünkü 16-bit = 2 bytes
                    yield speech.StreamingRecognizeRequest(
                        audio_content=audio_bytes[i:i + chunk_size * 2]
                    )

            # Streaming recognize
            responses = self.client.streaming_recognize(streaming_config, audio_generator())

            # En son final result'ı al
            transcript = ""
            confidence = 0.0

            for response in responses:
                if not response.results:
                    continue

                result = response.results[0]
                if not result.alternatives:
                    continue

                # is_final=True olan sonuçları topla
                if result.is_final:
                    transcript = result.alternatives[0].transcript
                    confidence = result.alternatives[0].confidence
                    logger.info(f"🎤 STT (streaming): {transcript} (confidence: {confidence:.2f})")

            return transcript, confidence

        except Exception as e:
            logger.error(f"Streaming STT error: {e}", exc_info=True)
            return "", 0.0


class TTSService:
    """Google Cloud Text-to-Speech service"""

    def __init__(self):
        try:
            self.client = texttospeech.TextToSpeechClient()
            self.voice = texttospeech.VoiceSelectionParams(
                language_code="tr-TR",
                name="tr-TR-Chirp3-HD-Leda",
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            )
            self.audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,  # Chirp3 için ideal hız
                sample_rate_hertz=24000  # HD model için 24kHz
            )
            logger.info("✅ Google TTS initialized (Chirp3-HD-Leda)")
        except Exception as e:
            logger.error(f"❌ TTS initialization failed: {e}")
            raise

    def text_to_speech(self, text: str) -> bytes:
        """Convert text to speech"""
        try:
            synthesis_input = texttospeech.SynthesisInput(text=text)
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=self.voice,
                audio_config=self.audio_config
            )
            logger.info(f"🔊 TTS: Generated {len(response.audio_content)} bytes")
            return response.audio_content
        except Exception as e:
            logger.error(f"TTS error: {e}", exc_info=True)
            return b""


# Global service instances (lazy loaded)
stt_service: Optional[GoogleSTTService] = None
tts_service: Optional[TTSService] = None

def get_stt_service() -> Optional[GoogleSTTService]:
    """Lazy initialize and return the STT service instance."""
    global stt_service
    if stt_service is None:
        try:
            stt_service = GoogleSTTService()
        except Exception as e:
            logger.error(f"❌ Failed to get STT service: {e}")
            stt_service = None
    return stt_service

def get_tts_service() -> Optional[TTSService]:
    """Lazy initialize and return the TTS service instance."""
    global tts_service
    if tts_service is None:
        try:
            tts_service = TTSService()
        except Exception as e:
            logger.error(f"❌ Failed to get TTS service: {e}")
            tts_service = None
    return tts_service


# ============================================================================
# Conversation State Management
# ============================================================================

# In-memory conversation storage (session_id -> state)
conversations: Dict[str, dict] = {}


def get_or_create_conversation(session_id: str) -> dict:
    """Get or create a conversation state"""
    if session_id not in conversations:
        conversations[session_id] = {
            "collected_info": {},
            "context": {},
            "history": [],
            "created_at": datetime.utcnow().isoformat()
        }
    return conversations[session_id]


# ============================================================================
# WebSocket Helper Functions
# ============================================================================

async def process_audio_buffer(websocket: WebSocket, audio_buffer: bytes, session_id: str, conversation: dict):
    """
    Process accumulated audio buffer with Google Cloud STT + Agent.

    Args:
        websocket: WebSocket connection
        audio_buffer: PCM audio data (Int16, 16kHz, mono)
        session_id: Session ID
        conversation: Conversation state
    """
    try:
        t_start = time.time()

        # STT: Convert audio to text
        stt = get_stt_service()
        if not stt:
            logger.error("STT service is not available.")
            await websocket.send_json({
                "type": "error",
                "content": "Ses tanıma hizmeti şu anda kullanılamıyor.",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            return

        logger.info(f"🎤 Processing audio buffer: {len(audio_buffer)} bytes")

        # Google Cloud Streaming STT (best quality)
        user_message, confidence = await run_streaming_stt(stt, audio_buffer)

        if not user_message:
            logger.warning("STT returned empty transcript")
            await websocket.send_json({
                "type": "error",
                "content": "Ses anlaşılamadı, lütfen tekrar edin.",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            return

        # Send transcription to client
        await websocket.send_json({
            "type": "transcription",
            "content": user_message,
            "confidence": confidence,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Process with agent
        await process_user_message(
            websocket=websocket,
            user_message=user_message,
            session_id=session_id,
            conversation=conversation
        )

        t_end = time.time()
        logger.info(f"PERF: Total audio processing time: {t_end - t_start:.4f}s")

    except Exception as e:
        logger.error(f"Error processing audio buffer: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "content": "Ses işleme hatası oluştu.",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        })


async def run_streaming_stt(stt: GoogleSTTService, audio_buffer: bytes) -> tuple:
    """
    Run Google Cloud Streaming STT on audio buffer.

    Returns:
        (transcript, confidence) tuple
    """
    try:
        # Streaming config
        chunk_size = int(16000 / 10)  # 100ms chunks

        def audio_generator():
            """Audio bytes'ı chunk'lara bölerek yield eder"""
            for i in range(0, len(audio_buffer), chunk_size * 2):  # *2 çünkü 16-bit = 2 bytes
                yield speech.StreamingRecognizeRequest(
                    audio_content=audio_buffer[i:i + chunk_size * 2]
                )

        responses = stt.client.streaming_recognize(stt.streaming_config, audio_generator())

        # En son final result'ı al
        transcript = ""
        confidence = 0.0

        for response in responses:
            if not response.results:
                continue

            result = response.results[0]
            if not result.alternatives:
                continue

            if result.is_final:
                transcript = result.alternatives[0].transcript
                confidence = result.alternatives[0].confidence
                logger.info(f"🎤 STT (final): {transcript} (confidence: {confidence:.2f})")

        return transcript, confidence

    except Exception as e:
        logger.error(f"Streaming STT error: {e}", exc_info=True)
        return "", 0.0


async def process_user_message(websocket: WebSocket, user_message: str, session_id: str, conversation: dict):
    """
    Process user message with LangGraph agent and send response.

    Args:
        websocket: WebSocket connection
        user_message: User's message text
        session_id: Session ID
        conversation: Conversation state
    """
    try:
        # Add to history
        conversation["history"].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.utcnow().isoformat()
        })

        # History boyutu kontrolü
        if len(conversation["history"]) > 50:
            removed_count = len(conversation["history"]) - 30
            conversation["history"] = conversation["history"][-30:]
            logger.warning(f"🧹 History trimmed: removed {removed_count} old messages")

        # Stream agent response
        agent_response_text = ""
        t_agent_start = time.time()

        async for event in stream_agent(
            user_message=user_message,
            session_id=session_id,
            collected_info=conversation["collected_info"],
            context=conversation["context"],
            history=conversation["history"]
        ):
            # Extract messages from event
            if "agent" in event:
                messages = event["agent"].get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    if hasattr(last_msg, "content") and last_msg.content:
                        agent_response_text = last_msg.content

            # Extract tool results
            if "tools" in event:
                messages = event["tools"].get("messages", [])
                for msg in messages:
                    if hasattr(msg, "content"):
                        try:
                            tool_result = json.loads(msg.content)
                            if tool_result.get("success"):
                                if "customer" in tool_result:
                                    customer = tool_result["customer"]
                                    conversation["context"]["customer_name"] = customer.get("name")
                                    conversation["context"]["customer_phone"] = customer.get("phone")
                                    conversation["collected_info"]["customer_phone"] = customer.get("phone")

                                if "code" in tool_result:
                                    conversation["collected_info"]["appointment_code"] = tool_result["code"]

                                if "campaigns" in tool_result:
                                    conversation["context"]["campaigns"] = tool_result["campaigns"]
                        except:
                            pass

        t_agent_end = time.time()
        logger.info(f"PERF: Agent processing: {t_agent_end - t_agent_start:.4f}s")

        # Add to history
        conversation["history"].append({
            "role": "assistant",
            "content": agent_response_text,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Send text response
        await websocket.send_json({
            "type": "text",
            "content": agent_response_text,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        })

        # TTS: Convert text to audio
        if agent_response_text:
            tts = get_tts_service()
            if tts:
                audio_bytes = tts.text_to_speech(agent_response_text)
                if audio_bytes:
                    import base64
                    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                    await websocket.send_json({
                        "type": "audio",
                        "content": audio_base64,
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })

        # Send stream end marker
        await websocket.send_json({
            "type": "stream_end",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error(f"Error processing user message: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "content": "Mesaj işleme hatası oluştu.",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        })


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/api/ws/v2/chat")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint with Google Cloud Streaming STT + a robust,
    utterance-based VAD (Voice Activity Detection) and processing logic.
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info(f"🔌 WebSocket connected (Utterance-based VAD): {session_id}")

    # --- State Management ---
    conversation = get_or_create_conversation(session_id)
    stt = get_stt_service()
    if not stt:
        logger.error("STT service not available")
        await websocket.close(code=1011, reason="STT service unavailable")
        return

    # Queues for thread-safe communication
    audio_queue = Queue()
    callback_queue = asyncio.Queue()

    # Core state variables
    processing_lock = False
    stt_started = False
    stt_thread = None
    
    # Utterance-specific state
    # This ID acts as a generation counter to prevent race conditions.
    utterance_id = 0
    last_interim_time = None
    accumulated_interim = ""
    speech_active = False

    # --- STT Configuration ---
    streaming_config = speech.StreamingRecognitionConfig(
        config=speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="tr-TR",
            model="latest_long",
            use_enhanced=True, # Enabled for better accuracy as per user's earlier comment
            enable_automatic_punctuation=True,
            speech_contexts=[speech.SpeechContext(
                phrases=[
                    # Onay kelimeleri (ÖNEMLI: İlk sırada)
                    "evet", "hayır", "olur", "tamam", "peki", "yok", "var",
                    # Randevu kelimeleri
                    "randevu", "randevu almak", "cilt bakımı", "saç kesimi",
                    "pedikür", "manikür", "yarın", "bugün", "saat", "uzman"
                ],
                boost=12.0  # 15'ten düşürüldü, çok yüksek boost diğer kelimeleri bastırıyor
            )]
        ),
        interim_results=True,
        single_utterance=False
    )

    # --- Helper Functions (defined within endpoint scope) ---

    def audio_generator():
        """Yields audio chunks from the queue. Stops on `None`."""
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                break
            yield speech.StreamingRecognizeRequest(audio_content=chunk)

    def process_stt_responses_sync():
        """
        Runs in a thread. Manages STT stream lifecycle using `utterance_id`
        to discard stale responses from previous streams.
        """
        nonlocal utterance_id, accumulated_interim, last_interim_time, speech_active

        # This outer loop handles stream restarts.
        while True:
            # Create a local copy of the utterance ID for this stream instance.
            local_utterance_id = utterance_id

            try:
                stream_gen = audio_generator()
                responses = stt.client.streaming_recognize(streaming_config, stream_gen)
                logger.info(f"🎙️ New STT stream started for utterance #{local_utterance_id}")

                for response in responses:
                    # **CRITICAL:** If the global utterance_id has changed, it means
                    # this stream is stale and must be terminated to prevent ghost triggers.
                    if local_utterance_id != utterance_id:
                        logger.warning(f"🛑 Stale stream #{local_utterance_id} detected. Terminating.")
                        break

                    if not response.results:
                        continue
                    
                    full_transcript_from_response = ""
                    is_final = False
                    
                    # Iterate through all result segments within the single response object
                    for result_segment in response.results:
                        if result_segment.alternatives and result_segment.alternatives[0].transcript:
                            # Concatenate the best alternative (first one) from each segment
                            full_transcript_from_response += result_segment.alternatives[0].transcript
                        
                        # Capture is_final flag
                        if result_segment.is_final:
                            is_final = True
                    
                    # Boş final response geliş olmak - son interim'i koru!
                    if is_final and not full_transcript_from_response.strip():
                        logger.debug(f"⏭️ Empty final response for utterance #{local_utterance_id}. Keeping accumulated_interim: '{accumulated_interim}'")
                        continue
                    
                    # Add detailed logging here
                    logger.info(f"DEBUG_STT_RAW: Utterance #{local_utterance_id}, IsFinal: {is_final}, FullTranscript: '{full_transcript_from_response}'")
                    print(f"DEBUG_STT_RAW: Utterance #{local_utterance_id}, Combined Transcript: '{full_transcript_from_response}', IsFinal: {is_final}, FullResponse: {response}", file=sys.stderr)

                    # Update buffer: APPEND for interim, REPLACE for final
                    # Bu sayede Google STT'nin kırıntı responses'ından para yapabiliriz
                    if full_transcript_from_response.strip():  # Sadece non-empty transcript'ler
                        if is_final:
                            # Final response: kesin söylenmiş, accumulated'ı güncelle
                            accumulated_interim = full_transcript_from_response
                        else:
                            # Interim: eğer daha önce hiç almadıysak başlat, yoksa append et
                            if not accumulated_interim:
                                accumulated_interim = full_transcript_from_response
                            # Interim'leri append etme, sadece replace et (Google STT full hypothesis döner)
                            else:
                                accumulated_interim = full_transcript_from_response
                        
                        last_interim_time = time.time()

                    if not speech_active and full_transcript_from_response.strip():
                        speech_active = True
                        logger.info(f"🎤 Speech started in utterance #{local_utterance_id}: {full_transcript_from_response[:30]}...")
                        callback_queue.put_nowait({
                            "type": "vad_speech_start",
                            "session_id": session_id,
                            "timestamp": datetime.utcnow().isoformat()
                        })

            except Exception as e:
                # Handle expected stream timeouts and errors gracefully.
                logger.warning(f"⚠️ STT stream for utterance #{local_utterance_id} ended: {e}")
                # The loop will naturally restart, but we check the utterance_id
                # to see if we should continue.
                if local_utterance_id != utterance_id:
                    logger.info(f"Utterance #{local_utterance_id} already processed. Thread is catching up.")
                continue # Always attempt to restart the stream.

    async def process_callbacks():
        """Processes events from the STT thread and timeout monitor."""
        nonlocal processing_lock
        while True:
            try:
                callback = await callback_queue.get()
                callback_type = callback.get("type")

                if callback_type == "process_message":
                    await process_user_message(
                        websocket=websocket,
                        user_message=callback["content"],
                        session_id=session_id,
                        conversation=conversation
                    )
                    processing_lock = False # Release lock after processing.
                else:
                    await websocket.send_json(callback)
            except Exception as e:
                logger.error(f"Callback processing error: {e}", exc_info=True)

    async def monitor_interim_timeout():
        """
        The single authority for deciding when an utterance has ended.
        Triggers LLM processing and manages the utterance lifecycle.
        """
        nonlocal utterance_id, last_interim_time, accumulated_interim, speech_active, processing_lock

        TIMEOUT_SECONDS = 1.2  # İlk kelimenin kaçmaması için artırıldı
        GREETINGS = ["alo", "merhaba"]  # Sadece pure greetings

        while True:
            await asyncio.sleep(0.15)  # Daha hassas kontrol (0.15s)

            if last_interim_time and not processing_lock and (time.time() - last_interim_time) >= TIMEOUT_SECONDS:
                # 1. Acquire lock.
                processing_lock = True
                
                # 2. Get final text.
                final_text = accumulated_interim.strip()

                # 3. **CRITICAL:** Increment utterance_id immediately.
                # This invalidates the current STT stream and prevents ghost responses.
                utterance_id += 1
                logger.info(f"⏱️ Silence detected. Ending utterance #{utterance_id - 1}. New utterance is #{utterance_id}.")

                # 4. Save final text BEFORE reset (Google STT boş final response yapabilir!)
                final_text_backup = final_text
                
                # 5. Reset state for the new utterance.
                last_interim_time = None
                accumulated_interim = ""
                speech_active = False

                # 6. Restart the STT stream by killing the old generator.
                audio_queue.put(None)

                # 7. REMOVED: Greeting-only filter - Tüm mesajları LLM'e gönder!
                # Alo, merhaba gibi basit greetings bile LLM'in cevapvermesine izin ver
                
                # 8. Short utterance guard.
                if len(final_text.strip()) < 2: # Çok kısa (1-2 karakter) mesajları ignore et
                    logger.info(f"⚠️ Ignoring very short utterance: '{final_text}'")
                    processing_lock = False
                    continue

                # 9. Google STT'nin boş final response problemi için
                logger.info(f"📝 Final text for LLM: '{final_text}' (from interim buffer)")

                # 10. Send final events to client and queue LLM task.
                await websocket.send_json({
                    "type": "vad_speech_end",
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                await websocket.send_json({
                    "type": "transcription",
                    "content": final_text,
                    "confidence": 0.95,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                logger.info(f"📤 Final transcription sent: '{final_text}'")

                callback_queue.put_nowait({
                    "type": "process_message",
                    "content": final_text
                })

    # --- Main Execution Logic ---
    callback_task = asyncio.create_task(process_callbacks())
    timeout_task = asyncio.create_task(monitor_interim_timeout())

    # STT thread'i hemen başlat (ilk audio gelmeden önce hazır olsun)
    stt_thread = threading.Thread(target=process_stt_responses_sync, daemon=True)
    stt_thread.start()
    stt_started = True
    logger.info("🚀 Google Cloud STT thread started at connection start")

    try:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")

            if message_type == "websocket.disconnect":
                logger.info(f"🔌 Client disconnected gracefully")
                break

            if "bytes" in message:
                # STT thread zaten çalışıyor, sadece audio'yu queue'ya at
                audio_queue.put(message["bytes"])

            elif "text" in message:
                data = json.loads(message["text"])
                if data.get("type") == "text":
                    # Manually trigger processing for text messages.
                    processing_lock = True
                    utterance_id += 1 # Invalidate any ongoing speech
                    audio_queue.put(None) # Reset STT stream
                    last_interim_time, accumulated_interim, speech_active = None, "", False
                    
                    logger.info(f"📨 Text message received. Processing: '{data.get('data', '')}'")
                    callback_queue.put_nowait({
                        "type": "process_message",
                        "content": data.get("data", "")
                    })
                else:
                    logger.warning(f"Unknown JSON message type: {data.get('type')}")

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info(f"🧹 Cleaning up session: {session_id}")
        audio_queue.put(None)
        callback_task.cancel()
        timeout_task.cancel()
        if stt_thread and stt_thread.is_alive():
            stt_thread.join(timeout=1.0)
        logger.info(f"✅ Cleanup complete for session: {session_id}")


# ============================================================================
# REST API Endpoints (for testing)
# ============================================================================

@app.get("/api")
async def api_info():
    """API information endpoint"""
    return {
        "name": "Beauty AI Backend v2",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "websocket": "/api/ws/v2/chat",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": "ok",
            "stt": "ok" if get_stt_service() else "error",
            "tts": "ok" if get_tts_service() else "error",
            "agent": "ok"
        }
    }


@app.post("/api/v2/chat")
async def chat_endpoint(request: dict):
    """
    REST API endpoint for testing (non-WebSocket)

    Request:
    {
        "message": "Merhaba",
        "session_id": "optional-session-id"
    }
    """
    message = request.get("message", "")
    session_id = request.get("session_id", str(uuid.uuid4()))

    if not message:
        return {"error": "Message is required"}

    conversation = get_or_create_conversation(session_id)

    # Invoke agent (non-streaming)
    from graph import invoke_agent

    response = invoke_agent(
        user_message=message,
        session_id=session_id,
        collected_info=conversation["collected_info"],
        context=conversation["context"],
        history=conversation["history"]
    )

    return {
        "response": response,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# Static Files & Frontend
# ============================================================================

# Mount static files from current backend2 directory
import os
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
INDEX_HTML_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"✅ Static files mounted from {STATIC_DIR}")

@app.get("/")
async def serve_index():
    """Serve the frontend HTML"""
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH)
    return {"message": "Beauty AI Backend v2 - WebSocket API", "websocket": "/api/ws/v2/chat"}


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Starting Beauty AI Backend v2...")

    # Initialize database
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")

    logger.info("✅ Backend v2 started successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Beauty AI Backend v2...")
    conversations.clear()
    logger.info("✅ Cleanup completed")


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
