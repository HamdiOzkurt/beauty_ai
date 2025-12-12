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
                    "randevu", "randevu almak", "randevu oluştur",
                    "cilt bakımı", "saç kesimi", "pedikür", "manikür",
                    "yarın", "bugün", "pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar",
                    "saat", "müsait", "dolu", "uygun", "uzman", "kampanya",
                    "telefon numarası", "isim", "soyisim"
                ],
                boost=15.0  # Bu kelimeleri daha çok önceliklendir
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
                name="tr-TR-Wavenet-C",
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            )
            self.audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=0.9,
                pitch=2.0,
                effects_profile_id=["headphone-class-device"],
                sample_rate_hertz=22050
            )
            logger.info("✅ Google TTS initialized")
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
# WebSocket Endpoint
# ============================================================================

@app.websocket("/api/ws/v2/chat")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time conversation with the agent.

    Message format (from client):
    {
        "type": "audio" | "text",
        "session_id": "unique-session-id",
        "data": base64_audio | text_message,
        "sample_rate": 16000 (for audio)
    }

    Response format (to client):
    {
        "type": "text" | "audio" | "error",
        "content": text_message | base64_audio,
        "session_id": "session-id",
        "timestamp": "2024-01-01T00:00:00"
    }
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info(f"🔌 WebSocket connected: {session_id}")

    try:
        while True:
            # Receive message (can be binary or JSON)
            message = await websocket.receive()

            # Check if it's binary (audio) or text (JSON)
            if "bytes" in message:
                # ⏱️ Start timing
                import time
                t_start = time.time()

                # Binary audio data
                audio_bytes = message["bytes"]
                t_audio_received = time.time()
                logger.info(f"PERF: Audio received at {t_audio_received:.4f}s")
                logger.info(f"📨 Received binary audio: {len(audio_bytes)} bytes")

                # Get conversation state
                conversation = get_or_create_conversation(session_id)

                # STT: Convert audio to text
                t_stt_start = time.time()
                logger.info(f"PERF: STT started at {t_stt_start:.4f}s")
                stt = get_stt_service()
                if not stt:
                    logger.error("STT service is not available.")
                    await websocket.send_json({
                        "type": "error",
                        "content": "Ses tanıma hizmeti şu anda kullanılamıyor.",
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    continue

                # Streaming STT kullan (daha iyi Türkçe tanıma)
                # WebM ise batch, PCM ise streaming
                is_webm = audio_bytes[:4] == b'\x1a\x45\xdf\xa3'

                if is_webm:
                    # WebM için batch mode (streaming desteklemiyor)
                    user_message, confidence = stt.transcribe_audio_bytes(audio_bytes)
                    logger.info(f"🎤 WebM format detected, using batch STT")
                else:
                    # PCM için streaming mode (daha iyi tanıma!)
                    logger.info(f"🎤 PCM format detected, using streaming STT")
                    
                    DEADLINE_SECONDS = 1.0
                    final_transcript = ""
                    confidence = 0.0

                    try:
                        # Audio'yu chunk'lara böl (streaming için)
                        chunk_size = int(16000 / 10)  # 100ms chunks

                        def audio_generator():
                            """Audio bytes'ı chunk'lara bölerek yield eder"""
                            for i in range(0, len(audio_bytes), chunk_size * 2):  # *2 çünkü 16-bit = 2 bytes
                                yield speech.StreamingRecognizeRequest(
                                    audio_content=audio_bytes[i:i + chunk_size * 2]
                                )
                        
                        responses = stt.client.streaming_recognize(stt.streaming_config, audio_generator(), timeout=DEADLINE_SECONDS * 2)
                        
                        for response in responses:
                            if not response.results:
                                continue

                            result = response.results[0]
                            if not result.alternatives:
                                continue

                            transcript = result.alternatives[0].transcript

                            if result.is_final:
                                final_transcript = transcript
                                confidence = result.alternatives[0].confidence
                                logger.info(f"🎤 STT (final): {final_transcript} (confidence: {confidence:.2f})")
                            else:
                                logger.info(f"🎤 STT (interim): {transcript}")
                        
                        user_message = final_transcript

                    except DeadlineExceeded:
                        logger.warning(f"Sessizlik nedeniyle konuşma sonlandırıldı. Son anlaşılan: {final_transcript}")
                        user_message = final_transcript
                    except Exception as e:
                        logger.error(f"Streaming STT error: {e}", exc_info=True)
                        user_message = ""
                        confidence = 0.0

                t_stt_end = time.time()
                logger.info(f"PERF: STT finished at {t_stt_end:.4f}s (duration: {t_stt_end - t_stt_start:.4f}s)")

                if not user_message:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Ses anlaşılamadı, lütfen tekrar edin.",
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    continue

                # Send transcription back to client
                await websocket.send_json({
                    "type": "transcription",
                    "content": user_message,
                    "confidence": confidence,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif "text" in message:
                # JSON text message
                import json
                data = json.loads(message["text"])
                message_type = data.get("type")
                session_id = data.get("session_id", session_id)

                logger.info(f"📨 Received {message_type} message")

                # Get conversation state
                conversation = get_or_create_conversation(session_id)

                if message_type == "text":
                    user_message = data.get("data", "")
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    continue
            else:
                logger.warning("Unknown message format")
                continue

            # Add to history
            conversation["history"].append({
                "role": "user",
                "content": user_message,
                "timestamp": datetime.utcnow().isoformat()
            })

            # History boyutu kontrolü - Çok büyürse eski mesajları sil
            if len(conversation["history"]) > 50:
                # Son 30 mesajı tut, eski 20'yi sil
                removed_count = len(conversation["history"]) - 30
                conversation["history"] = conversation["history"][-30:]
                logger.warning(f"🧹 History too large! Removed {removed_count} old messages. Current size: {len(conversation['history'])}")

            # Stream agent response
            agent_response_text = ""
            t_agent_start = time.time()
            logger.info(f"PERF: Agent started at {t_agent_start:.4f}s")

            try:
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
                                # Parse tool result and update collected_info
                                try:
                                    tool_result = json.loads(msg.content)
                                    if tool_result.get("success"):
                                        # Update collected info based on tool result
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

                    # Mesajdan hizmet/tarih bilgisi çıkar (basit keyword matching)
                    # Bu bilgileri collected_info'ya ekle ki AI sonraki adımlarda kullansın
                    user_msg_lower = user_message.lower()
                    services_keywords = ["cilt bakımı", "saç kesimi", "pedikür", "manikür"]
                    for service in services_keywords:
                        if service in user_msg_lower:
                            conversation["collected_info"]["service"] = service
                            logger.info(f"📝 Service detected and saved: {service}")
                            break

            except Exception as e:
                logger.error(f"Agent stream error: {e}", exc_info=True)
                agent_response_text = "Üzgünüm, bir hata oluştu. Lütfen tekrar dener misiniz?"
            
            t_agent_end = time.time()
            logger.info(f"PERF: Agent finished at {t_agent_end:.4f}s (duration: {t_agent_end - t_agent_start:.4f}s)")

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
                t_tts_start = time.time()
                logger.info(f"PERF: TTS started at {t_tts_start:.4f}s")
                tts = get_tts_service()
                if tts:
                    audio_bytes = tts.text_to_speech(agent_response_text)
                    t_tts_end = time.time()
                    logger.info(f"PERF: TTS finished at {t_tts_end:.4f}s (duration: {t_tts_end - t_tts_start:.4f}s)")
                    if audio_bytes:
                        import base64
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                        await websocket.send_json({
                            "type": "audio",
                            "content": audio_base64,
                            "session_id": session_id,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        t_audio_sent = time.time()
                        logger.info(f"PERF: Audio sent at {t_audio_sent:.4f}s")

                else:
                    logger.warning("TTS service is not available, skipping audio generation.")

            # Send stream end marker
            await websocket.send_json({
                "type": "stream_end",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            t_end = time.time()
            logger.info(f"PERF: Total request time: {t_end - t_start:.4f}s")

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": "Bağlantı hatası oluştu.",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass


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

# Mount static files from parent backend directory
import os
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", "static")
INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", "templates", "index.html")

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
