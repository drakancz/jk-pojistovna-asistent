"""Krok 4A: vymyšlená naskenovaná hlášení škody.

Pět skenů (`dokumenty/11-…` až `15-…`) vyrábí `scripts/dokumenty/skeny.py`,
správné údaje jsou v `dokumenty/hlaseni.json`. Testovací server je nahrává
příkazem `ukazkove-dokumenty` spolu s deseti PDF a čte je přes OCR
(napodobenina, nic neodchází ven)."""

import json

from playwright.sync_api import expect

from conftest import DOKUMENTY
from test_klient import over_jen_povolene, zeptej_se

SEZNAM = json.loads((DOKUMENTY / "hlaseni.json").read_text(encoding="utf-8"))
SMLOUVY = {
    p["smlouva"]: (p["pojisteni"], p["klient"])
    for p in json.loads((DOKUMENTY / "seznam.json").read_text(encoding="utf-8"))
    if p["typ"] == "smlouva"
}
ZACATEK = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".pdf": b"%PDF-"}


def test_skeny_sedi_se_smlouvami():
    assert len(SEZNAM) == 5
    assert len({p["kvalita"] for p in SEZNAM}) == 5, "každý sken má jinou kvalitu"
    assert {p["soubor"].rsplit(".", 1)[1] for p in SEZNAM} == {"png", "jpg", "pdf"}
    for p in SEZNAM:
        obsah = (DOKUMENTY / p["soubor"]).read_bytes()
        assert obsah.startswith(ZACATEK["." + p["soubor"].rsplit(".", 1)[1]]), p["soubor"]
        u = p["spravne_udaje"]
        # Hlášení navazuje na skutečnou smlouvu stejného klienta a pojištění.
        assert SMLOUVY[u["cislo_smlouvy"]] == (u["pojisteni"], u["pojistnik"]) == (p["pojisteni"], p["klient"])
        assert u["email"].endswith("@example.com")
        if u["polozky"]:
            assert sum(v["cena"] for v in u["polozky"]) == u["odhad_skody"]
        if u["policie"]:
            assert u["cislo_jednaci"]


def test_skeny_jsou_nahrane_u_klienta_a_prectene(prihlas):
    page = prihlas("admin")
    page.goto("/dokumenty")
    for p in SEZNAM:
        radek = page.locator("table tbody tr").filter(has_text=p["nazev"])
        expect(radek).to_have_count(1)
        expect(radek.locator('td[data-popis="Druh"]')).to_have_text("Hlášení škody")
        expect(radek.locator('td[data-popis="Klient"]')).to_have_text(p["klient"])
        expect(radek.locator('td[data-popis="Čtení"]')).to_contain_text("Přečteno")
        expect(radek.locator('td[data-popis="Čtení"]')).to_contain_text("2 strany" if p["stran"] == 2 else "1 strana")


def test_dvoustrankove_pdf_jde_cele_pres_ocr(prihlas):
    page = prihlas("admin")
    page.goto("/dokumenty")
    nazev = next(p["nazev"] for p in SEZNAM if p["stran"] == 2)
    page.get_by_role("link", name=nazev).click()
    for cislo in (1, 2):
        expect(page.get_by_text(f"Strana {cislo} · přepis skenu (OCR)")).to_be_visible()


def test_klientka_k_ai_neposle_ani_svoje_hlaseni(prihlas):
    page = prihlas("petra")
    poslane = zeptej_se(page, "Co jsem uvedla v hlášení škody o úrazu manžela na ledovci Stubai?")
    over_jen_povolene(prihlas, poslane, "Petra Malá")
