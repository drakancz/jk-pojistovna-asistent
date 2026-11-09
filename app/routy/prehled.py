"""Úvodní obrazovka po přihlášení. Vidí ji každý přihlášený (všechny tři role);
nepřihlášený je přesměrovaný na přihlášení (zadání, 3. 11. 2026)."""

from fastapi import APIRouter, Request

from app.opravneni import Prihlaseny
from app.sablony import stranka

router = APIRouter()


@router.get("/")
def prehled(request: Request, sezeni: Prihlaseny):
    return stranka(request, "prehled.html", sezeni)
