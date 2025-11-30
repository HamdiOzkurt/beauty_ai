"""
Quick Pattern Matcher - Deterministik hazır cevaplar
LLM'e gitmeden basit soruları yakala ve cevapla
"""

import re
import logging
from typing import Optional, Dict, List

class QuickPatternMatcher:
    """
    Basit keyword/pattern matching ile hazır cevaplar döndürür.
    LLM'den önce çalışır, hız ve maliyet optimizasyonu sağlar.
    """

    # Pattern definitions - Her pattern için keywords ve response
    PATTERNS: Dict[str, Dict[str, any]] = {
        "greeting": {
            "keywords": [
                "merhaba", "selam", "selamun aleyküm", "aleykum selam",
                "iyi günler", "günaydın", "iyi akşamlar", "iyi sabahlar",
                "hey", "hi", "hello"
            ],
            "response": "İyi günler! Size nasıl yardımcı olabilirim?",
            "priority": 1  # Yüksek öncelik
        },

        "working_hours": {
            "keywords": [
                "saat kaç", "kaça kadar", "ne zaman açık", "çalışma saati",
                "açılış", "kapanış", "kaçta açılıyor", "kaçta kapanıyor",
                "mesai saati", "açık mı"
            ],
            "response": "09:00 - 19:00 arası hizmetinizdeyiz.",
            "priority": 2
        },

        "location": {
            "keywords": [
                "nerede", "adres", "konum", "nasıl gidilir", "nasıl gelirim",
                "harita", "yol tarifi", "neredesiniz"
            ],
            "response": "Adresimiz: İstanbul, Şişli. Size yol tarifi gönderebilirim.",
            "priority": 2
        },

        "goodbye": {
            "keywords": [
                "hoşça kal", "görüşürüz", "güle güle", "bay bay",
                "teşekkürler görüşürüz", "sağ ol görüşürüz"
            ],
            "response": "İyi günler! Sizi bekleriz.",
            "priority": 3
        },

        "thank_you": {
            "keywords": [
                "teşekkür", "sağ ol", "çok teşekkür", "teşekkürler",
                "ellerine sağlık", "Allah razı olsun"
            ],
            "response": "Rica ederim! Başka bir konuda yardımcı olabilir miyim?",
            "priority": 3
        }
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Compile regex patterns for better performance (opsiyonel)
        self._compile_patterns()

    def _compile_patterns(self):
        """
        Pattern'leri compile et (performance optimization)
        Şimdilik basit substring matching yeterli ama
        gelecekte regex'e geçebiliriz
        """
        pass

    def _normalize_text(self, text: str) -> str:
        """
        Metni normalize et:
        - Küçük harfe çevir
        - Fazla boşlukları temizle
        - Noktalama işaretlerini temizle

        NOT: Türkçe karakter dönüşümü YAPMA (ş -> s yapmıyoruz)
        çünkü keyword'ler zaten Türkçe karakterli tanımlı
        """
        if not text:
            return ""

        # Küçük harfe çevir
        text = text.lower()

        # Noktalama işaretlerini boşlukla değiştir (kelime sınırları korunsun)
        text = re.sub(r'[.,!?;:]', ' ', text)

        # Fazla boşlukları tek boşluğa indir
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def check(self, user_message: str, conversation_history: Optional[List[Dict]] = None) -> Optional[str]:
        """
        User message'ı pattern'lere karşı kontrol et.
        Eğer match varsa hazır cevabı döndür, yoksa None.

        Args:
            user_message: Kullanıcının mesajı
            conversation_history: Konuşma geçmişi (context için)

        Returns:
            Hazır cevap string veya None
        """
        if not user_message or not isinstance(user_message, str):
            return None

        normalized_message = self._normalize_text(user_message)

        # Eğer mesaj çok kısa ise (< 2 karakter), pattern'e bakma
        if len(normalized_message) < 2:
            return None

        # Match edilen pattern'leri topla (priority ile)
        matches = []

        for pattern_name, pattern_config in self.PATTERNS.items():
            keywords = pattern_config["keywords"]
            priority = pattern_config.get("priority", 10)

            # Keyword matching - herhangi bir keyword mesajda var mı?
            for keyword in keywords:
                keyword_normalized = keyword.lower()

                # Substring matching
                if keyword_normalized in normalized_message:
                    matches.append({
                        "pattern": pattern_name,
                        "response": pattern_config["response"],
                        "priority": priority,
                        "keyword": keyword
                    })
                    # İlk match yeterli, aynı pattern'in diğer keyword'lerine bakma
                    break

        # Eğer match yoksa
        if not matches:
            self.logger.debug(f"No quick pattern matched for: '{user_message}'")
            return None

        # Priority'ye göre sırala (düşük priority = yüksek öncelik)
        matches.sort(key=lambda x: x["priority"])

        # En yüksek öncelikli pattern'i seç
        best_match = matches[0]

        self.logger.info(
            f"✅ Quick pattern matched: '{best_match['pattern']}' "
            f"(keyword: '{best_match['keyword']}')"
        )

        return best_match["response"]

    def add_pattern(self, pattern_name: str, keywords: List[str], response: str, priority: int = 5):
        """
        Runtime'da yeni pattern ekle (extensibility)

        Args:
            pattern_name: Pattern'in adı
            keywords: Anahtar kelimeler
            response: Dönülecek cevap
            priority: Öncelik (düşük = yüksek öncelik)
        """
        self.PATTERNS[pattern_name] = {
            "keywords": keywords,
            "response": response,
            "priority": priority
        }

        self.logger.info(f"New pattern added: {pattern_name}")

    def remove_pattern(self, pattern_name: str) -> bool:
        """
        Pattern'i kaldır

        Returns:
            True if removed, False if not found
        """
        if pattern_name in self.PATTERNS:
            del self.PATTERNS[pattern_name]
            self.logger.info(f"Pattern removed: {pattern_name}")
            return True
        return False


# ============================================================================
# TEST & VALIDATION
# ============================================================================

if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.DEBUG)

    matcher = QuickPatternMatcher()

    test_cases = [
        ("merhaba", "greeting"),
        ("Merhaba nasılsınız?", "greeting"),
        ("saat kaça kadar açıksınız", "working_hours"),
        ("Neredesiniz?", "location"),
        ("teşekkürler", "thank_you"),
        ("randevu almak istiyorum", None),  # LLM'e gitmeli
        ("yarın saat 3", None)  # LLM'e gitmeli
    ]

    print("\n" + "="*50)
    print("QUICK PATTERN MATCHER TEST")
    print("="*50 + "\n")

    for message, expected_pattern in test_cases:
        result = matcher.check(message)
        status = "✅" if (result is not None) == (expected_pattern is not None) else "❌"
        print(f"{status} Input: '{message}'")
        print(f"   Result: {result}")
        print()
