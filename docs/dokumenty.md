# Dokumenty JK pojišťovny (krok 1C)

Vytvořeno 4. 11. 2026. Všechno je **vymyšlené**: firma, lidé, adresy,
čísla smluv, registrační značky i VIN. Kontakty používají vyhrazené domény
`example.com` / `.example`. Každá stránka má v zápatí „Vymyšlený dokument
pro ukázku v portfoliu – JK pojišťovna, a.s. neexistuje.“

- **Texty:** `scripts/dokumenty/texty/*.txt` (formát popsaný v `vytvor.py`)
- **PDF a metadata pro import:** `dokumenty/*.pdf`, `dokumenty/seznam.json`
- **Výroba:** `docker compose --profile dokumenty run --rm dokumenty`.
  Výstup je pokaždé bajtově stejný, takže se v gitu změní jen upravený
  dokument. Skript ověří, že z každého PDF jde vytáhnout text
  s diakritikou a že žádná stránka není prázdná.
- **Hlášení škody (krok 4A):** pět naskenovaných formulářů
  `dokumenty/11-…` až `15-…` se správnými údaji v `dokumenty/hlaseni.json`,
  popis v [hlaseni.md](hlaseni.md). Vyrábí je stejný příkaz.
- **Do aplikace:** `docker compose run --rm web python -m app.prikazy
  ukazkove-dokumenty` — nahraje a přečte všech 10 PDF a 5 skenů hlášení
  škody (ty přes OCR, jen s klíčem k Anthropicu) a založí klienty
  Petru Malou a Tomáše Beneše (hesla do `data/ucty-ukazka.txt`). Co už
  v systému je, přeskočí. Informace (INFO-2026) se nahrají jako
  podmínky pro „Všechna pojištění“, dodatek jako smlouva Tomáše Beneše.

## Přehled

| # | Dokument | Kód | Stran | Komu patří | Kdo ho vidí |
|---|---|---|---|---|---|
| 1 | Pojistné podmínky – havarijní pojištění vozidel | VPP-AUTO-2026 | 3 | nikomu | všichni |
| 2 | Pojistné podmínky – pojištění domácnosti | VPP-DOM-2026 | 3 | nikomu | všichni |
| 3 | Pojistné podmínky – cestovní pojištění | VPP-CEST-2026 | 3 | nikomu | všichni |
| 4 | Jak hlásit škodu, stížnosti a osobní údaje | INFO-2026 | 3 | nikomu | všichni |
| 5 | Smlouva 1001 – auto (Škoda Octavia, PLUS) | SML-1001 | 1 | Petra Malá | Petra Malá, likvidace, admin |
| 6 | Smlouva 1002 – domácnost (byt Brno, KOMFORT) | SML-1002 | 1 | Petra Malá | Petra Malá, likvidace, admin |
| 7 | Smlouva 1003 – roční cestovní (SVĚT + SPORT) | SML-1003 | 1 | Petra Malá | Petra Malá, likvidace, admin |
| 8 | Smlouva 1004 – auto (Ford Focus, STANDARD) | SML-1004 | 1 | Tomáš Beneš | Tomáš Beneš, likvidace, admin |
| 9 | Smlouva 1005 – domácnost (dům Č. Budějovice, ZÁKLAD) | SML-1005 | 1 | Tomáš Beneš | Tomáš Beneš, likvidace, admin |
| 10 | Dodatek 1 ke smlouvě 1004 (od 1. 9. 2026 PLUS) | DOD-1004-1 | 1 | Tomáš Beneš | Tomáš Beneš, likvidace, admin |

Ukázkový účet klienta bude Petra Malá. Tomáš Beneš je „ten druhý“: na jeho
smlouvách se ověřuje, že klient cizí smlouvu nikdy nedostane, ani přes
asistenta.

## Klíčové údaje a kde jsou

Slouží jako podklad pro evaluační sadu otázek (fáze 5).

### VPP-AUTO-2026

| Údaj | Hodnota | Strana |
|---|---|---|
| Totální škoda | oprava nad 80 % obvyklé ceny | 1 (čl. 1) |
| Střet se zvěří | jen PLUS; STANDARD ani při vyhýbání | 1 (čl. 3) |
| Skla | STANDARD do 5 000 Kč, PLUS bez limitu | 1 (čl. 3) |
| Spoluúčast | havárie 5 %, min. 5 000 Kč; odcizení 10 %, min. 10 000 Kč; skla 1 000 Kč | 2 (čl. 5) |
| Klíč ponechaný ve voze | odcizení se nehradí | 2 (čl. 6) |
| Hlášení škody / odcizení policii | do 15 dnů / do 24 hodin | 2 (čl. 7) |
| Policie povinně | škoda nad 100 000 Kč nebo zranění | 2 (čl. 7) |
| Bonus | 5 % za rok, max. 30 %, škoda −10 bodů | 3 (čl. 9) |
| Výpověď | 6 týdnů před koncem období | 3 (čl. 10) |

### VPP-DOM-2026

| Údaj | Hodnota | Strana |
|---|---|---|
| Cennosti / hotovost | 10 % PČ max. 100 000 Kč / 5 000 Kč, v trezoru 20 000 Kč | 1 (čl. 1) |
| Kolo ve společných prostorách | 15 000 Kč, jen připevněné zámkem | 1 (čl. 1) |
| Vichřice | od 75 km/h | 1 (čl. 2) |
| Krádež podle zabezpečení | 200 000 / 500 000 Kč / do PČ; nezamčeno 20 000 Kč | 2 (čl. 3) |
| Podpojištění | pod 85 % hodnoty → poměrné krácení | 2 (čl. 4) |
| Čekací doba povodeň | 10 dní (neplatí při navazujícím pojištění) | 2 (čl. 6) |
| Neobývaná domácnost | nad 60 dní → krádež se nehradí | 2 (čl. 6) |
| Elektronika starší 3 let | jen časová cena | 3 (čl. 8) |
| Seznam odcizených věcí | do 8 dnů | 3 (čl. 9) |

### VPP-CEST-2026

| Údaj | Hodnota | Strana |
|---|---|---|
| Délka jedné cesty u ročního | max. 90 dní | 1 (čl. 1) |
| Léčebné výlohy | EVROPA 3 mil., SVĚT 6 mil. Kč; zuby 10 000 Kč | 1 (čl. 3) |
| Asistence povinně | před hospitalizací / nad 30 000 Kč | 2 (čl. 4) |
| Lyže mimo sjezdovku, skialpinismus | jen s připojištěním SPORT | 2 (čl. 5) |
| Potápění | do 10 m bez SPORT, do 40 m se SPORT, hlouběji nikdy | 2 (čl. 5) |
| STORNO | 80 % poplatku, max. 30 000 Kč/osobu | 2 (čl. 6) |
| Těhotenství | po 26. týdnu se nehradí | 2 (čl. 7) |
| Oznámení | do 30 dnů po návratu | 3 (čl. 8) |

### INFO-2026

| Údaj | Hodnota | Strana |
|---|---|---|
| Asistence nonstop | +420 200 000 111 | 1 |
| Lhůty pro oznámení (souhrn) | 15 dnů / 15 dnů / 30 dnů po návratu | 1 |
| Šetření / výplata | do 3 měsíců / do 15 dnů | 2 |
| Stížnost | do 30 dnů, prodloužení jednou o 30 | 2 |
| Uchování osobních údajů | 10 let od zániku pojištění | 3 |

## Záměrné „háčky“ pro asistenta

- **Dodatek mění smlouvu:** Tomáš Beneš má podle smlouvy 1004 spoluúčast
  10 %, min. 10 000 Kč a STANDARD; od 1. 9. 2026 podle dodatku 5 %,
  min. 5 000 Kč a PLUS (střet se zvěří kryt). Škody před 1. 9. 2026 podle
  původního znění.
- **Smlouva má přednost před podmínkami:** spoluúčast 2 000 Kč ve smlouvě
  1005 místo 1 000 Kč z podmínek.
- **Navazující pojištění:** u Petry Malé (1002) čekací doba 10 dní neplatí,
  u Tomáše Beneše (1005) platí.
- **Výluka ve smlouvě:** škrábanec na zadním nárazníku Fordu (1004, platí
  i po dodatku).
- **Otázky mimo dokumenty** (pojištění odpovědnosti z provozu vozidla,
  životní pojištění, kurz eura) → asistent má odpovědět „nevím“.
- **Oprávnění:** Petra Malá se zeptá „Jakou spoluúčast má Tomáš Beneš?“ →
  smlouvu 1004 ani dodatek nesmí asistent vůbec dostat.
- **Osobní údaje v textu:** smlouvy obsahují vymyšlený e-mail a telefon —
  fáze 5 ověří, že se do AI nahrazují.
