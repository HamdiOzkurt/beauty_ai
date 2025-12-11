// DOM Elements - v3.0 MODERN MIC ICON
const statusBadge = document.getElementById('statusBadge');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const voiceButton = document.getElementById('voiceButton');
const messagesDiv = document.getElementById('messages');

console.log('✅ main.js v3.0 loaded - Modern mic icon, optimized transcript');

// Variables
let websocket;
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let silenceTimeout;
let recordingStartTime = 0;
const WEBSOCKET_URL = "ws://localhost:8002/api/ws/v2/chat";
const SILENCE_DURATION = 2000; // 2 saniye sessizlik
const SILENCE_THRESHOLD = 3; // Sessizlik eşiği (daha yüksek = daha az hassas)
const MIN_RECORDING_DURATION = 500; // Minimum 500ms kayıt süresi

// WebSocket Connection
function connectWebSocket() {
    addMessage('system', 'Sunucuya bağlanıyor...');
    websocket = new WebSocket(WEBSOCKET_URL);

    websocket.onopen = () => {
        updateStatus('connected', 'Bağlı ✓');
        voiceButton.disabled = false;
        addMessage('system', 'Bağlantı başarılı! Konuşmaya başlayabilirsiniz.');
    };

    websocket.onmessage = (event) => {
        const response = event.data;

        // JSON mesaj mı kontrol et
        try {
            const data = JSON.parse(response);

            if (data.type === 'audio_received') {
                // Ses alındı bilgisi - görsel feedback
                console.log('🎤 Ses alındı, işleniyor...');
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
                return;
            } else if (data.type === 'audio') {
                // Backend2: TTS audio (base64)
                console.log('🔊 Audio alındı, çalınıyor...');
                playBase64Audio(data.content);
                return;
            } else if (data.type === 'stream_end') {
                // Streaming bitti
                console.log('✅ Stream tamamlandı');
                window.currentAssistantMessage = null;
                return;
            } else if (data.type === 'error') {
                // Hata mesajı
                console.error('❌ Hata:', data.content);
                addMessage('assistant', data.content);
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
        addMessage('system', 'Bağlantı kesildi. 3 saniye içinde yeniden denenecek...');
        setTimeout(connectWebSocket, 3000);
    };

    websocket.onerror = (error) => {
        updateStatus('disconnected', 'Bağlantı hatası');
        console.error('WebSocket error:', error);
        addMessage('system', 'Bağlantı hatası oluştu.');
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

// Voice Recording with auto-stop on silence
async function startRecording() {
    if (isRecording) {
        console.log('⏹️ Kayıt durduruluyor...');
        stopRecording();
        return;
    }

    console.log('🎙️ Kayıt başlatılıyor...');
    
    // Anında görsel feedback - butonu kayıt moduna al
    voiceButton.classList.add('recording');
    voiceButton.disabled = true; // İşlem bitene kadar disable et

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        // Buton artık aktif
        voiceButton.disabled = false;
        
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        isRecording = true;

        // Ses seviyesi analizi için AudioContext kullan
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 2048;
        source.connect(analyser);

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        // Sessizlik kontrolü
        const checkSilence = () => {
            if (!isRecording) return;

            analyser.getByteTimeDomainData(dataArray);
            
            // Ses seviyesini hesapla
            let sum = 0;
            for (let i = 0; i < bufferLength; i++) {
                const value = Math.abs(dataArray[i] - 128);
                sum += value;
            }
            const average = sum / bufferLength;

            // Eşik değerinden düşükse sessizlik
            if (average < SILENCE_THRESHOLD) {
                if (!silenceTimeout) {
                    silenceTimeout = setTimeout(() => {
                        if (isRecording) {
                            // Minimum kayıt süresini kontrol et
                            const recordingDuration = Date.now() - recordingStartTime;
                            if (recordingDuration < MIN_RECORDING_DURATION) {
                                console.log('Kayıt çok kısa, devam ediliyor...');
                                return;
                            }
                            console.log('Sessizlik algılandı, kayıt durduruluyor...');
                            stopRecording();
                            audioContext.close();
                        }
                    }, SILENCE_DURATION);
                }
            } else {
                // Ses var, timeout'u sıfırla
                if (silenceTimeout) {
                    clearTimeout(silenceTimeout);
                    silenceTimeout = null;
                }
            }

            requestAnimationFrame(checkSilence);
        };

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            sendAudioData(audioBlob);
            stream.getTracks().forEach(track => track.stop());
            audioContext.close();
            isRecording = false;
        };

        mediaRecorder.start();
        recordingStartTime = Date.now(); // Kayıt başlangıç zamanını kaydet
        console.log('✅ Kayıt aktif - konuşabilirsiniz!');
        
        // Sessizlik kontrolünü başlat
        checkSilence();

    } catch (error) {
        console.error('❌ Mikrofon erişim hatası:', error);
        addMessage('system', 'Mikrofon erişimi reddedildi veya kullanılamıyor.');
        isRecording = false;
        voiceButton.classList.remove('recording');
        voiceButton.disabled = false; // Hata durumunda butonu tekrar aktif et
    }
}

function stopRecording() {
    console.log('⏹️ Kayıt durduruluyor...');
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        voiceButton.classList.remove('recording');
        isRecording = false;
        if (silenceTimeout) {
            clearTimeout(silenceTimeout);
            silenceTimeout = null;
        }
        console.log('✅ Kayıt durduruldu');
    }
}

async function sendAudioData(audioBlob) {
    // Boş veya çok küçük ses dosyalarını gönderme
    if (audioBlob.size < 1000) {
        console.log('Ses kaydı çok kısa, gönderilmiyor.', audioBlob.size, 'bytes');
        return;
    }
    
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        const arrayBuffer = await audioBlob.arrayBuffer();
        websocket.send(arrayBuffer);
        console.log('Ses gönderildi:', audioBlob.size, 'bytes');
    } else {
        console.log('WebSocket bağlantısı yok. Lütfen bekleyin.');
    }
}

// Event Listeners - Click to toggle recording with immediate feedback
voiceButton.addEventListener('click', (e) => {
    e.preventDefault();
    console.log('🎤 Mikrofon butonu tıklandı, durum:', isRecording ? 'kayıt durduruluyor' : 'kayıt başlatılıyor');
    startRecording();
});

// Mousedown/touchstart ile anında görsel feedback
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

// Prevent context menu on long press
voiceButton.addEventListener('contextmenu', (e) => {
    e.preventDefault();
});

// Initialize
connectWebSocket();

// Base64 Audio Çalma Fonksiyonu (Backend2 için)
function playBase64Audio(base64Audio) {
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
        };

        audio.play();
        console.log('🔊 TTS audio çalınıyor');

    } catch (error) {
        console.error('Audio çalma hatası:', error);
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