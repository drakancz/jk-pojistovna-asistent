"""Vyhledávání v dokumentech (krok 2B): podle významu i slov, s dokumentem
a stránkou. Testovací server má nahraných 10 PDF JK pojišťovny (1C)."""

import pytest
from playwright.sync_api import Page, expect

from conftest import csrf, odesli_formular

PODMINKY_AUTO = "Pojistné podmínky pro havarijní pojištění vozidel"

# Otázky běžnými slovy (ne slovy z dokumentu) a text, který musí být
# v některém z pěti nalezených úryvků. Základ evaluační sady (fáze 5).
SADA = [
    ("Kolik zaplatím ze svého, když mi ukradnou auto?", "10 000"),
    ("Do kdy musím nahlásit krádež auta policii?", "24 hodin"),
    ("Je kryto, když srazím srnu?", "zvěří"),
    ("Kolik dostanu za ukradené kolo ze sklepa?", "15 000"),
    ("Při jaké rychlosti větru se hradí škoda na střeše?", "75 km"),
    ("Můžu se potápět do hloubky 30 metrů?", "40 m"),
    ("Proplatí mi zrušení zájezdu, když onemocním?", "80 %"),
    ("Jak dlouho uchováváte moje osobní údaje?", "10 let"),
    ("Co když mi někdo vykrade byt, který jsem nezamkl?", "20 000"),
    ("Jsem těhotná, zaplatí cestovní pojištění porod v cizině?", "26."),
    ("Jak a kdy vypovědět pojištění auta?", "6 týdnů"),
    ("Kolik je sleva za jízdu bez nehody?", "30 %"),
]
MINIMUM = 10  # z 12; 4. 11. 2026 našlo 11


def hledej(page: Page, otazka: str):
    page.goto("/hledani")
    page.get_by_label("Otázka", exact=True).fill(otazka)
    page.get_by_role("button", name="Hledat").click()
    expect(page.get_by_role("heading", name="Nalezené úryvky")).to_be_visible()
    return page.locator("li.nalez")


def test_najde_dokument_stranu_a_clanek(prihlas):
    page = prihlas("likvidace")
    page.get_by_role("link", name="Vyhledávání", exact=True).click()
    otazka = "Jaká je spoluúčast při odcizení vozidla?"
    nalezy = hledej(page, otazka)
    expect(nalezy).to_have_count(5)
    # Jiné testy nahrávají kopie podmínek pro auto pod vlastním názvem,
    # proto se hledá článek, ne konkrétní kopie dokumentu.
    spoluucast = nalezy.filter(has_text="Článek 5 – Spoluúčast").first
    expect(spoluucast).to_contain_text("strana 2")
    expect(spoluucast).to_contain_text("10 000 Kč")
    # Otázka zůstane v poli, ať jde upravit.
    expect(page.get_by_label("Otázka", exact=True)).to_have_value(otazka)
    # Likvidace detail dokumentu nevidí, takže ani odkaz na něj.
    expect(page.locator("li.nalez a")).to_have_count(0)


def test_cislo_smlouvy_najde_tu_smlouvu(prihlas):
    """Číslo smlouvy je jen v názvu dokumentu; hledání ho přesto využije
    (9. 11. 2026). Klientka cizí smlouvu podle čísla nenajde — hlídá
    test_klient.py (otázka s číslem 1004)."""
    page = prihlas("likvidace")
    nalezy = hledej(page, "Jaká je spoluúčast u smlouvy 1005?")
    expect(nalezy.filter(has_text="Pojistná smlouva č. 1005").first).to_be_visible()


def test_administrator_ma_odkaz_na_dokument(prihlas):
    page = prihlas("admin")
    nalezy = hledej(page, "Bonus za jízdu bez škod")
    nalezy.get_by_role("link", name=PODMINKY_AUTO).first.click()
    expect(page.get_by_role("heading", level=1)).to_have_text(PODMINKY_AUTO)


def test_sada_otazek(prihlas):
    page = prihlas("likvidace")
    nenalezeno = []
    for otazka, ocekavane in SADA:
        if ocekavane not in " ".join(hledej(page, otazka).all_inner_texts()):
            nenalezeno.append(otazka)
    assert len(SADA) - len(nenalezeno) >= MINIMUM, f"Nenalezeno: {nenalezeno}"


def test_prazdna_otazka(prihlas):
    page = prihlas("admin")
    odpoved = odesli_formular(page, "/hledani", data={"csrf": csrf(page), "otazka": "   "})
    assert odpoved.status == 400
    assert "Napište, co hledáte." in odpoved.text()


@pytest.mark.parametrize("ucet", ["admin", "likvidace"])
def test_odkaz_v_menu(prihlas, ucet):
    page = prihlas(ucet)
    expect(page.get_by_role("link", name="Vyhledávání", exact=True)).to_be_visible()
