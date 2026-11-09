"""Živá ukázka pro zájemce (krok 6A, rozhodnutí Jakuba 8. 11. 2026).

Zapíná se proměnnou `UKAZKA=1` (nastavuje Jakub na Railway). Bez ní se
aplikace chová přesně jako dřív — doma, v testech i jinde.

- **Tři ukázkové účty se známým heslem** (jeden za každou roli), vypsané
  na přihlašovací stránce. Heslo je veřejné **schválně** — vědomá výjimka
  z pravidla o tajemstvích: bez `UKAZKA=1` účty nevzniknou (zakládá je jen
  `obnov()`, která jinde odmítne běžet) a data ukázky jsou vymyšlená.
- **Jen prohlížení dokumentů:** nahrávání, mazání, „Přečíst znovu“
  a „Vytěžit znovu“ se odmítnou na serveru (`BLOKOVANO`) — stálo by to
  peníze za AI a jeden návštěvník by ukázku změnil ostatním. Opravy
  vytěžených údajů (likvidace) zůstávají, noc je vrátí.
- **Limit asistenta na návštěvníka** (10 otázek denně z jedné adresy,
  celkem 100), ne na sdílený účet. Ukládá se jen otisk adresy s dnem.
- **Obnova nejvýš jednou za pražský den:** při startu serveru
  (`python -m app.prikazy obnov-ukazku` ve `start.sh`) a při prvním
  požadavku nového dne (middleware v `app/main.py`). Služba se uspává,
  takže zvláštní plánovač na Railway není potřeba. Vrátí opravy
  vytěžených údajů do stavu návrhu AI, smaže historii, dotazy na AI,
  neúspěšná přihlášení a všechna sezení a nastaví heslo ukázkových účtů.
  Dokumenty a jejich přečtený text zůstávají — OCR se znovu neplatí.
"""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text, update

from app.bezpecnost import otisk_hesla, over_heslo, sjednot_email
from app.db import nove_sezeni
from app.modely import (
    Audit,
    Dokument,
    DotazAi,
    NeuspesnePrihlaseni,
    Role,
    Sezeni,
    UkazkaStav,
    Uzivatel,
    Vytezeni,
)
from app.nastaveni import nastaveni

PRAHA = ZoneInfo("Europe/Prague")
ZAMEK_OBNOVY = 6_011_001  # pg_advisory_xact_lock — obnova jen jednou naráz

# Veřejné heslo ukázkových účtů (viz výš, proč smí být v kódu).
HESLO = "ukazka-JK-2026"

BLOKOVANO = (
    "V ukázce se dokumenty nenahrávají, nemažou ani znovu nečtou a nevytěžují — "
    "stálo by to peníze za AI a ukázku by to změnilo ostatním návštěvníkům."
)


@dataclass(frozen=True)
class UkazkovyUcet:
    email: str
    jmeno: str
    role: Role
    popis: str  # co si v roli vyzkoušet (na přihlašovací stránce)


UCTY = (
    UkazkovyUcet(
        "ukazka-admin@jk-pojistovna.test",
        "Host (administrátor)",
        Role.ADMIN,
        "dokumenty, přečtený text a přesnost AI u hlášení",
    ),
    UkazkovyUcet(
        "ukazka-likvidace@jk-pojistovna.test",
        "Host (likvidace)",
        Role.LIKVIDACE,
        "hlášení škody: kontrola a oprava údajů vytěžených AI",
    ),
    # Klientka z ukázkových dokumentů — smlouvy 1001–1003 jsou její.
    UkazkovyUcet(
        "petra.mala@jk-pojistovna.test",
        "Petra Malá",
        Role.KLIENT,
        "asistent odpovídá jen z podmínek a vlastních smluv",
    ),
)

_overeno_dne: date | None = None


def je_ukazka() -> bool:
    return nastaveni().ukazka


def dnes() -> date:
    return datetime.now(PRAHA).date()


def otisk_navstevnika(adresa: str) -> str:
    """Otisk adresy pro limit na návštěvníka — se dnem, aby se adresa nedala
    vyčíst ani spojit přes více dní. Adresa sama se neukládá."""
    return hashlib.sha256(f"{dnes().isoformat()}|{adresa}".encode()).hexdigest()


def _ucty(db) -> None:
    """Založí ukázkové účty, nebo jim vrátí jméno, roli a známé heslo."""
    for ucet in UCTY:
        uzivatel = db.scalar(select(Uzivatel).where(Uzivatel.email == sjednot_email(ucet.email)))
        if uzivatel is None:
            uzivatel = Uzivatel(email=sjednot_email(ucet.email), jmeno=ucet.jmeno, role=ucet.role, otisk_hesla="")
            db.add(uzivatel)
        uzivatel.jmeno = ucet.jmeno
        uzivatel.role = ucet.role
        if not over_heslo(uzivatel, HESLO):
            uzivatel.otisk_hesla = otisk_hesla(HESLO)
    db.flush()


def obnov(vynutit: bool = False) -> bool:
    """Vrátí ukázku do výchozího stavu. Vrátí True, když obnova proběhla,
    False, když už dnes proběhla. Mimo ukázkový režim odmítne."""
    global _overeno_dne
    if not je_ukazka():
        raise RuntimeError("Obnova ukázky běží jen s UKAZKA=1.")
    den = dnes()
    with nove_sezeni() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:z)"), {"z": ZAMEK_OBNOVY})
        stav = db.get(UkazkaStav, 1)
        if stav is not None and stav.posledni_obnova == den and not vynutit:
            db.rollback()
            _overeno_dne = den
            return False
        _ucty(db)
        # Opravy a potvrzení likvidace pryč — zůstává návrh AI (OCR ani
        # vytěžení se znovu neplatí). Vyšší verze zneplatní otevřené formuláře.
        db.execute(
            update(Vytezeni)
            .where(Vytezeni.udaje.is_not(None) | Vytezeni.potvrzeno.is_not(None))
            .values(udaje=None, potvrzeno=None, potvrdil_id=None, verze=Vytezeni.verze + 1)
        )
        for tabulka in (Audit, DotazAi, NeuspesnePrihlaseni, Sezeni):
            db.execute(delete(tabulka))
        db.add(Audit(uzivatel_id=None, akce="ukazka_obnovena", podrobnosti={}))
        if stav is None:
            db.add(UkazkaStav(id=1, posledni_obnova=den))
        else:
            stav.posledni_obnova = den
        db.commit()
    _overeno_dne = den
    return True


def obnov_pokud_je_treba(vynutit: bool = False) -> None:
    """Pro middleware: levná kontrola v paměti, databáze jen po půlnoci."""
    if vynutit or _overeno_dne != dnes():
        obnov(vynutit)


def ma_dokumenty() -> bool:
    with nove_sezeni() as db:
        return (db.scalar(select(func.count()).select_from(Dokument)) or 0) > 0
