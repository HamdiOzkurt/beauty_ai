# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Beauty AI Backend v2 - A voice-enabled AI assistant for a beauty center, built with LangGraph/LangChain and Google Gemini. Handles appointment booking, customer queries, and service information via WebSocket with real-time STT/TTS.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run server (development)
python main.py

# Run with uvicorn (production-like)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Test Directus connection
python database.py
```

## Architecture

### Core Flow
```
WebSocket Request → STT (Google Cloud) → LangGraph Agent → Tool Execution → TTS (ElevenLabs) → Response
```

### Key Components

**main.py** - FastAPI server with:
- WebSocket endpoint (`/api/ws/v2/chat`) with streaming STT using Voice Activity Detection
- `GoogleSTTService` for STT (Google Cloud Speech-to-Text)
- `TTSService` for TTS (ElevenLabs with `eleven_multilingual_v2` model for Turkish)
- In-memory conversation state management

**graph.py** - LangGraph agent implementation:
- `AgentState` TypedDict: messages, collected_info, context
- Two-node graph: `agent` (LLM) → `tools` (execution) with conditional routing
- Uses `ChatGoogleGenerativeAI` with tool binding in AUTO mode

**repository.py** - Data access layer for Directus CMS:
- Repository classes: `CustomerRepository`, `AppointmentRepository`, `ServiceRepository`, `ExpertRepository`, `CampaignRepository`
- All data stored in Directus (no local PostgreSQL)
- Directus collections prefixed with `voises_`

**tools/** - LangChain tools with `@tool` decorator:
- `appointment_tools.py`: check_availability, create_appointment, cancel_appointment
- `customer_tools.py`: check_customer, get_customer_appointments, create_customer
- `info_tools.py`: list_services, list_experts, check_campaigns

### Data Flow
1. Audio → `GoogleSTTService.transcribe_audio_streaming()` → text
2. Text → `stream_agent()` → LangGraph processes with tools
3. Agent response → `TTSService.text_to_speech()` → audio
4. WebSocket sends: transcription, text response, audio (base64 MP3)

## Configuration

Environment variables (`.env`):
- `GEMINI_API_KEY` - Google Gemini API key
- `DIRECTUS_URL`, `DIRECTUS_TOKEN` - Directus CMS connection
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to Google Cloud service account JSON (for STT)
- `ELEVENLABS_API_KEY` - ElevenLabs API key (for TTS)
- `ELEVENLABS_VOICE_ID` - Voice ID (default: Rachel `21m00Tcm4TlvDq8ikWAM`)
- `ELEVENLABS_MODEL` - Model (default: `eleven_multilingual_v2` for Turkish)
- `TENANT_ID` - Multi-tenant identifier (default: 1)

## WebSocket Protocol

Client → Server:
```json
{"type": "text|audio", "session_id": "...", "data": "message|base64_audio"}
```

Server → Client:
```json
{"type": "text|audio|transcription|vad_speech_start|vad_speech_end|stream_end|error", "content": "...", "session_id": "..."}
```

## Key Implementation Details

- STT uses Google Cloud streaming recognition with interim results and custom speech contexts for Turkish beauty/appointment vocabulary
- TTS uses ElevenLabs `eleven_multilingual_v2` model for high-quality Turkish speech synthesis
- Agent system prompt is in `graph.py:SYSTEM_PROMPT` - defines tool usage policies and voice output constraints
- Conversation history limited to last 20 messages to prevent context overflow
- Business hours configurable via `BUSINESS_HOURS_START/END` settings
