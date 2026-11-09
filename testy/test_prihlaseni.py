"""Přihlášení se třemi rolemi, chybné heslo, omezení pokusů, odhlášení."""

import re

import pytest
from playwright.sync_api import expect

from conftest import UCTY, prihlas_stranku

NAZEV_ROLE = {"admin": "Administrátor", "likvidace": "Pracovník likvidace", "klient": "Klient"}


@pytest.mark.parametrize("adresa", ["/", "/dokumenty"])
def test_neprihlaseny_jde_na_prihlaseni(novy_kontext, adresa):
    page = novy_kontext().new_page()
    page.goto(adresa)
    expect(page).to_have_url(re.compile(r"/prihlaseni$"))
    expect(page.get_by_role("heading", name="Přihlášení")).to_be_visible()


@pytest.mark.parametrize("ucet", ["admin", "likvidace", "klient"])
def test_kazda_role_se_prihlasi(prihlas, ucet):
    page = prihlas(ucet)
    expect(page.get_by_role("heading", level=1)).to_contain_text(UCTY[ucet]["jmeno"])
    expect(page.locator("main")).to_contain_text(NAZEV_ROLE[ucet])


def test_spatne_heslo(novy_kontext):
    page = novy_kontext().new_page()
    page.goto("/prihlaseni")
    page.get_by_label("E-mail", exact=True).fill(UCTY["klient"]["email"])
    page.get_by_label("Heslo", exact=True).fill("urcite-spatne-heslo")
    page.get_by_role("button", name="Přihlásit").click()
    expect(page.get_by_role("alert")).to_have_text("E-mail nebo heslo nesedí.")
    assert page.url.endswith("/prihlaseni")


def test_neznamy_email_hlasi_totez(novy_kontext):
    """Z hlášky nejde poznat, jestli účet existuje."""
    page = novy_kontext().new_page()
    page.goto("/prihlaseni")
    page.get_by_label("E-mail", exact=True).fill("nikdo@test.invalid")
    page.get_by_label("Heslo", exact=True).fill("cokoli")
    page.get_by_role("button", name="Přihlásit").click()
    expect(page.get_by_role("alert")).to_have_text("E-mail nebo heslo nesedí.")


def test_po_peti_pokusech_blokace(novy_kontext):
    page = novy_kontext().new_page()
    page.goto("/prihlaseni")
    for _ in range(5):
        page.get_by_label("E-mail", exact=True).fill(UCTY["admin"]["email"])
        page.get_by_label("Heslo", exact=True).fill("spatne")
        page.get_by_role("button", name="Přihlásit").click()
        expect(page.get_by_role("alert")).to_be_visible()
    # Ani správné heslo teď z téže adresy neprojde.
    page.get_by_label("E-mail", exact=True).fill(UCTY["admin"]["email"])
    page.get_by_label("Heslo", exact=True).fill(UCTY["admin"]["heslo"])
    page.get_by_role("button", name="Přihlásit").click()
    expect(page.get_by_role("alert")).to_contain_text("Příliš mnoho neúspěšných pokusů")
    # Z jiné adresy se přihlásit jde.
    prihlas_stranku(novy_kontext().new_page(), "admin")


def test_odhlaseni(prihlas):
    page = prihlas("likvidace")
    page.get_by_role("button", name="Odhlásit").click()
    expect(page.get_by_role("heading", name="Přihlášení")).to_be_visible()
    page.goto("/")
    assert page.url.endswith("/prihlaseni")


def test_prihlaseny_na_prihlaseni_jde_na_prehled(prihlas):
    page = prihlas("klient")
    page.goto("/prihlaseni")
    expect(page.get_by_role("heading", level=1)).to_contain_text("Dobrý den")
