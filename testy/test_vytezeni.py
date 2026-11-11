"""Krok 4B: vytěžení údajů z hlášení škody.

Testovací server má nahraných 5 ukázkových hlášení (krok 4A), přečtených
napodobeninou OCR. Napodobenina na každé vytěžení vrátí správné údaje
hlášení 1001 — u něj tedy sedí všech 22 údajů, u ostatních méně. Tím se
ověří i měření přesnosti.

Oprávnění (Jakub, 4. 11. 2026): seznam, detail a sken vidí likvidace
a administrátor, klient dostane 404 (ani svoje hlášení), „Vytěžit znovu“
jen administrátor."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from conftest import DOKUMENTY, bez_vodorovneho_posuvu, csrf, napodobenina, odesli_formular

CEKANI = 30_000
SEZNAM = json.loads((DOKUMENTY / "hlaseni.json").read_text(encoding="utf-8"))
NAZEV = {p["smlouva"]: p["nazev"] for p in SEZNAM}


def id_hlaseni(page: Page, smlouva: str) -> int:
    page.goto("/hlaseni")
    odkaz = page.get_by_role("link", name=NAZEV[smlouva])
    return int(odkaz.get_attribute("href").rsplit("/", 1)[1])


def radek(page: Page, smlouva: str):
    return page.locator("table.hlaseni tbody tr").filter(has_text=NAZEV[smlouva])


def udaj(page: Page, klic: str):
    return page.locator(f'tr[data-udaj="{klic}"]')


def test_likvidace_vidi_vytezena_hlaseni(prihlas):
    page = prihlas("likvidace")
    page.get_by_role("link", name="Hlášení škody").click()
    expect(page).to_have_url(re.compile(r"/hlaseni$"))
    for p in SEZNAM:
        r = radek(page, p["smlouva"])
        expect(r).to_have_count(1)
        expect(r.locator('td[data-popis="Klient"]')).to_have_text(p["klient"])
        expect(r.locator('td[data-popis="Vytěžení"]')).to_have_text("Vytěženo", timeout=CEKANI)
    # Napodobenina vrací údaje hlášení 1001: smlouva, datum, částka.
    r = radek(page, "1001")
    expect(r.locator('td[data-popis="Smlouva"]')).to_have_text("1001")
    expect(r.locator('td[data-popis="Datum události"]')).to_have_text("9. 10. 2026")
    expect(r.locator('td[data-popis="Odhad škody"]')).to_have_text("18 500 Kč")
    # Přesnost vidí jen administrátor.
    expect(page.locator("#presnost-celkem")).to_have_count(0)


def test_detail_s_navrhem_a_skenem(prihlas):
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{id_hlaseni(page, '1001')}")
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    # Likvidace vidí návrh ve formuláři kontroly (krok 4C).
    expect(page.get_by_label("Pojistník", exact=True)).to_have_value("Petra Malá")
    expect(page.get_by_label("Registrační značka", exact=True)).to_have_value("1JK 0001")
    expect(page.get_by_label("Šetřila policie", exact=True)).to_have_value("ano")
    expect(page.get_by_label("Druh pojištění", exact=True)).to_have_value("auto")
    expect(page.get_by_label("Svědek nebo jiný účastník", exact=True)).to_have_value("")
    # Sken je vidět přímo na stránce (PNG) a jde otevřít.
    obrazek = page.locator("img.sken")
    expect(obrazek).to_be_visible()
    assert obrazek.evaluate("i => i.naturalWidth") > 1000
    # Likvidace nevytěžuje znovu (platí se) a nevidí kontrolu proti vzoru.
    expect(page.get_by_role("button", name="Vytěžit znovu")).to_have_count(0)
    expect(page.locator("#presnost")).to_have_count(0)
    expect(page.get_by_role("link", name="Text stránek a úryvky")).to_have_count(0)


def test_sken_pdf_ma_spravny_typ(prihlas):
    page = prihlas("likvidace")
    cislo = id_hlaseni(page, "1002")
    odpoved = page.request.get(f"/hlaseni/{cislo}/sken")
    assert odpoved.status == 200
    assert odpoved.headers["content-type"] == "application/pdf"
    assert odpoved.body().startswith(b"%PDF-")
    # Vlastní úzká politika: PDF se zobrazí, ale nespustí se žádný skript.
    csp = odpoved.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src" not in csp
    assert "frame-ancestors 'none'" in csp
    assert odpoved.headers["x-content-type-options"] == "nosniff"
    # Ostatní stránky mají dál přísnou politiku celé aplikace.
    stranka = page.request.get(f"/hlaseni/{cislo}")
    assert "object-src 'none'" in stranka.headers["content-security-policy"]


def test_administrator_vidi_presnost(prihlas):
    page = prihlas("admin")
    page.goto("/hlaseni")
    expect(radek(page, "1001").locator('td[data-popis="Přesnost"]')).to_have_text("22 z 22", timeout=CEKANI)
    # Kolo ze sklepa (1005) má jiné údaje než napodobenina: smlouva nesedí.
    jine = radek(page, "1005").locator('td[data-popis="Přesnost"]')
    expect(jine).to_have_text(re.compile(r"^\d+ z 22$"))
    assert int(jine.inner_text().split()[0]) < 22
    expect(page.locator("#presnost-celkem")).to_contain_text("údajů")

    page.get_by_role("link", name=NAZEV["1005"]).click()
    expect(udaj(page, "cislo_smlouvy")).to_contain_text("✗ správně: 1005")
    expect(udaj(page, "odhad_skody")).to_contain_text("✗ správně: 24 500 Kč")
    expect(udaj(page, "email")).to_contain_text("✗ správně: tomas.benes@example.com")
    # Prázdné u obou (poškozená osoba) sedí.
    expect(udaj(page, "poskozena_osoba")).to_contain_text("✓ sedí")


def test_vytezit_znovu_posle_prepis_se_schematem(prihlas):
    page = prihlas("admin")
    page.goto(f"/hlaseni/{id_hlaseni(page, '1004')}")
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    pred = napodobenina("/_posledni")["pocet_vytezeni"]
    page.get_by_role("button", name="Vytěžit znovu").click()
    expect(page.get_by_role("status")).to_have_text("Hlášení se znovu vytěžuje.")
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    stav = napodobenina("/_posledni")
    assert stav["pocet_vytezeni"] == pred + 1
    v = stav["vytezeni"]
    assert v["model"] == "claude-haiku-5-5"
    assert v["schema"] and v["prepis"] and v["pokyny"]
    assert v["thinking"] == {"type": "adaptive"}
    # Limit 16 nepovinných polí ve schématu (Anthropic jinak vrátí 400,
    # zjištěno naostro 10. 11. 2026) hlídá `vytezeni.pocet_nepovinnych()`;
    # napodobenina schéma ukládá jen jako ano/ne. TODO: test přes napodobeninu.
    assert v["bloky"] == [{"type": "text", "media_type": None}], "k vytěžení jde jen text, ne obrázek"


def test_chyba_ai_se_ukaze_a_jde_zopakovat(prihlas):
    page = prihlas("admin")
    page.goto(f"/hlaseni/{id_hlaseni(page, '1003')}")
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    napodobenina("/_rezim", {"chyba": True})
    try:
        page.get_by_role("button", name="Vytěžit znovu").click()
        expect(page.locator("#stav-vytezeni")).to_have_text("Chyba vytěžení", timeout=CEKANI)
        expect(page.locator(".udaje")).to_contain_text("Služba AI vrátila chybu 400.")
    finally:
        napodobenina("/_rezim", {"chyba": False})
    page.get_by_role("button", name="Vytěžit znovu").click()
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    expect(udaj(page, "pojistnik")).to_contain_text("Petra Malá")


def test_klient_hlaseni_nevidi(prihlas):
    admin = prihlas("admin")
    cislo = id_hlaseni(admin, "1001")
    page = prihlas("petra")  # ani svoje hlášení
    expect(page.get_by_role("link", name="Hlášení škody")).to_have_count(0)
    token = csrf(page)  # platný token vlastního sezení (stránka 404 formulář nemá)
    for adresa in ("/hlaseni", f"/hlaseni/{cislo}", f"/hlaseni/{cislo}/sken"):
        odpoved = page.goto(adresa)
        assert odpoved is not None and odpoved.status == 404, adresa
    znovu = odesli_formular(page, f"/hlaseni/{cislo}/vytezit", data={"csrf": token})
    assert znovu.status == 404


def test_likvidace_nevytezi_znovu(prihlas):
    page = prihlas("likvidace")
    cislo = id_hlaseni(page, "1001")
    pred = napodobenina("/_posledni")["pocet_vytezeni"]
    odpoved = odesli_formular(page, f"/hlaseni/{cislo}/vytezit", data={"csrf": csrf(page)})
    assert odpoved.status == 404
    assert napodobenina("/_posledni")["pocet_vytezeni"] == pred


def test_jiny_dokument_neni_hlaseni(prihlas):
    # Smlouva není hlášení: detail ani sken přes /hlaseni nejdou.
    page = prihlas("likvidace")
    for adresa in ("/hlaseni/1", "/hlaseni/1/sken"):
        odpoved = page.goto(adresa)
        assert odpoved is not None and odpoved.status == 404, adresa


def test_neprihlaseny_jde_na_prihlaseni(novy_kontext):
    page = novy_kontext().new_page()
    for adresa in ("/hlaseni", "/hlaseni/1", "/hlaseni/1/sken"):
        page.goto(adresa)
        expect(page).to_have_url(re.compile(r"/prihlaseni$"))
    odpoved = odesli_formular(page, "/hlaseni/1/vytezit", data={"csrf": "x"})
    assert odpoved.status == 303 and odpoved.headers["location"].endswith("/prihlaseni")


@pytest.mark.telefon
def test_detail_hlaseni_na_telefonu(prihlas, playwright):
    zarizeni = dict(playwright.devices["Pixel 7"])
    zarizeni.pop("default_browser_type", None)
    page = prihlas("admin", **zarizeni)
    page.goto("/hlaseni")
    bez_vodorovneho_posuvu(page)
    page.get_by_role("link", name=NAZEV["1002"]).click()
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    bez_vodorovneho_posuvu(page)
