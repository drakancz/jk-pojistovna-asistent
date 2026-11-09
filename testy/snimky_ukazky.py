"""Snímky pro README veřejné ukázky (krok 6C): ukázkový režim, vymyšlená data.

    docker compose --profile test run --rm -v ./docs/snimky:/out e2e python testy/snimky_ukazky.py

Odpověď asistenta se tu nefotí — v testech odpovídá napodobenina; snímek
odpovědi se pořídí ze živé ukázky s klíčem.
"""

import os
import random

from playwright.sync_api import Page, expect, sync_playwright

ADRESA = os.environ.get("ZAKLADNI_ADRESA_UKAZKY", "http://web-ukazka:8300")
OUT = "/out"
ROLE = {"admin": "Administrátor", "likvidace": "Pracovník likvidace", "klient": "Klient"}
HLASENI = "Hlášení škody ke smlouvě 1001 – odřené dveře na parkovišti"


def ip() -> str:
    return "10." + ".".join(str(random.randint(1, 250)) for _ in range(3))


def snimek(page: Page, nazev: str, cela: bool = False) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{OUT}/{nazev}.png", full_page=cela)
    print("ok", nazev)


with sync_playwright() as p:
    prohlizec = p.chromium.launch()

    def stranka(role: str | None, telefon: bool = False) -> Page:
        volby = p.devices["Pixel 7"] if telefon else {"viewport": {"width": 1440, "height": 900}}
        k = prohlizec.new_context(
            **volby,
            base_url=ADRESA,
            color_scheme="dark",
            locale="cs-CZ",
            timezone_id="Europe/Prague",
            extra_http_headers={"X-Forwarded-For": ip()},
        )
        page = k.new_page()
        page.goto("/prihlaseni")
        if role:
            page.get_by_role("button", name=f"Vyzkoušet jako {ROLE[role]}").click()
            expect(page.get_by_role("heading", level=1)).to_contain_text("Dobrý den")
        return page

    snimek(stranka(None), "prihlaseni")

    admin = stranka("admin")
    admin.goto("/dokumenty")
    snimek(admin, "dokumenty")

    likvidace = stranka("likvidace")
    likvidace.goto("/hledani")
    likvidace.get_by_label("Otázka").fill("Kolik zaplatím ze svého, když mi ukradnou auto?")
    likvidace.get_by_role("button", name="Hledat").click()
    snimek(likvidace, "hledani")
    likvidace.goto("/hlaseni")
    snimek(likvidace, "hlaseni")
    likvidace.get_by_role("link", name=HLASENI).click()
    expect(likvidace.locator("#stav-vytezeni")).to_have_text("Vytěženo", timeout=60_000)
    snimek(likvidace, "hlaseni-kontrola", cela=True)

    klient = stranka("klient", telefon=True)
    snimek(klient, "klient-telefon", cela=True)

    prohlizec.close()
