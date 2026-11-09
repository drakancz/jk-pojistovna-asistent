"""Krok 6A: živá ukázka (UKAZKA=1) na vlastním serveru `web-ukazka`.

Rozhodnutí Jakuba (8. 11. 2026):
- tři ukázkové účty se známým heslem na přihlašovací stránce,
- ukázkový administrátor jen prohlíží — nahrávání, mazání, „Přečíst znovu“
  a „Vytěžit znovu“ server odmítne i při přímém odeslání,
- limit asistenta na návštěvníka (adresu), ne na sdílený účet,
- každou noc se data vrátí (v testech na požádání hlavičkou).

Testy v souboru běží po sobě; obnova odhlásí všechny, proto je poslední.
"""

import os
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, expect

from conftest import PDF, bez_vodorovneho_posuvu, nahodna_ip

ADRESA = os.environ.get("ZAKLADNI_ADRESA_UKAZKY", "http://web-ukazka:8300")
HESLO = "ukazka-JK-2026"
CEKANI = 60_000
HLASENI = "Hlášení škody ke smlouvě 1001 – odřené dveře na parkovišti"
ROLE = {"admin": "Administrátor", "likvidace": "Pracovník likvidace", "klient": "Klient"}


@pytest.fixture
def kontext(browser: Browser):
    kontexty: list[BrowserContext] = []

    def vytvor(ip: str | None = None, **volby) -> BrowserContext:
        k = browser.new_context(base_url=ADRESA, extra_http_headers={"X-Forwarded-For": ip or nahodna_ip()}, **volby)
        kontexty.append(k)
        return k

    yield vytvor
    for k in kontexty:
        k.close()


def vyzkouset(page: Page, role: str) -> Page:
    """Přihlášení jedním klikem z přihlašovací stránky."""
    page.goto("/prihlaseni")
    page.get_by_role("button", name=f"Vyzkoušet jako {ROLE[role]}").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Dobrý den")
    return page


def odeslat(page: Page, adresa: str, data: dict | None = None, multipart: dict | None = None):
    csrf = page.locator("input[name=csrf]").first.get_attribute("value") or ""
    if multipart is not None:
        multipart = {"csrf": csrf, **multipart}
    return page.request.post(
        adresa,
        form={"csrf": csrf, **(data or {})} if multipart is None else None,
        multipart=multipart,
        headers={"Origin": ADRESA},
        max_redirects=0,
    )


def id_hlaseni(page: Page) -> int:
    page.goto("/hlaseni")
    page.get_by_role("link", name=HLASENI).click()
    expect(page.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    return int(page.url.rsplit("/", 1)[1])


def test_prihlasovaci_stranka_nabizi_tri_role(kontext):
    page = kontext().new_page()
    page.goto("/prihlaseni")
    ukazka = page.get_by_role("region", name="Vyzkoušejte ukázku")
    expect(ukazka).to_contain_text(HESLO)
    for nazev in ROLE.values():
        expect(ukazka.get_by_role("button", name=f"Vyzkoušet jako {nazev}")).to_be_visible()
    expect(page.get_by_text("Ukázka: firma JK pojišťovna i všechna data jsou vymyšlená")).to_be_visible()


@pytest.mark.parametrize("role", ["admin", "likvidace", "klient"])
def test_jednim_klikem_v_kazde_roli(kontext, role):
    page = vyzkouset(kontext().new_page(), role)
    expect(page.locator(".ucet")).to_contain_text(ROLE[role])


def test_administrator_jen_prohlizi(kontext):
    page = vyzkouset(kontext().new_page(), "admin")
    page.goto("/dokumenty")
    expect(page.get_by_text("Nahrávání, mazání a nové čtení jsou vypnuté.")).to_be_visible()
    expect(page.get_by_role("heading", name="Nahrát dokument")).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("^Smazat"))).to_have_count(0)
    pocet = page.locator("tbody tr").count()
    assert pocet >= 15  # 10 PDF a 5 skenů

    # Přímé odeslání formulářů server odmítne.
    nahrani = odeslat(page, "/dokumenty", multipart={
        "nazev": "Podvržený dokument", "druh": "PODMINKY", "pojisteni": "AUTO",
        "soubor": {"name": "a.pdf", "mimeType": "application/pdf", "buffer": PDF},
    })
    assert nahrani.status == 403
    assert "V ukázce se dokumenty nenahrávají" in nahrani.text()

    prvni = page.locator("tbody tr a").first.get_attribute("href") or ""
    dokument_id = prvni.rsplit("/", 1)[1]
    smazani = odeslat(page, f"/dokumenty/{dokument_id}/smazat")
    assert smazani.status == 303 and smazani.headers["location"].endswith("zprava=ukazka")
    cteni = odeslat(page, f"/dokumenty/{dokument_id}/precist")
    assert cteni.status == 303 and cteni.headers["location"].endswith("zprava=ukazka")

    cislo = id_hlaseni(page)
    expect(page.get_by_role("button", name="Vytěžit znovu")).to_have_count(0)
    vytezeni = odeslat(page, f"/hlaseni/{cislo}/vytezit")
    assert vytezeni.status == 303 and vytezeni.headers["location"].endswith("zprava=ukazka")

    page.goto("/dokumenty")
    expect(page.locator("tbody tr")).to_have_count(pocet)
    page.goto(f"/dokumenty/{dokument_id}?zprava=ukazka")
    expect(page.get_by_role("status")).to_contain_text("V ukázce se dokumenty nenahrávají")
    expect(page.get_by_role("button", name="Přečíst znovu")).to_have_count(0)


def test_limit_asistenta_na_navstevnika(kontext):
    """Limit 2 (AI_LIMIT_NAVSTEVNIK v testech): návštěvník A ho vyčerpá,
    návštěvník B se stejným účtem se ptá dál."""

    def zeptat(page: Page, otazka: str):
        page.get_by_label("Otázka", exact=True).fill(otazka)
        page.get_by_role("button", name="Zeptat se").click()

    a = vyzkouset(kontext(ip="10.200.0.1").new_page(), "klient")
    a.goto("/asistent")
    expect(a.locator("#zbyva")).to_have_text("Zbývá vám dnes 2 z 2 otázek.")
    for otazka in ("Co kryje havarijní pojištění?", "Jaká je spoluúčast?"):
        zeptat(a, otazka)
        expect(a.locator("#zbyva")).to_be_visible()
    expect(a.locator("#zbyva")).to_have_text("Zbývá vám dnes 0 z 2 otázek.")
    expect(a.get_by_role("button", name="Zeptat se")).to_be_disabled()

    b = vyzkouset(kontext(ip="10.200.0.2").new_page(), "klient")
    b.goto("/asistent")
    expect(b.locator("#zbyva")).to_have_text("Zbývá vám dnes 2 z 2 otázek.")


@pytest.mark.telefon
def test_prihlaseni_ukazky_na_telefonu(kontext, playwright: Playwright):
    zarizeni = dict(playwright.devices["Pixel 7"])
    zarizeni.pop("default_browser_type", None)
    page = kontext(**zarizeni).new_page()
    page.goto("/prihlaseni")
    expect(page.get_by_role("button", name="Vyzkoušet jako Pracovník likvidace")).to_be_visible()
    bez_vodorovneho_posuvu(page)


def test_zz_obnova_vrati_opravy_a_odhlasi(kontext):
    """Likvidace opraví údaj; obnova ho vrátí na návrh AI a odhlásí."""
    page = vyzkouset(kontext().new_page(), "likvidace")
    cislo = id_hlaseni(page)
    expect(page.locator("#stav-kontroly")).to_have_text("Čeká na kontrolu")
    page.get_by_label("Číslo smlouvy", exact=True).fill("9999")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.locator("#stav-kontroly")).to_have_text("Rozpracováno")

    # Obnova (v ukázce jednou za noc; tady na požádání).
    jiny = kontext().new_page()
    odpoved = jiny.request.get("/prihlaseni", headers={"X-Obnova-Ukazky": "1"})
    assert odpoved.ok

    page.goto(f"/hlaseni/{cislo}")
    expect(page).to_have_url(re.compile(r"/prihlaseni$"))
    vyzkouset(page, "likvidace")
    page.goto(f"/hlaseni/{cislo}")
    expect(page.locator("#stav-kontroly")).to_have_text("Čeká na kontrolu")
    expect(page.get_by_label("Číslo smlouvy", exact=True)).to_have_value("1001")
