"""Rozložení na telefonu: nic nepřečnívá do strany."""

import pytest
from playwright.sync_api import Playwright, expect

from conftest import DOKUMENTY, PDF, UCTY, bez_vodorovneho_posuvu, pripona

pytestmark = pytest.mark.telefon


@pytest.fixture
def telefon(playwright: Playwright) -> dict:
    zarizeni = dict(playwright.devices["Pixel 7"])
    zarizeni.pop("default_browser_type", None)  # prohlížeč volí pytest (chromium)
    return zarizeni


def test_prihlaseni_na_telefonu(novy_kontext, telefon):
    page = novy_kontext(**telefon).new_page()
    page.goto("/prihlaseni")
    expect(page.get_by_role("button", name="Přihlásit")).to_be_visible()
    bez_vodorovneho_posuvu(page)


@pytest.mark.parametrize("ucet", ["admin", "likvidace", "klient"])
def test_prehled_na_telefonu(prihlas, telefon, ucet):
    page = prihlas(ucet, **telefon)
    bez_vodorovneho_posuvu(page)


def test_dokumenty_na_telefonu(prihlas, telefon):
    page = prihlas("admin", **telefon)
    page.goto("/dokumenty")
    page.get_by_label("Název", exact=True).fill(f"Velmi dlouhý název pojistných podmínek pro telefon {pripona()}")
    page.get_by_label("Druh dokumentu", exact=True).select_option(label="Pojistné podmínky")
    page.get_by_label("Pojištění", exact=True).select_option(label="Cestovní pojištění")
    page.get_by_label("Soubor", exact=True).set_input_files(
        {"name": "dlouhy-nazev-souboru-s-podminkami-cestovniho-pojisteni.pdf",
         "mimeType": "application/pdf", "buffer": PDF}
    )
    page.get_by_role("button", name="Nahrát").click()
    expect(page.get_by_role("status")).to_be_visible()
    bez_vodorovneho_posuvu(page)


def test_detail_dokumentu_na_telefonu(prihlas, telefon):
    page = prihlas("admin", **telefon)
    nazev = f"Smlouva na telefonu {pripona()}"
    page.goto("/dokumenty")
    page.get_by_label("Název", exact=True).fill(nazev)
    page.get_by_label("Druh dokumentu", exact=True).select_option(label="Smlouva")
    page.get_by_label("Pojištění", exact=True).select_option(label="Havarijní pojištění auta")
    page.get_by_label("Klient", exact=True).select_option(label=UCTY["klient"]["jmeno"])
    page.get_by_label("Soubor", exact=True).set_input_files(
        {"name": "smlouva.pdf", "mimeType": "application/pdf",
         "buffer": (DOKUMENTY / "05-smlouva-1001-auto.pdf").read_bytes()}
    )
    page.get_by_role("button", name="Nahrát").click()
    page.get_by_role("link", name=nazev).click()
    expect(page.locator("#stav-cteni")).to_have_text("Přečteno", timeout=30_000)
    page.get_by_text("Strana 1", exact=True).click()
    expect(page.locator("details.strana").first).to_contain_text("TMBJK000000001001")
    bez_vodorovneho_posuvu(page)


def test_vyhledavani_na_telefonu(prihlas, telefon):
    page = prihlas("likvidace", **telefon)
    page.goto("/hledani")
    page.get_by_label("Otázka", exact=True).fill("Kolik dostanu za ukradené kolo ze sklepa?")
    page.get_by_role("button", name="Hledat").click()
    expect(page.locator("li.nalez").first).to_be_visible()
    bez_vodorovneho_posuvu(page)


def test_asistent_na_telefonu(prihlas, telefon):
    page = prihlas("admin", **telefon)
    page.goto("/asistent")
    page.get_by_label("Otázka", exact=True).fill("Kolik dostanu za ukradené kolo ze sklepa?")
    page.get_by_role("button", name="Zeptat se").click()
    expect(page.locator("#zdroj-1")).to_be_visible()
    page.locator("details.poslane summary").click()
    bez_vodorovneho_posuvu(page)


def test_klient_asistent_na_telefonu(prihlas, telefon):
    # Krok 3B: klient se ptá na svou smlouvu (Petra Malá, smlouva 1001).
    page = prihlas("petra", **telefon)
    page.goto("/asistent")
    page.get_by_label("Otázka", exact=True).fill("Jakou spoluúčast mám u Škody Octavia, smlouva 1001?")
    page.get_by_role("button", name="Zeptat se").click()
    expect(page.locator("#zdroj-1")).to_be_visible()
    page.locator("details.poslane summary").click()
    bez_vodorovneho_posuvu(page)
