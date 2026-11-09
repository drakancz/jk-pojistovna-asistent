"""Čtení dokumentů (krok 2A): text z PDF, přepis skenu Claudem (v testech
napodobenina, nic neodchází ven), úryvky s číslem stránky, opakované čtení."""

from playwright.sync_api import Page, expect

from conftest import DOKUMENTY, PDF, PNG, SKEN_PDF, UCTY, napodobenina, pripona
from test_dokumenty import nahraj

CEKANI = 30_000  # čtení běží na pozadí, stránka se sama obnovuje


def otevri_detail(page: Page, nazev: str) -> None:
    page.get_by_role("link", name=nazev).click()
    expect(page.get_by_role("heading", level=1)).to_have_text(nazev)


def stav(page: Page):
    return page.locator("#stav-cteni")


def uryvek(page: Page, *texty: str):
    radky = page.locator("table.uryvky tbody tr")
    for text in texty:
        radky = radky.filter(has_text=text)
    return radky


def test_pdf_se_precte_po_strankach(prihlas):
    page = prihlas("admin")
    pred = napodobenina("/_posledni")["pocet"]
    nazev = f"Podmínky auto {pripona()}"
    obsah = (DOKUMENTY / "01-pojistne-podminky-auto.pdf").read_bytes()
    nahraj(page, nazev, "Pojistné podmínky", "Havarijní pojištění auta",
           {"name": "podminky-auto.pdf", "mimeType": "application/pdf", "buffer": obsah})
    otevri_detail(page, nazev)

    expect(stav(page)).to_have_text("Přečteno", timeout=CEKANI)
    expect(page.locator(".udaje")).to_contain_text("3 strany")

    # Spoluúčast je na straně 2 a úryvek nese nadpis článku.
    spoluucast = uryvek(page, "Článek 5 – Spoluúčast", "5 % ze škody, nejméně 5 000 Kč").first
    expect(spoluucast).to_be_visible()
    expect(spoluucast.locator("td").nth(1)).to_have_text("2")
    # Bonus je na straně 3.
    expect(uryvek(page, "Článek 9 – Bonus za jízdu bez škod").first.locator("td").nth(1)).to_have_text("3")
    # Záhlaví a zápatí v úryvcích nejsou.
    expect(page.locator("table.uryvky")).not_to_contain_text("Vymyšlený dokument pro ukázku")
    expect(page.locator("table.uryvky")).not_to_contain_text("Strana 2 z 3")

    # Text stránky jde rozbalit.
    page.get_by_text("Strana 3", exact=True).click()
    expect(page.locator("details.strana").nth(2)).to_contain_text("Článek 10")

    # Běžné PDF se čte zdarma — ke Claudovi nic neodešlo.
    assert napodobenina("/_posledni")["pocet"] == pred


def test_obrazek_prepise_claude(prihlas):
    page = prihlas("admin")
    nazev = f"Hlášení škody sken {pripona()}"
    nahraj(page, nazev, "Hlášení škody", "Cestovní pojištění",
           {"name": "hlaseni.png", "mimeType": "image/png", "buffer": PNG},
           klient=UCTY["klient2"]["jmeno"])
    otevri_detail(page, nazev)

    expect(stav(page)).to_have_text("Přečteno", timeout=CEKANI)
    expect(page.locator(".udaje")).to_contain_text("1 strana")
    expect(page.get_by_text("Strana 1 · přepis skenu (OCR)")).to_be_visible()
    expect(uryvek(page, "Datum škody: 12. 10. 2026")).to_have_count(1)

    posledni = napodobenina("/_posledni")["posledni"]
    assert posledni["model"] == "claude-haiku-5-5"
    assert posledni["klic"] is True
    assert posledni["bloky"][0] == {"type": "image", "media_type": "image/png"}


def test_pdf_bez_textu_jde_na_ocr(prihlas):
    page = prihlas("admin")
    nazev = f"Naskenované PDF {pripona()}"
    nahraj(page, nazev, "Hlášení škody", "Havarijní pojištění auta",
           {"name": "sken.pdf", "mimeType": "application/pdf", "buffer": SKEN_PDF},
           klient=UCTY["klient"]["jmeno"])
    otevri_detail(page, nazev)

    expect(stav(page)).to_have_text("Přečteno", timeout=CEKANI)
    expect(page.get_by_text("Strana 1 · přepis skenu (OCR)")).to_be_visible()
    # Claudovi odešla jen ta jedna stránka jako PDF.
    blok = napodobenina("/_posledni")["posledni"]["bloky"][0]
    assert blok == {"type": "document", "media_type": "application/pdf"}


def test_poskozene_pdf_ukaze_chybu(prihlas):
    page = prihlas("admin")
    nazev = f"Poškozené PDF {pripona()}"
    nahraj(page, nazev, "Pojistné podmínky", "Cestovní pojištění",
           {"name": "rozbite.pdf", "mimeType": "application/pdf", "buffer": PDF})
    otevri_detail(page, nazev)
    expect(stav(page)).to_have_text("Chyba čtení", timeout=CEKANI)
    expect(page.locator(".udaje")).to_contain_text("PDF")
    expect(page.locator("table.uryvky")).to_have_count(0)


def test_chyba_ocr_a_precist_znovu(prihlas):
    page = prihlas("admin")
    nazev = f"Sken s chybou {pripona()}"
    napodobenina("/_rezim", {"chyba": True})
    try:
        nahraj(page, nazev, "Hlášení škody", "Pojištění domácnosti",
               {"name": "chyba.png", "mimeType": "image/png", "buffer": PNG},
               klient=UCTY["klient"]["jmeno"])
        otevri_detail(page, nazev)
        expect(stav(page)).to_have_text("Chyba čtení", timeout=CEKANI)
        expect(page.locator(".udaje")).to_contain_text("Anthropic stránku odmítl zpracovat.")
    finally:
        napodobenina("/_rezim", {"chyba": False})

    page.get_by_role("button", name="Přečíst znovu").click()
    expect(page.get_by_role("status")).to_have_text("Dokument se znovu čte.")
    expect(stav(page)).to_have_text("Přečteno", timeout=CEKANI)
    expect(uryvek(page, "Přepis napodobeniny OCR")).to_have_count(1)
