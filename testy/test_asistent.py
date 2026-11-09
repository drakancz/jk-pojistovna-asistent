"""Asistent (krok 3A): odpověď s citací dokumentu a stránky, „nevím“,
denní limit na účet. V testech odpovídá napodobenina Anthropicu — nic
neodchází ven. Celkový limit hlídá test_zz_limit_celkem.py (běží poslední)."""

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import csrf, napodobenina, odesli_formular

NEVIM = "Nevím – v dokumentech, které můžete vidět, odpověď není."


def zeptej_se(page: Page, otazka: str) -> None:
    page.goto("/asistent")
    page.get_by_label("Otázka", exact=True).fill(otazka)
    page.get_by_role("button", name="Zeptat se").click()


def zbyva(page: Page) -> int:
    nalez = re.search(r"Zbývá vám dnes (\d+)", page.locator("#zbyva").inner_text())
    assert nalez is not None
    return int(nalez.group(1))


def test_odpoved_s_citaci(prihlas):
    page = prihlas("likvidace")
    page.get_by_role("link", name="Asistent", exact=True).click()
    pred = zbyva(page)
    zeptej_se(page, "Jaká je spoluúčast při odcizení vozidla?")

    odpoved = page.locator("#odpoved")
    expect(odpoved).to_contain_text("odpověď napodobeniny")
    expect(odpoved.get_by_role("link", name="zdroj 1")).to_be_visible()
    # Citovaný zdroj = úryvek, který Claude dostal jako první, i se stránkou.
    zdroj = page.locator("#zdroj-1")
    # Seznam je sbalený (details), proto text_content místo inner_text.
    prvni_poslany = " ".join((page.locator("details.poslane li").first.text_content() or "").split())
    dokument, strana = prvni_poslany.split(" · ")[:2]
    expect(zdroj).to_contain_text(dokument)
    expect(zdroj).to_contain_text(strana)
    # Likvidace detail dokumentu nevidí, takže ani odkaz na něj.
    expect(zdroj.get_by_role("link")).to_have_count(0)

    posledni = napodobenina("/_posledni")["posledni"]
    assert posledni["model"] == "claude-haiku-5-5"
    assert posledni["pokyny"] and posledni["citace"]
    assert len(posledni["uryvky"]) == 8
    assert posledni["uryvky"][0].startswith(dokument)
    # Do limitu se otázka započítala.
    assert zbyva(page) == pred - 1


def test_bez_citace_je_nevim(prihlas):
    page = prihlas("admin")
    zeptej_se(page, "Jaký je dnes kurz eura?")
    expect(page.locator("#odpoved")).to_have_text(NEVIM)
    expect(page.locator("ol.zdroje")).to_have_count(0)


def test_podvrzena_citace_se_zahodi(prihlas):
    # Citace na úryvek, který jsme Claudovi neposlali, se nezobrazí —
    # a odpověď bez platné citace je „nevím“.
    page = prihlas("admin")
    zeptej_se(page, "podvrh: jaká je spoluúčast?")
    expect(page.locator("#odpoved")).to_have_text(NEVIM)


def test_administrator_ma_odkaz_na_dokument(prihlas):
    page = prihlas("admin")
    zeptej_se(page, "Bonus za jízdu bez škod")
    odkaz = page.locator("#zdroj-1").get_by_role("link")
    nazev = odkaz.inner_text()
    odkaz.click()
    expect(page.get_by_role("heading", level=1)).to_have_text(nazev)


def test_chyba_ai_se_nepocita(prihlas):
    page = prihlas("admin")
    page.goto("/asistent")
    pred = zbyva(page)
    napodobenina("/_rezim", {"chyba": True})
    try:
        zeptej_se(page, "Jaká je spoluúčast?")
        expect(page.get_by_role("alert")).to_contain_text("Otázka se nepočítá do limitu.")
    finally:
        napodobenina("/_rezim", {"chyba": False})
    # Otázka zůstane v poli a do limitu se nepočítá.
    expect(page.get_by_label("Otázka", exact=True)).to_have_value("Jaká je spoluúčast?")
    assert zbyva(page) == pred


def test_prazdna_otazka(prihlas):
    page = prihlas("admin")
    odpoved = odesli_formular(page, "/asistent", data={"csrf": csrf(page), "otazka": "  "})
    assert odpoved.status == 400
    assert "Napište, na co se chcete zeptat." in odpoved.text()


def test_limit_na_ucet(prihlas):
    page = prihlas("limit")
    page.goto("/asistent")
    for _ in range(zbyva(page)):
        odpoved = odesli_formular(page, "/asistent", data={"csrf": csrf(page), "otazka": "Co je totální škoda?"})
        assert odpoved.status == 200
    page.goto("/asistent")
    assert zbyva(page) == 0
    expect(page.get_by_role("button", name="Zeptat se")).to_be_disabled()
    # Ani přímé odeslání mimo tlačítko limit neobejde a k AI nic neodejde.
    pred = napodobenina("/_posledni")["pocet"]
    odpoved = odesli_formular(page, "/asistent", data={"csrf": csrf(page), "otazka": "Ještě jedna?"})
    assert odpoved.status == 429
    assert "Dnes jste už položili všech 20 otázek" in odpoved.text()
    assert napodobenina("/_posledni")["pocet"] == pred


@pytest.mark.parametrize("ucet", ["admin", "likvidace", "petra"])
def test_odkaz_v_menu(prihlas, ucet):
    page = prihlas(ucet)
    expect(page.get_by_role("link", name="Asistent", exact=True)).to_be_visible()
