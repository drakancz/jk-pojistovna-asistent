"""Přihlášení a odhlášení. Přihlášení je jediná obrazovka pro nepřihlášené."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import bezpecnost, ukazka
from app.db import db
from app.modely import Sezeni, Uzivatel
from app.opravneni import volitelne_sezeni
from app.sablony import stranka

router = APIRouter()

CHYBA_UDAJU = "E-mail nebo heslo nesedí."
CHYBA_POKUSU = "Příliš mnoho neúspěšných pokusů. Zkuste to znovu za 15 minut."


class PrihlasovaciUdaje(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    heslo: str = Field(min_length=1, max_length=200)


@router.get("/prihlaseni")
def formular(request: Request, sezeni: Annotated[Sezeni | None, Depends(volitelne_sezeni)]):
    if sezeni is not None:
        return RedirectResponse("/", status_code=303)
    return stranka(request, "prihlaseni.html")


@router.post("/prihlaseni")
def prihlasit(
    request: Request,
    sezeni_db: Annotated[Session, Depends(db)],
    email: Annotated[str, Form()] = "",
    heslo: Annotated[str, Form()] = "",
):
    ip = bezpecnost.adresa_klienta(request)
    if bezpecnost.je_zablokovano(sezeni_db, ip):
        return stranka(
            request, "prihlaseni.html", chyba=CHYBA_POKUSU, email=email[:254], status_code=429
        )

    try:
        udaje = PrihlasovaciUdaje(email=email, heslo=heslo)
    except ValidationError:
        udaje = None

    uzivatel = None
    if udaje is not None:
        uzivatel = sezeni_db.scalar(
            select(Uzivatel).where(Uzivatel.email == bezpecnost.sjednot_email(udaje.email))
        )
    # Veřejné heslo ukázky platí jen v ukázkovém režimu — kdyby se UKAZKA
    # vypnula, účty se známým heslem v databázi zůstanou, ale nepřihlásí se.
    verejne = udaje is not None and udaje.heslo == ukazka.HESLO and not ukazka.je_ukazka()
    if udaje is None or verejne or not bezpecnost.over_heslo(uzivatel, udaje.heslo):
        bezpecnost.zapis_neuspech(sezeni_db, ip)
        sezeni_db.commit()
        return stranka(
            request, "prihlaseni.html", chyba=CHYBA_UDAJU, email=email[:254], status_code=400
        )

    assert uzivatel is not None
    odpoved = RedirectResponse("/", status_code=303)
    bezpecnost.prihlas(sezeni_db, odpoved, uzivatel)
    sezeni_db.commit()
    return odpoved


@router.post("/odhlaseni")
def odhlasit(
    sezeni_db: Annotated[Session, Depends(db)],
    sezeni: Annotated[Sezeni | None, Depends(volitelne_sezeni)],
    csrf: Annotated[str, Form()] = "",
):
    odpoved = RedirectResponse("/prihlaseni", status_code=303)
    if sezeni is not None and bezpecnost.csrf_sedi(sezeni, csrf):
        bezpecnost.odhlas(sezeni_db, odpoved, sezeni)
        sezeni_db.commit()
    return odpoved
