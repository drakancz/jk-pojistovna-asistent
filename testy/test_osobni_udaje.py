"""Osobní údaje mimo AI (krok 5B): e-maily a telefony v otázce ani v úryvcích
k Anthropicu neodejdou. Kontrolujeme, co skutečně přišlo napodobenině
(`/_posledni`, jen ano/ne), ne co je vidět na stránce."""

from playwright.sync_api import Page, expect

from conftest import napodobenina


def zeptej_se(page: Page, otazka: str) -> dict:
    page.goto("/asistent")
    page.get_by_label("Otázka", exact=True).fill(otazka)
    page.get_by_role("button", name="Zeptat se").click()
    expect(page.locator("#odpoved")).to_be_visible()
    return napodobenina("/_posledni")["posledni"]


def test_kontakt_v_otazce_se_nahradi(prihlas):
    page = prihlas("likvidace")
    poslane = zeptej_se(
        page,
        "Klient volal z +420 777 123 456 (záložní 602-111-222) a psal z jan.novak@firma.cz:"
        " jaká je spoluúčast při odcizení vozidla?",
    )
    assert poslane["osobni_udaje"] is False
    assert poslane["nahrazeno"] is True
    # Převod otázky do slov dokumentů je samostatné volání AI — i tam bez kontaktu.
    prevod = napodobenina("/_posledni")["prevod"]
    assert prevod["osobni_udaje"] is False
    assert prevod["nahrazeno"] is True
    # Odpověď z dokumentů funguje dál, jen bez kontaktu.
    expect(page.locator("#odpoved")).to_contain_text("odpověď napodobeniny")


def test_kontakt_z_hlaseni_neodejde(prihlas):
    # Přepis hlášení škody (OCR napodobeniny) obsahuje telefon a e-mail.
    # Likvidace hlášení vidí, takže jeho úryvek k asistentovi jde — ale bez kontaktu.
    page = prihlas("likvidace")
    poslane = zeptej_se(page, "Přepis napodobeniny OCR: kontakt z hlášení škody")
    assert any("hlášení" in u.lower() or "hlaseni" in u.lower() for u in poslane["uryvky"]), poslane["uryvky"]
    assert poslane["osobni_udaje"] is False
    assert poslane["nahrazeno"] is True
