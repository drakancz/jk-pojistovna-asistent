"""Snímek skutečné odpovědi asistenta pro README a případovou studii (krok 6B).

Na rozdíl od snimky_ukazky.py potřebuje ukázku se SKUTEČNÝM klíčem
k Anthropicu (živá ukázka nebo místní web-ukazka s klíčem z .env), jinak by
na snímku byla odpověď napodobeniny. Stojí dvě otázky na Haiku (zlomek centu).

    ZAKLADNI_ADRESA_UKAZKY=http://web-ukazka:8300 \
    docker compose --profile test run --rm -v ./docs/snimky:/out e2e python testy/snimek_odpovedi.py
"""

import os
import random

from playwright.sync_api import Page, expect, sync_playwright

ADRESA = os.environ.get("ZAKLADNI_ADRESA_UKAZKY", "http://web-ukazka:8300")
OUT = "/out"
OTAZKA = "Mám u svého auta krytý střet se zvěří?"


def zeptej_se(page: Page, nazev: str) -> None:
    page.goto("/asistent")
    page.get_by_label("Otázka", exact=True).fill(OTAZKA)
    page.get_by_role("button", name="Zeptat se").click()
    # Skutečný model odpovídá pár sekund; bez citace by snímek nedával smysl.
    expect(page.get_by_role("link", name="zdroj 1")).to_be_visible(timeout=60_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    # Jen horní část: otázka, odpověď a začátek zdrojů (celé zdroje jsou dlouhé).
    page.screenshot(path=f"{OUT}/{nazev}.png")
    print("ok", nazev)


with sync_playwright() as p:
    prohlizec = p.chromium.launch()
    for nazev, volby in (
        ("asistent", {"viewport": {"width": 1440, "height": 1150}}),
        ("asistent-telefon", p.devices["Pixel 7"]),
    ):
        k = prohlizec.new_context(
            **volby,
            base_url=ADRESA,
            color_scheme="dark",
            locale="cs-CZ",
            timezone_id="Europe/Prague",
            extra_http_headers={"X-Forwarded-For": "10." + ".".join(str(random.randint(1, 250)) for _ in range(3))},
        )
        page = k.new_page()
        page.goto("/prihlaseni")
        page.get_by_role("button", name="Vyzkoušet jako Klient").click()
        expect(page.get_by_role("heading", level=1)).to_contain_text("Dobrý den")
        zeptej_se(page, nazev)
    prohlizec.close()
