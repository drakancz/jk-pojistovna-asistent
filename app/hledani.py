"""Vyhledávání v úryvcích (krok 2B): podle významu a podle slov zároveň.

- **Podle významu:** každý úryvek má „otisk“ (vektor) z lokálního modelu
  model2vec (`/opt/model`, stažený při sestavení obrazu). Otázka dostane
  otisk stejně a hledají se nejbližší úryvky (pgvector, kosinová
  vzdálenost). Nic neodchází ven, model běží v aplikaci.
- **Podle slov:** fulltext Postgresu nad textem bez diakritiky; slova
  z otázky se hledají podle začátku (Czech nemá v Postgresu slovník,
  „ukradenou“ a „ukradený“ tak najdou totéž).
- **Číslo dokumentu:** číslo z otázky („smlouva 1005“) přidá úryvky
  dokumentu, který ho nese v názvu (9. 11. 2026).
- **Spojení:** všechna pořadí se sečtou (reciprocal rank fusion). Na sadě
  12 otázek k dokumentům JK pojišťovny: význam 9, slova 10, obojí 11
  z 12 v prvních pěti (4. 11. 2026).

**Oprávnění patří do dotazu**: `hledej()` vždy dostane podmínku, které
dokumenty smí hledající vidět (`viditelne_dokumenty()`), a úryvek mimo
ni se z databáze vůbec nenačte. Asistent (fáze 3) dostane jen to, co
vrátí tahle funkce.
"""

import json
import logging
import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import ColumnElement, and_, case, false, func, literal, or_, select, true, update
from sqlalchemy.orm import Session
from tokenizers import Tokenizer

from app.db import nove_sezeni
from app.modely import Dokument, DruhDokumentu, Role, StavCteni, Uryvek, Uzivatel
from app.nastaveni import nastaveni

log = logging.getLogger(__name__)

DIMENZE = 256  # rozměr otisku modelu potion-multilingual-128M
KANDIDATU = 30  # kolik nejlepších z každého způsobu se spojuje
RRF_K = 60
MAX_OTAZKA = 300
DELKA_KMENE = 5  # slovo delší než tohle se hledá podle začátku

# Krátká slova, která nic nehledají (otázky běžnou češtinou).
NEHLEDAT = set(
    """a i k o s u v z ze se si je jsou to ta ten na do za po od pro pri jak
    kdy kde co kdo ktery ktera ktere muj moje mi me mne mu jsem jste byl bude
    nebo ale kdyz tak uz jen ani by aby""".split()
)

# Přivlastňovací zájmena bez diakritiky: klient se ptá na „svou“ smlouvu.
SVOJE = set(
    """muj moje meho memu mem mym moji mou mych mymi ma me
    svuj svoje sveho svemu svem svym svoji svou svych svymi sva sve""".split()
)
VLASTNICH_NAVIC = 3  # kolik úryvků vlastní smlouvy se přidá k nalezeným

_model: "_Model | None" = None
_zamek = threading.Lock()


# --- Otisk významu -----------------------------------------------------------


@dataclass
class _Model:
    """Model model2vec bez knihovny model2vec (ta si bere o 900 MB víc).

    Otisk textu = průměr řádků tabulky pro tokeny textu (bez neznámého
    tokenu, nejvýš `max_tokenu`), normalizovaný na délku 1 — totéž co
    `StaticModel.encode()`. Tabulka se čte z disku (memmap), v paměti
    zůstává hlavně tokenizér (asi 540 MB).
    """

    tokenizer: Tokenizer
    vektory: np.ndarray
    neznamy_token: int
    max_tokenu: int


def _nacti_model() -> _Model:
    global _model
    with _zamek:
        if _model is None:
            slozka = Path(nastaveni().cesta_modelu)
            udaje = json.loads((slozka / "nastaveni.json").read_text(encoding="utf-8"))
            vektory = np.load(slozka / "vektory.npy", mmap_mode="r")
            if vektory.shape[1] != DIMENZE or udaje["rozmer"] != DIMENZE:
                raise RuntimeError("Rozměr modelu nesedí se sloupcem uryvky.vektor.")
            _model = _Model(
                tokenizer=Tokenizer.from_file(str(slozka / "tokenizer.json")),
                vektory=vektory,
                neznamy_token=udaje["neznamy_token"],
                max_tokenu=udaje["max_tokenu"],
            )
    return _model


def otisky(texty: list[str]) -> list[np.ndarray | None]:
    """Otisk významu pro každý text, normalizovaný na délku 1.
    None u textu, ve kterém model nezná ani jeden token."""
    if not texty:
        return []
    model = _nacti_model()
    vysledek: list[np.ndarray | None] = []
    for kodovani in model.tokenizer.encode_batch_fast(texty, add_special_tokens=False):
        ids = [i for i in kodovani.ids if i != model.neznamy_token][: model.max_tokenu]
        if not ids:
            vysledek.append(None)
            continue
        vektor = np.asarray(model.vektory[np.array(ids)], dtype=np.float32).mean(axis=0)
        delka = float(np.linalg.norm(vektor))
        vysledek.append(vektor / delka if delka else None)
    return vysledek


def text_k_otisku(nadpis: str | None, text: str) -> str:
    return f"{nadpis}\n{text}" if nadpis else text


# --- Slova bez diakritiky ----------------------------------------------------


def bez_diakritiky(text: str) -> str:
    rozlozeny = unicodedata.normalize("NFKD", text.lower())
    return "".join(z for z in rozlozeny if not unicodedata.combining(z))


def slova_k_hledani(nadpis: str | None, text: str) -> str:
    """Text úryvku pro fulltext: malými písmeny a bez diakritiky."""
    return bez_diakritiky(text_k_otisku(nadpis, text))


def kmen(slovo: str) -> int:
    """Kolik písmen ze začátku slova se hledá. Šestipísmenné slovo bez
    posledních dvou („klicky“ → „klic“, „mesice“ → „mesi“), delší prvních
    pět jako dřív. Pětipísmenný kořen z „klicky“ („klick“) nenašel „klíč“."""
    return min(DELKA_KMENE, max(4, len(slovo) - 2))


def slova_otazky(otazka: str) -> list[str]:
    """Otázka → části tsquery („krade:*“, „auto“). Slovo delší než
    `DELKA_KMENE` se hledá podle začátku (čeština nemá v Postgresu slovník)."""
    casti: list[str] = []
    for slovo in re.findall(r"\w+", bez_diakritiky(otazka)):
        if slovo in NEHLEDAT or len(slovo) < 2 or "_" in slovo:
            continue
        cast = f"{slovo[:kmen(slovo)]}:*" if len(slovo) > DELKA_KMENE and not slovo.isdigit() else slovo
        if cast not in casti:
            casti.append(cast)
    return casti


# --- Kdo co smí najít --------------------------------------------------------


def viditelne_dokumenty(uzivatel: Uzivatel) -> ColumnElement[bool]:
    """Podmínka na tabulku dokumentů: co smí uživatel najít.

    - Administrátor a likvidace vidí všechny dokumenty (Jakub, 4. 11. 2026).
    - Klient (zadání 3. 11., krok 3B 4. 11. 2026): pojistné podmínky
      (nikomu nepatří) a **jen své** smlouvy a dodatky. Hlášení škody
      nenajde ani svoje — ta jsou jen pro likvidaci a administrátora.
      Cizí smlouva se tak z databáze vůbec nenačte, a nemůže proto
      odejít ani do AI (hlídá `testy/test_klient.py`).
    - Jakákoli jiná role nic.
    """
    if uzivatel.role in (Role.ADMIN, Role.LIKVIDACE):
        return true()
    if uzivatel.role == Role.KLIENT:
        return or_(
            and_(Dokument.druh == DruhDokumentu.PODMINKY, Dokument.klient_id.is_(None)),
            and_(Dokument.druh == DruhDokumentu.SMLOUVA, Dokument.klient_id == uzivatel.id),
        )
    return false()


# --- Hledání -----------------------------------------------------------------


def _podle_slov(db: Session, zaklad, casti: list[str]) -> list[int]:
    """Úryvky se slovy otázky, seřazené podle vzácnosti nalezených slov.

    Vzácné slovo („těhotná“) váží víc než slovo, které je skoro všude
    („pojištění“) — jako BM25. Samotné `ts_rank` vzácnost nezná: na sadě
    otázek našlo o dvě správné odpovědi méně. Počty se berou jen z toho,
    co hledající smí vidět (`zaklad` už má podmínku oprávnění).
    """
    if not casti:
        return []
    dotazy = [func.to_tsquery("simple", cast) for cast in casti]
    celkem = db.scalar(select(func.count()).select_from(zaklad.subquery())) or 0
    if not celkem:
        return []
    vahy: list[float] = []
    for dotaz in dotazy:
        vyskyt = db.scalar(
            select(func.count()).select_from(zaklad.where(Uryvek.slova_ts.op("@@")(dotaz)).subquery())
        ) or 0
        vahy.append(math.log(1 + (celkem - vyskyt + 0.5) / (vyskyt + 0.5)) if vyskyt else 0.0)
    if not any(vahy):
        return []
    skore = sum(
        (case((Uryvek.slova_ts.op("@@")(d), literal(v)), else_=literal(0.0)) for d, v in zip(dotazy, vahy, strict=True) if v),
        start=literal(0.0),
    )
    kterekoli = func.to_tsquery("simple", " | ".join(c for c, v in zip(casti, vahy, strict=True) if v))
    return list(
        db.scalars(
            zaklad.where(Uryvek.slova_ts.op("@@")(kterekoli))
            .order_by(skore.desc(), func.ts_rank(Uryvek.slova_ts, kterekoli, 1).desc(), Uryvek.id)
            .limit(KANDIDATU)
        )
    )


def _podle_cisla_dokumentu(db: Session, zaklad, otazka: str, otisk: np.ndarray | None) -> list[int]:
    """Úryvky dokumentů, jejichž název nese číslo z otázky („smlouva 1005“).

    Číslo smlouvy ve fulltextu nic neváží (je jen v názvu dokumentu, ne
    v úryvcích), takže „Jaká je spoluúčast u smlouvy 1005?“ našla obecné
    články podmínek místo smlouvy (evaluace 8. 11. 2026). Úryvky takového
    dokumentu jsou třetí pořadí do spojení, seřazené podle významu.
    `zaklad` už má podmínku oprávnění: klientka cizí smlouvu tímhle
    nenajde, i kdyby znala její číslo.
    """
    cisla = set(re.findall(r"(?<!\d)\d{3,6}(?!\d)", otazka))
    if not cisla:
        return []
    podminka = or_(*(Dokument.nazev.op("~")(rf"(^|\D){c}(\D|$)") for c in cisla))
    dotaz = zaklad.where(podminka)
    if otisk is not None:
        dotaz = dotaz.order_by(Uryvek.vektor.cosine_distance(otisk).nulls_last(), Uryvek.id)
    else:
        dotaz = dotaz.order_by(Uryvek.id)
    return list(db.scalars(dotaz.limit(KANDIDATU)))


@dataclass
class Nalez:
    uryvek_id: int
    dokument_id: int
    dokument: str
    strana: int
    nadpis: str | None
    text: str
    vyznam: bool  # našel ho otisk významu
    slova: bool  # našel ho fulltext


def pta_se_na_svoje(otazka: str) -> bool:
    return any(slovo in SVOJE for slovo in re.findall(r"\w+", bez_diakritiky(otazka)))


def _vlastni_smlouvy(
    db: Session, zaklad, nejlepsi: list[int], skore: dict[int, float], otisk: np.ndarray | None
) -> list[int]:
    """Úryvky vlastních smluv ke stejnému pojištění jako nalezené podmínky.

    „Mám u svého auta krytý střet se zvěří?“ našlo jen obecné podmínky
    (obě varianty), ne smlouvu, kde stojí, kterou variantu klientka má —
    asistent jí pak neuměl odpovědět (snímek živé odpovědi 10. 11. 2026).
    Volá se jen pro klienta: `zaklad` má podmínku oprávnění, takže
    smlouvy v něm jsou vždy jen jeho.
    """
    druhy_pojisteni = set(
        db.scalars(
            select(Dokument.pojisteni).join(Uryvek, Uryvek.dokument_id == Dokument.id).where(Uryvek.id.in_(nejlepsi))
        )
    )
    if not druhy_pojisteni:
        return []
    dotaz = zaklad.where(Dokument.druh == DruhDokumentu.SMLOUVA, Dokument.pojisteni.in_(druhy_pojisteni))
    if otisk is not None:
        dotaz = dotaz.order_by(Uryvek.vektor.cosine_distance(otisk).nulls_last(), Uryvek.id)
    else:
        dotaz = dotaz.order_by(Uryvek.id)
    kandidati = list(db.scalars(dotaz.limit(KANDIDATU)))
    # Nejdřív to, co hledání samo ohodnotilo, pak podle významu.
    poradi_vyznamu = {u: misto for misto, u in enumerate(kandidati)}
    kandidati.sort(key=lambda i: (-skore.get(i, 0.0), poradi_vyznamu[i]))
    return [i for i in kandidati if i not in nejlepsi][:VLASTNICH_NAVIC]


def _podle_vyznamu(db: Session, zaklad, otisk: np.ndarray | None) -> list[int]:
    if otisk is None:
        return []
    return list(
        db.scalars(
            zaklad.where(Uryvek.vektor.is_not(None)).order_by(Uryvek.vektor.cosine_distance(otisk)).limit(KANDIDATU)
        )
    )


def hledej(
    db: Session,
    otazka: str,
    smi_videt: ColumnElement[bool],
    pocet: int = 5,
    klient: bool = False,
    doplnek: str | None = None,
) -> list[Nalez]:
    """`klient=True`: otázka na „svou“ smlouvu přidá k nalezeným až
    `VLASTNICH_NAVIC` úryvků klientových smluv (`_vlastni_smlouvy`).

    `doplnek`: otázka převedená do slov dokumentů (`asistent.hledaci_slova`).
    Hledá se jím podle významu i slov jako dalšími dvěma pořadími; původní
    otázka zůstává, takže špatný převod hledání nezhorší víc než o jedno
    pořadí ze čtyř."""
    otazka = otazka.strip()[:MAX_OTAZKA]
    if not otazka:
        return []
    doplnek = (doplnek or "").strip()[:MAX_OTAZKA]
    zaklad = (
        select(Uryvek.id)
        .join(Dokument, Dokument.id == Uryvek.dokument_id)
        .where(Dokument.stav_cteni == StavCteni.PRECTENO, smi_videt)
    )

    otisk, otisk_doplnku = otisky([otazka, doplnek]) if doplnek else (otisky([otazka])[0], None)
    podle_vyznamu = _podle_vyznamu(db, zaklad, otisk)
    podle_slov = _podle_slov(db, zaklad, slova_otazky(otazka))
    podle_cisla = _podle_cisla_dokumentu(db, zaklad, otazka, otisk)
    poradi = [podle_vyznamu, podle_slov, podle_cisla]
    if doplnek:
        poradi += [_podle_vyznamu(db, zaklad, otisk_doplnku), _podle_slov(db, zaklad, slova_otazky(doplnek))]

    skore: dict[int, float] = {}
    for poradi_ in poradi:
        for misto, uryvek_id in enumerate(poradi_):
            skore[uryvek_id] = skore.get(uryvek_id, 0.0) + 1 / (RRF_K + misto)
    nejlepsi = sorted(skore, key=lambda i: (-skore[i], i))[:pocet]
    if not nejlepsi:
        return []
    if klient and pta_se_na_svoje(otazka):
        nejlepsi += _vlastni_smlouvy(db, zaklad, nejlepsi, skore, otisk)

    radky = {
        u.id: (u, nazev)
        for u, nazev in db.execute(
            select(Uryvek, Dokument.nazev)
            .join(Dokument, Dokument.id == Uryvek.dokument_id)
            .where(Uryvek.id.in_(nejlepsi), smi_videt)
        )
    }
    vyznam, slova = set(podle_vyznamu), set(podle_slov)
    return [
        Nalez(
            uryvek_id=i,
            dokument_id=radky[i][0].dokument_id,
            dokument=radky[i][1],
            strana=radky[i][0].strana,
            nadpis=radky[i][0].nadpis,
            text=radky[i][0].text,
            vyznam=i in vyznam,
            slova=i in slova,
        )
        for i in nejlepsi
        if i in radky
    ]


# --- Doplnění otisků k úryvkům z dřívějška ----------------------------------


def doplnit_chybejici(davka: int = 200) -> int:
    """Úryvkům přečteným před krokem 2B doplní otisk a slova. Vrátí počet.
    Zpracovaný = má `slova` (otisk může zůstat prázdný, když model nezná
    žádný token)."""
    hotovo = 0
    while True:
        with nove_sezeni() as db:
            radky = db.execute(
                select(Uryvek.id, Uryvek.nadpis, Uryvek.text)
                .where(Uryvek.slova.is_(None))
                .order_by(Uryvek.id)
                .limit(davka)
            ).all()
            if not radky:
                return hotovo
            vektory = otisky([text_k_otisku(n, t) for _, n, t in radky])
            for (uryvek_id, nadpis, text), vektor in zip(radky, vektory, strict=True):
                db.execute(
                    update(Uryvek)
                    .where(Uryvek.id == uryvek_id)
                    .values(vektor=vektor, slova=slova_k_hledani(nadpis, text))
                )
            db.commit()
            hotovo += len(radky)


def priprav() -> None:
    """Po startu na pozadí: načíst model (první hledání pak nečeká)
    a doplnit otisky, které chybí."""
    try:
        _nacti_model()
        pocet = doplnit_chybejici()
        if pocet:
            log.info("Doplněny otisky k %s úryvkům.", pocet)
    except Exception:  # noqa: BLE001 — start aplikace nesmí spadnout
        log.exception("Příprava vyhledávání selhala")
