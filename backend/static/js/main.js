// HTML Elementlerini Seçme
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const talkButton = document.getElementById('talkButton');
const logsDiv = document.getElementById('logs');
const textInput = document.getElementById('text-input');
const sendTextButton = document.getElementById('send-text-button');

// Değişkenler
let websocket;
let mediaRecorder;
let audioChunks = [];
const WEBSOCKET_URL = "ws://localhost:8001/api/ws/v1/chat";

// WebSocket Baglantisini Yoneten Fonksiyon
function connectWebSocket() {
    logMessage("Sunucuya baglaniyor...", "log-system");
    websocket = new WebSocket(WEBSOCKET_URL);

    websocket.onopen = () => {
        updateStatus("Baglandi", "connected");
        talkButton.disabled = false;
        textInput.disabled = false;
        sendTextButton.disabled = false;
        logMessage("Baglanti basarili. Asistan hazir.", "log-system");
    };

    websocket.onmessage = (event) => {
        // Sunucudan gelen yanıt her zaman metin olacak
        const responseText = event.data;
        logMessage(`<strong>Asistan:</strong> ${responseText}`, "log-assistant");

        // Tarayıcının kendi TTS motoru ile metni seslendir
        const utterance = new SpeechSynthesisUtterance(responseText);
        utterance.lang = 'tr-TR'; // Dil ayarı
        window.speechSynthesis.speak(utterance);
    };

    websocket.onclose = (event) => {
        updateStatus("Baglanti kapandi", "disconnected");
        talkButton.disabled = true;
        textInput.disabled = true;
        sendTextButton.disabled = true;
        logMessage("Baglanti kesildi. 3 saniye icinde tekrar denenecek.", "log-system");
        console.log("WebSocket kapandi:", event);
        setTimeout(connectWebSocket, 3000);
    };

    websocket.onerror = (error) => {
        updateStatus("Baglanti Hatasi", "disconnected");
        console.error("WebSocket Hatasi: ", error);
        logMessage("Bir baglanti hatasi olustu.", "log-system");
    };
}

// Durum Göstergesini Güncelleyen Fonksiyon
function updateStatus(text, statusClass) {
    statusText.textContent = text;
    statusIndicator.className = statusClass;
}

// Log Alanına Mesaj Ekleyen Fonksiyon
function logMessage(message, className) {
    const entry = document.createElement('div');
    entry.className = `log-entry ${className}`;
    entry.innerHTML = `[${new Date().toLocaleTimeString()}] ${message}`;
    logsDiv.appendChild(entry);
    logsDiv.scrollTop = logsDiv.scrollHeight; // Otomatik aşağı kaydırma
}

// Metin Mesajını Gönderen Fonksiyon
function sendTextMessage() {
    const text = textInput.value.trim();
    if (text && websocket && websocket.readyState === WebSocket.OPEN) {
        logMessage(`<strong>Siz:</strong> ${text}`, "log-user");
        // Backend'in metin ve ses verisini ayırt edebilmesi için JSON formatında gönderiyoruz.
        const message = {
            type: "text",
            data: text
        };
        websocket.send(JSON.stringify(message));
        textInput.value = '';
    }
}

// Ses Kaydını Başlatan Fonksiyon
async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Mikrofon desteği bu tarayıcıda bulunmuyor.');
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        updateStatus("Dinliyor...", "listening");
        talkButton.classList.add('recording');
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.start();
        logMessage("<strong>Siz:</strong> (konuşuyorsunuz...)", "log-user");

        audioChunks = [];
        mediaRecorder.ondataavailable = event => {
            audioChunks.push(event.data);
        };
    } catch (err) {
        console.error("Mikrofon erişim hatası:", err);
        alert("Mikrofonu kullanabilmek için tarayıcıdan izin vermelisiniz.");
        updateStatus("Mikrofon Hatası", "disconnected");
    }
}

// Ses Kaydını Durduran ve Gönderen Fonksiyon
function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
        updateStatus("Isleniyor...", "connected");
        talkButton.classList.remove('recording');

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                // Backend'in metin ve ses verisini ayırt edebilmesi için Blob olarak gönderiyoruz.
                // Backend tarafı bu ikisini ayırt etmeli.
                websocket.send(audioBlob);
                logMessage("Ses verisi islenmek uzere gonderildi.", "log-system");
            }
            audioChunks = [];
        };
    }
}

// Olay Dinleyicileri
talkButton.addEventListener('mousedown', startRecording);
talkButton.addEventListener('mouseup', stopRecording);
talkButton.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
talkButton.addEventListener('touchend', (e) => { e.preventDefault(); stopRecording(); });

sendTextButton.addEventListener('click', sendTextMessage);
textInput.addEventListener('keypress', (event) => {
    if (event.key === 'Enter') {
        sendTextMessage();
    }
});

// Sayfa yüklendiğinde WebSocket bağlantısını başlat
window.onload = connectWebSocket;
