# Verify backend v2

`POST /verify` ve `POST /verify/stream` JSON/SSE sözleşmelerini korur.
`GET /health` sağlayıcı çağırmayan liveness kontrolüdür; HTTP 200 içindeki
`status=degraded` yapılandırmanın hazır olmadığını belirtir. Gerçek sağlayıcı
başarısını kanıtlamaz. İç başlangıç hataları yayınlanmaz. `/health/deep` her
ortamda 404; üretimde `/docs`, `/redoc`, `/openapi.json` kapalıdır.

## Yerel çalıştırma ve test

Repo kökünde, tercihen ayrı venv içinde:

```powershell
python -m pip install -r backend_v2/requirements-test.txt
python -m pytest backend_v2/tests -q
cd backend_v2
uvicorn app.main:app --workers 1 --no-proxy-headers --no-access-log
```

`.env.example` şablondur; anahtarları yerel ortamdan sağlayın, Git'e eklemeyin.
Testler mock kullanır; yeni HTTP testleri dış socket bağlantısını da engeller.
Windows asyncio iç loopback socketpair bağlantısına izin verilir.
API hata ayrıntısı her ortamda kapalıdır; `EXPOSE_ERROR_DETAIL` public API'de
artık etkili değildir. AI/retrieval/pipeline mantığı değiştirilmemiştir.

## Kapasite ve güvenlik

- `MAX_ACTIVE_VERIFICATIONS=2`: endpoint'ler ortak kapasite kullanır. Doluysa
  429 `BUSY`, `Retry-After: 1`. Hata/timeout/disconnect sonrasında çalışan sync
  thread varsa gerçekten bitene kadar slot tutulur. Lifespan'da kurulan
  `TrackingExecutor`, mevcut adapter `asyncio.to_thread` çağrılarını izler.
- `MAX_BACKGROUND_THREADS=8` dış executor sınırıdır; retrieval iç havuzları
  nedeniyle toplam thread sayısına hard limit değildir. İç havuzların kapanmasını
  dış thread bekler. Takılan thread zorla öldürülmez, slotu tutmaya devam eder.
- `MAX_RSS_MB=384`: kabul anındaki RSS yüksekse veya ölçülemiyorsa 503
  `LOW_MEMORY`, `Retry-After: 30`. Bu işletim sistemi RAM sınırı değildir;
  devam eden işin ani bellek artışı OOM oluşturabilir. Container limiti ve gerçek
  yük testi ayrıca gerekir. Loglarda RSS ve OS process peak MiB ölçülür.
- Ortak IP kotaları: `RATE_LIMIT_PER_MINUTE=10`, `HOURLY_QUOTA=100`,
  `DAILY_QUOTA=500`; süreç geneli `GLOBAL_DAILY_QUOTA=1000`. UTC epoch tabanlı
  sabit pencere kullanılır; sınırda iki kat burst mümkündür. Red yanıtı 429
  `RATE_LIMITED`, `Retry-After` kalan pencere süresidir. Hatalı/BUSY denemeleri
  kota tüketir. İstek sayısı token veya kredi bütçesi değildir.
- `MAX_TRACKED_CLIENTS=10000`: tablo dolunca yeni IP fail-closed reddedilir.
  Sayaçlar yeniden başlamada sıfırlanır. **Çoklu worker/replica ortak sayaç
  tutmaz**; kapasite ve kota süreç başınadır. Ölçekleme için ortak atomik
  sayaç deposu gerekir; bu çalışma onu eklemez. Tek worker kullanın.
- Gövde Content-Length'e güvenilmeden, chunked dahil 65536 byte ile sınırlıdır.
  Ingress slow-client/bağlantı limitleri ayrıca yapılandırılmalıdır.
- `TRUSTED_PROXY_CIDRS` boşsa X-Forwarded-For yok sayılır. Doğrudan peer
  güvenilir ise zincirde sağdan sola ilk güvenilmeyen IP kullanılır. Uvicorn
  proxy dönüşümü kapalı kalmalıdır. Render ingress CIDR ve header temizleme
  davranışını doğrulamadan geniş CIDR eklemeyin. Aksi halde spoofing veya tüm
  kullanıcıların tek kotaya düşmesi mümkündür. NAT kullanıcıları kotayı paylaşır.
- `CORS_ORIGINS` virgülle ayrılmış tam origin listesidir; üretim yalnız HTTPS
  kabul eder. CORS kimlik doğrulama değildir. `X-Request-ID` sunucuda üretilir;
  istemci değeri kullanılmaz. CORS expose headers: `X-Request-ID`, `Retry-After`.
- Güvenli loglar ID, durum, RSS, peak ve aktif sayısını içerir; gövde, IP,
  query, anahtar ve traceback içermez. Eski adapter logları merkezi filtreyle
  genel mesaja dönüştürülür; HTTP URL erişim logları kapatılır.

## Docker ve Render — canlıya uygulanmadı

```powershell
docker build -f backend_v2/Dockerfile -t verify-backend .
docker run --rm -p 8000:8000 --memory=512m --env-file backend_v2/.env verify-backend
```

Context repo kökü, Dockerfile `backend_v2/Dockerfile`. Dockerfile'a özgü ignore
dosyası `.env`, Git ve yerel bağımlılıkları dışlar. UID 10001 ve HEALTHCHECK
eklenmiştir. Doğrudan Python bağımlılıkları yereldeki sürümlere sabitlenmiştir;
transitif bağımlılıkların tamamı kilitli değildir. Docker Python 3.12 kullanır;
yerel Python farklı olduğundan container build ve smoke testi ayrıca gereklidir.

`backend_v2/render.yaml` Blueprint taslağıdır. Blueprint Path bu dosya, repo
`MertBulut11/verify-v2`, branch `fatih/api-security`. Root Directory boş,
Docker Context `.`, Dockerfile Path `backend_v2/Dockerfile`, Health Check
`/health`. Otomatik deploy kapalıdır. Mevcut servise uygulamadan önce taslağın
yeni servis oluşturmadığını kontrol edin. Anahtarları panelde secret ortam
değişkeni olarak girin. Gerçek frontend origin ve doğrulanmış ingress CIDR gerekir.
Panelde değişiklik yapılmadı; Git gönderimi/deploy öncesi açık onay gereklidir.

Cold-start: offline stub sağlayıcılarla container başlatıp başlangıçtan ilk health
200'e süreyi ve ilk mock verify süresini ayrı ölçün. Onaylı Render deploy sonrası
pasif durumdan ilk health yanıtına en az 5 ölçüm alın; medyan/p95, plan, commit,
RSS/peak kaydedin. Health kredisi tüketmez; gerçek verify için ayrıca onay gerekir.
Bu çalışma canlı cold-start sonucu iddia etmez.

Rollback: mevcut başarılı deploy ID/commit ve secretsiz ayar envanterini kaydedin.
Onay sonrası Render Events'ten önceki başarılı deploy'a dönün; health, CORS ve
endpoint gizliliğini kontrol edin. Ortam ayarlarının otomatik döndüğünü
varsaymayın, ayrı doğrulayın. Otomatik deploy kapalı kalsın.
[Docker](https://render.com/docs/docker),
[Blueprint](https://render.com/docs/blueprint-spec),
[Rollback](https://render.com/docs/rollbacks).

## Groq ve Tavily bütçe işlemleri — hesap değişikliği yapılmadı

Groq [Spend Limits](https://console.groq.com/docs/spend-limits): ücretli katmanda
organization owner aylık ortak harcama limiti/uyarı ayarlayabilir. Takip 10–15
dakika gecikebilir; sıfır aşım garantisi değildir. Günlük/haftalık veya API
anahtarı başına harcama sınırı varsaymayın. Bu özellik için ücretsiz hesabı
yükseltmeyin. [Rate limits](https://console.groq.com/docs/rate-limits) token/istek
sınırıdır, harcama limiti değildir. Hesap sahibi mevcut ücretsiz limitleri ve
kullanım ekranını kontrol etmelidir.

Tavily [resmi PAYG rehberi](https://help.tavily.com/articles/8280756099-how-to-set-a-limit-for-pay-as-you-go-option)
plan ayarlarında aylık kullanım limiti ve limite yaklaşma/aşma bildirimlerini
anlatır. Ücretsiz hesapta özel USD eşikleri veya gecikmesiz hard stop olduğunu
varsaymayın. [Dashboard](https://help.tavily.com/articles/7015474742-tavily-usage-dashboard)
üzerinden tüketimi izleyin. PAYG/otomatik ek kredi etkinleştirmeyin.
Hesapların mevcut plan/özellikleri doğrulanmadı. Gerçek limit/uyarı değişikliği
için hesap sahibi onayı gerekir. Uygulama kotası diğer uygulamaların aynı
organization/anahtar harcamalarını kapsamaz.

## Ekip entegrasyon notu

`llm.py` ve `retrieval.py` değiştirilmedi. Mevcut `asyncio.to_thread` executor
entegrasyonu ile çalışır. Ayrı executor veya fire-and-forget işe geçilirse
thread yaşam döngüsü yeniden entegre/test edilmelidir. Mert'in reasoning fallback
logundaki exception içeriği merkezi filtreyle gizlenir; ileride o satırın yerinde
temizlenmesi önerilir. Arda'nın iç thread havuzları dış çağrı bitmeden kapanmalıdır.
