"""Asistent (krok 3A): otázka → odpověď s citací dokumentu a stránky.

Oprávnění (Jakub, 4. 11. 2026): **vidí a používá každý přihlášený** —
administrátor, pracovník likvidace a od kroku 3B i klient (ten se ptá jen
nad podmínkami a svými smlouvami). Nepřihlášený je přesměrovaný na
přihlášení. Co kdo najde, hlídá podmínka v dotazu
(`viditelne_dokumenty()`), ne tahle obrazovka — cizí smlouvu tak klient
nedostane on ani AI.

Otázka jde formulářem (POST), ne v adrese, a neukládá se.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app import asistent, hledani, ukazka
from app.bezpecnost import adresa_klienta, csrf_sedi
from app.db import db
from app.opravneni import Prihlaseny
from app.sablony import stranka

router = APIRouter()


def _navstevnik(request: Request) -> str | None:
    """V živé ukázce se limit počítá na návštěvníka (Jakub, 8. 11. 2026)."""
    return ukazka.otisk_navstevnika(adresa_klienta(request)) if ukazka.je_ukazka() else None


def _stranka(request, sezeni, sezeni_db, status_code: int = 200, **kontext):
    return stranka(
        request,
        "asistent.html",
        sezeni,
        status_code=status_code,
        zapnuty=asistent.je_zapnuty(),
        zbyva=asistent.zbyva(sezeni_db, sezeni.uzivatel.id, _navstevnik(request)),
        max_delka=hledani.MAX_OTAZKA,
        **kontext,
    )


@router.get("/asistent")
def formular(request: Request, sezeni: Prihlaseny, sezeni_db: Annotated[Session, Depends(db)]):
    return _stranka(request, sezeni, sezeni_db)


@router.post("/asistent")
def odpovez(
    request: Request,
    sezeni: Prihlaseny,
    sezeni_db: Annotated[Session, Depends(db)],
    csrf: Annotated[str, Form()] = "",
    otazka: Annotated[str, Form()] = "",
):
    otazka = otazka.strip()[: hledani.MAX_OTAZKA]
    if not csrf_sedi(sezeni, csrf):
        return _stranka(request, sezeni, sezeni_db, otazka=otazka)
    if not otazka:
        return _stranka(request, sezeni, sezeni_db, 400, otazka=otazka, chyba="Napište, na co se chcete zeptat.")
    try:
        odpoved = asistent.zeptej_se(
            sezeni_db,
            sezeni.uzivatel,
            otazka,
            hledani.viditelne_dokumenty(sezeni.uzivatel),
            _navstevnik(request),
        )
    except asistent.LimitVycerpan as e:
        return _stranka(request, sezeni, sezeni_db, 429, otazka=otazka, chyba=str(e))
    except asistent.ChybaAsistenta as e:
        return _stranka(request, sezeni, sezeni_db, 503, otazka=otazka, chyba=str(e))
    return _stranka(request, sezeni, sezeni_db, otazka=otazka, odpoved=odpoved)
