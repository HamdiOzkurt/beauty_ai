"""
Test Orchestrator V4 - Test Senaryosu ile
test_senaryosu.md dosyasındaki soruları kullanarak V4'ü test eder
"""

import asyncio
import sys
import logging

# Encoding fix for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add backend to path
sys.path.insert(0, ".")

from agents.orchestrator_v4 import OrchestratorV4

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Test senaryosu soruları
TEST_SCENARIOS = [
    {
        "section": "Bölüm 1: Genel Bilgi Alma ve Sorgulama",
        "tests": [
            {
                "name": "Adım 1.1: Kampanyaları Sorma",
                "user_input": "Merhabalar, herhangi bir kampanyanız var mı?",
                "expected_tool": "check_campaigns",
                "expected_behavior": "Kampanya bilgisi vermeli"
            },
            {
                "name": "Adım 1.2: Hizmetleri Listeleme",
                "user_input": "Peki, hangi hizmetleriniz var?",
                "expected_tool": "list_services",
                "expected_behavior": "Hizmetleri listelemeli"
            },
            {
                "name": "Adım 1.3: Uzmanları Listeleme",
                "user_input": "Saç kesimi için hangi uzmanlarınız var?",
                "expected_tool": "list_experts",
                "expected_behavior": "Saç kesimi uzmanlarını listelemeli"
            }
        ]
    },
    {
        "section": "Bölüm 2: Yeni Müşteri ve Randevu Oluşturma",
        "tests": [
            {
                "name": "Adım 2.1: Müsaitlik Sorgulama",
                "user_input": "Harika. Haftaya salı günü saç kesimi için müsait misiniz?",
                "expected_tool": "check_availability",
                "expected_behavior": "Müsait saatleri göstermeli"
            },
            {
                "name": "Adım 2.2: Randevu Başlatma",
                "user_input": "Tamamdır, saat 14:30'a randevu almak istiyorum.",
                "expected_tool": "check_availability",
                "expected_behavior": "Müsaitlik bilgisi vermeli"
            },
            {
                "name": "Adım 2.3: Telefon Verme (Yeni Müşteri)",
                "user_input": "0555 111 22 33",
                "expected_tool": "create_new_customer",
                "expected_behavior": "İsim soyisim istemeli"
            },
            {
                "name": "Adım 2.4: İsim Verme",
                "user_input": "Ayşe Test",
                "expected_tool": "confirm",
                "expected_behavior": "Randevu onayı istemeli"
            },
            {
                "name": "Adım 2.5: Onay",
                "user_input": "Evet, onaylıyorum",
                "expected_tool": "create_appointment",
                "expected_behavior": "Randevu kodu vermeli"
            }
        ]
    },
    {
        "section": "Bölüm 3: Mevcut Müşteri ve Randevu Yönetimi",
        "tests": [
            {
                "name": "Adım 3.1: Randevuları Sorgulama",
                "user_input": "İyi günler, 0555 111 22 33 numaralı telefonun randevularını öğrenebilir miyim?",
                "expected_tool": "get_customer_appointments",
                "expected_behavior": "Randevuları listelemeli"
            },
            {
                "name": "Adım 3.2: Randevu İptali",
                "user_input": "Bu randevumu iptal etmek istiyorum.",
                "expected_tool": "confirm",
                "expected_behavior": "İptal onayı istemeli"
            },
            {
                "name": "Adım 3.3: İptal Onayı",
                "user_input": "Evet, eminim.",
                "expected_tool": "cancel_appointment",
                "expected_behavior": "İptal onayı vermeli"
            }
        ]
    },
    {
        "section": "Bölüm 4: Ekstra Araçların Testi",
        "tests": [
            {
                "name": "Adım 4.1: Tamamlayıcı Hizmet Önermesi",
                "user_input": "Saç kesimi yaptırdıktan sonra başka ne önerirsiniz?",
                "expected_tool": "suggest_complementary_service",
                "expected_behavior": "Tamamlayıcı hizmet önermeli"
            },
            {
                "name": "Adım 4.2: Alternatif Zaman Önermesi",
                "user_input": "Yarın sabah saat 8'e saç kesimi randevusu istiyorum.",
                "expected_tool": "suggest_alternative_times",
                "expected_behavior": "Alternatif saatler önermeli (8:00 dolu ise)"
            }
        ]
    }
]


async def run_single_test(orchestrator, session_id, test_data):
    """Tek bir test adımını çalıştır ve içeriği validate et"""
    print(f"\n{'='*70}")
    print(f"TEST: {test_data['name']}")
    print(f"{'='*70}")
    print(f"[USER]: {test_data['user_input']}")

    try:
        response = await orchestrator.process_request(
            session_id=session_id,
            user_message=test_data['user_input'],
            websocket=None
        )

        print(f"\n[ASSISTANT]: {response}")
        print(f"\n[EXPECTED]: {test_data['expected_behavior']}")
        print(f"[EXPECTED TOOL]: {test_data['expected_tool']}")

        # İçerik validasyonu
        validation_result = validate_response_content(
            response=response,
            expected_tool=test_data['expected_tool'],
            expected_behavior=test_data['expected_behavior']
        )

        if validation_result["valid"]:
            print(f"[VALIDATION]: PASS - {validation_result['reason']}")
        else:
            print(f"[VALIDATION]: FAIL - {validation_result['reason']}")

        # Kısa bekleme (gerçek konuşma simülasyonu)
        await asyncio.sleep(0.5)

        return {
            "test_name": test_data['name'],
            "success": validation_result["valid"],
            "response": response,
            "validation_reason": validation_result["reason"]
        }

    except Exception as e:
        print(f"\n[ERROR]: {str(e)}")
        logging.error(f"Test failed: {e}", exc_info=True)
        return {
            "test_name": test_data['name'],
            "success": False,
            "error": str(e),
            "validation_reason": "Exception occurred"
        }


def validate_response_content(response: str, expected_tool: str, expected_behavior: str) -> dict:
    """
    Response içeriğini validate et - sadece HTTP 200 değil, gerçek içerik kontrolü.

    Returns:
        {"valid": bool, "reason": str}
    """
    response_lower = response.lower()

    # Boş yanıt kontrolü
    if not response or len(response.strip()) < 5:
        return {"valid": False, "reason": "Yanıt boş veya çok kısa"}

    # Tool-specific validations
    validations = {
        "check_campaigns": {
            "keywords": ["kampanya", "indirim", "fırsat", "promosyon", "bulunmuyor"],
            "reason": "Kampanya bilgisi içermeli"
        },
        "list_services": {
            "keywords": ["hizmet", "saç", "kesim", "pedikür", "manikür"],
            "reason": "Hizmet listesi içermeli"
        },
        "list_experts": {
            "keywords": ["uzman", "ayşe", "mehmet", "fatma", "personel", "kim", "çalış"],
            "reason": "Uzman isimleri veya uzman bilgisi içermeli"
        },
        "check_availability": {
            "keywords": ["müsait", "boş", "saat", "tarih", "uygun", "dolu"],
            "reason": "Müsaitlik bilgisi içermeli"
        },
        "ask_missing (phone)": {
            "keywords": ["telefon", "numara", "hangi numara"],
            "reason": "Telefon numarası sorusu içermeli"
        },
        "create_new_customer": {
            "keywords": ["ad", "isim", "soyad", "soy isim"],
            "reason": "İsim soyisim sorusu içermeli"
        },
        "confirm": {
            "keywords": ["onay", "emin", "doğru", "randevu", "iptal"],
            "reason": "Onay sorusu içermeli"
        },
        "create_appointment": {
            "keywords": ["randevu", "oluştur", "kod", "rnv", "bekli"],
            "reason": "Randevu kodu veya onay içermeli"
        },
        "get_customer_appointments": {
            "keywords": ["randevu", "tarih", "saat", "bulunmuyor", "kayıtlı"],
            "reason": "Randevu bilgisi veya 'bulunmuyor' içermeli"
        },
        "cancel_appointment": {
            "keywords": ["iptal", "edildi", "vazgeç"],
            "reason": "İptal onayı içermeli"
        },
        "suggest_complementary_service": {
            "keywords": ["öneri", "hizmet", "bakım", "tamamla"],
            "reason": "Hizmet önerisi içermeli"
        },
        "suggest_alternative_times": {
            "keywords": ["alternatif", "başka", "saat", "dolu", "müsait"],
            "reason": "Alternatif saat önerisi içermeli"
        }
    }

    # Expected tool'a göre validation yap
    if expected_tool in validations:
        validation = validations[expected_tool]
        keywords = validation["keywords"]

        # En az bir keyword eşleşmeli
        if any(keyword in response_lower for keyword in keywords):
            return {"valid": True, "reason": f"İçerik doğru: {validation['reason']}"}
        else:
            return {
                "valid": False,
                "reason": f"İçerik eksik. Beklenen: {validation['reason']}, Keywords: {keywords}"
            }

    # Generic validation (tool mapping yoksa)
    if len(response) > 10:
        return {"valid": True, "reason": "Genel validation geçti (tool mapping yok)"}

    return {"valid": False, "reason": "Validation kriteri bulunamadı"}


async def run_section_tests(orchestrator, section_data, session_base):
    """Bir bölümdeki tüm testleri çalıştır"""
    print(f"\n\n{'#'*80}")
    print(f"# {section_data['section']}")
    print(f"{'#'*80}\n")

    # Her bölüm için yeni session (temiz başlangıç)
    session_id = f"{session_base}_{section_data['section'].split(':')[0].replace(' ', '_')}"

    results = []
    for test in section_data['tests']:
        result = await run_single_test(orchestrator, session_id, test)
        results.append(result)

    return results


async def main():
    """Ana test fonksiyonu"""
    print("\n" + "="*80)
    print("ORCHESTRATOR V4 - TEST SENARYOSU")
    print("test_senaryosu.md dosyasındaki soruları kullanarak test ediliyor")
    print("="*80 + "\n")

    # Orchestrator V4'ü başlat
    print("[INFO] OrchestratorV4 başlatılıyor...")
    conversations = {}
    orchestrator = OrchestratorV4(conversations)
    print("[OK] OrchestratorV4 hazır!\n")

    # Tüm test sonuçları
    all_results = []

    # Her bölümü sırayla çalıştır
    for section in TEST_SCENARIOS:
        section_results = await run_section_tests(
            orchestrator,
            section,
            session_base="test_scenario"
        )
        all_results.extend(section_results)

    # Özet rapor
    print("\n\n" + "="*80)
    print("TEST SONUÇLARI ÖZETİ")
    print("="*80)

    total = len(all_results)
    success = sum(1 for r in all_results if r['success'])
    failed = total - success

    print(f"\nToplam Test: {total}")
    print(f"[OK] Başarılı: {success}")
    print(f"[FAIL] Başarısız: {failed}")
    print(f"Başarı Oranı: {(success/total)*100:.1f}%")

    # Başarısız testleri listele
    if failed > 0:
        print("\n[FAIL] Başarısız Testler:")
        for r in all_results:
            if not r['success']:
                error_msg = r.get('error', r.get('validation_reason', 'Unknown error'))
                print(f"  - {r['test_name']}")
                print(f"    Sebep: {error_msg}")
    else:
        print("\n[OK] Tüm testler başarılı!")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
