"""Čtení dokumentu na pozadí: text stránek (PDF nebo OCR) → úryvky. Krok 2A.

Průběh: nahrání (nebo „Přečíst znovu“) nastaví stav CEKA a předá dokument
sem. Čtení si dokument převezme podmíněným zápisem (CEKA → CTE_SE), takže
ho nikdy nečtou dva naráz. Výsledek nahradí staré stránky a úryvky
v jedné transakci.

- Stránka PDF s textem se přečte přímo (zdarma).
- Stránka bez textu (sken) a obrázek jdou ke Claudovi (`app.ocr`) — jen
  jednou, výsledek se uloží. Bez klíče skončí dokument ve stavu
  „čeká na OCR“ a k Claudovi neodejde nic.
- Chyba se zapíše jako krátký důvod pro člověka, nikdy obsah dokumentu.
"""

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError
from sqlalchemy import delete, select, update

from app import hledani, ocr, vytezeni
from app.db import nove_sezeni
from app.modely import Dokument, DruhDokumentu, StavCteni, Strana, Uryvek, Vytezeni
from app.nastaveni import nastaveni
from app.soubory import PDF
from app.uryvky import rozdel

log = logging.getLogger(__name__)

# Stránka PDF s méně znaky než tolik se bere jako sken (bez textové vrstvy).
MIN_ZNAKU_TEXTU = 20
MAX_STRAN = 500

_fronta = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cteni")


class ChybaCteni(Exception):
    """Důvod pro člověka, ukáže se u dokumentu."""


def na_pozadi(ukol) -> None:
    """Spustí úkol ve frontě čtení (start aplikace nečeká)."""
    _fronta.submit(ukol)


def naplanuj(dokument_id: int) -> None:
    """Předá dokument ke čtení na pozadí (odpověď prohlížeči nečeká)."""
    _fronta.submit(_bezpecne_precti, dokument_id)


def naplanuj_cekajici() -> None:
    """Po startu aplikace: dočte, co zůstalo rozečtené nebo čekající
    (restart serveru uprostřed čtení). Když mezitím přibyl klíč
    k Anthropicu, přečte i skeny, které na OCR čekaly — jen jednou."""
    stavy = [StavCteni.CTE_SE]
    if ocr.je_zapnute():
        stavy.append(StavCteni.CEKA_NA_OCR)
    with nove_sezeni() as db:
        db.execute(
            update(Dokument)
            .where(Dokument.stav_cteni.in_(stavy))
            .values(stav_cteni=StavCteni.CEKA)
        )
        db.commit()
        cekajici = db.scalars(select(Dokument.id).where(Dokument.stav_cteni == StavCteni.CEKA))
        for dokument_id in cekajici:
            naplanuj(dokument_id)


def _bezpecne_precti(dokument_id: int) -> None:
    try:
        precti(dokument_id)
    except Exception:  # noqa: BLE001 — vlákno na pozadí nesmí spadnout potichu
        log.exception("Čtení dokumentu %s selhalo", dokument_id)


def _stranky_pdf(obsah: bytes) -> list[tuple[str | None, bytes]]:
    """Pro každou stránku (text, nebo None u skenu; jednostránkové PDF pro OCR)."""
    try:
        ctenar = PdfReader(io.BytesIO(obsah))
        if ctenar.is_encrypted:
            raise ChybaCteni("PDF je zaheslované.")
        stranky = list(ctenar.pages)
    except PyPdfError as e:
        raise ChybaCteni("PDF je poškozené a nejde přečíst.") from e
    if not stranky:
        raise ChybaCteni("PDF nemá žádnou stránku.")
    if len(stranky) > MAX_STRAN:
        raise ChybaCteni(f"PDF má víc než {MAX_STRAN} stran.")

    vysledek: list[tuple[str | None, bytes]] = []
    for strana in stranky:
        try:
            text = strana.extract_text() or ""
        except PyPdfError:
            text = ""
        if len(text.strip()) >= MIN_ZNAKU_TEXTU:
            vysledek.append((text, b""))
            continue
        zapis = PdfWriter()
        zapis.add_page(strana)
        buffer = io.BytesIO()
        zapis.write(buffer)
        vysledek.append((None, buffer.getvalue()))
    return vysledek


def _texty_stranek(obsah: bytes, typ: str) -> tuple[list[str], list[bool]] | None:
    """Texty všech stránek a příznak OCR. None = sken a OCR je vypnuté."""
    kusy = _stranky_pdf(obsah) if typ == PDF else [(None, obsah)]
    ke_skenu = [i for i, (text, _) in enumerate(kusy) if text is None]
    if ke_skenu and not ocr.je_zapnute():
        return None
    if len(ke_skenu) > nastaveni().ocr_max_stran:
        raise ChybaCteni(f"Sken má víc než {nastaveni().ocr_max_stran} stran k přepisu.")

    texty: list[str] = []
    for text, kus in kusy:
        if text is not None:
            texty.append(text)
            continue
        try:
            texty.append(ocr.prepis(kus, PDF if typ == PDF else typ))
        except ocr.ChybaOcr as e:
            raise ChybaCteni(str(e)) from e
    return texty, [text is None for text, _ in kusy]


def precti(dokument_id: int) -> None:
    with nove_sezeni() as db:
        # Převzetí: jen dokument, který čeká. Druhé čtení téhož nezačne.
        prevzato = db.execute(
            update(Dokument)
            .where(Dokument.id == dokument_id, Dokument.stav_cteni == StavCteni.CEKA)
            .values(stav_cteni=StavCteni.CTE_SE, chyba_cteni=None)
        ).rowcount
        db.commit()
        if not prevzato:
            return
        dokument = db.get(Dokument, dokument_id)
        if dokument is None:
            return
        obsah, typ, druh = dokument.obsah, dokument.typ_obsahu, dokument.druh

    stav, chyba, texty, ocr_stranek = StavCteni.PRECTENO, None, [], []
    try:
        vysledek = _texty_stranek(obsah, typ)
        if vysledek is None:
            stav = StavCteni.CEKA_NA_OCR
        else:
            texty, ocr_stranek = vysledek
    except ChybaCteni as e:
        stav, chyba = StavCteni.CHYBA, str(e)[:200]
    except Exception:  # noqa: BLE001 — nečekaná chyba nesmí nechat dokument „čte se“
        log.exception("Nečekaná chyba při čtení dokumentu %s", dokument_id)
        stav, chyba = StavCteni.CHYBA, "Nečekaná chyba při čtení."

    # Postgres neuloží znak NUL, který se v textu z PDF občas objeví.
    texty = [t.replace("\x00", "") for t in texty]
    # Otisky významu pro vyhledávání (krok 2B) — mimo transakci, trvá to chvíli.
    uryvky = rozdel(texty) if stav == StavCteni.PRECTENO else []
    try:
        vektory = hledani.otisky([hledani.text_k_otisku(u.nadpis, u.text) for u in uryvky])
    except Exception:  # noqa: BLE001 — bez otisku se dá hledat aspoň podle slov
        log.exception("Otisky úryvků dokumentu %s se nepodařilo spočítat", dokument_id)
        vektory = [None] * len(uryvky)
    with nove_sezeni() as db:
        # Nejdřív stav (zamkne řádek dokumentu). Když byl dokument mezitím
        # smazán, nezapíše se nic.
        zapsano = db.execute(
            update(Dokument)
            .where(Dokument.id == dokument_id, Dokument.stav_cteni == StavCteni.CTE_SE)
            .values(
                stav_cteni=stav,
                chyba_cteni=chyba,
                pocet_stran=len(texty) if stav == StavCteni.PRECTENO else None,
                precteno=datetime.now(UTC) if stav == StavCteni.PRECTENO else None,
            )
        ).rowcount
        if not zapsano:
            db.rollback()
            return
        db.execute(delete(Uryvek).where(Uryvek.dokument_id == dokument_id))
        db.execute(delete(Strana).where(Strana.dokument_id == dokument_id))
        if stav == StavCteni.PRECTENO:
            for cislo, (text, je_ocr) in enumerate(zip(texty, ocr_stranek, strict=True), start=1):
                db.add(Strana(dokument_id=dokument_id, cislo=cislo, text=text, ocr=je_ocr))
            for u, vektor in zip(uryvky, vektory, strict=True):
                db.add(
                    Uryvek(
                        dokument_id=dokument_id,
                        strana=u.strana,
                        poradi=u.poradi,
                        nadpis=u.nadpis,
                        text=u.text,
                        vektor=vektor,
                        slova=hledani.slova_k_hledani(u.nadpis, u.text),
                    )
                )
        if druh == DruhDokumentu.HLASENI and stav != StavCteni.PRECTENO:
            # Návrh údajů bez přečteného textu by neměl z čeho vycházet.
            db.execute(delete(Vytezeni).where(Vytezeni.dokument_id == dokument_id))
        db.commit()
    # Hlášení škody: z přečteného textu se vytěží údaje (krok 4B).
    if druh == DruhDokumentu.HLASENI and stav == StavCteni.PRECTENO:
        vytezeni.naplanuj(dokument_id)
