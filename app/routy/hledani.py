"""Vyhledávání v dokumentech (krok 2B) — zkušební obrazovka, než přijde
asistent (fáze 3): otázka → nejlepší úryvky s dokumentem a stránkou.

Oprávnění (Jakub, 4. 11. 2026): **vidí a používá administrátor a pracovník
likvidace** (oba vidí všechny dokumenty). Klient dostane 404 — má jen
Asistenta (Jakub, 4. 11. 2026, krok 3B). Nepřihlášený je přesměrovaný
na přihlášení. Co kdo najde, hlídá podmínka v dotazu
(`viditelne_dokumenty()`), ne tahle obrazovka.

Otázka se posílá formulářem (POST), ne v adrese — nemá zůstat v historii
prohlížeče ani v logu serveru. Nic se neukládá.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app import hledani
from app.bezpecnost import csrf_sedi
from app.db import db
from app.opravneni import Zamestnanec
from app.sablony import stranka

router = APIRouter()


@router.get("/hledani")
def formular(request: Request, sezeni: Zamestnanec):
    return stranka(request, "hledani.html", sezeni, max_delka=hledani.MAX_OTAZKA)


@router.post("/hledani")
def vysledky(
    request: Request,
    sezeni: Zamestnanec,
    sezeni_db: Annotated[Session, Depends(db)],
    csrf: Annotated[str, Form()] = "",
    otazka: Annotated[str, Form()] = "",
):
    kontext: dict = {"max_delka": hledani.MAX_OTAZKA, "otazka": otazka.strip()[: hledani.MAX_OTAZKA]}
    if not csrf_sedi(sezeni, csrf):
        return stranka(request, "hledani.html", sezeni, **kontext)
    if not kontext["otazka"]:
        kontext["chyba"] = "Napište, co hledáte."
        return stranka(request, "hledani.html", sezeni, status_code=400, **kontext)
    kontext["nalezy"] = hledani.hledej(
        sezeni_db, kontext["otazka"], hledani.viditelne_dokumenty(sezeni.uzivatel)
    )
    kontext["hledano"] = True
    return stranka(request, "hledani.html", sezeni, **kontext)
