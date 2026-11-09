"""Kdo smí kam. Kontrola je první závislost každé chráněné adresy.

Nepovolaný dostane 404 (ne „nemáte oprávnění“) — z odpovědi se nemá dát
vyčíst, co v systému existuje. Nepřihlášený je přesměrovaný na přihlášení.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.bezpecnost import nacti_sezeni
from app.db import db
from app.modely import Role, Sezeni


class Neprihlasen(Exception):
    """Zachytí ji obsluha v main.py a přesměruje na /prihlaseni."""


def volitelne_sezeni(request: Request, sezeni_db: Annotated[Session, Depends(db)]) -> Sezeni | None:
    return nacti_sezeni(sezeni_db, request)


def vyzaduj_prihlaseni(
    sezeni: Annotated[Sezeni | None, Depends(volitelne_sezeni)],
) -> Sezeni:
    if sezeni is None:
        raise Neprihlasen()
    return sezeni


def vyzaduj_roli(*role: Role):
    def kontrola(sezeni: Annotated[Sezeni, Depends(vyzaduj_prihlaseni)]) -> Sezeni:
        if sezeni.uzivatel.role not in role:
            raise HTTPException(status_code=404)
        return sezeni

    return kontrola


Prihlaseny = Annotated[Sezeni, Depends(vyzaduj_prihlaseni)]
Administrator = Annotated[Sezeni, Depends(vyzaduj_roli(Role.ADMIN))]
# Administrátor a pracovník likvidace (vyhledávání, krok 2B).
Zamestnanec = Annotated[Sezeni, Depends(vyzaduj_roli(Role.ADMIN, Role.LIKVIDACE))]
# Jen pracovník likvidace: opravuje a potvrzuje vytěžené údaje (krok 4C).
Likvidace = Annotated[Sezeni, Depends(vyzaduj_roli(Role.LIKVIDACE))]
