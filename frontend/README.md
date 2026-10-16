# verify frontend

Türkçe haber ve iddia inceleme arayüzü. Sonuçlar; açıklama, kaynak bağlantıları ve incelemenin sınırlarıyla birlikte gösterilir.

## Teknolojiler

- Next.js App Router, React ve TypeScript
- CSS değişkenleriyle tanımlanan renk, tipografi ve boşluk sistemi
- Yerel fontlar; açık/koyu tema ve azaltılmış hareket desteği
- Node.js test çalıştırıcısı, ESLint ve GitHub Actions

## Geliştirme

Node.js 20.9 veya üzeri gereklidir. Komutları bu klasörde çalıştırın:

```sh
npm ci
npm run dev
```

Uygulama varsayılan olarak `http://localhost:3000` adresinde açılır.

Gerçek servise bağlanmak için `.env.example` dosyasını `.env.local` olarak kopyalayın ve `NEXT_PUBLIC_API_BASE_URL` değerini ayarlayın. Gizli API anahtarları frontend'e eklenmez. Bu değişken yayın derlemesine gömüldüğünden adres değişikliğinde yeniden derleme gerekir.

Servis adresi tanımlı değilken geliştirme ortamında mock veriler kullanılır. Üretim derlemesinde canlı inceleme kapalıdır; hazır örnek rapor erişilebilir kalır. Mock sonuçları ve hazır örnek, canlı analizden açıkça ayrılır.

## Kalite kontrolleri

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

Monorepo için otomatik kontroller kökteki `.github/workflows/frontend-ci.yml` dosyasında tanımlıdır. Bu iş akışı yalnızca frontend değişikliklerinde çalışır ve yayınlama yapmaz.

TypeScript 7'nin `tsc` derleyicisi `@typescript/native` takma adıyla kullanılır. ESLint'in gerektirdiği derleyici API'si, `typescript` adıyla kurulan TypeScript 6 uyumluluk paketiyle sağlanır. Ayrıntılar: [Microsoft TypeScript uyumluluk rehberi](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/#running-side-by-side-with-typescript-6.0).

## Klasör yapısı

| Klasör | Sorumluluk |
| --- | --- |
| `app/` | Sayfalar, metadata, fontlar ve genel CSS |
| `components/` | Form, rapor, kaynaklar, navigasyon ve ortak bileşenler |
| `hooks/` | İstek yaşam döngüsü ve analiz durumu |
| `lib/api/` | Servis istemcisi, yanıt doğrulama ve mock veriler |
| `lib/` | Girdi, tarih, atıf ve rapor yardımcıları |
| `tests/` | Birim, sözleşme ve bileşen testleri |

## Davranış ve güvenlik

- API istemcisi `GET /health` ve `POST /verify` uç noktalarını kullanır. Bağlantıyla inceleme yalnızca servis desteklediğinde sunulur.
- Bozuk satırlar geçerli sonuçlardan ayrılır; geçerli sonuç kalmadığında hata gösterilir. İncelenemeyen iddialara hüküm üretilmez.
- Kaynak adresleri HTTP/HTTPS ile sınırlıdır. Açıklamalar React metin düğümleriyle çizilir; kaynak metni HTML olarak çalıştırılmaz.
- İptal ve zaman aşımı tüm istek yaşam döngüsünde uygulanır. İstemci iptali, sunucudaki işlemin mutlaka durduğunu garanti etmez.
- Raporlar frontend'de kalıcı saklanmaz. Tema tercihi tarayıcıda tutulur. Canlı servislerin veri işleme koşulları gizlilik sayfasında ayrıca açıklanır.
- `/ornek/apollo-11` kaynaklı hazır rapordur. Kopyalama ve yazdırma araçları tarayıcıda çalışır.

API ayrıntıları: [API sözleşmesi](docs/API_CONTRACT.md). Bakım notları: [Frontend düzeltmeleri](docs/FRONTEND_FIXES.md).
