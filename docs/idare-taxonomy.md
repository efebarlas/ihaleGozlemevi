# İdare taxonomy: `idare_turu` and `il`

A closed list of types for classifying an idare from its **name** (the bulletin has no sector or province field).
Used for peer groups (data-contract §4.1). It is deliberately fine enough that peers are alike in buying behavior,
and small enough (19 values) to label by hand and to check an agent against.

## `idare_turu` (closed list)

| code | Turkish label | definition |
|---|---|---|
| `buyuksehir_belediyesi` | Büyükşehir belediyesi | A metropolitan municipality itself (`… Büyükşehir Belediyesi`, `… Büyükşehir Belediye Başkanlığı`), incl. its departments and branches. |
| `belediye` | Belediye | A district, provincial or town municipality (`… Belediyesi`, `… Belediye Başkanlığı`) that is not a büyükşehir, incl. its departments. |
| `belediye_sirketi` | Belediye şirketi / bağlı kuruluşu | A company or affiliate owned by a municipality (`… Belediyesi … A.Ş.`, `… Ulaşım A.Ş.`) and municipal utilities such as `… Su ve Kanalizasyon İdaresi` (İSKİ, ASKİ, İZSU). |
| `il_ozel_idaresi` | İl özel idaresi | `… İl Özel İdaresi` and its directorates. |
| `valilik_kaymakamlik` | Valilik / kaymakamlık | `… Valiliği`, `… Kaymakamlığı`, and their project/fund units (`… Valiliği Proje Koordinasyon`, `… Sosyal Yardımlaşma Vakfı` of a governorship). |
| `saglik` | Hastane / sağlık | Public hospitals, `İl/İlçe Sağlık Müdürlüğü`, `Halk Sağlığı`, `Ağız ve Diş Sağlığı`, family-health and community-health centres. A **university** hospital is `universite`. |
| `universite` | Üniversite | Any unit of a university (rectorate, faculty, university hospital, `… Üniversitesi`). |
| `meb_okul` | MEB / okul | `İl/İlçe Milli Eğitim Müdürlüğü`, schools (`… Lisesi`, `… İlkokulu`, `… Anaokulu`), halk eğitim, rehberlik/RAM centres. |
| `karayollari` | Karayolları | `Karayolları Genel Müdürlüğü` and its regional directorates (`… Bölge Müdürlüğü`). |
| `dsi` | DSİ | `Devlet Su İşleri Genel Müdürlüğü` and its regional directorates (`DSİ …. Bölge Müdürlüğü`). |
| `dmo` | DMO | `Devlet Malzeme Ofisi Genel Müdürlüğü` and its purchasing branches. |
| `tcdd` | TCDD | `TCDD`, `Türkiye Cumhuriyeti Devlet Demiryolları` and its enterprises/regional directorates. |
| `enerji_kit` | Enerji KİT | State energy enterprises: EÜAŞ, TEİAŞ, BOTAŞ, TPAO, TKİ and their branches/plants (not the ministry). |
| `diger_kit` | Diğer KİT / kamu şirketi | Other state-owned enterprises and public companies: PTT, DHMİ, Türkşeker, TRT, THY, Çaykur, TMO, MKE, TDİ, etc. |
| `tsk_guvenlik` | TSK / jandarma / emniyet | Armed forces, gendarmerie, police, coast guard and their units (`… Komutanlığı`, `… Emniyet Müdürlüğü`, `Askerlik Şubesi`, `Askeri Fabrikalar`). |
| `adalet` | Adalet / cezaevi | Courthouses, justice commissions, prosecutors' offices, prisons (`Ceza İnfaz Kurumu`, `Adliye`, `Adalet Komisyonu`). |
| `bakanlik_tasra` | Bakanlık taşra teşkilatı | Provincial/district/regional units of ministries and central agencies that are not covered above (`… İl Tarım ve Orman Müdürlüğü`, `… Çevre, Şehircilik İl Müdürlüğü`, `… Bölge Müdürlüğü`, `… Gençlik ve Spor İl Müdürlüğü`). |
| `merkezi_idare` | Merkezi idare | Ministries and head-office bodies: `… Bakanlığı`, `… Genel Müdürlüğü` (head office), `… Başkanlığı`, `… Kurumu`, presidency, parliament, regulators, councils. |
| `diger` | Diğer | None of the above or too unclear to say. Prefer `diger` over a guess. |

## Tie-break rules (apply in this order; the first that matches wins)

1. **Named bodies beat generic words.** `dmo`, `tcdd`, `dsi`, `karayollari`, `enerji_kit` and `diger_kit` are decided by their own name,
   even if the name also contains `Genel Müdürlüğü`, `Bölge`, `Hastane` or a province.
2. **University before hospital and school.** `… Üniversitesi Hastanesi` → `universite`; a school inside a university → `universite`.
3. **Company before municipality.** A name with `Belediye` and a company form (`A.Ş.`, `Anonim Şirketi`, `Ltd.`) → `belediye_sirketi`.
   `Su ve Kanalizasyon İdaresi` → `belediye_sirketi`.
4. **Büyükşehir before belediye.** `Büyükşehir` in the name → `buyuksehir_belediyesi`; otherwise `Belediye` → `belediye`.
5. **İl özel idaresi, then valilik/kaymakamlık.**
6. **Hospital/health before MEB before adalet before TSK/güvenlik.** A name with two of these takes the first in this list
   (`Adalet Bakanlığı … Hastanesi` → `saglik`).
7. **Provincial units before the ministry.** A name ending in `İl/İlçe/Bölge Müdürlüğü` of a ministry → `bakanlik_tasra`;
   a head-office `Genel Müdürlüğü` / `Bakanlığı` / `Başkanlığı` with no provincial unit → `merkezi_idare`.
8. **When unsure, `diger`** (never guess a specific type from a weak hint).

## `il`

- `il` is one of Turkey's **81 province names** (canonical spelling: `Antalya`, `İzmir`, `Şanlıurfa`, `Iğdır`, …) or **null**.
- **Exactly one** province stated in the name → that province. **Two or more** distinct provinces → null (ambiguous).
- A **central body takes the il of its unit when the name states it**: `Devlet Su İşleri 12. Bölge …` → null (no province named),
  `Karayolları 14. Bölge Müdürlüğü Erzurum` → `Erzurum`, `Milli Eğitim … Kadıköy` → null (a district is not a province).
- The `il` is read from the **idare name only**. The yüklenici's address is the contractor's province, never use it, and
  do not infer the il from the type (a `Karayolları` name with no province stays null).
- Common short forms count as the province: `Afyon` → Afyonkarahisar, `Maraş` → Kahramanmaraş, `Antep` → Gaziantep, `Urfa` → Şanlıurfa.

## File formats

**Label file** (hand-made by an independent labeler, never edited by the builders): `tests/labels/idare_types.jsonl`,
one JSON object per line:

```json
{"idare": "ANTALYA BÜYÜKŞEHİR BELEDİYESİ FEN İŞLERİ DAİRE BAŞKANLIĞI", "turu": "buyuksehir_belediyesi", "il": "Antalya"}
```

`idare` is the name as printed; `turu` is a code from the table; `il` is a province or `null`. Optional: `labeler`, `note`.
Records are matched to predictions by the normalized idare key (`ihale.keys.normalize_key`).

**Lookup table** (built once by a build session): `data/idare_table.jsonl`, one JSON object per line, keyed by the normalized idare key:

```json
{"key": "antalya büyükşehir belediyesi fen işleri daire başkanlığı", "name": "ANTALYA BÜYÜKŞEHİR BELEDİYESİ FEN İŞLERİ DAİRE BAŞKANLIĞI",
 "turu": "buyuksehir_belediyesi", "il": "Antalya", "confidence": 0.97}
```

Optional: `turu_run1` / `turu_run2` (and `il_run1` / `il_run2`) when the table was built twice, for the self-consistency check; `note`.
`confidence` is in [0, 1]; the `hybrid` classifier trusts the table only at ≥ 0.9.
