"""
TTS Ses Profilleri - Hızlı Geçiş
"""

# Wavenet-A: Genç, dinamik, samimi kadın sesi (ÖNERİLEN)
VOICE_PROFILE_A = {
    "name": "tr-TR-Wavenet-A",
    "speaking_rate": 0.98,
    "pitch": 0.0,
    "description": "Genç, doğal, samimi - Güzellik salonu için ideal"
}

# Wavenet-E: Profesyonel, enerjik kadın sesi (HIZ OPTİMİZE)
VOICE_PROFILE_E = {
    "name": "tr-TR-Wavenet-E",
    "speaking_rate": 1.05,  # Daha hızlı konuşma
    "pitch": 0.1,  # Daha doğal ton
    "description": "Profesyonel, doğal, hızlı - Modern salon için (ÖNERİLEN)"
}

# Wavenet-D: Olgun, sıcak, güvenilir kadın sesi (EN DOĞAL)
VOICE_PROFILE_D = {
    "name": "tr-TR-Wavenet-D",
    "speaking_rate": 1.0,  # Normal hız
    "pitch": -0.1,  # Hafif düşük, sıcak ton
    "description": "EN DOĞAL: Sıcak, güvenilir, profesyonel kadın sesi - SABİT"
}

# Wavenet-C: Orta yaş, profesyonel kadın sesi
VOICE_PROFILE_C = {
    "name": "tr-TR-Wavenet-C",
    "speaking_rate": 0.97,
    "pitch": 0.0,
    "description": "Orta yaş, profesyonel, açık - Klinik için"
}

# AKTİF PROFIL - SABİT (DEĞIŞMEZ!)
ACTIVE_PROFILE = VOICE_PROFILE_D  # <-- Wavenet-D: En doğal, sıcak kadın sesi
