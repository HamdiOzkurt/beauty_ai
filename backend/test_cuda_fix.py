"""
cuDNN düzeltme testi - bu scripti çalıştırarak test edin
"""

# ÖNCE cuda_setup import et
import cuda_setup

# Şimdi ctranslate2'yi test et
print("=" * 60)
print("cuDNN Test - ctranslate2 import ediliyor...")
print("=" * 60)

try:
    import ctranslate2
    print("✅ ctranslate2 başarıyla import edildi!")
    print(f"   Versiyon: {ctranslate2.__version__}")
    
    # Faster-whisper test
    print("\n🧪 faster-whisper test ediliyor...")
    from faster_whisper import WhisperModel
    print("✅ faster-whisper import edildi!")
    
    print("\n🎯 BAŞARILI! cuDNN sorunu çözüldü!")
    
except Exception as e:
    print(f"\n❌ HATA: {e}")
    import traceback
    traceback.print_exc()

print("=" * 60)
