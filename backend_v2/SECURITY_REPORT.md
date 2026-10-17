# Fatih backend çalışma raporu — 17 Ekim 2026

Branch: `fatih/api-security`. Commit, push, PR, merge, deployment veya hesap
değişikliği yapılmadı. Yalnızca `backend_v2/` değiştirildi. `llm.py`, `retrieval.py`,
`pipeline.py`, eski proje ve diğer ekip dizinleri değiştirilmedi.

| Görev | Durum | Kanıt / açık iş |
|---|---|---|
| 1. RAM/peak ve güvenli limit | KISMEN TAMAMLANDI | Yerel RSS/peak ölçüldü; ayarlanabilir admission eşiği ve ölçüm hatasında güvenli red test edildi. Gerçek container/retrieval yük profili henüz yok. |
| 2. Aktif inceleme kapasitesi | TAMAMLANDI | Ortak BUSY 429; başarı/hata/timeout/disconnect temizliği; çalışan thread bitene kadar kapasite tutma test edildi. |
| 3. Kota/rate/body | TAMAMLANDI | Ortak dakika/saat/gün ve süreç günlük kotası; 64 KiB/chunked kontrolü; Retry-After; bounded IP tablosu ve pencere sıfırlaması test edildi. |
| 4. Proxy/CORS/HTTP hata | TAMAMLANDI | Varsayılan XFF güvensiz; CIDR ve zincir kontrolleri; çoklu origin ayarı; JSON HTTP hataları ve reddedilmiş preflight test edildi. Gerçek ingress ayarı deploy öncesi doğrulanmalı. |
| 5. Üretim endpoint gizliliği | TAMAMLANDI | Deep endpoint her ortamda kapalı; üretim docs/redoc/openapi 404; health ve hata yanıtları sır sızdırmıyor. |
| 6. Docker/log/bağımlılık | KISMEN TAMAMLANDI | Non-root, HEALTHCHECK, secret build-context hariç tutma, güvenli log ve doğrudan sürüm pinleri eklendi. Yerel testler/pip check geçti. Docker komutu yok; image build/container smoke testi yapılmadı. |
| 7. Render hazırlığı | KISMEN TAMAMLANDI | Blueprint taslağı, repo-root context, Dockerfile, cold-start yöntemi ve rollback yazıldı. Canlı cold-start/rollback ve panel ayarları uygulanmadı. |
| 8. Groq/Tavily bütçeleri | MANUEL İŞLEM GEREKİYOR | Resmi kaynaklar README'de; desteklenen limit/uyarıların kapsamı ve sınırlamaları yazıldı. Gerçek hesap planı/ayarları doğrulanmadı, değiştirilmedi. |
| 9. CONFIG_ERROR/startup sızıntısı | TAMAMLANDI | init_error/detail/exception/traceback dış yanıtlardan çıkarıldı; başlangıç exception ve iki verify endpoint'i test edildi. |
| 10. Request ID | TAMAMLANDI | Sunucunun ürettiği ID tüm HTTP yanıtlarında/preflight'ta; CORS expose; bileşen/erişim loglarıyla korelasyon test edildi. |

## Gerçek doğrulama sonuçları

- İlk mevcut suite: `python -m pytest backend_v2/tests -q` → **19 passed in 9.47s**.
- İlk yeni suite: **20 passed, 17 failed**. Ağ engeli Windows asyncio'nun
  loopback socketpair'ini de kesiyordu; Windows process handle için ctypes
  argtypes eksikti. Her iki neden düzeltildi.
- Son suite: `python -m pytest backend_v2/tests -q --tb=short` →
  **44 passed in 10.51s** (19 mevcut + 25 yeni test vakası).
- `python -m pip check` → **No broken requirements found**.
- `git diff --check` → boşluk hatası yok. İzlenen dosyalar `git diff`, yeni
  dosyalar `git diff --no-index -- NUL <dosya>` ile incelendi. No-index için
  exit 1 yeni içerik farkı anlamına gelir. Windows LF/CRLF uyarısı mevcut.
- `git diff --exit-code -- backend_v2/app/llm.py backend_v2/app/retrieval.py backend_v2/app/pipeline.py`
  → değişiklik yok (exit 0).
- Gerçek Groq/Tavily çağrısı yapılmadı. HTTP testleri mock, ASGI disconnect ve
  dış socket engeli kullanır; Windows iç loopback bağlantısına izin verir.

## Ölçüm

`python backend_v2/tools/measure_capacity.py`, Windows / Python **3.14.0**,
offline sentetik async iş, gerçek sağlayıcı veya lifespan initialization yok:

| Ölçüm | Sonuç |
|---|---:|
| Eşzamanlı gönderilen istek | 20 |
| HTTP 200 | 2 |
| HTTP 429 | 18 |
| Toplam süre | 0,0394 saniye |
| RSS başlangıç | 55,11 MiB |
| RSS bitiş | 55,67 MiB |
| OS process peak | 55,67 MiB |
| Bitişte aktif slot | 0 |

Bu ölçüm kapasite korumasının sentetik profilidir; gerçek Groq/Tavily/retrieval
bellek tüketimini, Docker cold-start süresini veya Render kapasitesini kanıtlamaz.

## Değişen dosyalar

- `app/main.py`, `app/config.py`: entegrasyon, güvenli başlangıç/hatalar ve endpoint ayarları.
- `app/security.py`, `app/resources.py`, `app/safe_logging.py`: korumalar ve thread/log yaşam döngüsü.
- `tests/test_security.py`: 25 yeni test vakası.
- `tools/measure_capacity.py`: offline sentetik ölçüm aracı.
- `Dockerfile`, `Dockerfile.dockerignore`: non-root, healthcheck ve context gizliliği.
- `requirements.txt`, `requirements-test.txt`: sabit doğrudan bağımlılıklar ve test araçları.
- `render.yaml`: uygulanmamış Blueprint taslağı.
- `.env.example`, `README.md`, `SECURITY_REPORT.md`: ayarlar, işletim ve sonuç raporu.

## Kalan riskler ve manuel Render geçişi

1. Docker kurulu bir ortamda Python 3.12 image build ve non-root/healthcheck smoke
   testini yapın. Yerel doğrulama Python 3.14'tedir. Transitif bağımlılıkların
   tümü kilitli değildir; doğrudan bağımlılık pinleri vardır.
2. Render mevcut servis/branch, repo-root context ve Dockerfile yolunu doğrulayın.
   Taslağı yeni servis oluşturacak şekilde yanlış uygulamayın. Panelde secret
   anahtarları, gerçek CORS origin'lerini ve doğrulanmış ingress CIDR'lerini
   tanımlamak için önce açık onay alın. Geniş proxy CIDR eklemeyin.
3. Bir worker kullanın. Çoklu worker/replica kotaları paylaşmaz; yeniden başlatma
   sayaçları sıfırlar. Sabit pencerelerde sınır anında burst mümkündür. IP kotası
   NAT kullanıcılarını birlikte sınırlar; CORS kimlik doğrulama değildir.
4. RAM eşiği yalnızca yeni iş kabulünü durdurur; çalışan işteki ani artış için
   OS hard limit değildir. Gerçek retrieval yük testi ve plan RAM limitine göre
   ayar gerekir. İç thread havuzları toplam thread sayısını artırabilir.
5. Mevcut adapter'lar değişmeden default executor üzerinden izlenir. Mert/Arda
   ayrı executor veya bağımsız arka plan işi eklerse entegrasyon gerekir.
   Mert'in exception içeren fallback logu merkezi filtreyle temizlenmektedir;
   yerinde temizleme önerisi README'dedir. Takılan thread slotu tutar.
6. Ingress slow-client/bağlantı limitlerini doğrulayın. Canlı deploy öncesi önceki
   başarılı deploy ID ve secretsiz ayar envanterini kaydedin. Onay sonrası deploy,
   cold-start ölçümü ve gerektiğinde rollback uygulayın; ayarların da geri
   döndüğünü varsaymayın. Health liveness'tır, sağlayıcı readiness testi değildir.
7. Groq/Tavily plan ve mevcut kullanımını hesap sahibi doğrulamalı; hesap limit ve
   uyarı değişikliği öncesi açık onay gerekir. Ücretli plan/PAYG/ek kredi açılmadı.

Resmi sağlayıcı ve Render kaynakları ile ayrıntılı adımlar `README.md` içindedir.
