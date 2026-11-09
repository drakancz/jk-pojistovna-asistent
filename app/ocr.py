"""Přepis naskenované stránky Claudem (OCR) — krok 2A.

Model Claude Haiku 5.5 (Jakub, 3. 11. 2026: nejlevnější, na přepis stačí).
Volá se **jen jednou při čtení dokumentu**, výsledek se uloží do databáze.
Bez klíče `ANTHROPIC_API_KEY` je OCR vypnuté — nikdy se nedosazuje náhradní
hodnota. V testech odpovídá napodobenina (`scripts/napodobenina_anthropic.py`),
nic neodchází ven.
"""

import base64

import anthropic

from app.nastaveni import nastaveni
from app.soubory import PDF

MODEL = "claude-haiku-5-5"

POKYN = (
    "Přepiš veškerý text z této stránky naskenovaného dokumentu přesně tak, "
    "jak je napsaný, včetně čísel, dat a diakritiky. Zachovej pořadí čtení "
    "a odstavce; nadpisy dej na samostatný řádek. Tabulku přepiš po řádcích "
    "a buňky odděl znakem |. Ručně vyplněné údaje přepiš také. Přeškrtnutý "
    "text přepiš jako ~~text~~. Zaškrtávací políčko přepiš před jeho popiskem "
    "jako [x] (zaškrtnuté) nebo [ ] (prázdné). Nic "
    "nevysvětluj, nic nepřidávej, nic neopravuj a nic nevynechávej. Nečitelné "
    "místo označ [nečitelné]. Když na stránce žádný text není, odpověz prázdně."
)


class ChybaOcr(Exception):
    """Důvod pro člověka (krátce, česky) — ukáže se u dokumentu."""


def je_zapnute() -> bool:
    return bool(nastaveni().anthropic_api_key.strip())


def _klient() -> anthropic.Anthropic:
    n = nastaveni()
    return anthropic.Anthropic(
        api_key=n.anthropic_api_key,
        base_url=n.anthropic_base_url or None,
        timeout=90.0,
        max_retries=2,
    )


def prepis(obsah: bytes, typ: str) -> str:
    """Jedna stránka (jednostránkové PDF, PNG nebo JPEG) → text."""
    data = base64.standard_b64encode(obsah).decode("ascii")
    if typ == PDF:
        blok = {"type": "document", "source": {"type": "base64", "media_type": PDF, "data": data}}
    else:
        blok = {"type": "image", "source": {"type": "base64", "media_type": typ, "data": data}}

    try:
        odpoved = _klient().messages.create(
            model=MODEL,
            max_tokens=8000,
            # Přepis nepotřebuje přemýšlení: vypnuté a nízké úsilí = nižší cena.
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": [blok, {"type": "text", "text": POKYN}]}],
        )
    except anthropic.AuthenticationError as e:
        raise ChybaOcr("Klíč k Anthropicu je neplatný.") from e
    except anthropic.RateLimitError as e:
        raise ChybaOcr("Překročený limit u Anthropicu, zkuste to později.") from e
    except anthropic.BadRequestError as e:
        raise ChybaOcr("Anthropic stránku odmítl zpracovat.") from e
    except anthropic.APIStatusError as e:
        raise ChybaOcr(f"Služba OCR vrátila chybu {e.status_code}.") from e
    except anthropic.APIConnectionError as e:
        raise ChybaOcr("Služba OCR není dostupná.") from e

    if odpoved.stop_reason == "refusal":
        raise ChybaOcr("Claude odmítl stránku přepsat.")
    if odpoved.stop_reason == "max_tokens":
        raise ChybaOcr("Stránka je na přepis příliš dlouhá.")
    return "\n".join(b.text for b in odpoved.content if b.type == "text").strip()
