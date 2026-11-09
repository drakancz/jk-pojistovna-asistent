"""Správa dokumentů: seznam, nahrání, detail s přečteným textem, opakované
čtení a smazání.

Oprávnění (zadání, Jakub 3. 11. 2026): **vidí, nahrává i maže jen
administrátor**. Klient a pracovník likvidace dostanou 404, nepřihlášený
přesměrování na přihlášení. Klient a likvidace uvidí své dokumenty až
přes asistenta (fáze 3), s filtrem podle oprávnění už ve vyhledávání.

Detail dokumentu (text stránek a úryvky) vidí a čtení znovu spouští jen
administrátor (Jakub, 4. 11. 2026, krok 2A); nepřihlášenému nic.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import cteni, ukazka
from app.bezpecnost import csrf_sedi
from app.db import db
from app.modely import (
    Audit,
    Dokument,
    DruhDokumentu,
    Pojisteni,
    Role,
    Sezeni,
    StavCteni,
    Strana,
    Uryvek,
    Uzivatel,
)
from app.nastaveni import nastaveni
from app.opravneni import Administrator
from app.sablony import stranka
from app.soubory import PDF, bezpecny_nazev, rozpoznej_typ

router = APIRouter()

# Zprávy po přesměrování — v adrese je jen klíč, nikdy text (nic se neodráží).
ZPRAVY = {
    "nahrano": "Dokument je nahraný.",
    "smazano": "Dokument je smazaný.",
    "neexistuje": "Dokument už v systému není.",
    "cteni": "Dokument se znovu čte.",
    "uz_se_cte": "Dokument se právě čte, počkejte na výsledek.",
    "ukazka": ukazka.BLOKOVANO,
}

# Dokud se čte, stránka se sama obnovuje (bez skriptu, CSP to dovolí).
PROBIHA = {StavCteni.CEKA, StavCteni.CTE_SE}


class NovyDokument(BaseModel):
    nazev: str = Field(min_length=1, max_length=200)
    druh: DruhDokumentu
    pojisteni: Pojisteni
    klient_id: int | None = Field(default=None, ge=1)


def _klienti(sezeni_db: Session) -> list[Uzivatel]:
    return list(
        sezeni_db.scalars(
            select(Uzivatel).where(Uzivatel.role == Role.KLIENT).order_by(Uzivatel.jmeno)
        )
    )


def _seznam(
    request: Request,
    sezeni_db: Session,
    sezeni: Sezeni,
    chyba: str | None = None,
    hodnoty: dict | None = None,
    status_code: int = 200,
):
    dokumenty = list(sezeni_db.scalars(select(Dokument).order_by(Dokument.nahrano.desc())))
    zprava = ZPRAVY.get(request.query_params.get("zprava", ""))
    return stranka(
        request,
        "dokumenty.html",
        sezeni,
        dokumenty=dokumenty,
        obnovit=any(d.stav_cteni in PROBIHA for d in dokumenty),
        klienti=_klienti(sezeni_db),
        chyba=chyba,
        zprava=zprava,
        hodnoty=hodnoty or {},
        max_mb=nastaveni().max_upload_mb,
        status_code=status_code,
    )


@router.get("/dokumenty")
def seznam(request: Request, sezeni: Administrator, sezeni_db: Annotated[Session, Depends(db)]):
    return _seznam(request, sezeni_db, sezeni)


@router.post("/dokumenty")
async def nahrat(
    request: Request,
    sezeni: Administrator,
    sezeni_db: Annotated[Session, Depends(db)],
    soubor: Annotated[UploadFile | None, File()] = None,
    csrf: Annotated[str, Form()] = "",
    nazev: Annotated[str, Form()] = "",
    druh: Annotated[str, Form()] = "",
    pojisteni: Annotated[str, Form()] = "",
    klient_id: Annotated[str, Form()] = "",
):
    if not csrf_sedi(sezeni, csrf):
        return RedirectResponse("/dokumenty", status_code=303)
    if ukazka.je_ukazka():
        return _seznam(request, sezeni_db, sezeni, chyba=ukazka.BLOKOVANO, status_code=403)

    hodnoty = {"nazev": nazev[:200], "druh": druh, "pojisteni": pojisteni, "klient_id": klient_id}

    def chyba(text: str):
        return _seznam(request, sezeni_db, sezeni, chyba=text, hodnoty=hodnoty, status_code=400)

    try:
        udaje = NovyDokument(
            nazev=nazev.strip(),
            druh=druh,  # type: ignore[arg-type]
            pojisteni=pojisteni,  # type: ignore[arg-type]
            klient_id=int(klient_id) if klient_id.strip().isdigit() else None,
        )
    except ValidationError:
        return chyba("Vyplňte název (nejvýš 200 znaků), druh dokumentu a pojištění.")

    # Komu dokument patří: smlouva vždy klientovi, podmínky nikomu.
    if udaje.druh == DruhDokumentu.PODMINKY:
        udaje.klient_id = None
    elif udaje.druh == DruhDokumentu.SMLOUVA and udaje.klient_id is None:
        return chyba("U smlouvy vyberte klienta, kterému patří.")
    if udaje.klient_id is not None:
        klient = sezeni_db.get(Uzivatel, udaje.klient_id)
        if klient is None or klient.role != Role.KLIENT:
            return chyba("Vybraný klient v systému není.")

    if soubor is None or not soubor.filename:
        return chyba("Vyberte soubor.")
    limit = nastaveni().max_upload_mb * 1024 * 1024
    obsah = await soubor.read(limit + 1)
    if len(obsah) == 0:
        return chyba("Soubor je prázdný.")
    if len(obsah) > limit:
        return chyba(f"Soubor je větší než {nastaveni().max_upload_mb} MB.")

    typ = rozpoznej_typ(obsah)
    if typ is None:
        return chyba("Soubor není PDF ani obrázek PNG nebo JPEG (kontroluje se obsah, ne přípona).")
    if udaje.druh != DruhDokumentu.HLASENI and typ != PDF:
        return chyba("Podmínky a smlouvy musí být PDF. Obrázek jde nahrát jen jako hlášení škody.")

    dokument = Dokument(
        nazev=udaje.nazev,
        nazev_souboru=bezpecny_nazev(soubor.filename),
        druh=udaje.druh,
        pojisteni=udaje.pojisteni,
        klient_id=udaje.klient_id,
        typ_obsahu=typ,
        velikost=len(obsah),
        sha256=hashlib.sha256(obsah).hexdigest(),
        obsah=obsah,
        nahral_id=sezeni.uzivatel_id,
    )
    sezeni_db.add(dokument)
    sezeni_db.flush()
    # Historie ve stejné transakci — bez obsahu souboru.
    sezeni_db.add(
        Audit(
            uzivatel_id=sezeni.uzivatel_id,
            akce="dokument_nahran",
            podrobnosti={
                "dokument_id": dokument.id,
                "nazev": dokument.nazev,
                "velikost": dokument.velikost,
            },
        )
    )
    sezeni_db.commit()
    # Čtení (text, OCR, úryvky) běží na pozadí, stránka nečeká.
    cteni.naplanuj(dokument.id)
    return RedirectResponse("/dokumenty?zprava=nahrano", status_code=303)


@router.get("/dokumenty/{dokument_id}")
def detail(
    dokument_id: int,
    request: Request,
    sezeni: Administrator,
    sezeni_db: Annotated[Session, Depends(db)],
):
    dokument = sezeni_db.get(Dokument, dokument_id)
    if dokument is None:
        raise HTTPException(status_code=404)
    stranky = sezeni_db.scalars(
        select(Strana).where(Strana.dokument_id == dokument_id).order_by(Strana.cislo)
    )
    uryvky = sezeni_db.scalars(
        select(Uryvek).where(Uryvek.dokument_id == dokument_id).order_by(Uryvek.poradi)
    )
    return stranka(
        request,
        "dokument.html",
        sezeni,
        d=dokument,
        stranky=list(stranky),
        uryvky=list(uryvky),
        zprava=ZPRAVY.get(request.query_params.get("zprava", "")),
        obnovit=dokument.stav_cteni in PROBIHA,
    )


@router.post("/dokumenty/{dokument_id}/precist")
def precist_znovu(
    dokument_id: int,
    sezeni: Administrator,
    sezeni_db: Annotated[Session, Depends(db)],
    csrf: Annotated[str, Form()] = "",
):
    adresa = f"/dokumenty/{dokument_id}"
    if not csrf_sedi(sezeni, csrf):
        return RedirectResponse(adresa, status_code=303)
    if ukazka.je_ukazka():
        return RedirectResponse(f"{adresa}?zprava=ukazka", status_code=303)
    if sezeni_db.get(Dokument, dokument_id) is None:
        return RedirectResponse("/dokumenty?zprava=neexistuje", status_code=303)
    # Podmíněný zápis: když se dokument právě čte, druhé čtení nezačne.
    zmeneno = sezeni_db.execute(
        update(Dokument)
        .where(Dokument.id == dokument_id, Dokument.stav_cteni.not_in(PROBIHA))
        .values(stav_cteni=StavCteni.CEKA, chyba_cteni=None)
    ).rowcount
    if not zmeneno:
        sezeni_db.rollback()
        return RedirectResponse(f"{adresa}?zprava=uz_se_cte", status_code=303)
    sezeni_db.add(
        Audit(
            uzivatel_id=sezeni.uzivatel_id,
            akce="dokument_cten_znovu",
            podrobnosti={"dokument_id": dokument_id},
        )
    )
    sezeni_db.commit()
    cteni.naplanuj(dokument_id)
    return RedirectResponse(f"{adresa}?zprava=cteni", status_code=303)


@router.post("/dokumenty/{dokument_id}/smazat")
def smazat(
    dokument_id: int,
    sezeni: Administrator,
    sezeni_db: Annotated[Session, Depends(db)],
    csrf: Annotated[str, Form()] = "",
):
    if not csrf_sedi(sezeni, csrf):
        return RedirectResponse("/dokumenty", status_code=303)
    if ukazka.je_ukazka():
        return RedirectResponse("/dokumenty?zprava=ukazka", status_code=303)
    dokument = sezeni_db.get(Dokument, dokument_id)
    if dokument is None:
        return RedirectResponse("/dokumenty?zprava=neexistuje", status_code=303)
    sezeni_db.add(
        Audit(
            uzivatel_id=sezeni.uzivatel_id,
            akce="dokument_smazan",
            podrobnosti={"dokument_id": dokument.id, "nazev": dokument.nazev},
        )
    )
    sezeni_db.delete(dokument)
    sezeni_db.commit()
    return RedirectResponse("/dokumenty?zprava=smazano", status_code=303)
