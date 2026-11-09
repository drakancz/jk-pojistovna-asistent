# Hlášení škody JK pojišťovny (krok 4A)

Vytvořeno 4. 11. 2026. Pět vymyšlených formulářů „Hlášení pojistné
události“, které vypadají jako sken nebo fotka: **bez textové vrstvy**,
text z nich jde jen přepisem (OCR). Navazují na smlouvy z
[dokumenty.md](dokumenty.md). Lidé, adresy, čísla jednací i telefony jsou
vymyšlené, e-maily na `example.com`. V zápatí každé stránky je „Vymyšlený
dokument pro ukázku v portfoliu“.

- **Zdroj (údaje na formuláři):** `scripts/dokumenty/hlaseni.json`
- **Kreslení a „skenování“:** `scripts/dokumenty/skeny.py` — formulář se
  vyplní „rukou“ (písmo Comic Neue, modře, každé písmeno trochu jinak)
  a pak zhorší podle kvality. Pevné semínko → bajtově stejný výstup.
- **Výstup:** `dokumenty/11-…` až `15-…` a `dokumenty/hlaseni.json`
  (metadata pro import a **správné údaje** — podle nich se v kroku 4B
  změří, jak přesně AI údaje vytěží).
- **Výroba:** `docker compose --profile dokumenty run --rm dokumenty`
  (spolu s PDF). Skript ověří, že PDF skeny nemají textovou vrstvu a že
  žádný obrázek nepřesáhne limit Claude API.
- **Do aplikace:** `ukazkove-dokumenty` je nahraje spolu s deseti PDF
  jako „Hlášení škody“ klienta ze smlouvy. Bez klíče k Anthropicu
  zůstanou ve stavu „čeká na OCR“ a nic neodchází; s klíčem se přepíší
  jednou (6 stran, odhadem pod 0,05 $).
- **Kdo je vidí:** likvidace a administrátor. Klient je nenajde ani svoje
  (krok 3B) — hlídá `testy/test_hlaseni.py` i `test_klient.py`.

## Přehled

| # | Soubor | Smlouva, klient | Událost | Sken | Na co se hodí |
|---|---|---|---|---|---|
| 1 | `11-hlaseni-1001-auto.png` | 1001 auto, Petra Malá | 9. 10. 2026, odřené dveře na parkovišti, 18 500 Kč | čistý barevný sken | základní případ |
| 2 | `12-hlaseni-1002-domacnost.pdf` | 1002 domácnost, Petra Malá | 21. 10. 2026, vytopení od souseda, 46 300 Kč | šedý, pootočený, **2 strany** (formulář + seznam věcí) | tabulka věcí, součet sedí s odhadem |
| 3 | `13-hlaseni-1004-auto.jpg` | 1004 auto, Tomáš Beneš | 18. 10. 2026, srážka se srnou, 32 000 Kč | **fotka mobilem**: šikmo, stín, okraje stolu | datum zkratkou „18.10.26“; řídila Eva Benešová |
| 4 | `14-hlaseni-1005-domacnost.png` | 1005 domácnost, Tomáš Beneš | 27. 10. 2026, krádež kola ze sklepa, 24 500 Kč | **špatný**: nízký kontrast, šum, rozmazání | přeškrtnutých 26 000 Kč, platí 24 500 Kč; čas chybí |
| 5 | `15-hlaseni-1003-cestovni.pdf` | 1003 cestovní, Petra Malá | 3. 10. 2026, úraz při lyžování (Stubai), 1 240 EUR | **kopie kopie**: tmavý zrnitý tisk, skvrna od kávy přes popis | částka v eurech; ošetřený je spolupojištěný Karel Malý |

## Souvislosti se smlouvami (pro asistenta a likvidaci)

- **Srna (1004):** stalo se 18. 10. 2026, tedy po dodatku č. 1 — platí
  PLUS (střet se zvěří krytý), spoluúčast 5 %, nejméně 5 000 Kč, a Eva
  Benešová smí řídit.
- **Kolo ze sklepa (1005):** věci ve sklepě jsou pojištěné do 30 000 Kč,
  spoluúčast 2 000 Kč.
- **Vytopení (1002):** voda od souseda, ne povodeň — spoluúčast 1 000 Kč.
- **Lyžování (1003):** riziko kryje připojištění SPORT, které smlouva má;
  ošetření pod 30 000 Kč, asistence povinná nebyla, ale volali ji.
- **Parkoviště (1001):** PLUS, spoluúčast 5 %, nejméně 5 000 Kč.

## Co z toho bude dál

Krok 4B (hotovo): Claude z přepisu vyplní údaje hlášení a administrátor
na obrazovce Hlášení škody vidí, kolik z 22 údajů sedí se `spravne_udaje`
(u textu platí i doslovný `zapis`).

Krok 4C (hotovo, `app/kontrola.py`): pracovník likvidace údaje ve
formuláři opraví a potvrdí — přeškrtnutá částka, zkrácené datum a skvrna
jsou připravené právě na to. Opravy jdou do `vytezeni.udaje`, návrh AI
zůstává; administrátor vidí přesnost AI i po kontrole.
