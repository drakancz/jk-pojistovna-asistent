"""Šablony stránek (Jinja2) a pomocníci pro ně."""

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import ukazka as _ukazka
from app.modely import (
    NAZVY_DRUHU,
    NAZVY_POJISTENI,
    NAZVY_ROLI,
    NAZVY_STAVU_CTENI,
    NAZVY_STAVU_VYTEZENI,
    Sezeni,
)

PRAHA = ZoneInfo("Europe/Prague")

sablony = Jinja2Templates(directory=Path(__file__).parent / "sablony")


def _cas(hodnota: datetime | None) -> str:
    if hodnota is None:
        return ""
    return hodnota.astimezone(PRAHA).strftime("%-d. %-m. %Y %H:%M")


def _velikost(bajty: int) -> str:
    if bajty < 1024:
        return f"{bajty} B"
    if bajty < 1024 * 1024:
        return f"{bajty / 1024:.0f} kB".replace(".", ",")
    return f"{bajty / 1024 / 1024:.1f} MB".replace(".", ",")


def _stran(pocet: int | None) -> str:
    pocet = pocet or 0
    if pocet == 1:
        return "1 strana"
    return f"{pocet} strany" if 2 <= pocet <= 4 else f"{pocet} stran"


def _uryvku(pocet: int) -> str:
    if pocet == 1:
        return "1 úryvek"
    return f"{pocet} úryvky" if 2 <= pocet <= 4 else f"{pocet} úryvků"


sablony.env.filters["stran"] = _stran
sablony.env.filters["uryvku"] = _uryvku
sablony.env.filters["cas"] = _cas
sablony.env.filters["velikost"] = _velikost
sablony.env.globals.update(
    ukazka=_ukazka.je_ukazka,
    UKAZKOVE_UCTY=_ukazka.UCTY,
    HESLO_UKAZKY=_ukazka.HESLO,
    NAZVY_ROLI=NAZVY_ROLI,
    NAZVY_DRUHU=NAZVY_DRUHU,
    NAZVY_POJISTENI=NAZVY_POJISTENI,
    NAZVY_STAVU_CTENI=NAZVY_STAVU_CTENI,
    NAZVY_STAVU_VYTEZENI=NAZVY_STAVU_VYTEZENI,
)


def stranka(
    request: Request,
    nazev: str,
    sezeni: Sezeni | None = None,
    status_code: int = 200,
    **kontext: Any,
):
    return sablony.TemplateResponse(
        request,
        nazev,
        {"sezeni": sezeni, "uzivatel": sezeni.uzivatel if sezeni else None, **kontext},
        status_code=status_code,
    )
