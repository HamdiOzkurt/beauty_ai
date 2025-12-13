// DOM Elements - v4.0 GOOGLE CLOUD VAD - CONTINUOUS LISTENING
const statusBadge = document.getElementById('statusBadge');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const voiceButton = document.getElementById('voiceButton');
const messagesDiv = document.getElementById('messages');

console.log('✅ main.js v4.0 loaded - Google Cloud VAD, Continuous Listening, Auto Voice Detection');

// ============================================================================
// State Machine
// ============================================================================
const STATES = {
    LISTENING: 'listening',        // Kullanıcıyı dinliyor (mikrofon açık)
    PROCESSING: 'processing',      // Backend'de işleniyor
    SPEAKING: 'speaking',          // AI konuşuyor (mikrofon kapalı)
    IDLE: 'idle'                   // Başlangıç/durdurulmuş
};

// ============================================================================
// Variables
// ============================================================================
let websocket;
let mediaRecorder;
let audioChunks = [];
let currentState = STATES.IDLE;
let audioStream = null;
let audioContext = null;
let isSystemActive = false; // Sistem açık/kapalı
let processorNode = null;
const WEBSOCKET_URL = "ws://localhost:8002/api/ws/v2/chat";
const CHUNK_DURATION = 100; // 100ms chunks (Google Cloud optimal)
const SAMPLE_RATE = 16000; // Google Cloud requires 16kHz

// ============================================================================
// State Management
// ============================================================================
function setState(newState) {
    if (currentState === newState) return;

    console.log(`🔄 State: ${currentState} → ${newState}`);
    currentState = newState;

    // UI güncellemesi
    updateUIForState(newState);

    // State'e göre mikrofon kontrolü
    switch(newState) {
        case STATES.LISTENING:
            enableMicrophone();
            updateStatus('listening', '🎤 Dinliyorum...');
            break;
        case STATES.PROCESSING:
            disableMicrophone();
            updateStatus('processing', '⚙️ İşleniyor...');
            break;
        case STATES.SPEAKING:
            disableMicrophone();
            updateStatus('speaking', '🗣️ Konuşuyorum...');
            break;
        case STATES.IDLE:
            disableMicrophone();
            updateStatus('idle', '⏸️ Beklemede');
            break;
    }
}

function updateUIForState(state) {
    // Buton görünümünü güncelle
    voiceButton.className = 'voice-btn';

    switch(state) {
        case STATES.LISTENING:
            voiceButton.classList.add('listening');
            break;
        case STATES.PROCESSING:
            voiceButton.classList.add('processing');
            break;
        case STATES.SPEAKING:
            voiceButton.classList.add('speaking');
            break;
    }
}

function enableMicrophone() {
    if (audioStream) {
        audioStream.getAudioTracks().forEach(track => {
            track.enabled = true;
        });
        console.log('✅ Mikrofon açıldı');
    }
}

function disableMicrophone() {
    if (audioStream) {
        audioStream.getAudioTracks().forEach(track => {
            track.enabled = false;
        });
        console.log('🔇 Mikrofon kapatıldı (echo prevention)');
    }
}

// ============================================================================
// WebSocket Connection
// ============================================================================
function connectWebSocket() {
    addMessage('system', 'Sunucuya bağlanıyor...');
    websocket = new WebSocket(WEBSOCKET_URL);

    websocket.onopen = () => {
        updateStatus('connected', 'Bağlı ✓');
        voiceButton.disabled = false;
        addMessage('system', 'Bağlantı başarılı! Butona basarak sistemi aktif edin.');

        // Continuous listening'i başlatmaya hazır
        setState(STATES.IDLE);
    };

    websocket.onmessage = (event) => {
        const response = event.data;

        // JSON mesaj mı kontrol et
        try {
            const data = JSON.parse(response);

            if (data.type === 'vad_speech_start') {
                // Google Cloud VAD: Konuşma başladı (görsel feedback only)
                console.log('🎤 VAD: Konuşma algılandı');
                // State değiştirme - mikrofon açık kalsın!
                return;
            } else if (data.type === 'vad_speech_end') {
                // Google Cloud VAD: Konuşma bitti
                console.log('🎤 VAD: Konuşma bitti');
                return;
            } else if (data.type === 'transcript' || data.type === 'transcription') {
                // Kullanıcı mesajını HEMEN göster
                const text = data.text || data.content;
                addMessage('user', text);
                console.log('📝 Transcript alındı:', text);
                return;
            } else if (data.type === 'text') {
                // Backend2: AI text response
                addMessage('assistant', data.content);
                console.log('🤖 AI yanıtı:', data.content);
                setState(STATES.SPEAKING); // AI konuşmaya başlayacak
                return;
            } else if (data.type === 'audio') {
                // Backend2: TTS audio (base64)
                console.log('🔊 Audio alındı, çalınıyor...');
                playBase64Audio(data.content, () => {
                    // Audio bitince LISTENING moduna dön
                    if (isSystemActive) {
                        setState(STATES.LISTENING);
                    }
                });
                return;
            } else if (data.type === 'stream_end') {
                // Streaming bitti - state değişikliği audio.onended tarafından yönetilecek.
                console.log('✅ Stream tamamlandı');
                window.currentAssistantMessage = null;
                // HATALI KOD KALDIRILDI: Sesin bitmesini beklemeden durumu değiştiren
                // setTimeout fonksiyonu burada yer alıyordu. Artık sadece audio.onended
                // durumu tekrar LISTENING'e çevirecek.
                return;
            } else if (data.type === 'error') {
                // Hata mesajı
                console.error('❌ Hata:', data.content);
                addMessage('assistant', data.content);
                setState(STATES.LISTENING); // Hatadan sonra tekrar dinle
                return;
            }
        } catch (e) {
            // JSON değilse normal streaming chunk (backend v1 için)
            if (!window.currentAssistantMessage) {
                window.currentAssistantMessage = addMessage('assistant', '', true);
            }
            appendToMessage(window.currentAssistantMessage, response);
        }
    };

    websocket.onclose = () => {
        updateStatus('disconnected', 'Bağlantı koptu');
        voiceButton.disabled = true;
        stopContinuousListening();
        addMessage('system', 'Bağlantı kesildi. 3 saniye içinde yeniden denenecek...');
        setTimeout(connectWebSocket, 3000);
    };

    websocket.onerror = (error) => {
        updateStatus('disconnected', 'Bağlantı hatası');
        console.error('WebSocket error:', error);
        addMessage('system', 'Bağlantı hatası oluştu.');
        stopContinuousListening();
    };
}

// Update Status
function updateStatus(status, text) {
    if (statusDot) {
        statusDot.className = `status-dot ${status}`;
    }
    if (statusText) statusText.textContent = text;
}

// Add Message
function addMessage(type, content, isStreaming = false) {
    // Sistem mesajlarını gösterme (sadece console'a yaz)
    if (type === 'system') {
        console.log('[SYSTEM]', content);
        return;
    }

    // Remove welcome message on first real message
    const welcome = messagesDiv.querySelector('.welcome-message');
    if (welcome) {
        welcome.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';
    bubbleDiv.textContent = content;
    
    // Saat bilgisi ekle (Saat:Dakika:Saniye)
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    timeDiv.textContent = `${hours}:${minutes}:${seconds}`;
    
    messageDiv.appendChild(bubbleDiv);
    messageDiv.appendChild(timeDiv);
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    // Streaming mode için referans döndür
    if (isStreaming) {
        return { messageDiv, bubbleDiv };
    }
}

// Append text to existing message (for streaming)
function appendToMessage(messageRef, text) {
    if (!messageRef || !messageRef.bubbleDiv) return;
    
    messageRef.bubbleDiv.textContent += text;
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// ============================================================================
// Continuous Audio Streaming (Google Cloud VAD)
// ============================================================================
async function startContinuousListening() {
    if (isSystemActive) {
        console.log('⏹️ Sistem durduruluyor...');
        stopContinuousListening();
        return;
    }

    console.log('🎙️ Continuous listening başlatılıyor...');

    try {
        // Mikrofon izni al
        audioStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: SAMPLE_RATE,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        // AudioContext oluştur
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: SAMPLE_RATE
        });

        const source = audioContext.createMediaStreamSource(audioStream);

        // ScriptProcessor ile audio chunks gönder
        const bufferSize = 4096;
        processorNode = audioContext.createScriptProcessor(bufferSize, 1, 1);

        processorNode.onaudioprocess = (e) => {
            if (!isSystemActive || currentState !== STATES.LISTENING) {
                return; // LISTENING state'de değilse ses gönderme
            }

            // Audio data'yı al
            const inputData = e.inputBuffer.getChannelData(0);

            // RMS (Root Mean Square) hesapla - ses seviyesi
            let sum = 0;
            for (let i = 0; i < inputData.length; i++) {
                sum += inputData[i] * inputData[i];
            }
            const rms = Math.sqrt(sum / inputData.length);

            // REMOVED: RMS_THRESHOLD
            // Google Cloud STT backend'de VAD yapıyor! Pause'lar da ses sinyali!
            // Tüm audio chunks'ları gönder, Google STT intelligently handles silence
            // Eğer hiç filter yapmazsan pause'larda boş frames alıyor ki bu natural segmentation sağlıyor

            // Float32Array'i Int16Array'e çevir (Google Cloud format)
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                const s = Math.max(-1, Math.min(1, inputData[i]));
                pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            // WebSocket üzerinden gönder
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(pcmData.buffer);
            }
        };

        source.connect(processorNode);
        processorNode.connect(audioContext.destination);

        isSystemActive = true;
        setState(STATES.LISTENING);

        console.log('✅ Continuous listening aktif - konuşabilirsiniz!');
        voiceButton.textContent = '⏸️';
        addMessage('system', 'Sistem aktif! Konuşmaya başlayın.');

    } catch (error) {
        console.error('❌ Mikrofon erişim hatası:', error);
        addMessage('system', 'Mikrofon erişimi reddedildi. Lütfen tarayıcı izinlerini kontrol edin.');
        isSystemActive = false;
        setState(STATES.IDLE);
    }
}

function stopContinuousListening() {
    console.log('⏹️ Continuous listening durduruluyor...');

    if (processorNode) {
        processorNode.disconnect();
        processorNode = null;
    }

    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
        audioStream = null;
    }

    isSystemActive = false;
    setState(STATES.IDLE);
    voiceButton.textContent = '🎤';

    console.log('✅ Sistem durduruldu');
}

// ============================================================================
// Event Listeners - Toggle continuous listening
// ============================================================================
voiceButton.addEventListener('click', (e) => {
    e.preventDefault();
    console.log('🎤 Buton tıklandı, sistem durumu:', isSystemActive ? 'durduruluyor' : 'başlatılıyor');
    startContinuousListening();
});

// Visual feedback
voiceButton.addEventListener('mousedown', () => {
    voiceButton.style.transform = 'scale(0.95)';
});

voiceButton.addEventListener('mouseup', () => {
    voiceButton.style.transform = 'scale(1)';
});

voiceButton.addEventListener('touchstart', () => {
    voiceButton.style.transform = 'scale(0.95)';
});

voiceButton.addEventListener('touchend', () => {
    voiceButton.style.transform = 'scale(1)';
});

// Prevent context menu
voiceButton.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});

// Initialize
connectWebSocket();

// ============================================================================
// Audio Playback (TTS)
// ============================================================================
function playBase64Audio(base64Audio, onEnded) {
    try {
        // Base64'ü binary'ye çevir
        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // Audio blob oluştur ve çal
        const audioBlob = new Blob([bytes], { type: 'audio/mp3' });
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);

        audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            console.log('🔊 TTS audio bitti');

            // Callback çağır (state'i LISTENING'e döndürmek için)
            if (onEnded) {
                onEnded();
            }
        };

        audio.play();
        console.log('🔊 TTS audio çalınıyor');

    } catch (error) {
        console.error('Audio çalma hatası:', error);

        // Hata olsa bile callback çağır
        if (onEnded) {
            onEnded();
        }
    }
}

// Google TTS Fonksiyonu (Backend v1 için - fallback)
async function playGoogleTTS(text) {
    try {
        const response = await fetch(`/api/tts?text=${encodeURIComponent(text)}`, {
            method: 'POST'
        });

        if (!response.ok) {
            console.error('TTS hatası:', response.statusText);
            return;
        }

        // Audio blob al ve çal
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);

        audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
        };

        audio.play();
        console.log('🎤 Google TTS çalınıyor');

    } catch (error) {
        console.error('TTS çalma hatası:', error);
    }
}