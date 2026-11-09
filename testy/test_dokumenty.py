"""Nahrávání a mazání dokumentů administrátorem."""

from playwright.sync_api import Page, expect

from conftest import PDF, PNG, PODVRH, UCTY, pripona


def nahraj(page: Page, nazev: str, druh: str, pojisteni: str, soubor: dict, klient: str | None = None):
    page.goto("/dokumenty")
    page.get_by_label("Název", exact=True).fill(nazev)
    page.get_by_label("Druh dokumentu", exact=True).select_option(label=druh)
    page.get_by_label("Pojištění", exact=True).select_option(label=pojisteni)
    if klient:
        page.get_by_label("Klient", exact=True).select_option(label=klient)
    page.get_by_label("Soubor", exact=True).set_input_files(soubor)
    page.get_by_role("button", name="Nahrát").click()


def radek(page: Page, nazev: str):
    return page.get_by_role("row").filter(has_text=nazev)


def test_nahrani_podminek(prihlas):
    page = prihlas("admin")
    nazev = f"Podmínky havarijního pojištění {pripona()}"
    nahraj(page, nazev, "Pojistné podmínky", "Havarijní pojištění auta",
           {"name": "podminky.pdf", "mimeType": "application/pdf", "buffer": PDF})
    expect(page.get_by_role("status")).to_have_text("Dokument je nahraný.")
    expect(radek(page, nazev)).to_contain_text("Pojistné podmínky")
    expect(radek(page, nazev)).to_contain_text("podminky.pdf")


def test_smlouva_patri_klientovi(prihlas):
    page = prihlas("admin")
    nazev = f"Smlouva domácnost {pripona()}"
    # Bez klienta neprojde…
    nahraj(page, nazev, "Smlouva", "Pojištění domácnosti",
           {"name": "smlouva.pdf", "mimeType": "application/pdf", "buffer": PDF})
    expect(page.get_by_role("alert")).to_contain_text("vyberte klienta")
    expect(radek(page, nazev)).to_have_count(0)
    # …s klientem ano.
    nahraj(page, nazev, "Smlouva", "Pojištění domácnosti",
           {"name": "smlouva.pdf", "mimeType": "application/pdf", "buffer": PDF},
           klient=UCTY["klient"]["jmeno"])
    expect(radek(page, nazev)).to_contain_text(UCTY["klient"]["jmeno"])


def test_podvrzeny_soubor_odmitnut(prihlas):
    page = prihlas("admin")
    nazev = f"Podvrh {pripona()}"
    nahraj(page, nazev, "Pojistné podmínky", "Cestovní pojištění",
           {"name": "podvrh.pdf", "mimeType": "application/pdf", "buffer": PODVRH})
    expect(page.get_by_role("alert")).to_contain_text("není PDF ani obrázek")
    expect(radek(page, nazev)).to_have_count(0)
    # Vyplněné údaje zůstaly, ať se nemusí psát znovu.
    expect(page.get_by_label("Název", exact=True)).to_have_value(nazev)


def test_obrazek_jen_jako_hlaseni(prihlas):
    page = prihlas("admin")
    nazev = f"Sken {pripona()}"
    nahraj(page, nazev, "Pojistné podmínky", "Cestovní pojištění",
           {"name": "sken.png", "mimeType": "image/png", "buffer": PNG})
    expect(page.get_by_role("alert")).to_contain_text("musí být PDF")
    nahraj(page, nazev, "Hlášení škody", "Cestovní pojištění",
           {"name": "sken.png", "mimeType": "image/png", "buffer": PNG},
           klient=UCTY["klient2"]["jmeno"])
    expect(radek(page, nazev)).to_contain_text("Hlášení škody")


def test_smazani_s_potvrzenim(prihlas):
    page = prihlas("admin")
    nazev = f"Ke smazání {pripona()}"
    nahraj(page, nazev, "Pojistné podmínky", "Havarijní pojištění auta",
           {"name": "smazat.pdf", "mimeType": "application/pdf", "buffer": PDF})

    # Zrušit nic nesmaže.
    radek(page, nazev).get_by_role("button", name=f"Smazat {nazev}").click()
    okno = page.get_by_role("dialog")
    expect(okno).to_contain_text(nazev)
    expect(okno).to_contain_text("nejde vzít zpět")
    okno.get_by_role("button", name="Zrušit").click()
    expect(okno).to_be_hidden()
    expect(radek(page, nazev)).to_have_count(1)

    # Smazat smaže.
    radek(page, nazev).get_by_role("button", name=f"Smazat {nazev}").click()
    page.get_by_role("dialog").get_by_role("button", name="Smazat", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("Dokument je smazaný.")
    expect(radek(page, nazev)).to_have_count(0)
