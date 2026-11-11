"""Krok 3B: klient a oprávnění ve vyhledávání.

Klient se ptá asistenta jen nad pojistnými podmínkami a svými smlouvami
(zadání 3. 11., Jakub 4. 11. 2026). Hlavní kontrola je v tom, co skutečně
odešlo k AI (napodobenina si pamatuje názvy poslaných úryvků): cizí
smlouva ani hlášení škody tam nesmí být nikdy — ani když se na ně klient
zeptá přímo. Petra Malá má smlouvy 1001–1003, Tomáš Beneš 1004, 1005
a dodatek (docs/dokumenty.md).

Každý odeslaný úryvek se ověřuje proti seznamu dokumentů, jak ho vidí
administrátor (druh a komu patří) — během sady totiž jiné testy nahrávají
další podmínky, smlouvy i hlášení."""

import pytest
from playwright.sync_api import Page, expect

from conftest import PNG, UCTY, csrf, napodobenina, odesli_formular, pripona
from test_cteni import CEKANI, otevri_detail, stav
from test_dokumenty import nahraj

PETRA = ("Pojistná smlouva č. 1001", "Pojistná smlouva č. 1002", "Pojistná smlouva č. 1003")
TOMAS = ("Pojistná smlouva č. 1004", "Pojistná smlouva č. 1005", "Dodatek č. 1 k pojistné smlouvě č. 1004")

NA_TOMASE = "Jakou spoluúčast má Tomáš Beneš na Ford Focus podle dodatku ke smlouvě 1004?"
NA_PETRU = "Jakou spoluúčast má Petra Malá u havarijního pojištění Škody Octavia, smlouva 1001?"


def zeptej_se(page: Page, otazka: str) -> list[str]:
    """Položí otázku tlačítkem a vrátí názvy úryvků, které odešly k AI."""
    page.goto("/asistent")
    page.get_by_label("Otázka", exact=True).fill(otazka)
    page.get_by_role("button", name="Zeptat se").click()
    expect(page.locator("#odpoved")).to_be_visible()
    return napodobenina("/_posledni")["posledni"]["uryvky"]


def nazev_dokumentu(titul: str) -> str:
    """„Název dokumentu, strana 2 – Článek 5“ → „Název dokumentu“."""
    return titul.rsplit(", strana ", 1)[0]


def over_jen_povolene(prihlas, poslane: list[str], jmeno_klienta: str) -> None:
    """Každý úryvek, který odešel k AI, je z podmínek nebo ze smlouvy
    tohoto klienta. Pravdu bere ze seznamu dokumentů administrátora."""
    admin = prihlas("admin")
    admin.goto("/dokumenty")
    radky = admin.locator("table tbody tr").evaluate_all(
        """radky => radky.map(r => [
            r.querySelector('td[data-popis="Název"] strong').textContent.trim(),
            r.querySelector('td[data-popis="Druh"]').textContent.trim(),
            r.querySelector('td[data-popis="Klient"]').textContent.trim(),
        ])"""
    )
    dokumenty = {nazev: (druh, klient) for nazev, druh, klient in radky}
    assert poslane, "podmínky měl asistent dostat"
    for titul in poslane:
        druh, klient = dokumenty[nazev_dokumentu(titul)]
        assert druh == "Pojistné podmínky" or (druh == "Smlouva" and klient == jmeno_klienta), (
            f"{jmeno_klienta} dostal(a) k AI cizí úryvek: {titul} ({druh}, {klient})"
        )


def test_klient_ma_asistenta(prihlas):
    page = prihlas("petra")
    expect(page.get_by_role("main")).to_contain_text("Ptejte se asistenta na pojistné podmínky a na své smlouvy.")
    page.get_by_role("link", name="Asistent", exact=True).click()
    expect(page.get_by_role("heading", level=2)).to_have_text("Zeptejte se na podmínky a své smlouvy")
    expect(page.locator("#zbyva")).to_contain_text("z 20 otázek")
    # Vyhledávání a dokumenty zůstávají jen pro tým.
    expect(page.get_by_role("link", name="Vyhledávání", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="Dokumenty", exact=True)).to_have_count(0)


def test_klient_najde_svou_smlouvu(prihlas):
    page = prihlas("petra")
    poslane = zeptej_se(page, NA_PETRU)
    assert any(n.startswith(PETRA[0]) for n in poslane), poslane
    # Odpověď cituje úryvek, který AI dostala (napodobenina cituje první).
    expect(page.locator("#zdroj-1")).to_contain_text(nazev_dokumentu(poslane[0]))
    # Klient nemá detail dokumentu, takže ani odkaz na něj.
    expect(page.locator("#zdroj-1").get_by_role("link")).to_have_count(0)
    over_jen_povolene(prihlas, poslane, "Petra Malá")


def test_otazka_na_svou_smlouvu_bez_cisla(prihlas):
    # „Svého auta“ bez čísla smlouvy: hledání samo našlo jen podmínky (obě
    # varianty) a asistent nevěděl, kterou má klientka (10. 11. 2026).
    # K nalezeným se proto přidá její smlouva ke stejnému pojištění.
    page = prihlas("petra")
    poslane = zeptej_se(page, "Mám u svého auta krytý střet se zvěří?")
    assert any(n.startswith(PETRA[0]) for n in poslane), poslane
    assert not any(n.startswith(TOMAS) for n in poslane), poslane
    over_jen_povolene(prihlas, poslane, "Petra Malá")


def test_otazka_na_cizi_smlouvu_ji_opravdu_najde(prihlas):
    # Kontrola testu níž: stejná otázka u likvidace Benešovy smlouvy najde.
    # Bez toho by „klient je nedostal“ mohlo projít jen proto, že je
    # vyhledávání nenajde vůbec.
    poslane = zeptej_se(prihlas("likvidace"), NA_TOMASE)
    assert any(n.startswith(TOMAS) for n in poslane), poslane


@pytest.mark.parametrize(
    ("ucet", "jmeno", "otazka", "cizi"),
    [("petra", "Petra Malá", NA_TOMASE, TOMAS), ("tomas", "Tomáš Beneš", NA_PETRU, PETRA)],
)
def test_cizi_smlouva_do_ai_neodejde(prihlas, ucet, jmeno, otazka, cizi):
    page = prihlas(ucet)
    poslane = zeptej_se(page, otazka)
    assert not any(n.startswith(cizi) for n in poslane), poslane
    # Ani v seznamu „Z čeho asistent vybíral“ cizí smlouva není.
    vybiral = page.locator("details.poslane").text_content() or ""
    for nazev in cizi:
        assert nazev not in vybiral
    over_jen_povolene(prihlas, poslane, jmeno)


def test_klient_bez_smluv_dostane_jen_podminky(prihlas):
    page = prihlas("klient2")
    poslane = zeptej_se(page, "Co mám ve smlouvě o spoluúčasti a jaké je pojistné?")
    over_jen_povolene(prihlas, poslane, UCTY["klient2"]["jmeno"])


def test_hlaseni_skody_klient_nedostane_ani_svoje(prihlas):
    # Hlášení škody vidí jen likvidace a administrátor (zadání 3. 11. 2026),
    # i když patří klientovi.
    admin = prihlas("admin")
    nazev = f"Hlášení škody klienta {pripona()}"
    nahraj(admin, nazev, "Hlášení škody", "Havarijní pojištění auta",
           {"name": "hlaseni.png", "mimeType": "image/png", "buffer": PNG},
           klient=UCTY["klient2"]["jmeno"])
    otevri_detail(admin, nazev)
    expect(stav(admin)).to_have_text("Přečteno", timeout=CEKANI)

    # Otázka na slova z přepisu hlášení („Přepis napodobeniny OCR“).
    poslane = zeptej_se(prihlas("klient2"), "Přepis napodobeniny OCR: hlášení škody, datum škody 12. 10. 2026")
    assert not any(nazev_dokumentu(n) == nazev for n in poslane), poslane
    over_jen_povolene(prihlas, poslane, UCTY["klient2"]["jmeno"])


def test_klient_primo_odeslany_dotaz_take_jen_svoje(prihlas):
    # Odeslání mimo formulář nic neobejde — filtr je na serveru.
    page = prihlas("petra")
    odpoved = odesli_formular(page, "/asistent", data={"csrf": csrf(page), "otazka": NA_TOMASE})
    assert odpoved.status == 200
    poslane = napodobenina("/_posledni")["posledni"]["uryvky"]
    assert not any(n.startswith(TOMAS) for n in poslane), poslane
    over_jen_povolene(prihlas, poslane, "Petra Malá")
