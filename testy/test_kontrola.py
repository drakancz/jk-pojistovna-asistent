"""Krok 4C: kontrola vytěžených údajů člověkem.

Každý test si nahraje vlastní kopii skenu hlášení 1005 (krádež kola),
aby nesahal na ukázková hlášení, která používá `test_vytezeni.py`.
Napodobenina na vytěžení vrací údaje hlášení 1001 — AI se tedy „splete“
v čísle smlouvy (1001 místo 1005), částce (18 500 místo 24 500 Kč) atd.
a pracovník likvidace to opraví. Kopie má stejný otisk jako ukázkové
hlášení 1005, takže administrátor vidí přesnost proti jeho správným údajům.

Oprávnění (Jakub, 4. 11. 2026): opravuje, potvrzuje a vrací ke kontrole
jen likvidace; administrátor jen čte; klient 404; „Vytěžit znovu“ jen
dokud údaje nikdo neopravil.
"""

import re

import pytest
from playwright.sync_api import Page, expect

from conftest import DOKUMENTY, UCTY, bez_vodorovneho_posuvu, csrf, napodobenina, odesli_formular, pripona
from test_dokumenty import nahraj

CEKANI = 30_000
SKEN = DOKUMENTY / "14-hlaseni-1005-domacnost.png"


def nove_hlaseni(prihlas) -> int:
    """Administrátor nahraje kopii skenu; vrátí číslo hlášení po vytěžení."""
    admin = prihlas("admin")
    nazev = f"Kopie hlášení kola {pripona()}"
    nahraj(admin, nazev, "Hlášení škody", "Pojištění domácnosti",
           {"name": "kolo.png", "mimeType": "image/png", "buffer": SKEN.read_bytes()},
           klient=UCTY["tomas"]["jmeno"])
    admin.goto("/hlaseni")
    admin.get_by_role("link", name=nazev).click()
    expect(admin.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=CEKANI)
    cislo = int(admin.url.rsplit("/", 1)[1])
    admin.context.close()
    return cislo


def pole(page: Page, popis: str):
    return page.get_by_label(popis, exact=True)


def udaj(page: Page, klic: str):
    return page.locator(f'[data-udaj="{klic}"]')


def test_likvidace_opravi_potvrdi_a_vrati(prihlas):
    cislo = nove_hlaseni(prihlas)
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{cislo}")
    expect(page.locator("#stav-kontroly")).to_have_text("Čeká na kontrolu")
    # Formulář je předvyplněný návrhem AI.
    expect(pole(page, "Číslo smlouvy")).to_have_value("1001")
    expect(pole(page, "Odhad výše škody")).to_have_value("18500")
    expect(pole(page, "Datum události")).to_have_value("2026-10-09")
    expect(pole(page, "Šetřila policie")).to_have_value("ano")

    pole(page, "Číslo smlouvy").fill("1005")
    pole(page, "Odhad výše škody").fill("24 500")
    pole(page, "Čas").fill("")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.get_by_role("status")).to_have_text("Opravy jsou uložené. Údaje zatím nejsou potvrzené.")
    expect(page.locator("#stav-kontroly")).to_have_text("Rozpracováno")
    expect(pole(page, "Číslo smlouvy")).to_have_value("1005")
    expect(pole(page, "Odhad výše škody")).to_have_value("24500")
    expect(udaj(page, "cislo_smlouvy")).to_contain_text("AI navrhla: 1001")
    expect(udaj(page, "odhad_skody")).to_contain_text("AI navrhla: 18 500 Kč")

    historie = page.locator(".historie > li")
    expect(historie).to_have_count(1)
    expect(historie.first).to_contain_text("Oprava údajů")
    expect(historie.first).to_contain_text(UCTY["likvidace"]["jmeno"])
    expect(historie.first).to_contain_text("Číslo smlouvy: 1001 → 1005")
    expect(historie.first).to_contain_text("Odhad výše škody: 18 500 Kč → 24 500 Kč")
    expect(historie.first).to_contain_text("Čas: 17:40 → —")

    # Potvrzení: údaje se uzamknou, formulář zmizí.
    page.get_by_role("button", name="Potvrdit údaje").click()
    expect(page.get_by_role("status")).to_have_text("Údaje jsou potvrzené.")
    expect(page.locator("#stav-kontroly")).to_contain_text("Potvrzeno")
    expect(page.locator("#stav-kontroly").locator("..")).to_contain_text(UCTY["likvidace"]["jmeno"])
    expect(page.get_by_role("heading", name="Potvrzené údaje")).to_be_visible()
    expect(page.locator("form.formular-kontroly")).to_have_count(0)
    expect(udaj(page, "cislo_smlouvy")).to_contain_text("1005")
    expect(historie).to_have_count(2)
    expect(historie.first).to_contain_text("Potvrzení údajů")

    # Uložit potvrzené přímo nejde.
    odpoved = odesli_formular(page, f"/hlaseni/{cislo}/kontrola",
                              data={"csrf": csrf(page), "verze": "99", "cislo_smlouvy": "9999"})
    assert odpoved.status == 303 and "zprava=nelze_upravit" in odpoved.headers["location"]

    # Vrácení ke kontrole přes potvrzovací okno; Zrušit nic nezmění.
    page.get_by_role("button", name="Vrátit ke kontrole").click()
    okno = page.get_by_role("dialog")
    expect(okno).to_contain_text("Vrátit ke kontrole?")
    okno.get_by_role("button", name="Zrušit").click()
    expect(okno).to_be_hidden()
    expect(page.locator("#stav-kontroly")).to_contain_text("Potvrzeno")
    page.get_by_role("button", name="Vrátit ke kontrole").click()
    page.get_by_role("dialog").get_by_role("button", name="Vrátit ke kontrole").click()
    expect(page.get_by_role("status")).to_have_text("Údaje jsou vrácené ke kontrole.")
    expect(page.locator("#stav-kontroly")).to_have_text("Rozpracováno")
    expect(pole(page, "Číslo smlouvy")).to_have_value("1005")  # opravy zůstaly
    expect(historie).to_have_count(3)
    expect(historie.first).to_contain_text("Vrácení ke kontrole")

    # Seznam ukazuje stav kontroly a opravené údaje.
    page.goto("/hlaseni")
    radek = page.locator("table.hlaseni tbody tr").filter(has=page.locator(f'a[href="/hlaseni/{cislo}"]'))
    expect(radek.locator('td[data-popis="Kontrola"]')).to_have_text("Rozpracováno")
    expect(radek.locator('td[data-popis="Smlouva"]')).to_have_text("1005")
    expect(radek.locator('td[data-popis="Odhad škody"]')).to_have_text("24 500 Kč")


def test_bez_zmeny_se_nic_neulozi(prihlas):
    cislo = nove_hlaseni(prihlas)
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{cislo}")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.get_by_role("status")).to_have_text("Nic se nezměnilo, není co uložit.")
    expect(page.locator("#stav-kontroly")).to_have_text("Čeká na kontrolu")
    expect(page.locator(".historie > li")).to_have_count(0)
    # Potvrdit beze změny jde: AI měla pravdu.
    page.get_by_role("button", name="Potvrdit údaje").click()
    expect(page.locator("#stav-kontroly")).to_contain_text("Potvrzeno")
    historie = page.locator(".historie > li")
    expect(historie).to_have_count(1)
    expect(historie.first).to_contain_text("Potvrzení údajů")


def test_chybny_vstup_se_neulozi(prihlas):
    cislo = nove_hlaseni(prihlas)
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{cislo}")
    pole(page, "Číslo smlouvy").fill("1005")
    pole(page, "Odhad výše škody").fill("osmnáct tisíc")
    pole(page, "Čas").fill("25:00")
    page.get_by_label("Rok pořízení, řádek 1", exact=True).fill("2021")
    page.get_by_role("button", name="Potvrdit údaje").click()

    expect(page.get_by_role("alert")).to_contain_text("opravte zvýrazněná políčka")
    expect(pole(page, "Odhad výše škody")).to_have_attribute("aria-invalid", "true")
    expect(udaj(page, "odhad_skody")).to_contain_text("Zadejte celé číslo")
    expect(udaj(page, "cas_udalosti")).to_contain_text("Zadejte čas jako 14:30.")
    expect(udaj(page, "polozky")).to_contain_text("Řádek 1: vyplňte, o jakou věc jde.")
    # Co člověk napsal, zůstane ve formuláři; nic se neuložilo.
    expect(pole(page, "Číslo smlouvy")).to_have_value("1005")
    expect(pole(page, "Odhad výše škody")).to_have_value("osmnáct tisíc")
    page.goto(f"/hlaseni/{cislo}")
    expect(page.locator("#stav-kontroly")).to_have_text("Čeká na kontrolu")
    expect(pole(page, "Číslo smlouvy")).to_have_value("1001")

    # Příliš dlouhý text a hodnota mimo nabídku (podvržený formulář).
    odpoved = odesli_formular(page, f"/hlaseni/{cislo}/kontrola", data={
        "csrf": csrf(page), "verze": page.locator("input[name=verze]").get_attribute("value"),
        "misto": "x" * 501, "mena": "BTC", "akce": "ulozit"})
    assert odpoved.status == 400
    assert "Nejvýš 500 znaků." in odpoved.text() and "Vyberte jednu z nabízených možností." in odpoved.text()


def test_seznam_veci_jde_doplnit_a_smazat(prihlas):
    cislo = nove_hlaseni(prihlas)
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{cislo}")
    page.get_by_label("Věc, řádek 1", exact=True).fill("horské jízdní kolo")
    page.get_by_label("Rok pořízení, řádek 1", exact=True).fill("2024")
    page.get_by_label("Cena, řádek 1", exact=True).fill("24 500")
    page.get_by_label("Věc, řádek 3", exact=True).fill("visací zámek")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.get_by_role("status")).to_contain_text("Opravy jsou uložené")
    # Prázdný druhý řádek se vynechal; přibyly další volné řádky.
    expect(page.get_by_label("Věc, řádek 2", exact=True)).to_have_value("visací zámek")
    expect(page.get_by_label("Cena, řádek 1", exact=True)).to_have_value("24500")
    expect(page.get_by_label("Věc, řádek 5", exact=True)).to_have_value("")
    expect(page.locator(".historie > li").first).to_contain_text(
        "horské jízdní kolo (2024, 24 500 Kč); visací zámek (?, ?)")

    # Smazání řádku = vymazat ho celý.
    page.get_by_label("Věc, řádek 2", exact=True).fill("")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.get_by_label("Věc, řádek 2", exact=True)).to_have_value("")
    expect(page.get_by_label("Věc, řádek 1", exact=True)).to_have_value("horské jízdní kolo")


def test_soubeh_neprepise_cizi_opravu(prihlas):
    cislo = nove_hlaseni(prihlas)
    prvni = prihlas("likvidace")
    druha = prihlas("likvidace")
    prvni.goto(f"/hlaseni/{cislo}")
    druha.goto(f"/hlaseni/{cislo}")
    pole(prvni, "Číslo smlouvy").fill("1005")
    prvni.get_by_role("button", name="Uložit rozpracované").click()
    expect(prvni.get_by_role("status")).to_contain_text("Opravy jsou uložené")

    pole(druha, "Číslo smlouvy").fill("7777")
    druha.get_by_role("button", name="Potvrdit údaje").click()
    expect(druha.get_by_role("status")).to_contain_text("Údaje mezitím změnil někdo jiný")
    expect(pole(druha, "Číslo smlouvy")).to_have_value("1005")
    expect(druha.locator("#stav-kontroly")).to_have_text("Rozpracováno")


def test_administrator_jen_cte_a_vidi_presnost(prihlas):
    cislo = nove_hlaseni(prihlas)
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{cislo}")
    pole(page, "Číslo smlouvy").fill("1005")
    pole(page, "Odhad výše škody").fill("24500")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.locator("#stav-kontroly")).to_have_text("Rozpracováno")
    # Likvidace přesnost proti vzoru nevidí.
    expect(page.locator("#presnost")).to_have_count(0)

    admin = prihlas("admin")
    admin.goto(f"/hlaseni/{cislo}")
    expect(admin.locator("form.formular-kontroly")).to_have_count(0)
    expect(admin.get_by_role("button", name="Potvrdit údaje")).to_have_count(0)
    expect(admin.get_by_role("button", name="Vytěžit znovu")).to_have_count(0)
    expect(udaj(admin, "cislo_smlouvy")).to_contain_text("AI ✗ · po kontrole ✓")
    expect(udaj(admin, "pojistnik")).to_contain_text("AI ✗ · po kontrole ✗ správně: Tomáš Beneš")
    ai, po = (int(x) for x in re.findall(
        r"AI správně (\d+) z 22 údajů, po kontrole člověkem (\d+) z 22", admin.locator("#presnost").inner_text())[0])
    assert po == ai + 2

    admin.goto("/hlaseni")
    radek = admin.locator("table.hlaseni tbody tr").filter(has=admin.locator(f'a[href="/hlaseni/{cislo}"]'))
    expect(radek.locator('td[data-popis="Po kontrole"]')).to_have_text(f"{po} z 22")
    expect(admin.locator("#presnost-kontroly")).to_contain_text("po kontrole člověkem")

    # Administrátor neopravuje ani nevrací (404); znovu vytěžit opravené nejde.
    token = csrf(admin)
    for adresa in (f"/hlaseni/{cislo}/kontrola", f"/hlaseni/{cislo}/vratit"):
        assert odesli_formular(admin, adresa, data={"csrf": token, "verze": "1"}).status == 404, adresa
    pred = napodobenina("/_posledni")["pocet_vytezeni"]
    odpoved = odesli_formular(admin, f"/hlaseni/{cislo}/vytezit", data={"csrf": token})
    assert odpoved.status == 303 and "zprava=opraveno" in odpoved.headers["location"]
    assert napodobenina("/_posledni")["pocet_vytezeni"] == pred


def test_bez_csrf_se_nic_neulozi(prihlas):
    cislo = nove_hlaseni(prihlas)
    page = prihlas("likvidace")
    page.goto(f"/hlaseni/{cislo}")
    verze = page.locator("input[name=verze]").get_attribute("value")
    odpoved = odesli_formular(page, f"/hlaseni/{cislo}/kontrola",
                              data={"csrf": "spatny", "verze": verze, "cislo_smlouvy": "9999", "akce": "potvrdit"})
    assert odpoved.status == 303
    page.goto(f"/hlaseni/{cislo}")
    expect(page.locator("#stav-kontroly")).to_have_text("Čeká na kontrolu")
    expect(pole(page, "Číslo smlouvy")).to_have_value("1001")


def test_klient_a_neprihlaseny_nemaji_pristup(prihlas, novy_kontext):
    cislo = nove_hlaseni(prihlas)
    klient = prihlas("tomas")  # ani u vlastního hlášení
    token = csrf(klient)
    for adresa in (f"/hlaseni/{cislo}/kontrola", f"/hlaseni/{cislo}/vratit"):
        assert odesli_formular(klient, adresa, data={"csrf": token, "verze": "1"}).status == 404, adresa

    page = novy_kontext().new_page()
    for adresa in (f"/hlaseni/{cislo}/kontrola", f"/hlaseni/{cislo}/vratit"):
        odpoved = odesli_formular(page, adresa, data={"csrf": "x"})
        assert odpoved.status == 303 and odpoved.headers["location"].endswith("/prihlaseni"), adresa


@pytest.mark.telefon
def test_kontrola_na_telefonu(prihlas, playwright):
    cislo = nove_hlaseni(prihlas)
    zarizeni = dict(playwright.devices["Pixel 7"])
    zarizeni.pop("default_browser_type", None)
    page = prihlas("likvidace", **zarizeni)
    page.goto(f"/hlaseni/{cislo}")
    expect(pole(page, "Číslo smlouvy")).to_be_visible()
    bez_vodorovneho_posuvu(page)
    pole(page, "Odhad výše škody").fill("x")
    page.get_by_role("button", name="Uložit rozpracované").click()
    expect(page.get_by_role("alert")).to_be_visible()
    bez_vodorovneho_posuvu(page)
