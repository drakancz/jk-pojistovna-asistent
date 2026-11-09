"""Kdo smí na správu dokumentů: jen administrátor. Ostatní 404, i při přímém
odeslání formuláře mimo tlačítka. Plus ochrana formulářů a hlavičky."""

import pytest
from playwright.sync_api import expect

from conftest import ADRESA, PDF, csrf, odesli_formular


@pytest.mark.parametrize("ucet", ["klient", "likvidace"])
def test_dokumenty_jen_administrator(prihlas, ucet):
    page = prihlas(ucet)
    # V menu odkaz není…
    expect(page.get_by_role("link", name="Dokumenty")).to_have_count(0)
    # …a adresa vrací 404.
    odpoved = page.goto("/dokumenty")
    assert odpoved is not None and odpoved.status == 404
    expect(page.get_by_role("heading", name="Stránka nenalezena")).to_be_visible()


@pytest.mark.parametrize("ucet", ["klient", "likvidace"])
def test_nahrani_a_smazani_primo_vraci_404(prihlas, ucet):
    page = prihlas(ucet)
    token = csrf(page)  # platný token vlastního sezení
    nahrani = odesli_formular(
        page,
        "/dokumenty",
        multipart={
            "csrf": token,
            "nazev": "Podvržené",
            "druh": "PODMINKY",
            "pojisteni": "AUTO",
            "soubor": {"name": "a.pdf", "mimeType": "application/pdf", "buffer": PDF},
        },
    )
    assert nahrani.status == 404
    smazani = odesli_formular(page, "/dokumenty/1/smazat", data={"csrf": token})
    assert smazani.status == 404
    # Ani opakované čtení (krok 2A) mimo tlačítka.
    cteni = odesli_formular(page, "/dokumenty/1/precist", data={"csrf": token})
    assert cteni.status == 404


@pytest.mark.parametrize("ucet", ["klient", "likvidace"])
def test_detail_dokumentu_jen_administrator(prihlas, ucet):
    # Přečtený text a úryvky vidí jen administrátor (Jakub, 4. 11. 2026).
    page = prihlas(ucet)
    odpoved = page.goto("/dokumenty/1")
    assert odpoved is not None and odpoved.status == 404
    expect(page.get_by_role("heading", name="Stránka nenalezena")).to_be_visible()


def test_neprihlaseny_nevidi_detail(novy_kontext):
    page = novy_kontext().new_page()
    page.goto("/dokumenty/1")
    expect(page).to_have_url("/prihlaseni")
    odpoved = odesli_formular(page, "/dokumenty/1/precist", data={"csrf": "x"})
    assert odpoved.status == 303
    assert odpoved.headers["location"].endswith("/prihlaseni")


def test_neexistujici_dokument_404(prihlas):
    page = prihlas("admin")
    odpoved = page.goto("/dokumenty/999999")
    assert odpoved is not None and odpoved.status == 404


def test_neprihlaseny_nenahraje(novy_kontext):
    page = novy_kontext().new_page()
    page.goto("/prihlaseni")
    odpoved = odesli_formular(page, "/dokumenty", data={"nazev": "x"})
    assert odpoved.status == 303
    assert odpoved.headers["location"].endswith("/prihlaseni")


def test_administrator_vidi_dokumenty(prihlas):
    page = prihlas("admin")
    page.get_by_role("link", name="Dokumenty", exact=True).click()
    expect(page.get_by_role("heading", name="Dokumenty", level=1)).to_be_visible()


def test_formular_z_cizi_stranky_odmitnut(prihlas):
    page = prihlas("admin")
    odpoved = page.request.post(
        "/dokumenty/1/smazat",
        form={"csrf": csrf(page)},
        headers={"Origin": "https://utocnik.example"},
        max_redirects=0,
    )
    assert odpoved.status == 403


def test_spatny_csrf_nic_nesmaze(prihlas):
    page = prihlas("admin")
    odpoved = odesli_formular(page, "/dokumenty/1/smazat", data={"csrf": "spatny"})
    assert odpoved.status == 303
    assert "zprava" not in odpoved.headers["location"]


def test_bezpecnostni_hlavicky(novy_kontext):
    page = novy_kontext().new_page()
    odpoved = page.goto(f"{ADRESA}/prihlaseni")
    assert odpoved is not None
    hlavicky = odpoved.headers
    assert "script-src 'self'" in hlavicky["content-security-policy"]
    assert "frame-ancestors 'none'" in hlavicky["content-security-policy"]
    assert hlavicky["x-content-type-options"] == "nosniff"
    assert "server" not in hlavicky


def test_klient_vyhledavani_nema(prihlas):
    # Klient má jen Asistenta, Vyhledávání je pro tým (Jakub, 4. 11. 2026,
    # krok 3B). Co klient přes asistenta najde, hlídá test_klient.py.
    page = prihlas("petra")
    expect(page.get_by_role("link", name="Vyhledávání", exact=True)).to_have_count(0)
    odpoved = page.goto("/hledani")
    assert odpoved is not None and odpoved.status == 404
    page.goto("/")
    hledani = odesli_formular(page, "/hledani", data={"csrf": csrf(page), "otazka": "spoluúčast"})
    assert hledani.status == 404
    assert "spoluúčast" not in hledani.text().lower()


def test_neprihlaseny_nehleda(novy_kontext):
    page = novy_kontext().new_page()
    page.goto("/hledani")
    expect(page).to_have_url("/prihlaseni")
    odpoved = odesli_formular(page, "/hledani", data={"csrf": "x", "otazka": "spoluúčast"})
    assert odpoved.status == 303
    assert odpoved.headers["location"].endswith("/prihlaseni")


def test_neprihlaseny_asistenta_nema(novy_kontext):
    page = novy_kontext().new_page()
    page.goto("/asistent")
    expect(page).to_have_url("/prihlaseni")
    odpoved = odesli_formular(page, "/asistent", data={"csrf": "x", "otazka": "spoluúčast"})
    assert odpoved.status == 303
