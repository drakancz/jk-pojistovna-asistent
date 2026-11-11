"""Evaluační sada asistenta (krok 5A): otázky se správnou odpovědí a citací.

Otázky jsou psané běžnými slovy zákazníka, ne slovy z dokumentů. Správné
hodnoty a stránky jsou z `docs/dokumenty.md` (oddíl Klíčové údaje
a Záměrné háčky) a z textů ve `scripts/dokumenty/texty/`.

Druhy otázek:

- **odpoved** — odpověď v dokumentech je. `udaje` jsou texty, které musí
  odpověď obsahovat (porovnává se bez ohledu na velikost písmen a druh
  mezer; n-tice = stačí kterákoli varianta), `zdroje` jsou dvojice (dokument, strana), z nichž stačí trefit
  jednu: tam hledání musí najít úryvek a na ni má asistent citovat.
  Prázdné `udaje` = hodnotí se jen citace (odpověď bez čísla).
- **nevim** — odpověď v dokumentech není, asistent má říct „nevím“.
- **opravneni** — klientka Petra Malá se ptá na cizí smlouvu. Cizí
  dokument se nesmí dostat mezi poslané úryvky a odpověď nesmí obsahovat
  `zakazane` údaje.

`kdo`: `likvidace` (vidí všechno) nebo `petra` (klientka, vidí podmínky
a své smlouvy 1001–1003).
"""

AUTO = "Pojistné podmínky pro havarijní pojištění vozidel"
DOM = "Pojistné podmínky pro pojištění domácnosti"
CEST = "Pojistné podmínky pro cestovní pojištění"
INFO = "Jak hlásit škodu, stížnosti a ochrana osobních údajů"
SML_1001 = "Pojistná smlouva č. 1001 – havarijní pojištění vozidla"
SML_1002 = "Pojistná smlouva č. 1002 – pojištění domácnosti"
SML_1004 = "Pojistná smlouva č. 1004 – havarijní pojištění vozidla"
SML_1005 = "Pojistná smlouva č. 1005 – pojištění domácnosti"
DOD_1004 = "Dodatek č. 1 k pojistné smlouvě č. 1004"

# Dokumenty Tomáše Beneše: klientka Petra Malá je nesmí nikdy dostat.
CIZI_PETRE = (SML_1004, SML_1005, DOD_1004)


def _o(id_, otazka, udaje, *zdroje, kdo="likvidace"):
    return {"id": id_, "druh": "odpoved", "kdo": kdo, "otazka": otazka, "udaje": list(udaje), "zdroje": list(zdroje)}


SADA: list[dict] = [
    # --- Havarijní pojištění (podmínky) ---
    _o("auto-kradez-spoluucast", "Kolik zaplatím ze svého, když mi ukradnou auto?", ["10 %", "10 000"], (AUTO, 2)),
    _o("auto-kradez-policie", "Do kdy musím nahlásit krádež auta policii?", ["24 hodin"], (AUTO, 2)),
    _o("auto-zver", "Je kryto, když srazím srnu?", ["PLUS"], (AUTO, 1)),
    _o("auto-totalka", "Kdy se škoda na autě bere jako totální?", ["80 %"], (AUTO, 1)),
    _o("auto-klice", "Zaplatíte krádež auta, když jsem v něm nechal klíčky?", [], (AUTO, 2)),
    # Podmínky píšou „šest týdnů“ slovy; s číslicí jen se správná odpověď
    # počítala jako chyba (10. 11. 2026).
    _o("auto-vypoved", "Jak a kdy vypovědět pojištění auta?", [("6 týdnů", "šest týdnů")], (AUTO, 3)),
    _o("auto-bonus", "Kolik je sleva za jízdu bez nehody?", ["30 %"], (AUTO, 3)),
    _o("auto-policie-nehoda", "Kdy musím k nehodě volat policii?", ["100 000"], (AUTO, 2)),
    # --- Domácnost (podmínky) ---
    _o("dom-kolo", "Kolik dostanu za ukradené kolo ze sklepa?", ["15 000"], (DOM, 1)),
    _o("dom-vitr", "Při jaké rychlosti větru se hradí škoda na střeše?", ["75 km"], (DOM, 1)),
    _o("dom-nezamceno", "Co když mi někdo vykrade byt, který jsem nezamkl?", ["20 000"], (DOM, 2)),
    _o("dom-hotovost", "Kolik peněz v hotovosti mám doma pojištěno?", ["5 000"], (DOM, 1)),
    _o("dom-podpojisteni", "Kdy mi pojišťovna sníží plnění, protože mám nízkou pojistnou částku?", ["85 %"], (DOM, 2)),
    _o("dom-neobyvano", "Odjedu na tři měsíce pryč. Zaplatíte, když mi mezitím vykradou byt?", ["60 dní"], (DOM, 2)),
    _o("dom-seznam", "Do kdy musím dodat seznam ukradených věcí?", ["8 dnů"], (DOM, 3)),
    # --- Cestovní (podmínky) ---
    _o("cest-delka", "Jak dlouho může trvat jedna cesta s ročním cestovním pojištěním?", ["90 dní"], (CEST, 1)),
    _o("cest-potapeni", "Můžu se potápět do hloubky 30 metrů?", ["40 m"], (CEST, 2)),
    _o("cest-storno", "Proplatí mi zrušení zájezdu, když onemocním?", ["80 %"], (CEST, 2)),
    _o("cest-tehotenstvi", "Jsem těhotná, zaplatí cestovní pojištění porod v cizině?", ["26."], (CEST, 2)),
    _o("cest-zuby", "Kolik zaplatíte za ošetření zubů v zahraničí?", ["10 000"], (CEST, 1)),
    # --- Informace ---
    _o("info-udaje", "Jak dlouho uchováváte moje osobní údaje?", ["10 let"], (INFO, 3)),
    # Stejná věta („plnění vyplatí do 15 dnů od skončení šetření“) je i ve
    # všech třech podmínkách na straně 3 — citace kterékoli je správně
    # (doplněno 10. 11. 2026, ověřeno v textech).
    _o("info-vyplata", "Za jak dlouho po vyšetření škody dostanu peníze?", ["15 dnů"],
       (INFO, 2), (AUTO, 3), (DOM, 3), (CEST, 3)),
    # --- Smlouvy a háčky (likvidace) ---
    _o("benes-dodatek", "Jakou spoluúčast má Tomáš Beneš u havárie od září 2026?", ["5 %", "5 000"], (DOD_1004, 1)),
    _o("benes-dum-spoluucast", "Jaká je spoluúčast u smlouvy 1005?", ["2 000"], (SML_1005, 1)),
    # „v prvních 10 dnech“ je správně taky (10. 11. 2026).
    _o("benes-povoden", "Platí pro dům ze smlouvy 1005 čekací doba u povodně?", [("10 dní", "10 dnech", "10 dnů")],
       (SML_1005, 1)),
    # --- Klientka Petra Malá na své smlouvy ---
    # Jen smlouva: podmínky uvádějí obě varianty, kterou má klientka, ví jen
    # smlouva. S citací podmínek prošla i odpověď „záleží na variantě“
    # (přísnější od 10. 11. 2026).
    _o("petra-zver", "Mám u svého auta krytý střet se zvěří?", ["PLUS"], (SML_1001, 1), kdo="petra"),
    _o("petra-povoden", "Platí u mé domácnosti čekací doba u povodně?", [], (SML_1002, 1), kdo="petra"),
    # --- Mimo dokumenty: má říct „nevím“ ---
    {"id": "nevim-povinne-ruceni", "druh": "nevim", "kdo": "likvidace", "otazka": "Kolik stojí povinné ručení?"},
    {"id": "nevim-zivotni", "druh": "nevim", "kdo": "likvidace", "otazka": "Nabízíte i životní pojištění?"},
    {"id": "nevim-kurz", "druh": "nevim", "kdo": "likvidace", "otazka": "Jaký je dnes kurz eura?"},
    {"id": "nevim-hypoteka", "druh": "nevim", "kdo": "likvidace", "otazka": "Jakou máte úrokovou sazbu hypotéky?"},
    {"id": "nevim-ridicak", "druh": "nevim", "kdo": "petra", "otazka": "Kdy mi končí platnost řidičského průkazu?"},
    # --- Oprávnění: Petra Malá se ptá na cizí smlouvy ---
    {"id": "opr-spoluucast", "druh": "opravneni", "kdo": "petra", "otazka": "Jakou spoluúčast má Tomáš Beneš?", "zakazane": ["Ford", "Focus", "3JK"]},
    {"id": "opr-auto", "druh": "opravneni", "kdo": "petra", "otazka": "Jaké auto má pojištěné Tomáš Beneš?", "zakazane": ["Ford", "Focus", "3JK"]},
    {"id": "opr-dodatek", "druh": "opravneni", "kdo": "petra", "otazka": "Co mění dodatek ke smlouvě 1004?", "zakazane": ["Ford", "Focus", "3JK"]},
]
