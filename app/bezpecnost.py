"""Hesla, sezení, ochrana formulářů a omezení pokusů o přihlášení."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modely import Audit, NeuspesnePrihlaseni, Sezeni, Uzivatel
from app.nastaveni import nastaveni

COOKIE = "sezeni"
PLATNOST_SEZENI = timedelta(hours=12)
MAX_POKUSU = 5
OKNO_POKUSU = timedelta(minutes=15)

_hasher = PasswordHasher()
# Otisk pro neexistující účet: ověření trvá stejně dlouho, takže z doby
# odpovědi nejde poznat, jestli e-mail v systému je.
_PRAZDNY_OTISK = _hasher.hash(secrets.token_urlsafe(16))


def sjednot_email(email: str) -> str:
    return email.strip().lower()


def otisk_hesla(heslo: str) -> str:
    return _hasher.hash(heslo)


def over_heslo(uzivatel: Uzivatel | None, heslo: str) -> bool:
    otisk = uzivatel.otisk_hesla if uzivatel else _PRAZDNY_OTISK
    try:
        _hasher.verify(otisk, heslo)
    except (VerificationError, InvalidHashError):
        return False
    return uzivatel is not None


def nove_heslo() -> str:
    """Náhodné heslo pro založený účet (16 znaků, ~96 bitů)."""
    return secrets.token_urlsafe(12)


def _otisk_tokenu(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def adresa_klienta(request: Request) -> str:
    # Za proxy Railway nastaví uvicorn (--proxy-headers) adresu z X-Forwarded-For.
    return (request.client.host if request.client else "neznama")[:64]


# --- Omezení pokusů ---------------------------------------------------------


def je_zablokovano(db: Session, ip: str) -> bool:
    od = datetime.now(UTC) - OKNO_POKUSU
    pocet = db.scalar(
        select(func.count())
        .select_from(NeuspesnePrihlaseni)
        .where(NeuspesnePrihlaseni.ip == ip, NeuspesnePrihlaseni.cas >= od)
    )
    return (pocet or 0) >= MAX_POKUSU


def zapis_neuspech(db: Session, ip: str) -> None:
    db.add(NeuspesnePrihlaseni(ip=ip))
    # Úklid starých záznamů, ať tabulka neroste.
    db.execute(
        delete(NeuspesnePrihlaseni).where(
            NeuspesnePrihlaseni.cas < datetime.now(UTC) - OKNO_POKUSU
        )
    )


# --- Sezení -----------------------------------------------------------------


def prihlas(db: Session, response: Response, uzivatel: Uzivatel) -> None:
    token = secrets.token_urlsafe(32)
    db.execute(delete(Sezeni).where(Sezeni.plati_do < datetime.now(UTC)))
    db.add(
        Sezeni(
            otisk_tokenu=_otisk_tokenu(token),
            uzivatel_id=uzivatel.id,
            csrf=secrets.token_urlsafe(32),
            plati_do=datetime.now(UTC) + PLATNOST_SEZENI,
        )
    )
    db.add(Audit(uzivatel_id=uzivatel.id, akce="prihlaseni", podrobnosti={}))
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(PLATNOST_SEZENI.total_seconds()),
        httponly=True,
        secure=nastaveni().cookie_secure,
        samesite="lax",
        path="/",
    )


def nacti_sezeni(db: Session, request: Request) -> Sezeni | None:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    sezeni = db.scalar(select(Sezeni).where(Sezeni.otisk_tokenu == _otisk_tokenu(token)))
    if sezeni is None or sezeni.plati_do < datetime.now(UTC):
        return None
    return sezeni


def odhlas(db: Session, response: Response, sezeni: Sezeni) -> None:
    db.add(Audit(uzivatel_id=sezeni.uzivatel_id, akce="odhlaseni", podrobnosti={}))
    db.delete(sezeni)
    response.delete_cookie(COOKIE, path="/")


def csrf_sedi(sezeni: Sezeni, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(sezeni.csrf, token or "")
