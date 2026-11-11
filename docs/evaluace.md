# Evaluace asistenta (krok 5A)

Hotovo 8. 11. 2026. Měří čísly, jak dobře asistent hledá a odpovídá,
místo dojmu „zdá se, že to funguje“.

## Co se měří

Sada **35 otázek** v `app/evaluace_sada.py`, psaných slovy zákazníka:

| Druh | Počet | Co je správně |
|---|---|---|
| s odpovědí v dokumentech | 27 | odpověď obsahuje správné údaje (částka, lhůta) **a** cituje správný dokument a stránku |
| mimo dokumenty | 5 | asistent řekne „nevím“ (povinné ručení, životní pojištění, kurz eura…) |
| oprávnění | 3 | klientka Petra Malá se ptá na smlouvy Tomáše Beneše: cizí dokument k AI vůbec neodejde a v odpovědi není |

Sada pokrývá i záměrné háčky z `docs/dokumenty.md`: dodatek, který mění
smlouvu, smlouvu s jinou spoluúčastí než podmínky, čekací dobu podle toho,
jestli pojištění navazuje.

**Dvě části:**

1. **Vyhledávání** (bez AI, zdarma, kdykoli): je správná stránka mezi
   prvními pěti úryvky? Jaké je její průměrné pořadí (MRR)? Nenajde
   klientka cizí smlouvu?
2. **Odpovědi** (s klíčem k Anthropicu): přesně stejné úryvky a pokyny
   jako skutečný asistent (`asistent.parametry()`), poslané hromadnou
   dávkou (Message Batches API, **o 50 % levnější**, výsledek do hodiny).
   Jde mimo denní limit asistenta a do databáze nic nezapisuje.
   S klíčem se před hledáním každá otázka převede do slov dokumentů
   (`asistent.hledaci_slova()`, od 10. 11. 2026) jako u skutečného
   asistenta, takže i vyhledávací čísla odpovídají tomu, co dostane
   uživatel. Bez klíče se měří hledání jen podle otázky.

**Výsledky 10. 11. 2026:** čtyři běhy naostro 34, 32, 32, 34 z 35.
Dlouhodobě padá „Kolik zaplatíte za ošetření zubů v zahraničí?“ —
odpověď je v tabulce limitů, kterou čtení PDF rozsype do řádků
(„akutní zubní ošetření / 10 000 Kč / 10 000 Kč“). Námět: číst tabulky
po řádcích („akutní zubní ošetření: EVROPA 10 000 Kč, SVĚT 10 000 Kč“).

## Jak spustit

```
# Jen vyhledávání (bez klíče, zdarma)
docker compose run --rm web python -m app.prikazy evaluace --zprava docs/evaluace-vysledky.md

# I odpovědi AI (potřebuje ANTHROPIC_API_KEY v .env, cca setiny dolaru)
docker compose run --rm web python -m app.prikazy evaluace --odpovedi --zprava docs/evaluace-vysledky.md
```

- `--primo`: otázky jednu po druhé místo dávky (hned, ale bez slevy).
- `--vystup`: podrobné výsledky v JSON (výchozí `data/evaluace.json`,
  mimo repozitář — obsahuje i text odpovědí).
- Zpráva (`--zprava`) má jen čísla a značky ✓/✗, žádný text odpovědí.

**Odhad ceny** jednoho běhu s odpověďmi: 35 otázek × asi 3 000 vstupních
a 200 výstupních tokenů, Haiku 5.5 s hromadnou slevou ≈ **0,01 $**.
Skutečnou spotřebu vypíše souhrn (`spotreba`).

## Testy

Testovací server pustí evaluaci při startu nad čistými dokumenty
(`scripts/test-server.sh`); odpovědi dává napodobenina Anthropicu, která
umí i hromadné dávky. `testy/test_evaluace.py` hlídá:

- vyhledávání najde správnou stránku aspoň u 21 z 27 otázek,
- klientka cizí smlouvu nenajde a k AI ji nepošle (0 případů),
- hodnocení počítá správně (napodobenina cituje vždy první úryvek, takže
  citace musí sedět přesně s pořadím z vyhledávání),
- odpovědi šly jednou dávkou, modelem Haiku 5.5, s citacemi a bez e-mailů
  a telefonů.

Chytrost modelu testy neměří — na to je běh s klíčem.

## První výsledky (8. 11. 2026, jen vyhledávání)

| Ukazatel | Výsledek |
|---|---|
| Správná stránka mezi prvními 5 | **23 z 27 (85 %)** |
| Správná stránka hned první | 13 z 27 (48 %) |
| MRR (1 = vždy první) | 0,63 |
| Cizí smlouva ve výsledcích klientky | **0 z 6** |

**Co měření ukázalo** (náměty na zlepšení, zatím neopravené):

- *„Kolik zaplatím ze svého, když mi ukradnou auto?“* — mezi prvními pěti
  jsou řádky „Rozsah pojištění“ ze smluv (i se spoluúčastí), ne článek 5
  podmínek. Pro likvidaci, která vidí všechny smlouvy, vítězí konkrétní
  smlouva nad obecnými podmínkami.
- *„Jaká je spoluúčast u smlouvy 1005?“* — najdou se články o spoluúčasti
  v podmínkách, smlouva 1005 ne. Číslo smlouvy hledání nevyužije; pomohlo
  by hledat ho přímo v názvu dokumentu.
- *„Zaplatíte krádež auta, když jsem v něm nechal klíčky?“* — hledání
  sklouzne ke krádeži z domácnosti; „klíčky“ se nepotkají s „klíčem
  ponechaným ve vozidle“.
- *„Odjedu na tři měsíce pryč…“* — „tři měsíce“ přitáhnou články o době
  trvání pojištění, ne pravidlo o domácnosti neobývané přes 60 dní.
- Hned první je správná stránka jen u poloviny otázek, proto asistent
  dostává 8 úryvků, ne 1.

Odpovědi modelu se změří, až bude klíč (před živou ukázkou).

## Po úpravě hledání (9. 11. 2026, jen vyhledávání)

Dvě obecné úpravy podle měření výš (ne slovník na míru otázkám):

1. **Číslo dokumentu z otázky** — „smlouva 1005“ přidá do spojení úryvky
   dokumentů, které to číslo nesou v názvu (jen z těch, které hledající
   smí vidět).
2. **Kratší kořen šestipísmenných slov** — „klíčky“ se hledá jako „klic“,
   takže najde „klíč ponechaný ve vozidle“.

| Ukazatel | 8. 11. | 9. 11. |
|---|---|---|
| Správná stránka mezi prvními 5 | 23 z 27 (85 %) | **25 z 27 (93 %)** |
| Správná stránka hned první | 13 z 27 | 13 z 27 |
| MRR | 0,63 | 0,67 |
| Cizí smlouva ve výsledcích klientky | 0 z 6 | **0 z 6** |

Nenajde dál: *„Kolik zaplatím ze svého…“* (= spoluúčast) a *„Odjedu na
tři měsíce…“* (= neobývaná domácnost přes 60 dní). Tady nepomůže kořen
slova, chtělo by to model, který rozumí významu lépe než současný malý
lokální. Minimum v `testy/test_evaluace.py` zvednuto na 23.
