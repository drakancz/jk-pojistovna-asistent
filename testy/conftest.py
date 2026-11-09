"""Společné pomůcky testů v prohlížeči.

Testovací server (scripts/test-server.sh) před během vymaže testovací
databázi a založí účty s náhodnými hesly do /stav/ucty.json.
"""

import json
import os
import random
import secrets
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

ADRESA = os.environ.get("ZAKLADNI_ADRESA", "http://web-test:8100")
UCTY = json.loads(Path("/stav/ucty.json").read_text(encoding="utf-8"))

# Nejmenší soubory, které projdou kontrolou obsahu.
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PODVRH = b"Tohle neni PDF, jen text s priponou .pdf\n"
def _pdf(*objekty: bytes) -> bytes:
    """Platné PDF i s tabulkou odkazů (xref), objekty číslované od 1."""
    vystup = b"%PDF-1.4\n"
    pozice = []
    for cislo, obj in enumerate(objekty, start=1):
        pozice.append(len(vystup))
        vystup += b"%d 0 obj\n" % cislo + obj + b"\nendobj\n"
    xref = len(vystup)
    vystup += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekty) + 1)
    vystup += b"".join(b"%010d 00000 n \n" % p for p in pozice)
    vystup += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objekty) + 1, xref)
    return vystup


# PDF s jednou stránkou bez textu = „sken“ (půjde na OCR).
SKEN_PDF = _pdf(
    b"<</Type/Catalog/Pages 2 0 R>>",
    b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
    b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>",
)
# Vymyšlená PDF JK pojišťovny (krok 1C), připojená do kontejneru testů.
DOKUMENTY = Path("/prace/dokumenty")
NAPODOBENINA = os.environ.get("NAPODOBENINA", "http://napodobenina:8200")


def napodobenina(cesta: str, data: dict | None = None) -> dict:
    """Ovládání napodobeniny Anthropicu (režim chyby, poslední dotaz)."""
    import urllib.request

    pozadavek = urllib.request.Request(
        NAPODOBENINA + cesta,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(pozadavek, timeout=10) as odpoved:
        return json.loads(odpoved.read())


def nahodna_ip() -> str:
    """Každý kontext má vlastní adresu, ať se omezení pokusů mezi testy nepletou."""
    return "10.{}.{}.{}".format(*(random.randint(1, 254) for _ in range(3)))


def pripona() -> str:
    return secrets.token_hex(3)


def bez_vodorovneho_posuvu(page: Page) -> None:
    sirka = page.evaluate("document.documentElement.scrollWidth")
    okno = page.evaluate("document.documentElement.clientWidth")
    assert sirka <= okno, f"Stránka přečnívá: {sirka} px při šířce {okno} px"


@pytest.fixture
def novy_kontext(browser: Browser) -> Iterator[Callable[..., BrowserContext]]:
    kontexty: list[BrowserContext] = []

    def vytvor(**volby) -> BrowserContext:
        kontext = browser.new_context(
            base_url=ADRESA,
            extra_http_headers={"X-Forwarded-For": nahodna_ip()},
            **volby,
        )
        kontexty.append(kontext)
        return kontext

    yield vytvor
    for kontext in kontexty:
        kontext.close()


def prihlas_stranku(page: Page, ucet: str) -> Page:
    udaje = UCTY[ucet]
    page.goto("/prihlaseni")
    page.get_by_label("E-mail", exact=True).fill(udaje["email"])
    page.get_by_label("Heslo", exact=True).fill(udaje["heslo"])
    page.get_by_role("button", name="Přihlásit").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Dobrý den")
    return page


@pytest.fixture
def prihlas(novy_kontext) -> Callable[..., Page]:
    """prihlas("admin") → přihlášená stránka v novém kontextu."""

    def prihlaseni(ucet: str, **volby) -> Page:
        return prihlas_stranku(novy_kontext(**volby).new_page(), ucet)

    return prihlaseni


def csrf(page: Page) -> str:
    return page.locator("input[name=csrf]").first.get_attribute("value") or ""


def odesli_formular(page: Page, adresa: str, data: dict | None = None, multipart: dict | None = None):
    """Přímé odeslání formuláře (mimo tlačítka) se sezením stránky a správným Origin."""
    return page.request.post(
        adresa,
        form=data if multipart is None else None,
        multipart=multipart,
        headers={"Origin": ADRESA},
        max_redirects=0,
    )
