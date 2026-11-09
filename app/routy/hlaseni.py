"""Hlášení škody: seznam, detail s údaji vytěženými AI, sken, nové
vytěžení (krok 4B) a kontrola člověkem (krok 4C).

Oprávnění (zadání 3. 11., Jakub 4. 11. 2026): **vidí administrátor
a pracovník likvidace**, klient dostane 404 (ani svoje hlášení),
nepřihlášený přesměrování na přihlášení. „Vytěžit znovu“ (platí se
u Anthropicu) jen administrátor, a jen dokud údaje nikdo neopravil.
**Opravuje, potvrzuje a vrací ke kontrole jen likvidace**; administrátor
vidí údaje jen pro čtení. Přesnost proti správným údajům ukázkových
hlášení (AI i po kontrole) vidí jen administrátor.
"""

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import kontrola, ukazka, vytezeni
from app.bezpecnost import csrf_sedi
from app.db import db
from app.modely import (
    NAZVY_STAVU_KONTROLY,
    Audit,
    Dokument,
    DruhDokumentu,
    Role,
    Sezeni,
    StavCteni,
    StavVytezeni,
    Uzivatel,
    Vytezeni,
)
from app.opravneni import Administrator, Likvidace, Zamestnanec
from app.sablony import stranka

router = APIRouter()

ZPRAVY = {
    "vytezuje": "Hlášení se znovu vytěžuje.",
    "ukazka": ukazka.BLOKOVANO,
    "nelze": "Hlášení teď vytěžit nejde — ještě se čte nebo vytěžuje.",
    "opraveno": "Znovu vytěžit nejde — údaje už kontroloval člověk a jeho práce by se ztratila.",
    "ulozeno": "Opravy jsou uložené. Údaje zatím nejsou potvrzené.",
    "potvrzeno": "Údaje jsou potvrzené.",
    "vraceno": "Údaje jsou vrácené ke kontrole.",
    "beze_zmen": "Nic se nezměnilo, není co uložit.",
    "soubeh": "Údaje mezitím změnil někdo jiný. Zobrazuje se aktuální stav — opravu případně zopakujte.",
    "nelze_upravit": "Údaje teď upravit nejde — hlášení se vytěžuje nebo jsou údaje už potvrzené.",
}
# Sken se otevírá jako samostatný dokument: prohlížeč k zobrazení PDF
# potřebuje object-src; skripty ani styly ze stránky tu nejsou.
CSP_SKENU = "default-src 'none'; img-src 'self'; object-src 'self'; frame-ancestors 'none'; base-uri 'none'"
CTENI_PROBIHA = {StavCteni.CEKA, StavCteni.CTE_SE}
VYTEZENI_PROBIHA = {StavVytezeni.CEKA, StavVytezeni.PROBIHA}
AKCE_HISTORIE = {
    "hlaseni_opraveno": "Oprava údajů",
    "hlaseni_potvrzeno": "Potvrzení údajů",
    "hlaseni_vraceno": "Vrácení ke kontrole",
    "hlaseni_vytezeno_znovu": "Nové vytěžení AI",
}


def _hlaseni(sezeni_db: Session, dokument_id: int) -> tuple[Dokument, Vytezeni | None]:
    dokument = sezeni_db.get(Dokument, dokument_id)
    if dokument is None or dokument.druh != DruhDokumentu.HLASENI:
        raise HTTPException(status_code=404)
    v = sezeni_db.scalar(select(Vytezeni).where(Vytezeni.dokument_id == dokument_id))
    return dokument, v


def _bezi(dokument: Dokument, v: Vytezeni | None) -> bool:
    return dokument.stav_cteni in CTENI_PROBIHA or (v is not None and v.stav in VYTEZENI_PROBIHA)


def _lze_upravit(dokument: Dokument, v: Vytezeni | None) -> bool:
    return (
        v is not None
        and v.stav == StavVytezeni.HOTOVO
        and bool(v.navrh)
        and v.potvrzeno is None
        and not _bezi(dokument, v)
    )


def _presnost(srovnani: dict | None) -> tuple[int, int] | None:
    return (sum(s for s, _ in srovnani.values()), len(srovnani)) if srovnani else None


def _historie(sezeni_db: Session, dokument_id: int) -> list[dict]:
    radky = sezeni_db.execute(
        select(Audit, Uzivatel)
        .outerjoin(Uzivatel, Uzivatel.id == Audit.uzivatel_id)
        .where(
            Audit.akce.in_(AKCE_HISTORIE),
            Audit.podrobnosti["dokument_id"].as_integer() == dokument_id,
        )
        .order_by(Audit.cas.desc(), Audit.id.desc())
        .limit(50)
    ).all()
    popisky = {klic: popisek for klic, popisek, _ in vytezeni.POLE}
    return [
        {
            "cas": a.cas,
            "kdo": u.jmeno if u else "smazaný účet",
            "akce": AKCE_HISTORIE[a.akce],
            "zmeny": [
                (popisky.get(klic, klic), z["puvodne"], z["nove"])
                for klic, z in (a.podrobnosti.get("zmeny") or {}).items()
            ],
        }
        for a, u in radky
    ]


@router.get("/hlaseni")
def seznam(request: Request, sezeni: Zamestnanec, sezeni_db: Annotated[Session, Depends(db)]):
    radky = sezeni_db.execute(
        select(Dokument, Vytezeni)
        .outerjoin(Vytezeni, Vytezeni.dokument_id == Dokument.id)
        .where(Dokument.druh == DruhDokumentu.HLASENI)
        .order_by(Dokument.nahrano.desc(), Dokument.id.desc())
    ).all()
    admin = sezeni.uzivatel.role == Role.ADMIN
    hlaseni = []
    sedi_celkem = poli_celkem = 0
    # Srovnání AI a člověka na stejných (zkontrolovaných) hlášeních.
    kontrola_ai = kontrola_clovek = kontrola_poli = kontrolovanych = 0
    for d, v in radky:
        presnost = presnost_po = None
        if admin and v is not None and v.navrh:
            presnost = _presnost(vytezeni.porovnej(v.navrh, d.sha256))
            if presnost is not None:
                sedi_celkem += presnost[0]
                poli_celkem += presnost[1]
                if v.udaje:
                    presnost_po = _presnost(vytezeni.porovnej(v.udaje, d.sha256))
                    kontrola_ai += presnost[0]
                    kontrola_clovek += presnost_po[0]
                    kontrola_poli += presnost_po[1]
                    kontrolovanych += 1
        hlaseni.append({"d": d, "v": v, "presnost": presnost, "presnost_po": presnost_po,
                        "udaje": (v.udaje or v.navrh or {}) if v else {}})
    return stranka(
        request,
        "hlaseni.html",
        sezeni,
        hlaseni=hlaseni,
        presnost_celkem=(sedi_celkem, poli_celkem) if poli_celkem else None,
        presnost_kontroly=(kontrolovanych, kontrola_ai, kontrola_clovek, kontrola_poli) if kontrola_poli else None,
        zobraz=vytezeni.zobraz,
        NAZVY_STAVU_KONTROLY=NAZVY_STAVU_KONTROLY,
        obnovit=any(_bezi(h["d"], h["v"]) for h in hlaseni),
    )


def _detail(
    request: Request,
    sezeni: Sezeni,
    sezeni_db: Session,
    dokument: Dokument,
    v: Vytezeni | None,
    hodnoty: dict | None = None,
    chyby: dict[str, str] | None = None,
    zprava: str | None = None,
    status_code: int = 200,
):
    role = sezeni.uzivatel.role
    admin = role == Role.ADMIN
    navrh = v.navrh if v and v.navrh else None
    udaje = v.udaje if v and v.udaje else None
    srovnani = vytezeni.porovnej(navrh, dokument.sha256) if admin and navrh else None
    srovnani_po = vytezeni.porovnej(udaje, dokument.sha256) if admin and udaje else None
    upravit = role == Role.LIKVIDACE and _lze_upravit(dokument, v)
    if upravit and hodnoty is None:
        hodnoty = kontrola.do_formulare(udaje or navrh)
    return stranka(
        request,
        "hlaseni_detail.html",
        sezeni,
        status_code=status_code,
        d=dokument,
        v=v,
        pole=vytezeni.POLE,
        udaje=udaje or navrh,
        opraveno=kontrola.opraveno_oproti_ai(navrh, udaje) if navrh else {},
        srovnani=srovnani,
        srovnani_po=srovnani_po,
        presnost=_presnost(srovnani),
        presnost_po=_presnost(srovnani_po),
        zobraz=vytezeni.zobraz,
        je_obrazek=dokument.typ_obsahu.startswith("image/"),
        lze_vytezit=admin
        and dokument.stav_cteni == StavCteni.PRECTENO
        and not _bezi(dokument, v)
        and udaje is None,
        upravit=upravit,
        vratit=role == Role.LIKVIDACE and v is not None and v.potvrzeno is not None,
        hodnoty=hodnoty,
        radky_polozek=kontrola.radky_polozek(hodnoty) if hodnoty else [],
        druh_pole=kontrola.druh_pole,
        vybery=kontrola.VYBERY,
        max_delka=vytezeni.MAX_DELKA_TEXTU,
        chyby=chyby or {},
        historie=_historie(sezeni_db, dokument.id) if v else [],
        NAZVY_STAVU_KONTROLY=NAZVY_STAVU_KONTROLY,
        zprava=zprava,
        obnovit=_bezi(dokument, v),
    )


@router.get("/hlaseni/{dokument_id}")
def detail(
    dokument_id: int,
    request: Request,
    sezeni: Zamestnanec,
    sezeni_db: Annotated[Session, Depends(db)],
):
    dokument, v = _hlaseni(sezeni_db, dokument_id)
    return _detail(request, sezeni, sezeni_db, dokument, v, zprava=ZPRAVY.get(request.query_params.get("zprava", "")))


@router.get("/hlaseni/{dokument_id}/sken")
def sken(dokument_id: int, sezeni: Zamestnanec, sezeni_db: Annotated[Session, Depends(db)]):
    dokument, _ = _hlaseni(sezeni_db, dokument_id)
    # Typ je ověřený podle prvních bajtů už při nahrání (app.soubory).
    nazev = re.sub(r"[^A-Za-z0-9._-]", "_", dokument.nazev_souboru)[:100] or "sken"
    return Response(
        content=dokument.obsah,
        media_type=dokument.typ_obsahu,
        headers={"Content-Disposition": f'inline; filename="{nazev}"', "Content-Security-Policy": CSP_SKENU},
    )


@router.post("/hlaseni/{dokument_id}/vytezit")
def vytezit_znovu(
    dokument_id: int,
    sezeni: Administrator,
    sezeni_db: Annotated[Session, Depends(db)],
    csrf: Annotated[str, Form()] = "",
):
    adresa = f"/hlaseni/{dokument_id}"
    if not csrf_sedi(sezeni, csrf):
        return RedirectResponse(adresa, status_code=303)
    if ukazka.je_ukazka():
        return RedirectResponse(f"{adresa}?zprava=ukazka", status_code=303)
    dokument, v = _hlaseni(sezeni_db, dokument_id)
    if v is not None and v.udaje is not None:
        return RedirectResponse(f"{adresa}?zprava=opraveno", status_code=303)
    if dokument.stav_cteni != StavCteni.PRECTENO or _bezi(dokument, v):
        return RedirectResponse(f"{adresa}?zprava=nelze", status_code=303)
    if v is not None:
        # Podmíněný zápis: probíhající vytěžení se nepřeruší a opravy
        # člověka (uložené mezitím) se nepřepíšou.
        zmeneno = sezeni_db.execute(
            update(Vytezeni)
            .where(Vytezeni.id == v.id, Vytezeni.stav.not_in(VYTEZENI_PROBIHA), Vytezeni.udaje.is_(None))
            .values(stav=StavVytezeni.CEKA, chyba=None, verze=Vytezeni.verze + 1)
        ).rowcount
        if not zmeneno:
            sezeni_db.rollback()
            return RedirectResponse(f"{adresa}?zprava=nelze", status_code=303)
    sezeni_db.add(
        Audit(uzivatel_id=sezeni.uzivatel_id, akce="hlaseni_vytezeno_znovu", podrobnosti={"dokument_id": dokument_id})
    )
    sezeni_db.commit()
    vytezeni.naplanuj(dokument_id)
    return RedirectResponse(f"{adresa}?zprava=vytezuje", status_code=303)


async def _formular(request: Request) -> dict[str, str]:
    """Odeslaný formulář jako slovník textů (soubory se nepřijímají)."""
    return {k: v for k, v in (await request.form()).items() if isinstance(v, str)}


def _verze(formular: dict[str, str]) -> int:
    text = formular.get("verze", "")
    return int(text) if text.isdigit() else -1


@router.post("/hlaseni/{dokument_id}/kontrola")
def ulozit_kontrolu(
    dokument_id: int,
    request: Request,
    sezeni: Likvidace,
    sezeni_db: Annotated[Session, Depends(db)],
    formular: Annotated[dict[str, str], Depends(_formular)],
):
    adresa = f"/hlaseni/{dokument_id}"
    if not csrf_sedi(sezeni, formular.get("csrf", "")):
        return RedirectResponse(adresa, status_code=303)
    dokument, v = _hlaseni(sezeni_db, dokument_id)
    if not _lze_upravit(dokument, v):
        return RedirectResponse(f"{adresa}?zprava=nelze_upravit", status_code=303)
    verze = _verze(formular)
    if verze != v.verze:
        return RedirectResponse(f"{adresa}?zprava=soubeh", status_code=303)

    udaje, hodnoty, chyby = kontrola.precti(formular)
    if chyby:
        return _detail(request, sezeni, sezeni_db, dokument, v, hodnoty=hodnoty, chyby=chyby, status_code=400)

    potvrdit = formular.get("akce") == "potvrdit"
    zmeny = kontrola.rozdily(v.udaje or v.navrh, udaje)
    if not zmeny and not potvrdit:
        return RedirectResponse(f"{adresa}?zprava=beze_zmen", status_code=303)

    hodnoty_zapisu: dict = {"udaje": udaje, "verze": Vytezeni.verze + 1}
    if potvrdit:
        hodnoty_zapisu.update(potvrzeno=datetime.now(UTC), potvrdil_id=sezeni.uzivatel_id)
    # Podmíněný zápis: jen když od načtení formuláře nikdo nic nezměnil.
    zmeneno = sezeni_db.execute(
        update(Vytezeni)
        .where(
            Vytezeni.id == v.id,
            Vytezeni.verze == verze,
            Vytezeni.stav == StavVytezeni.HOTOVO,
            Vytezeni.potvrzeno.is_(None),
        )
        .values(**hodnoty_zapisu)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not zmeneno:
        sezeni_db.rollback()
        return RedirectResponse(f"{adresa}?zprava=soubeh", status_code=303)
    if zmeny:
        sezeni_db.add(Audit(uzivatel_id=sezeni.uzivatel_id, akce="hlaseni_opraveno",
                            podrobnosti={"dokument_id": dokument_id, "zmeny": zmeny}))
    if potvrdit:
        sezeni_db.add(Audit(uzivatel_id=sezeni.uzivatel_id, akce="hlaseni_potvrzeno",
                            podrobnosti={"dokument_id": dokument_id}))
    sezeni_db.commit()
    return RedirectResponse(f"{adresa}?zprava={'potvrzeno' if potvrdit else 'ulozeno'}", status_code=303)


@router.post("/hlaseni/{dokument_id}/vratit")
def vratit_ke_kontrole(
    dokument_id: int,
    sezeni: Likvidace,
    sezeni_db: Annotated[Session, Depends(db)],
    csrf: Annotated[str, Form()] = "",
    verze: Annotated[str, Form()] = "",
):
    adresa = f"/hlaseni/{dokument_id}"
    if not csrf_sedi(sezeni, csrf):
        return RedirectResponse(adresa, status_code=303)
    _, v = _hlaseni(sezeni_db, dokument_id)
    if v is None or v.potvrzeno is None:
        return RedirectResponse(adresa, status_code=303)
    zmeneno = sezeni_db.execute(
        update(Vytezeni)
        .where(Vytezeni.id == v.id, Vytezeni.verze == _verze({"verze": verze}), Vytezeni.potvrzeno.is_not(None))
        .values(potvrzeno=None, potvrdil_id=None, verze=Vytezeni.verze + 1)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not zmeneno:
        sezeni_db.rollback()
        return RedirectResponse(f"{adresa}?zprava=soubeh", status_code=303)
    sezeni_db.add(Audit(uzivatel_id=sezeni.uzivatel_id, akce="hlaseni_vraceno", podrobnosti={"dokument_id": dokument_id}))
    sezeni_db.commit()
    return RedirectResponse(f"{adresa}?zprava=vraceno", status_code=303)
