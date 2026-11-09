"""Text stránek → úryvky pro vyhledávání (krok 2A).

Čisté funkce bez databáze. Pravidla:

- **Úryvek nikdy nepřesahuje stránku** — citace „dokument, strana N“ pak
  vždy sedí.
- Každý úryvek nese **nejbližší nadpis** nad sebou („Článek 5 – Spoluúčast“),
  i když nadpis byl na předchozí stránce. Bez něj by úryvek „5 % ze škody“
  nedával smysl.
- Nový nadpis začíná nový úryvek; dlouhý článek se dělí po řádcích
  na kousky kolem 700 znaků.
- Záhlaví a zápatí (řádky, které se opakují na každé stránce, a „Strana
  N z M“) se do úryvků nedávají.
"""

import re
from dataclasses import dataclass

CIL_ZNAKU = 700
MAX_ZNAKU = 1000
MIN_ZNAKU = 200

_VELKE = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
_NADPIS = re.compile(
    rf"^(Článek \d+\b.*|\d+(\.\d+)*\.? [{_VELKE}].*)$"
)
_STRANA = re.compile(r"^Strana \d+ z \d+$")


@dataclass(frozen=True)
class NovyUryvek:
    strana: int
    poradi: int
    nadpis: str | None
    text: str


def je_nadpis(radek: str) -> bool:
    """„Článek 5 – Spoluúčast“, „8.1 Oprava vozidla“, „3. Lhůty pro oznámení“.
    Věta s tečkou na konci (číslovaný krok postupu) nadpis není."""
    return (
        len(radek) <= 80
        and not radek.endswith((".", ";", ",", ":"))
        and _NADPIS.match(radek) is not None
    )


def _vzor(radek: str) -> str:
    return re.sub(r"\d+", "#", radek.strip())


def opakovane_radky(stranky: list[str]) -> set[str]:
    """Řádky (čísla nahrazená #), které jsou na každé stránce = záhlaví/zápatí."""
    if len(stranky) < 2:
        return set()
    sady = [{_vzor(r) for r in s.splitlines() if r.strip()} for s in stranky]
    return set.intersection(*sady)


def _radky(text: str, vynechat: set[str]) -> list[str]:
    """Řádky stránky bez záhlaví a zápatí; osamocená odrážka „•“ se spojí
    s následujícím řádkem (tak ji vrací pypdf)."""
    vysledek: list[str] = []
    odrazka = False
    for surovy in text.splitlines():
        radek = " ".join(surovy.split())
        if not radek or _STRANA.match(radek) or _vzor(radek) in vynechat:
            continue
        if radek == "•":
            odrazka = True
            continue
        if odrazka:
            radek = f"• {radek}"
            odrazka = False
        vysledek.append(radek)
    return vysledek


def _je_pododdil(radek: str) -> bool:
    """„8.1 Oprava vozidla“ patří pod „Článek 8 – …“."""
    return re.match(r"^\d+\.\d+", radek) is not None


def rozdel(stranky: list[str]) -> list[NovyUryvek]:
    """Texty stránek (stránka 1 = index 0) → úryvky v pořadí čtení."""
    vynechat = opakovane_radky(stranky)
    uryvky: list[NovyUryvek] = []
    nadpis: str | None = None
    hlavni: str | None = None  # poslední nadpis první úrovně

    for cislo, text in enumerate(stranky, start=1):
        kousek: list[str] = []
        delka = 0

        def uloz() -> None:
            nonlocal kousek, delka
            obsah = "\n".join(kousek).strip()
            if obsah:
                uryvky.append(NovyUryvek(cislo, len(uryvky) + 1, nadpis, obsah))
            kousek, delka = [], 0

        for radek in _radky(text, vynechat):
            if je_nadpis(radek):
                uloz()
                if _je_pododdil(radek) and hlavni:
                    nadpis = f"{hlavni} › {radek}"[:200]
                else:
                    hlavni = nadpis = radek[:200]
                continue
            if kousek and (
                delka + len(radek) > MAX_ZNAKU
                or (delka >= CIL_ZNAKU and kousek[-1].endswith((".", ";")))
            ) and delka >= MIN_ZNAKU:
                uloz()
            kousek.append(radek)
            delka += len(radek) + 1
        uloz()
    return uryvky
