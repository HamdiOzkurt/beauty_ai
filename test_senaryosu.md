# Güzellik Merkezi Asistanı - Uçtan Uca Test Senaryosu

Bu dosya, sesli asistanın tüm yeteneklerini (araçlarını) manuel olarak test etmek için tasarlanmış bir konuşma akışı senaryosu içerir. Lütfen aşağıdaki adımları sırasıyla takip ederek asistanla konuşun ve beklenen yanıtları alıp almadığınızı kontrol edin.

**Önemli:**
- **Yeni Müşteri Senaryosu** için daha önce sisteme kaydetmediğiniz bir telefon numarası kullanın (örn: 0555 111 22 33).
- **Mevcut Müşteri Senaryosu** için bir önceki adımda kullandığınız numarayı tekrar kullanın.

---

### Bölüm 1: Genel Bilgi Alma ve Sorgulama

Bu bölümde asistanın bilgi verme ve listeleme yetenekleri test edilir.

**Adım 1.1: Kampanyaları Sorma**
- **Amaç:** `check_campaigns` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Merhabalar, herhangi bir kampanyanız var mı?"
- **🤖 Asistandan beklenen yanıt:** Aktif kampanyalar varsa bunları listelemeli, yoksa "Şu an aktif bir kampanyamız bulunmuyor" gibi bir yanıt vermelidir.

**Adım 1.2: Hizmetleri Listeleme**
- **Amaç:** `list_services` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Peki, hangi hizmetleriniz var?"
- **🤖 Asistandan beklenen yanıt:** Veritabanında kayıtlı olan tüm aktif hizmetleri saymalıdır (örn: "Saç kesimi, pedikür gibi hizmetlerimiz mevcut.").

**Adım 1.3: Uzmanları Listeleme**
- **Amaç:** `list_experts` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Saç kesimi için hangi uzmanlarınız var?"
- **🤖 Asistandan beklenen yanıt:** Sadece "saç kesimi" hizmetini veren uzmanları listelemelidir.

---

### Bölüm 2: Yeni Müşteri ve Randevu Oluşturma

Bu bölümde yeni bir müşteri için randevu oluşturma akışının tamamı test edilir.

**Adım 2.1: Müsaitlik Sorgulama**
- **Amaç:** `check_availability` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Harika. Haftaya salı günü saç kesimi için müsait misiniz?"
- **🤖 Asistandan beklenen yanıt:** Belirtilen gün için uygun saatleri ve o saatlerde müsait olan uzmanları listelemelidir.

**Adım 2.2: Randevu Başlatma ve Müşteri Yaratma**
- **Amaç:** `create_appointment` ve `create_new_customer` araçlarını tetiklemek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Tamamdır, saat 14:30'a Ayşe Hanım'a (veya listelenen bir uzman) randevu almak istiyorum."
- **🤖 Asistandan beklenen yanıt:** "Elbette, hangi telefon numarası için randevu oluşturuyoruz?" gibi bir soruyla telefon numaranızı istemelidir.

**Adım 2.3: Yeni Telefon Numarası Verme**
- **Amaç:** Yeni müşteri kaydını doğrulamak.
- **🗣️ Kullanıcı olarak siz söyleyin:** "(Sistemde kayıtlı olmayan bir numara söyleyin, örn: 0555 111 22 33)"
- **🤖 Asistandan beklenen yanıt:** "Bu numaraya ilk kez randevu oluşturuluyor. Adınız ve soyadınız nedir?" gibi bir soruyla isim istemelidir.

**Adım 2.4: İsim Verme ve Randevuyu Onaylama**
- **Amaç:** `create_appointment` aracının tamamlanması.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Ayşe Test."
- **🤖 Asistandan beklenen yanıt:** Randevu detaylarını özetleyip ("Ayşe Test adına, 0555 111 22 33 numarası için, haftaya salı 14:30'da Ayşe Hanım'a saç kesimi randevunuzu onaylıyor musunuz?") onay istemelidir.

**Adım 2.5: Onay**
- **🗣️ Kullanıcı olarak siz söyleyin:** "Evet, onaylıyorum."
- **🤖 Asistandan beklenen yanıt:** "Randevunuz başarıyla oluşturuldu. Randevu kodunuz: [KOD]. İyi günler dileriz." gibi bir onay mesajı vermelidir.

---

### Bölüm 3: Mevcut Müşteri ve Randevu Yönetimi

Bu bölümde daha önceden kaydedilmiş bir müşterinin işlemleri test edilir.

**Adım 3.1: Mevcut Randevuları Sorgulama**
- **Amaç:** `get_customer_appointments` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "İyi günler, 0555 111 22 33 numaralı telefonun randevularını öğrenebilir miyim?"
- **🤖 Asistandan beklenen yanıt:** Bir önceki adımda oluşturulan randevunun tarihini, saatini ve hizmetini doğru bir şekilde söylemelidir.

**Adım 3.2: Randevu İptali**
- **Amaç:** `cancel_appointment` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Bu randevumu iptal etmek istiyorum."
- **🤖 Asistandan beklenen yanıt:** "Randevunuzu iptal etmek istediğinizden emin misiniz?" diye onay istemeli.

**Adım 3.3: İptal Onayı**
- **🗣️ Kullanıcı olarak siz söyleyin:** "Evet, eminim."
- **🤖 Asistandan beklenen yanıt:** "Randevunuz başarıyla iptal edilmiştir." şeklinde bir onay mesajı vermelidir.

---

### Bölüm 4: Ekstra Araçların Testi

Bu bölümde daha az kullanılan ama önemli olan diğer araçlar test edilir.

**Adım 4.1: Tamamlayıcı Hizmet Önermesi**
- **Amaç:** `suggest_complementary_service` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Saç kesimi yaptırdıktan sonra başka ne önerirsiniz?"
- **🤖 Asistandan beklenen yanıt:** Saç kesimiyle alakalı veya alakasız başka hizmetler önermelidir (örn: "Saçınıza bakım yaptırmaya ne dersiniz? Veya manikür hizmetimiz de mevcut.").

**Adım 4.2: Alternatif Zaman Önermesi**
- **Amaç:** `suggest_alternative_times` aracını test etmek.
- **🗣️ Kullanıcı olarak siz söyleyin:** "Yarın sabah saat 8'e saç kesimi randevusu istiyorum." (Bu saatin dolu olduğunu varsayarak)
- **🤖 Asistandan beklenen yanıt:** "Maalesef o saatimiz dolu. Ancak size aynı gün içinde [SAAT] veya sonraki günler için [SAAT] gibi alternatifler önerebilirim." şeklinde dolu olduğu bilgisini ve alternatifleri sunmalıdır.
