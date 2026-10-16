# Frontend bakım notları

## Hata dayanıklılığı

- Bozuk API satırları geçerli sonuçları düşürmeden ayrılır.
- Geçersiz kaynak adresleri kanıt sayımına alınmaz.
- Bilinmeyen işlem durumları sonuç olarak gösterilmez.
- Tekrarlanan iddia kimlikleri ve özel karakterler bağlantı çakışmasına yol açmaz.
- Geçersiz takvim günleri tarih olarak gösterilmez.
- Sağlık hataları, iptal ve yanıt gövdesi zaman aşımı ayrı ele alınır.

## Arayüz

Tema ve hareket tercihleri dış kaynak abonelikleriyle izlenir. Örnek gösterimi, kısa ekranlarda animasyon başlamasını beklerken içeriği gizlemez. Renk, tipografi ve boşluk sistemi korunur.

## Doğrulama

Lint, TypeScript, birim/bileşen testleri ve üretim derlemesi kalite iş akışının parçalarıdır. Yerel doğrulamada 197 test başarılıdır. Örnek rapor 320, 768 ve 1440 piksel genişliklerinde, tema ve rapor navigasyonuyla birlikte kontrol edilmiştir.

Gerçek sağlayıcılara bağlanan uçtan uca analiz bu değişiklik kapsamında çalıştırılmadı. Backend geliştiricisinin benzersiz kaynak kimliklerini ve istemci iptalinden sonra sunucu işleminin davranışını ayrıca doğrulaması gerekir.
