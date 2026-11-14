# Altın tablo (golden table) — Flame in Freefall, NASA Space Apps 2026

Bu klasör, taslak veri raporunun (veri_seti_taslak_raporu, Ek A ve bölüm 5.3, 5.5, 6.2, 6.3) tanımladığı **altın tablonun ilk LLM taslağını** içerir. Tablonun hiçbir satırı henüz bir insan tarafından doğrulanmamıştır: tüm satırlarda `dogrulandi = hayır`, `dogrulayan = hayır`.

| Dosya | İçerik |
|---|---|
| `golden_table.csv` | 17 çekirdek yatırım, yatırım başına bir satır, 46 sütun (UTF-8 BOM'lu; Excel Türkçe karakterleri doğru gösterir) |
| `golden_table_evidence.jsonl` | Alan başına kanıt kayıtları (393 kayıt): `investigation_id, field, source_id, page, snippet, source_kind, auto_check` |
| `golden_table_celiskiler.csv` | Çelişki listesi (66 kayıt, bölüm 5.5): `investigation_id, alan, deger_1, kaynak_1, deger_2, kaynak_2, secilen, gerekce` |
| `../../reference/manifest.csv` | Kaynak kayıt defteri; S-001…S-051 dolduruldu, S-055…S-085 eklendi, S-052…S-054 değiştirilmedi |

## Nasıl üretildi

1. Altı araştırma notu (Saffire, BASS, SAME/DAFT, FLEX/FLEX-2/CFI, ACME, SPICE/SLICE) yerel repo dosyalarından (`raw/docs`, `raw/psi`) ve web kaynaklarından alan bazında değer + kaynak + sayfa + alıntı topladı. Yerel PDF'ler `pdftotext -layout` ile, PSI tabloları satır satır okundu.
2. Bu notlar tek bir yapılandırılmış veri setine (kaynak listesi, satırlar, kanıtlar, çelişkiler) dönüştürüldü ve bir Python betiği ile CSV/JSONL/manifest dosyaları üretildi. Normalize değerler (O2 kesri, psi, cm/s) ham değer + birimden hesaplandı; türetilmiş sütunlar (bölüm 6.3) otomatik hesaplandı.
3. Her yerel kanıt kaydı otomatik kontrolden geçirildi (aşağıda `auto_check`). Web kaynaklı kayıtlar otomatik kontrol edilemez ve elle kontrol listesindedir.
4. Ekip kararları uygulandı: Saffire-III akışı = 25 cm/s (30 cm/s çelişki olarak kayıtlı); FLEX basıncında 0.0 mmHg anomalisi hariç; BASS-II O2 = kalibre başlangıç O2 sütunu, 5 imkânsız son O2 değeri hariç; yörünge (mikro-g) değerleri 1-g yer verisine tercih edildi.

Betikler (oturum çalışma alanında, repoya taşınması önerilir): `build_golden.py` (üretim), `check_evidence.py` (otomatik kontrol), veri modülleri `gt_sources.py`, `gt_rows.py`, `gt_evidence.py`.

## Sütun sözlüğü

Sütun sırası: önce Ek A sütunları, sonra ham değer/niteleyici sütunları, sonra türetilmiş sütunlar. Çok değerli hücrelerde ayırıcı `" | "`. Sayılarda ondalık ayırıcı nokta.

### Ek A sütunları

| Sütun | Açıklama |
|---|---|
| `id` | Yatırım kimliği (Saffire-I, Saffire-II, Saffire-III, BASS, BASS-II, SAME, SAME-R, DAFT, DAFT-2, FLEX, FLEX-2, CFI, ACME-CFI-G, ACME-BRE, ACME-E-FIELD, SPICE, SLICE). Zorunlu |
| `ad` | Tam ad (İngilizce resmî ad — Türkçe karşılık). Zorunlu |
| `kategori` | önleme / algılama / söndürme (çoklu olabilir). Zorunlu. Kategori bir çıkarımsa `kategori_notu` açıklar |
| `yakit_tipi` | katı / sıvı / gaz (Ek A'daki `yakıt_tipi`) |
| `yakit_sekil_boyut` | Numune veya brülör şekli ve boyutu, mm (Ek A'daki `yakıt_şekil_boyut`) |
| `o2_min`, `o2_max` | O2 kesri (0-1); kaynak yüzde verirse /100 |
| `basinc_psi_min`, `basinc_psi_max` | Toplam basınç, psi (1 atm = 14.696 psi; 1 bar = 14.5038 psi; 1 kPa = 0.145038 psi; 1 mmHg = 0.0193368 psi) |
| `akis_cm_s_min`, `akis_cm_s_max` | Zorlanmış hava/eş-akış hızı, cm/s (Ek A'daki `akis_cm_s` iki sütuna bölündü) |
| `donanim` | MSG / CIR (MDCA, ACME) / diğer + kısa açıklama |
| `olcumler` | Sensörler ve ölçüm türleri |
| `degisen_ve_sabit` | "Değişen: … Sabit: …" biçiminde |
| `ana_bulgu` | 1-2 cümlelik Türkçe, kaynağa dayalı özet (her iddia kanıt dosyasında `field = ana_bulgu` ile desteklenir) |
| `kaynak_idleri` | Bu satırda kullanılan manifest kimlikleri. DAFT-2, FLEX-2 ve CFI'da `durum = kaynak yok` olan sonuç kayıtları da listelenir |
| `sayfa` | Kaynak başına sayfa/satır listesi: `S-001: s.15; s.30 | S-074: satır 20`. Web kaynakları `web …` önekiyle |
| `dogrulandi`, `dogrulayan` | Elle doğrulama durumu ve kişi. Şu an tüm satırlarda `hayır` |

### Ham değer ve niteleyici sütunları (bölüm 5.3)

| Sütun | Açıklama |
|---|---|
| `yakit_malzeme` | Malzeme/yakıt adları |
| `o2_raw`, `o2_birim_raw`, `o2_not` | Kaynaktaki ham O2 ifadesi, birimi; niteleyici (yaklaşık, tahmini, türetilmiş, hariç tutulan değerler) |
| `basinc_raw`, `basinc_birim_raw`, `basinc_not` | Ham basınç ifadesi, birimi, niteleyici ve dönüşüm notu |
| `akis_raw`, `akis_birim_raw`, `akis_not` | Ham akış ifadesi, birimi, niteleyici ("kadar", "durgun" vb.) |

### Türetilmiş sütunlar (bölüm 6.3)

| Sütun | Tanım |
|---|---|
| `po2_psi_min` | `o2_min × basinc_psi_min` |
| `po2_psi_max` | `o2_max × basinc_psi_max` |
| `o2_ratio_vs_air` | `o2_max / 0.209` (0.209 challenge metninde yok, teyit edilecek — facts C-002, C-004) |
| `lunar_o2_flag` | `o2_max ≥ 0.30` → evet/hayır; o2_max bilinmiyorsa bilinmiyor |
| `lunar_pressure_flag` | `basinc_psi_min ≤ 10.2` → evet/hayır; bilinmiyorsa bilinmiyor |
| `lunar_joint_flag` | **evet** yalnızca tek bir testte O2 ≥ 0.30 ve P ≤ 10.2 psi birlikte gösterilirse; iki bayrak da evet ama farklı testlerde veya test bazında kontrol edilemiyorsa **kısmi**; bayraklardan biri hayır ise **hayır**; biri bilinmiyorsa **bilinmiyor** |
| `lunar_not` | Ortak bayrağın gerekçesi (FLEX için CSV satır satır kontrol sonucu) |
| `material_class` | kumaş / plastik / diğer katı / sıvı / gaz (çoklu) |
| `gravity_regime` | mikro yerçekimi / normal / benzetim; 1-g yer karşılaştırması varsa "normal (…)" eklenir |
| `varied_axes` | Testler arasında değişen eksenler (kısa etiketler) |
| `evidence_level` | "LLM taslağı" (kaynaklı satır) / "eksik" (kaynaksız satır: DAFT-2). İnsan doğrulamasından sonra "doğrulanmış" olacak |
| `n_sources` | Satırda kullanılan farklı belge sayısı (aynı belgenin yinelenen manifest kayıtları — ör. mini-kitap S-024/S-033/S-036/S-041/S-045/S-051 = S-071 — bir kez sayılır; "kaynak yok" kayıtları sayılmaz) |
| `year_span` | Kullanılan kaynakların yayın yılı aralığı (test yılı değil; test yılları `yil_araligi`nda) |
| `test_sayisi` | Test/numune sayısı ve tanımı (kaynaklar farklıysa notlu) |
| `yil_araligi` | Uçuş operasyonlarının yılları |
| `kategori_notu` | Kategori çıkarımsa gerekçesi |
| `celiski_var` | Bu yatırım için çelişki listesinde kayıt varsa evet |

## Boş değer ve çelişki kuralları

* **Zorunlu alanlar** (`id`, `ad`, `kategori`, `kaynak_idleri`, `sayfa`) her satırda doludur. Diğer boş hücreler **"bilinmiyor"** yazılır; bilinmeyen hiçbir zaman 0 değildir ve tahminle doldurulmaz.
* **0 değeri** yalnızca kaynak koşulu açıkça söylüyorsa kullanıldı: BASS (akış "sıfır", fan kapalı), BASS-II (Air display = 0), SAME-R ("quiescent to 8 cm/s" → 0-8; yorum `akis_not`ta). FLEX, ACME-CFI-G ve ACME-BRE'de ortam durgun olduğu halde brülör/fiber hareketi nedeniyle akış **0 olarak kodlanmadı**, "bilinmiyor" bırakıldı.
* **Tek nokta değerler** (FLEX-2: etanol, %30 O2, 2.4 atm görüntü altyazısı; CFI aday testi) aralık olmadığı için normalize sütunlara yazılmadı, ham/not sütunlarında tutuldu.
* **Psi dönüşümleri** kaynakta psi yoksa yapıldı ve `basinc_not` sütununda belirtildi (SPICE/SLICE ~100 kPa, BRE ve CFI-G bar, FLEX mmHg, BASS/BASS-II atm).
* **po2 sütunları aralık uçlarının çarpımıdır, aynı testin değeri olmak zorunda değildir.** Örnek: FLEX `po2_psi_max = 0.34 × 44.859 = 15.25 psi`, ama 0.34 O2'li testler ~0.7 atm'de yapıldı; ACME-CFI-G'de 0.85 ters alevde brülörden akan oksitleyicinin O2'sidir, ortam değil. Ay üssü filtresinde `lunar_joint_flag` ve `lunar_not` kullanılmalı.
* **Çelişkiler** (bölüm 5.5): iki değer de kaynak ve yer bilgisiyle `golden_table_celiskiler.csv`'ye yazıldı; `secilen` sütunu tabloya giren değeri, `gerekce` nedenini verir. Ajan kural R-007 gereği iki değeri de göstermelidir.
* Mikro-g değerleri 1-g yer verisine tercih edildi; 1-g verisi varsa `gravity_regime` bunu belirtir.

## Doğrulama durumu ve otomatik kontrol

`auto_check` yöntemi: yerel kaynaklar için manifestteki `repo yolu:` notundan dosya bulunur; ilgili sayfa/satır metni çıkarılır (PDF: `pdftotext -f N -l N -layout`; csv/txt: satır; xlsx: `Sayfa!satır N`; docx: boş olmayan paragraf sırası). Alıntıdaki **her sayı** metinde sayı sınırlarıyla geçmeli **ve** alıntı kelimelerinin en az %60'ı (sayı yoksa %80'i) bulunmalı → `bulundu`, aksi halde `şüpheli`. Normalize edilmiş değerler (ör. mmHg→psi) kaynakta birebir geçmediği için kontrol, ham değeri içeren alıntı üzerinden yapılır. Web kaynakları → `web: elle kontrol edilecek`. Kontrol yanlış sayfaları yakaladığı test edildi (ör. aynı alıntı komşu sayfada `şüpheli` çıkıyor).

| auto_check | Kayıt sayısı |
|---|---|
| bulundu | 239 |
| şüpheli | 0 |
| web: elle kontrol edilecek | 154 |
| **Toplam** | **393** |

İlk çalıştırmada 1 kayıt `şüpheli` çıktı (BASS donanım alıntısı yanlış metadata satırına bağlanmıştı: satır 40 → doğrusu satır 42) ve düzeltildi.

**Dikkat:** `bulundu`, alıntının o sayfada geçtiğini gösterir; tablodaki yorumun/normalize değerin doğru olduğunu garanti etmez. Ana bulguların çoğu (SAME, SAME-R, DAFT, ACME, SPICE, SLICE) yalnız web kaynaklarına dayanır.

Satır başına "bilinmiyor" hücre sayısı (46 sütun üzerinden): Saffire-I 0, Saffire-II 7, Saffire-III 8, BASS 0, BASS-II 0, SAME 18, SAME-R 15, DAFT 21, DAFT-2 31, FLEX 3, FLEX-2 16, CFI 22, ACME-CFI-G 2, ACME-BRE 3, ACME-E-FIELD 19, SPICE 0, SLICE 2.

## Ekibin önce elle kontrol etmesi gerekenler (öncelik sırasıyla)

1. **Saffire-III akış hızı (25 vs 30 cm/s).** Tabloda 25 (S-001 s.16, s.30, uçuş sonrası). 30 cm/s PSI-100 metadata (S-009), DoD (S-008) ve uçuş öncesi makalede (S-005). Kesin karar için Urban vd. 2019, Combustion and Flame, Tablo 1 (S-007; açık erişim kopyası hal-02042950) okunmalı.
2. **ACME-E-FIELD kısmi yerçekimi iddiası.** Challenge metni (facts F-020) E-FIELD'ın kısmi yerçekimini benzettiğini söylüyor; erişilen hiçbir birincil kaynak (S-038, S-042, S-043, S-044) bunu desteklemiyor. `gravity_regime` = "mikro yerçekimi | benzetim (… doğrulanmadı)". Chien vd. 2022 (Combustion and Flame; olası NTRS 20220005205) okunmalı.
3. **DAFT-2 kimliği.** "DAFT-2" adıyla hiçbir kaynak bulunamadı (S-025…S-027 = kaynak yok). Dolaylı ipucu: DAFT'ın Exp 10 ve Exp 13 seansları olabilir (S-016 s.6). NTRS 20070031686 ve NASA ISS Research Explorer DAFT sayfası kontrol edilmeli; gerekirse DAFT ile birleştirme kararı verilmeli.
4. **FLEX-2 ve CFI boşlukları.** İşletim tarihleri, test sayısı, O2/basınç/seyreltici aralıkları ve sonuç kaynağı yok (S-031, S-034 = kaynak yok). Adaylar: Dietrich vd. 2024 (doi 10.1007/s12217-024-10115-x), AIAA J. doi 10.2514/1.J057128, Farouk vd. (S-079, "FLEX 1268" testinin CFI'ye ait olup olmadığı). PSI'da ayrı FLEX-2/CFI tablosu aranmalı.
5. **Web alıntıları (154 kayıt).** WebFetch özetleyicisinden geldiği için birebir doğruluğu garanti değil; özellikle `[WebFetch özeti, birebir değil]` ve `[tablo özeti, birebir değil]` etiketli kayıtlar (S-023, S-035, S-037 Tablo 1, S-079). ACME-CFI-G O2 aralığı (0.12-0.85) ve basınç (0.46-3 bar) Kim vd. 2023 Tablo 1'den elle doğrulanmalı; 0.85'in ortam değil brülör oksitleyicisi olduğu teyit edilmeli.
6. **ACME-BRE basınç alt sınırı** (Tablo 2.1: 0.56 bar vs metin: ~0.4 bar) ve test sayısı alt kümeleri (149 / 122 / 59).
7. **BASS-II basıncı** min ölçülen (99.2 kPa) + max nominal (1 atm) birleşimi; ekip ölçülen aralığı (14.388-14.431 psi) tercih edebilir.
8. **SAME/SAME-R/DAFT koşulları**: O2, basınç ve (SAME için) akış sayısal olarak hiçbir kaynakta yok; SAME-1 akış/ısıtıcı değerleri NTRS 20070031686 veya SAE 2008-01-2089'da olabilir.
9. **Saffire-I basıncı** Cygnus kabin sensöründen (telemetri penceresi); yanma anına karşılık gelen satırlar ayrıca kontrol edilmeli.
10. Kategori çıkarımları (`kategori_notu`): FLEX-2/CFI → söndürme, ACME-CFI-G/E-FIELD/SPICE/SLICE → önleme (dolaylı). Ekip f3 skorunda (doğrudan = 1, dolaylı = 0.4) bunu dikkate almalı.
